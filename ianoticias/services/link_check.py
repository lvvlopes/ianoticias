"""Validação de links das matérias antes de persistir.

Um link quebrado exibido no portal destrói credibilidade. Este módulo confirma
que a URL da matéria responde com sucesso (2xx após seguir redirects) ANTES de
salvar o artigo — e antes de gastar tokens no LLM.

Estratégia:
- HEAD primeiro (barato). Muitos servidores, porém, rejeitam HEAD (403/405/501)
  ou não o implementam → cai para GET (stream, sem baixar o corpo inteiro).
- Redirects são seguidos (301/302 NÃO é link quebrado; o navegador segue).
- Qualquer erro de transporte/timeout = considerado indisponível.
"""
from __future__ import annotations

import httpx

# User-Agent de navegador: alguns portais respondem 403 a clientes "robô".
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 IANoticias/1.0"
)
_HEADERS = {"User-Agent": _UA, "Accept": "*/*"}
_RETRY_WITH_GET = {403, 405, 406, 501}


async def is_reachable(client: httpx.AsyncClient, url: str, timeout: float = 8.0) -> bool:
    """True se a URL responde 2xx/3xx→2xx seguindo redirects."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        resp = await client.head(
            url, follow_redirects=True, timeout=timeout, headers=_HEADERS
        )
        if resp.status_code < 400:
            return True
        if resp.status_code not in _RETRY_WITH_GET:
            return False
    except httpx.HTTPError:
        pass  # tenta GET abaixo

    # Fallback GET (stream: não baixamos o corpo inteiro, só o status).
    try:
        async with client.stream(
            "GET", url, follow_redirects=True, timeout=timeout, headers=_HEADERS
        ) as resp:
            return resp.status_code < 400
    except httpx.HTTPError:
        return False


def build_client() -> httpx.AsyncClient:
    """Client compartilhado para uma execução de ingest (reuso de conexões)."""
    return httpx.AsyncClient(
        headers=_HEADERS,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    )
