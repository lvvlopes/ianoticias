"""Rotas de UI: home, login, filtro de categoria."""
from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import date, datetime
from typing import Iterable
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ianoticias.config.settings import settings
from ianoticias.db.engine import get_session
from ianoticias.db.models import Article, Category
from ianoticias.repositories import articles as repo
from ianoticias.security import auth
from ianoticias.templating import templates
from ianoticias.text_search import parse_query

router = APIRouter(tags=["ui"])


# --- Localização PT-BR para datas -------------------------------------------
WEEKDAYS_SHORT_PT = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")
WEEKDAYS_LONG_PT = (
    "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo",
)
MONTHS_SHORT_PT = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def _pt_util_date(dt: datetime) -> str:
    """Ex.: 'QUI · 30 JUL 2026' (para a utility bar)."""
    return (
        f"{WEEKDAYS_SHORT_PT[dt.weekday()]} · "
        f"{dt.day:02d} {MONTHS_SHORT_PT[dt.month - 1].upper()} {dt.year}"
    )


def _pt_day_label(d: date) -> str:
    """Ex.: 'Quinta · 30 jul' (para o cabeçalho do dia)."""
    return (
        f"{WEEKDAYS_LONG_PT[d.weekday()]} · "
        f"{d.day:02d} {MONTHS_SHORT_PT[d.month - 1]}"
    )


def _group_by_day(items: Iterable[Article]) -> "OrderedDict[date, list[Article]]":
    grouped: "OrderedDict[date, list[Article]]" = OrderedDict()
    for a in items:
        grouped.setdefault(a.day, []).append(a)
    return grouped


def _parse_category(raw: str | None) -> Category | None:
    if not raw or raw == "todas":
        return None
    try:
        return Category(raw)
    except ValueError:
        return None


def _build_home_context(items: list[Article]) -> dict:
    """Deriva hero/subs/trending/ticker a partir da lista completa e ordenada.

    Independe da busca: o topo do portal continua sendo o topo do portal
    mesmo quando o leitor está filtrando a lista lá embaixo.
    """
    return {
        "hero": items[0] if items else None,
        "subs": items[1:3],
        "trending": items[1:6],
        "ticker_items": items[:10],
    }


def _parse_day(raw: str | None) -> date | None:
    """Aceita o formato do <input type="date"> (YYYY-MM-DD); ignora lixo."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


# Quantas matérias cada página da lista traz. A home tem mais de mil artigos:
# sem isso, uma visita carrega o acervo inteiro de uma vez.
PAGE_SIZE = 30


async def _search_context(
    request: Request,
    session: AsyncSession,
    *,
    categoria: str | None,
    q: str | None,
    fonte: str | None,
    de: str | None,
    ate: str | None,
    ordem: str | None,
    pagina: int = 1,
) -> dict:
    """Roda a busca e monta tudo que a lista (e a barra de filtros) precisa."""
    category = _parse_category(categoria)
    q = (q or "").strip()
    fonte = (fonte or "").strip() or None
    day_from = _parse_day(de)
    day_to = _parse_day(ate)
    ordem = ordem if ordem in repo.ORDERS else "recentes"
    pagina = max(1, pagina)
    offset = (pagina - 1) * PAGE_SIZE

    filters = dict(q=q, source=fonte, day_from=day_from, day_to=day_to)

    # Os contadores saem de agregações no banco — nada de trazer as linhas só
    # para contá-las. `totals` ignora a categoria de propósito: é o que cada
    # chip mostra, inclusive os não selecionados.
    totals = await repo.count_by_category(session, **filters)
    per_day = await repo.count_by_day(session, category=category, **filters)
    items = await repo.search_page(
        session, category=category, order=ordem,
        limit=PAGE_SIZE, offset=offset, **filters,
    )

    total_count = sum(totals.values())
    result_count = totals[category.value] if category is not None else total_count
    has_more = offset + len(items) < result_count

    selected = categoria if categoria in ("ia", "eng_dev_ia", "gestao_ia") else "todas"
    include_terms, _ = parse_query(q)
    grouped = _group_by_day(items)

    return {
        "request": request,
        "grouped": grouped,
        "per_day": per_day,
        "selected_category": selected,
        "q": q,
        "fonte": fonte or "",
        "de": de or "",
        "ate": ate or "",
        "ordem": ordem,
        "hl_terms": include_terms,
        "totals": totals,
        "total_count": total_count,
        "result_count": result_count,
        "pagina": pagina,
        # Link do "Carregar mais": mesma busca, próxima página. `dia_corte`
        # diz qual cabeçalho de dia já foi impresso, para não repetir.
        "next_url": _next_url(
            q=q, fonte=fonte, de=de, ate=ate, ordem=ordem,
            categoria=selected, pagina=pagina + 1,
            dia_corte=items[-1].day if items else None,
        ) if has_more else None,
        "remaining": max(0, result_count - offset - len(items)),
        # `has_advanced` = o painel de busca tem algo preenchido (a editoria
        # não conta: ela vive nos chips, fora do painel).
        "has_advanced": bool(q or fonte or day_from or day_to or ordem != "recentes"),
        "has_filters": bool(q or fonte or day_from or day_to or ordem != "recentes" or category),
        "is_admin": auth.is_admin(request),
        "day_label": _pt_day_label,
    }


def _next_url(**params) -> str:
    """Monta a URL da próxima página deixando de fora o que é vazio/padrão."""
    clean = {}
    for key, value in params.items():
        if value in (None, "", "todas"):
            continue
        if key == "ordem" and value == "recentes":
            continue
        clean[key] = value.isoformat() if isinstance(value, date) else str(value)
    return "/?" + urlencode(clean)


@router.get("/")
async def home(
    request: Request,
    categoria: str | None = None,
    q: str | None = None,
    fonte: str | None = None,
    de: str | None = None,
    ate: str | None = None,
    ordem: str | None = None,
    pagina: int = 1,
    dia_corte: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    ctx = await _search_context(
        request, session, categoria=categoria, q=q, fonte=fonte,
        de=de, ate=ate, ordem=ordem, pagina=pagina,
    )

    # "Carregar mais": só os blocos de dia + o próximo botão, para anexar no
    # fim da lista. `dia_corte` evita repetir o cabeçalho de um dia que a
    # página anterior já abriu.
    if pagina > 1:
        return templates.TemplateResponse(
            "partials/article_page.html",
            {**ctx, "hide_day_head_for": _parse_day(dia_corte)},
        )

    # Requisição do HTMX (usuário mexeu nos filtros): devolve só a lista.
    # Os chips e os contadores viajam junto, com swap out-of-band.
    if request.headers.get("hx-request") == "true":
        return templates.TemplateResponse(
            "partials/article_list.html", {**ctx, "oob_counts": True}
        )

    # Carga completa da página: hero/ticker vêm sempre do topo do acervo.
    return templates.TemplateResponse(
        "index.html",
        {
            **ctx,
            "sources": await repo.list_source_names(session),
            "util_date_label": _pt_util_date(datetime.now()),
            **_build_home_context(await repo.list_for_home(session, limit=10)),
        },
    )


@router.get("/articles")
async def articles_fragment(
    request: Request,
    categoria: str | None = None,
    q: str | None = None,
    fonte: str | None = None,
    de: str | None = None,
    ate: str | None = None,
    ordem: str | None = None,
    pagina: int = 1,
    session: AsyncSession = Depends(get_session),
):
    """Fragmento HTMX: só a lista, sem o layout."""
    ctx = await _search_context(
        request, session, categoria=categoria, q=q, fonte=fonte,
        de=de, ate=ate, ordem=ordem, pagina=pagina,
    )
    return templates.TemplateResponse(
        "partials/article_list.html", {**ctx, "oob_counts": True}
    )


def _canonical(request: Request, path: str) -> str:
    """URL absoluta do portal, para meta tags e links de compartilhamento.

    Usa `PUBLIC_SITE_URL` (o domínio canônico) e cai para o host da requisição
    quando a variável não está configurada — assim o link compartilhado nunca
    aponta para localhost em produção, nem para produção num deploy de preview
    sem env.
    """
    base = (settings.public_site_url or "").rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}{path}"


def _share_summary(article: Article, limit: int = 200) -> str:
    """1º parágrafo do resumo, cortado — vira a descrição do preview do link."""
    first = (article.ig_content or "").split("\n\n")[0].strip()
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


@router.get("/noticia/{article_id}")
async def article_page(
    request: Request,
    article_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Permalink de uma notícia — a página que se compartilha.

    Existe para dar um endereço próprio a cada item (com Open Graph, para o
    preview aparecer no WhatsApp/X/LinkedIn). O texto continua sendo só o
    resumo: a matéria completa fica na fonte, linkada em destaque.
    """
    try:
        uuid.UUID(article_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Notícia não encontrada.") from None

    article = await repo.get_by_id(session, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Notícia não encontrada.")

    share_url = _canonical(request, f"/noticia/{article.id}")
    return templates.TemplateResponse(
        "noticia.html",
        {
            "request": request,
            "is_admin": auth.is_admin(request),
            "article": article,
            "share_url": share_url,
            "share_summary": _share_summary(article),
            "share_image": article.source_image_url or article.image_url,
            "day_label": _pt_day_label(article.day),
            "util_date_label": _pt_util_date(datetime.now()),
        },
    )


@router.get("/sobre")
async def about(request: Request):
    """Página estática: método da curadoria, compromissos editoriais e contato."""
    return templates.TemplateResponse(
        "sobre.html",
        {
            "request": request,
            "is_admin": auth.is_admin(request),
            "util_date_label": _pt_util_date(datetime.now()),
        },
    )


@router.get("/login")
async def login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": error,
            "util_date_label": _pt_util_date(datetime.now()),
        },
    )


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if auth.login(request, password):
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    auth.logout(request)
    return RedirectResponse("/", status_code=303)
