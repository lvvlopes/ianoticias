"""Publicação no Instagram via Meta Graph API.

Fluxo (Instagram Business/Creator + Página do Facebook):
    1) POST /{IG_USER_ID}/media com image_url + caption  → creation_id
    2) POST /{IG_USER_ID}/media_publish com creation_id  → media_id

Em MOCK_IG=1 (ou sem token), simula os dois passos e devolve um id fake.

TODO: implementar renovação do token de longa duração da Meta. Tokens de curta
duração vencem em ~1h; os de longa duração duram ~60 dias e podem ser
renovados via GET /oauth/access_token?grant_type=fb_exchange_token. Para
automação real, agendar uma rotina de refresh (fora do escopo deste MVP).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ianoticias.config.settings import settings
from ianoticias.repositories import settings_repo

# Chaves no app_settings para o token gerenciado (renovável sem redeploy).
KEY_IG_TOKEN = "ig.access_token"
KEY_IG_TOKEN_TS = "ig.token_refreshed_at"
# Renova quando o token guardado tiver mais de N dias (o da Meta dura ~60).
_REFRESH_AFTER_DAYS = 45


class InstagramError(RuntimeError):
    """Erro reportado pela Meta Graph API."""


@dataclass
class PublishResult:
    media_id: str


def _cta() -> str:
    """Chamada de engajamento. Se houver handle, inclui o "Siga @...";
    salvamentos/compartilhamentos são o que mais impulsiona alcance no IG."""
    handle = settings.ig_handle.lstrip("@").strip()
    if handle:
        return f"👉 Siga @{handle} para IA todo dia · 💾 Salve · 🔁 Compartilhe"
    return "💾 Salve este post · 🔁 Compartilhe · 💬 Comente o que achou"


def build_caption(*, ig_title: str, ig_content: str, hashtags: list[str], source_url: str) -> str:
    """Legenda do post. Se IG_HASHTAGS_IN_COMMENT, as hashtags NÃO entram aqui
    (vão para o primeiro comentário — legenda mais limpa)."""
    parts = [ig_title, "", ig_content, "", _cta(), "",
             "📖 Matéria completa no link da bio", f"Fonte: {source_url}"]
    if not settings.ig_hashtags_in_comment and hashtags:
        parts += ["", " ".join(f"#{t.lstrip('#')}" for t in hashtags)]
    return "\n".join(parts)


def build_first_comment(hashtags: list[str]) -> str:
    """Texto do primeiro comentário: hashtag da marca + hashtags da matéria.
    Retorna '' se não houver nada a postar (ou se estiver desligado)."""
    if not settings.ig_hashtags_in_comment:
        return ""
    tags: list[str] = []
    brand = settings.ig_brand_hashtag.lstrip("#").strip()
    if brand:
        tags.append(f"#{brand}")
    for t in hashtags:
        tag = f"#{t.lstrip('#').strip()}"
        if tag.lower() not in (x.lower() for x in tags):
            tags.append(tag)
    return " ".join(tags)


async def _graph_post(
    client: httpx.AsyncClient, path: str, data: dict, token: str, *, retries: int = 3
) -> dict:
    payload = {**data, "access_token": token}
    url = f"https://graph.facebook.com/{settings.graph_api_version}/{path}"

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.post(url, data=payload)
        except httpx.TransportError as exc:
            # Erro de rede (ReadError, ConnectError, timeout...) — tenta de novo
            # com backoff. Não confundir com erro DA API (que vem no corpo).
            last_exc = exc
            if attempt < retries - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            raise InstagramError(
                f"Falha de rede ao chamar a Graph API após {retries} tentativas: "
                f"{type(exc).__name__}. Verifique sua conexão/firewall/antivírus."
            ) from exc

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        if resp.status_code >= 400 or "error" in body:
            msg = body.get("error", {}).get("message") or f"HTTP {resp.status_code}"
            raise InstagramError(msg)
        return body

    # Inalcançável, mas mantém o type-checker feliz.
    raise InstagramError(f"Graph API indisponível: {last_exc}")


async def publish(*, image_url: str, caption: str, access_token: str | None = None) -> PublishResult:
    """Executa os dois passos da Graph API e retorna o id do media publicado."""
    token = access_token or settings.ig_access_token
    if settings.mock_ig or not (token and settings.ig_user_id):
        return PublishResult(media_id="mock_" + str(abs(hash(image_url)))[:12])

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1) Container
        container = await _graph_post(
            client,
            f"{settings.ig_user_id}/media",
            {"image_url": image_url, "caption": caption},
            token,
        )
        creation_id = container.get("id")
        if not creation_id:
            raise InstagramError("Resposta sem id de container.")

        # 2) Publish
        published = await _graph_post(
            client,
            f"{settings.ig_user_id}/media_publish",
            {"creation_id": creation_id},
            token,
        )
        media_id = published.get("id")
        if not media_id:
            raise InstagramError("Resposta sem id de media publicado.")

        return PublishResult(media_id=str(media_id))


async def post_comment(*, media_id: str, message: str, access_token: str | None = None) -> str | None:
    """Publica um comentário no media recém-postado (usado p/ as hashtags).

    Best-effort: se falhar (permissão de comentários, etc.), NÃO derruba o post
    — apenas devolve None. Requer a permissão instagram_manage_comments no token.
    """
    token = access_token or settings.ig_access_token
    if not message or settings.mock_ig or not (token and settings.ig_user_id):
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            body = await _graph_post(
                client, f"{media_id}/comments", {"message": message}, token
            )
        return str(body.get("id")) if body.get("id") else None
    except InstagramError:
        return None


# ---------------------------------------------------------------------------
# Gerência do token de longa duração (renovação automática)
# ---------------------------------------------------------------------------
async def resolve_token(session) -> str:
    """Token efetivo: o guardado no banco (renovável) ou o do .env como base."""
    stored = await settings_repo.get(session, KEY_IG_TOKEN)
    return stored or settings.ig_access_token


async def _exchange_long_lived(current_token: str) -> tuple[str, int] | None:
    """Troca um token por outro de longa duração (~60 dias) via fb_exchange_token.
    Retorna (novo_token, expires_in_segundos) ou None se falhar."""
    if not (settings.meta_app_id and settings.meta_app_secret and current_token):
        return None
    url = f"https://graph.facebook.com/{settings.graph_api_version}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "fb_exchange_token": current_token,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None
    tok = data.get("access_token")
    if not tok:
        return None
    return tok, int(data.get("expires_in", 5184000))


async def force_refresh(session) -> tuple[bool, str]:
    """Renova o token agora e persiste no banco. Retorna (ok, mensagem)."""
    current = await resolve_token(session)
    result = await _exchange_long_lived(current)
    if result is None:
        return False, "Não foi possível renovar (token inválido/expirado ou app sem segredo). Gere um novo com scripts/ig_token.py."
    new_token, expires_in = result
    now = datetime.now(timezone.utc)
    await settings_repo.set(session, KEY_IG_TOKEN, new_token)
    await settings_repo.set(session, KEY_IG_TOKEN_TS, now.isoformat())
    await session.commit()
    return True, f"Token renovado — validade ~{expires_in // 86400} dias."


async def refresh_if_needed(session) -> None:
    """Renova o token de forma OPORTUNÍSTICA se estiver velho (ou sem registro).

    Chamado antes de publicar: como o app é de uso periódico, isso mantém o
    token sempre fresco sem depender de cron (que a Vercel free não tem).
    """
    if settings.mock_ig or not settings.meta_app_secret:
        return
    ts_raw = await settings_repo.get(session, KEY_IG_TOKEN_TS)
    if ts_raw:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(ts_raw)).days
            if age_days < _REFRESH_AFTER_DAYS:
                return  # ainda fresco
        except ValueError:
            pass
    # Sem registro ou já velho → tenta renovar (best-effort, não derruba o post).
    await force_refresh(session)


def token_status_age_days(ts_iso: str | None) -> int | None:
    """Idade em dias do token guardado (para exibir no admin)."""
    if not ts_iso:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts_iso)).days
    except ValueError:
        return None
