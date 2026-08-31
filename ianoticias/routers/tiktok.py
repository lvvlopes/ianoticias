"""Geração de assets para TikTok (Photo Mode + roteiro em texto).

Não publica na API — devolve um .zip com 4 JPGs (cenas: hook, fato, impacto,
fonte) + `roteiro.txt` com legenda pronta. Fluxo: admin baixa o pack, abre
CapCut/InShot no celular, arrasta os 4 slides na ordem, cola a legenda,
escolhe uma trilha do catálogo TikTok e exporta.

Rota:
    GET /api/tiktok/pack/{article_id}  → attachment .zip

A rota antiga `GET /api/tiktok/card/{article_id}` continua funcionando
(devolve só a capa 9:16 — útil como fallback).
"""
from __future__ import annotations

import asyncio
import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ianoticias.config.settings import settings
from ianoticias.db.engine import get_session
from ianoticias.repositories import articles as repo
from ianoticias.security.auth import AdminRequired
from ianoticias.services.image_card import (
    build_card_tiktok_jpeg,
    build_tt_fato,
    build_tt_fonte,
    build_tt_hook,
    build_tt_impacto,
)

router = APIRouter(prefix="/api", tags=["tiktok"])


def _slug(text: str, maxlen: int = 40) -> str:
    text = re.sub(r"[^a-zA-Z0-9-]+", "-", (text or "").lower()).strip("-")
    return (text or "post")[:maxlen]


def _split_paras(ig_content: str) -> tuple[str, str]:
    """Divide ig_content em (fato, impacto). Cai pro texto inteiro se só 1 parágrafo."""
    paras = [p.strip() for p in (ig_content or "").split("\n\n") if p.strip()]
    if not paras:
        return ("", "")
    if len(paras) == 1:
        return (paras[0], "")
    return (paras[0], "\n\n".join(paras[1:]))


def _script_text(article, fato: str, impacto: str) -> str:
    """Roteiro em texto puro pra colar na legenda do TikTok."""
    handle = settings.ig_handle.lstrip("@").strip() or "ianoticiaslv"
    brand = "#" + settings.ig_brand_hashtag.lstrip("#").strip() if settings.ig_brand_hashtag else "#IANoticias"
    tags = [f"#{t.lstrip('#').strip()}" for t in (article.hashtags or [])][:6]
    hashtags_line = " ".join([brand, "#IA", "#InteligenciaArtificial", "#tecnologia", *tags])

    lines = [
        "===== ROTEIRO TIKTOK =====",
        "",
        f"Categoria: {article.category.value}",
        f"Notícia:   {article.ig_title}",
        f"Fonte:     {article.source_name} — {article.source_url}",
        "",
        "----- ESTRUTURA DAS CENAS (arraste os JPGs nesta ordem) -----",
        "",
        "[0-3s]   hook.jpg      → título entra grande, hook forte",
        "[3-15s]  fato.jpg      → 1º parágrafo (o que aconteceu)",
        "[15-25s] impacto.jpg   → 2º parágrafo (por que importa)",
        "[25-30s] fonte.jpg     → CTA: siga @" + handle,
        "",
        "----- LEGENDA (cola no TikTok) -----",
        "",
        article.ig_title,
        "",
        fato,
        "",
        (impacto if impacto else ""),
        "",
        f"👉 Siga @{handle} para IA todo dia",
        f"📖 Fonte: {article.source_name}",
        "",
        hashtags_line,
        "",
        "----- DICAS -----",
        "",
        "• Escolha uma TRILHA do catálogo TikTok (é o que ativa alcance).",
        "• Deixe cada slide com 3-5s (exceto o hook, que pode ser 2-3s).",
        "• Ative LEGENDAS AUTOMÁTICAS do CapCut e ajuste os erros de acento.",
        "• Publique entre 12h-14h ou 19h-21h para melhor alcance.",
        "",
    ]
    return "\n".join(lines)


def _build_pack_zip(article, fato: str, impacto: str) -> bytes:
    """Monta o .zip com os 4 JPGs + roteiro.txt."""
    slides = {
        "1-hook.jpg": build_tt_hook(
            title=article.ig_title,
            category=article.category.value,
            source_url=article.source_url,
            source_name=article.source_name,
        ),
        "2-fato.jpg": build_tt_fato(
            body=fato or article.ig_title,
            category=article.category.value,
            source_url=article.source_url,
            source_name=article.source_name,
        ),
        "3-impacto.jpg": build_tt_impacto(
            body=impacto or "Continue acompanhando para os próximos desdobramentos.",
            category=article.category.value,
            source_url=article.source_url,
            source_name=article.source_name,
        ),
        "4-fonte.jpg": build_tt_fonte(
            handle=settings.ig_handle or "ianoticiaslv",
            category=article.category.value,
            source_url=article.source_url,
            source_name=article.source_name,
        ),
    }
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        for name, data in slides.items():
            zf.writestr(name, data)
        zf.writestr("roteiro.txt", _script_text(article, fato, impacto))
    return buf.getvalue()


@router.get("/tiktok/pack/{article_id}")
async def tiktok_pack_download(
    article_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = AdminRequired,
):
    article = await repo.get_by_id(session, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article não encontrado.")

    fato, impacto = _split_paras(article.ig_content)
    zip_bytes = await asyncio.to_thread(_build_pack_zip, article, fato, impacto)
    filename = f"ianoticias-tiktok-{_slug(article.ig_title)}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.get("/tiktok/card/{article_id}")
async def tiktok_card_download(
    article_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = AdminRequired,
):
    """Fallback: baixa só a capa 9:16 (sem as demais cenas)."""
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
