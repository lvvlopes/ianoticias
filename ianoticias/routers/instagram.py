"""POST /api/instagram/publish — protegido."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ianoticias.db.engine import get_session
from ianoticias.repositories import articles as repo
from ianoticias.security.auth import AdminRequired
from ianoticias.services import instagram as ig
from ianoticias.services.extractor import extract_article
from ianoticias.services.image_card import build_card_jpeg
from ianoticias.services.storage import upload_card_image
from ianoticias.templating import templates

router = APIRouter(prefix="/api", tags=["instagram"])


@router.post("/instagram/publish")
async def instagram_publish(
    request: Request,
    article_id: str = Form(...),
    session: AsyncSession = Depends(get_session),
    _: None = AdminRequired,
):
    article = await repo.get_by_id(session, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article não encontrado.")

    # Backfill da imagem da fonte (og:image) se ainda não temos.
    source_image_url = article.source_image_url
    if not source_image_url:
        try:
            extracted = await extract_article(article.source_url)
            source_image_url = extracted.image_url
            if source_image_url:
                await repo.set_source_image_url(session, article.id, source_image_url)
                article.source_image_url = source_image_url
        except Exception:  # noqa: BLE001 — og:image é best-effort
            source_image_url = None

    # Sempre (re)gera o card no publish: garante layout novo, formato JPEG e a
    # foto atual da fonte (artigos antigos podem ter um PNG obsoleto salvo).
    jpeg = await asyncio.to_thread(
        build_card_jpeg,
        title=article.ig_title,
        category=article.category.value,
        source_url=article.source_url,
        source_name=article.source_name,
        ig_content=article.ig_content,
        source_image_url=source_image_url,
    )
    image_url = await upload_card_image(article_id=str(article.id), image_bytes=jpeg)
    await repo.set_image_url(session, article.id, image_url)
    article.image_url = image_url

    caption = ig.build_caption(
        ig_title=article.ig_title,
        ig_content=article.ig_content,
        hashtags=list(article.hashtags or []),
        source_url=article.source_url,
    )

    # Mantém o token de longa duração fresco (renova se estiver velho) e usa o
    # token gerenciado (banco → .env) em todas as chamadas à Graph API.
    await ig.refresh_if_needed(session)
    token = await ig.resolve_token(session)

    try:
        result = await ig.publish(image_url=image_url, caption=caption, access_token=token)
    except ig.InstagramError as exc:
        raise HTTPException(status_code=502, detail=f"Erro na Meta Graph API: {exc}") from exc

    # Hashtags como primeiro comentário (best-effort; não derruba o post).
    comment = ig.build_first_comment(list(article.hashtags or []))
    if comment:
        await ig.post_comment(media_id=result.media_id, message=comment, access_token=token)

    await repo.mark_posted(session, article.id, result.media_id)
    await session.commit()
    await session.refresh(article)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/article_card.html",
            {"request": request, "article": article, "is_admin": True},
        )
    return {"ok": True, "media_id": result.media_id}
