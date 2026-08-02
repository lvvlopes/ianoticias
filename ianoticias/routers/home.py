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
    """Deriva hero/subs/trending/ticker/totais a partir da lista ordenada."""
    totals = {"ia": 0, "eng_dev_ia": 0, "gestao_ia": 0}
    for a in items:
        totals[a.category.value] += 1

    return {
        "all_items": items,
        "total_count": len(items),
        "hero": items[0] if items else None,
        "subs": items[1:3],
        "trending": items[1:6],
        "ticker_items": items[:10],
        "totals": totals,
    }


@router.get("/")
async def home(
    request: Request,
    categoria: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    category = _parse_category(categoria)
    # Para as métricas globais (contadores por categoria, hero, ticker),
    # precisamos sempre da lista COMPLETA — o filtro afeta apenas a lista
    # renderizada por dia mais abaixo.
    all_items = await repo.list_for_home(session, category=None)
    filtered = all_items if category is None else [a for a in all_items if a.category == category]

    grouped = _group_by_day(filtered)
    ctx = _build_home_context(all_items)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "grouped": grouped,
            "selected_category": categoria or "todas",
            "is_admin": auth.is_admin(request),
            "util_date_label": _pt_util_date(datetime.now()),
            "day_label": _pt_day_label,
            **ctx,
        },
    )


@router.get("/articles")
async def articles_fragment(
    request: Request,
    categoria: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Fragmento HTMX: só a lista, sem o layout — usado pelos filtros de categoria."""
    category = _parse_category(categoria)
    items = await repo.list_for_home(session, category=category)
    grouped = _group_by_day(items)
    return templates.TemplateResponse(
        "partials/article_list.html",
        {
            "request": request,
            "grouped": grouped,
            "selected_category": categoria or "todas",
            "is_admin": auth.is_admin(request),
            "day_label": _pt_day_label,
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
