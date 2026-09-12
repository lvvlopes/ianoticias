"""Camada de acesso a dados para `articles`.

Todas as funções recebem uma AsyncSession já aberta (injetada pelo router ou
criada pelo pipeline).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select, update

from ianoticias.db.models import Article, Category, IgStatus
from ianoticias.text_search import ACCENT_DST, ACCENT_SRC, like_pattern, parse_query


async def exists_by_url(session, source_url: str) -> bool:
    """True se já existe artigo com aquela URL canônica (dedup)."""
    stmt = select(func.count()).select_from(Article).where(Article.source_url == source_url)
    result = await session.scalar(stmt)
    return bool(result)


async def existing_urls(session, urls: list[str]) -> set[str]:
    """Retorna o subconjunto de `urls` que já está no banco (dedup em lote)."""
    if not urls:
        return set()
    stmt = select(Article.source_url).where(Article.source_url.in_(urls))
    rows = await session.execute(stmt)
    return {r[0] for r in rows.all()}


async def insert_article(session, **fields) -> Article:
    article = Article(**fields)
    session.add(article)
    await session.flush()  # popula o id
    return article


async def get_by_id(session, article_id: uuid.UUID | str) -> Article | None:
    if isinstance(article_id, str):
        article_id = uuid.UUID(article_id)
    return await session.get(Article, article_id)


async def set_image_url(session, article_id: uuid.UUID, image_url: str) -> None:
    await session.execute(
        update(Article).where(Article.id == article_id).values(image_url=image_url)
    )


async def set_source_image_url(session, article_id: uuid.UUID, url: str) -> None:
    await session.execute(
        update(Article).where(Article.id == article_id).values(source_image_url=url)
    )


async def mark_posted(session, article_id: uuid.UUID, ig_post_id: str) -> None:
    await session.execute(
        update(Article)
        .where(Article.id == article_id)
        .values(ig_status=IgStatus.posted, ig_post_id=ig_post_id)
    )


async def recompute_featured_for_day(session, day: date, per_category: int) -> None:
    """Recalcula (idempotente) os `featured` de um dia.

    Zera o featured do dia e marca os `per_category` mais recentes de cada
    categoria como featured.
    """
    # 1) zera tudo do dia
    await session.execute(
        update(Article).where(Article.day == day).values(featured=False)
    )

    # 2) para cada categoria, marca os N mais recentes
    for category in Category:
        stmt = (
            select(Article.id)
            .where(Article.day == day, Article.category == category)
            .order_by(Article.published_at.desc(), Article.created_at.desc())
            .limit(per_category)
        )
        ids = [row[0] for row in (await session.execute(stmt)).all()]
        if ids:
            await session.execute(
                update(Article).where(Article.id.in_(ids)).values(featured=True)
            )


async def list_for_home(
    session,
    category: Category | None = None,
    day_limit: int = 14,
) -> list[Article]:
    """Lista artigos ordenados por dia (desc), featured primeiro, mais recente.

    O agrupamento por dia é feito na camada de apresentação (router/template).
    """
    stmt = select(Article)
    if category is not None:
        stmt = stmt.where(Article.category == category)
    stmt = stmt.order_by(
        Article.day.desc(),
        Article.featured.desc(),
        Article.published_at.desc(),
        Article.created_at.desc(),
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def distinct_days(session, limit: int = 14) -> list[date]:
    stmt = select(Article.day).distinct().order_by(Article.day.desc()).limit(limit)
    rows = await session.execute(stmt)
    return [r[0] for r in rows.all()]


# ---------------------------------------------------------------------------
# Busca / filtros da home
# ---------------------------------------------------------------------------

def _haystack():
    """Expressão SQL com todo o texto pesquisável de um artigo, normalizado.

    `translate` remove acentos e `lower` iguala a caixa — a mesma dupla que
    `text_search.fold()` aplica no termo digitado, então "gestao" acha "gestão".
    """
    blob = func.concat_ws(
        " ",
        Article.ig_title,
        Article.title_original,
        Article.ig_content,
        Article.source_name,
        func.array_to_string(Article.hashtags, " "),
    )
    return func.lower(func.translate(blob, ACCENT_SRC, ACCENT_DST))


ORDERS = ("recentes", "antigas", "fonte")


async def search_for_home(
    session,
    *,
    q: str | None = None,
    source: str | None = None,
    day_from: date | None = None,
    day_to: date | None = None,
    order: str = "recentes",
) -> list[Article]:
    """Artigos que batem com a busca — sem filtro de categoria.

    A categoria fica de fora de propósito: o router usa esta lista para contar
    quantos resultados cada editoria tem e só então aplica o filtro escolhido.
    """
    stmt = select(Article)

    include, exclude = parse_query(q)
    if include or exclude:
        hay = _haystack()
        for term in include:
            stmt = stmt.where(hay.like(like_pattern(term), escape="\\"))
        for term in exclude:
            stmt = stmt.where(~hay.like(like_pattern(term), escape="\\"))

    if source:
        stmt = stmt.where(Article.source_name == source)
    if day_from is not None:
        stmt = stmt.where(Article.day >= day_from)
    if day_to is not None:
        stmt = stmt.where(Article.day <= day_to)

    if order == "antigas":
        stmt = stmt.order_by(
            Article.day.asc(), Article.published_at.asc(), Article.created_at.asc()
        )
    elif order == "fonte":
        stmt = stmt.order_by(
            Article.source_name.asc(), Article.day.desc(), Article.published_at.desc()
        )
    else:  # "recentes" (padrão) — mesma ordenação da home sem busca
        stmt = stmt.order_by(
            Article.day.desc(),
            Article.featured.desc(),
            Article.published_at.desc(),
            Article.created_at.desc(),
        )

    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def list_source_names(session) -> list[str]:
    """Fontes distintas, em ordem alfabética — alimenta o select de fonte."""
    stmt = select(Article.source_name).distinct().order_by(Article.source_name)
    rows = await session.execute(stmt)
    return [r[0] for r in rows.all()]
