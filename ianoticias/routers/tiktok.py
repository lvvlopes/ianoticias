"""Geração do card 9:16 para o TikTok (Photo Mode).

Não publica na API — apenas devolve o JPEG como download. O fluxo é:
admin baixa o card daqui, abre o app do TikTok e publica manualmente.

Rota:
    GET /api/tiktok/card/{article_id}  → attachment JPEG 1080x1920
"""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ianoticias.db.engine import get_session
from ianoticias.repositories import articles as repo
from ianoticias.security.auth import AdminRequired
from ianoticias.services.image_card import build_card_tiktok_jpeg

router = APIRouter(prefix="/api", tags=["tiktok"])


def _slug(text: str, maxlen: int = 40) -> str:
    text = re.sub(r"[^a-zA-Z0-9-]+", "-", (text or "").lower()).strip("-")
    return (text or "post")[:maxlen]


@router.get("/tiktok/card/{article_id}")
async def tiktok_card_download(
    article_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = AdminRequired,
):
    article = await repo.get_by_id(session, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article não encontrado.")

    jpeg = await asyncio.to_thread(
        build_card_tiktok_jpeg,
        title=article.ig_title,
        category=article.category.value,
        source_url=article.source_url,
        source_name=article.source_name,
    )
    filename = f"ianoticias-tiktok-{_slug(article.ig_title)}.jpg"
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )
