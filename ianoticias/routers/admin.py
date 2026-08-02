"""Tela /admin: gerenciar fontes de feed e prompts do LLM.

Tudo protegido por sessão de admin. As "regras de pesquisa/pipeline" são
exibidas somente para leitura; feeds e prompts são editáveis e persistidos
no banco (tabelas feed_sources / app_settings).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ianoticias.config.feeds import FEEDS as DEFAULT_FEEDS
from ianoticias.config.settings import settings
from ianoticias.db.engine import get_session
from ianoticias.db.models import Category
from ianoticias.repositories import feeds_repo, settings_repo
from ianoticias.security.auth import AdminRequired, is_admin
from ianoticias.services.config_store import (
    KEY_SYSTEM_PROMPT,
    KEY_USER_TEMPLATE,
    ensure_llm_defaults,
)
from ianoticias.services import instagram as ig
from ianoticias.services.llm import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_TEMPLATE
from ianoticias.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[AdminRequired])

VALID_REGIONS = {"br", "world"}


def _clean_region(raw: str) -> str:
    raw = (raw or "").strip().lower()
    return raw if raw in VALID_REGIONS else "world"


def _clean_hint(raw: str) -> Category:
    try:
        return Category((raw or "").strip())
    except ValueError:
        return Category.ia


# Regras do pipeline exibidas somente-leitura (não editáveis pela tela).
def _readonly_rules() -> list[dict[str, str]]:
    return [
        {"label": "Janela temporal", "value": "Somente matérias das últimas 24h"},
        {"label": "Deduplicação", "value": "Hash SHA-256 da URL canônica (pula o que já existe)"},
        {"label": "Classificação", "value": "3 categorias fixas: ia · eng_dev_ia · gestao_ia"},
        {"label": "Cap por execução", "value": f"{settings.ingest_max_items} itens (env INGEST_MAX_ITEMS)"},
        {"label": "Destaques (featured)", "value": f"{settings.featured_per_category} por categoria/dia (env FEATURED_PER_CATEGORY)"},
        {"label": "Fuso do agrupamento", "value": f"{settings.timezone}"},
        {"label": "Modelo OpenAI", "value": f"{settings.openai_model} (env OPENAI_MODEL)"},
        {"label": "Extração de texto", "value": "trafilatura (fallback: resumo do feed)"},
    ]


@router.get("")
async def admin_home(
    request: Request,
    session: AsyncSession = Depends(get_session),
    saved: str | None = None,
):
    # Semeia prompts e fontes default se ainda não existirem — assim a tela já
    # abre com a lista atual do código na primeira vez (sem precisar buscar).
    await ensure_llm_defaults(session)
    if await feeds_repo.count(session) == 0:
        await feeds_repo.bulk_insert_defaults(session, DEFAULT_FEEDS)
    await session.commit()

    feeds = await feeds_repo.list_all(session)
    prompts = await settings_repo.get_many(session, [KEY_SYSTEM_PROMPT, KEY_USER_TEMPLATE])

    # Status do token do Instagram (idade do último refresh guardado).
    token_ts = await settings_repo.get(session, ig.KEY_IG_TOKEN_TS)
    token_age = ig.token_status_age_days(token_ts)

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "is_admin": is_admin(request),
            "feeds": feeds,
            "system_prompt": prompts.get(KEY_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
            "user_template": prompts.get(KEY_USER_TEMPLATE, DEFAULT_USER_TEMPLATE),
            "rules": _readonly_rules(),
            "categories": [c.value for c in Category],
            "saved": saved,
            "ig_configured": settings.has_instagram,
            "ig_token_age": token_age,
            "ig_token_msg": request.query_params.get("igmsg"),
        },
    )


@router.post("/ig/refresh-token")
async def refresh_ig_token(session: AsyncSession = Depends(get_session)):
    from urllib.parse import quote

    ok, msg = await ig.force_refresh(session)
    return RedirectResponse(f"/admin?igmsg={quote(msg)}", status_code=303)


# --------------------------------------------------------------------------
# Feeds (CRUD)
# --------------------------------------------------------------------------
@router.post("/feeds")
async def create_feed(
    name: str = Form(...),
    url: str = Form(...),
    region: str = Form("world"),
    hint: str = Form("ia"),
    session: AsyncSession = Depends(get_session),
):
    name, url = name.strip(), url.strip()
    if name and url:
        await feeds_repo.create(
            session,
            name=name,
            url=url,
            region=_clean_region(region),
            hint=_clean_hint(hint),
        )
        await session.commit()
    return RedirectResponse("/admin?saved=feed", status_code=303)


@router.post("/feeds/{feed_id}")
async def update_feed(
    feed_id: str,
    name: str = Form(...),
    url: str = Form(...),
    region: str = Form("world"),
    hint: str = Form("ia"),
    enabled: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    await feeds_repo.update_fields(
        session,
        feed_id,
        name=name.strip(),
        url=url.strip(),
        region=_clean_region(region),
        hint=_clean_hint(hint),
        enabled=enabled is not None,
    )
    await session.commit()
    return RedirectResponse("/admin?saved=feed", status_code=303)


@router.post("/feeds/{feed_id}/toggle")
async def toggle_feed(feed_id: str, session: AsyncSession = Depends(get_session)):
    await feeds_repo.toggle(session, feed_id)
    await session.commit()
    return RedirectResponse("/admin?saved=feed", status_code=303)


@router.post("/feeds/{feed_id}/delete")
async def delete_feed(feed_id: str, session: AsyncSession = Depends(get_session)):
    await feeds_repo.remove(session, feed_id)
    await session.commit()
    return RedirectResponse("/admin?saved=feed", status_code=303)


# --------------------------------------------------------------------------
# Prompts do LLM
# --------------------------------------------------------------------------
@router.post("/prompt")
async def save_prompt(
    system_prompt: str = Form(...),
    user_template: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    await settings_repo.set(session, KEY_SYSTEM_PROMPT, system_prompt.strip())
    await settings_repo.set(session, KEY_USER_TEMPLATE, user_template.strip())
    await session.commit()
    return RedirectResponse("/admin?saved=prompt", status_code=303)


@router.post("/prompt/reset")
async def reset_prompt(session: AsyncSession = Depends(get_session)):
    await settings_repo.set(session, KEY_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
    await settings_repo.set(session, KEY_USER_TEMPLATE, DEFAULT_USER_TEMPLATE)
    await session.commit()
    return RedirectResponse("/admin?saved=prompt", status_code=303)
