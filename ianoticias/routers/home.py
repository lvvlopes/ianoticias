"""Rotas de UI: home, login, filtro de categoria."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from typing import Iterable

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

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


def _count_by_category(items: Iterable[Article]) -> dict[str, int]:
    totals = {cat: 0 for cat in ("ia", "eng_dev_ia", "gestao_ia")}
    for a in items:
        totals[a.category.value] += 1
    return totals


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
) -> dict:
    """Roda a busca e monta tudo que a lista (e a barra de filtros) precisa."""
    category = _parse_category(categoria)
    q = (q or "").strip()
    fonte = (fonte or "").strip() or None
    day_from = _parse_day(de)
    day_to = _parse_day(ate)
    ordem = ordem if ordem in repo.ORDERS else "recentes"

    # `matched` ignora a categoria de propósito — é o universo da busca, e é
    # dele que saem os contadores de cada chip de editoria.
    matched = await repo.search_for_home(
        session, q=q, source=fonte, day_from=day_from, day_to=day_to, order=ordem
    )
    filtered = matched if category is None else [a for a in matched if a.category == category]

    include_terms, _ = parse_query(q)
    return {
        "request": request,
        "grouped": _group_by_day(filtered),
        "selected_category": categoria if categoria in ("ia", "eng_dev_ia", "gestao_ia") else "todas",
        "q": q,
        "fonte": fonte or "",
        "de": de or "",
        "ate": ate or "",
        "ordem": ordem,
        "hl_terms": include_terms,
        "totals": _count_by_category(matched),
        "total_count": len(matched),
        "result_count": len(filtered),
        # `has_advanced` = o painel de busca tem algo preenchido (a editoria
        # não conta: ela vive nos chips, fora do painel).
        "has_advanced": bool(q or fonte or day_from or day_to or ordem != "recentes"),
        "has_filters": bool(q or fonte or day_from or day_to or ordem != "recentes" or category),
        "is_admin": auth.is_admin(request),
        "day_label": _pt_day_label,
    }


@router.get("/")
async def home(
    request: Request,
    categoria: str | None = None,
    q: str | None = None,
    fonte: str | None = None,
    de: str | None = None,
    ate: str | None = None,
    ordem: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    ctx = await _search_context(
        request, session, categoria=categoria, q=q, fonte=fonte, de=de, ate=ate, ordem=ordem
    )

    # Requisição do HTMX (usuário mexeu na busca): devolve só a lista.
    # Os contadores dos chips viajam junto, com swap out-of-band.
    if request.headers.get("hx-request") == "true":
        return templates.TemplateResponse(
            "partials/article_list.html", {**ctx, "oob_counts": True}
        )

    # Carga completa da página: hero/ticker/rail vêm sempre do acervo inteiro.
    all_items = await repo.list_for_home(session, category=None)
    return templates.TemplateResponse(
        "index.html",
        {
            **ctx,
            "sources": await repo.list_source_names(session),
            "util_date_label": _pt_util_date(datetime.now()),
            **_build_home_context(all_items),
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
    session: AsyncSession = Depends(get_session),
):
    """Fragmento HTMX: só a lista, sem o layout."""
    ctx = await _search_context(
        request, session, categoria=categoria, q=q, fonte=fonte, de=de, ate=ate, ordem=ordem
    )
    return templates.TemplateResponse(
        "partials/article_list.html", {**ctx, "oob_counts": True}
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
