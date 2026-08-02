"""Upload do PNG do card para o bucket público do Supabase Storage.

Usamos a REST API do Storage diretamente via httpx, em vez do supabase-py.
Motivos:
  - Funciona com QUALQUER formato de chave (JWT legado `eyJ...` E as chaves
    novas `sb_secret_...`). O supabase-py 2.x valida a chave como JWT e rejeita
    as novas com "Invalid API key".
  - Menos dependências no bundle (a SPEC pede deps enxutas).

Endpoints usados:
  - Upload:  POST {SUPABASE_URL}/storage/v1/object/{bucket}/{path}
  - Público: GET  {SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}

Em `MOCK_STORAGE=1` (ou sem credenciais), salva em
`static/mock_cards/<article_id>.png` e devolve uma URL local — útil para dev.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ianoticias.config.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MOCK_DIR = BASE_DIR / "static" / "mock_cards"


class StorageError(RuntimeError):
    """Falha no upload para o Supabase Storage."""


def _mock_upload(article_id: str, image_bytes: bytes) -> str:
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = MOCK_DIR / f"{article_id}.jpg"
    path.write_bytes(image_bytes)
    return f"{settings.public_site_url.rstrip('/')}/static/mock_cards/{article_id}.jpg"


def _public_url(path: str) -> str:
    base = settings.supabase_url.rstrip("/")
    bucket = settings.supabase_storage_bucket
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


async def _real_upload(article_id: str, image_bytes: bytes) -> str:
    base = settings.supabase_url.rstrip("/")
    bucket = settings.supabase_storage_bucket
    key = settings.supabase_service_role_key
    # JPEG: exigência da API de publicação do Instagram (PNG é recusado).
    path = f"{article_id}.jpg"
    upload_url = f"{base}/storage/v1/object/{bucket}/{path}"

    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "image/jpeg",
        # Sobrescreve o card se já existir (regeração do mesmo artigo).
        "x-upsert": "true",
        "cache-control": "3600",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(upload_url, content=image_bytes, headers=headers)

    if resp.status_code >= 400:
        # Mensagem de erro da Storage API (bucket inexistente, chave inválida, etc.)
        try:
            detail = resp.json()
        except ValueError:
            detail = {"message": resp.text[:200]}
        msg = detail.get("message") or detail.get("error") or f"HTTP {resp.status_code}"
        raise StorageError(
            f"Upload falhou ({resp.status_code}): {msg}. "
            f"Verifique se o bucket '{bucket}' existe e é público, e se a "
            f"SUPABASE_SERVICE_ROLE_KEY está correta."
        )

    return _public_url(path)


async def upload_card_image(*, article_id: str, image_bytes: bytes) -> str:
    """Devolve a URL pública do card JPEG (ou local, em modo mock)."""
    if not settings.has_storage:
        return _mock_upload(article_id, image_bytes)
    return await _real_upload(article_id, image_bytes)
