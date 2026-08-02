"""Acesso a dados das fontes de feed (tabela feed_sources).

Todas as funções recebem uma AsyncSession já aberta.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update

from ianoticias.db.models import Category, FeedSource


async def count(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(FeedSource)) or 0)


async def list_all(session) -> list[FeedSource]:
    """Todas as fontes, ordenadas por position e nome (para a tela admin)."""
    stmt = select(FeedSource).order_by(FeedSource.position.asc(), FeedSource.name.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def list_enabled(session) -> list[FeedSource]:
    """Somente fontes ativas — usadas pelo pipeline de ingestão."""
    stmt = (
        select(FeedSource)
        .where(FeedSource.enabled.is_(True))
        .order_by(FeedSource.position.asc(), FeedSource.name.asc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_by_id(session, feed_id: uuid.UUID | str) -> FeedSource | None:
    if isinstance(feed_id, str):
        feed_id = uuid.UUID(feed_id)
    return await session.get(FeedSource, feed_id)


async def create(
    session, *, name: str, url: str, region: str, hint: Category, enabled: bool = True
) -> FeedSource:
    max_pos = await session.scalar(select(func.coalesce(func.max(FeedSource.position), 0)))
    feed = FeedSource(
        name=name,
        url=url,
        region=region,
        hint=hint,
        enabled=enabled,
        position=int(max_pos or 0) + 1,
    )
    session.add(feed)
    await session.flush()
    return feed


async def update_fields(
    session,
    feed_id: uuid.UUID | str,
    *,
    name: str,
    url: str,
    region: str,
    hint: Category,
    enabled: bool,
) -> None:
    if isinstance(feed_id, str):
        feed_id = uuid.UUID(feed_id)
    await session.execute(
        update(FeedSource)
        .where(FeedSource.id == feed_id)
        .values(
            name=name,
            url=url,
            region=region,
            hint=hint,
            enabled=enabled,
            updated_at=func.now(),
        )
    )


async def toggle(session, feed_id: uuid.UUID | str) -> None:
    if isinstance(feed_id, str):
        feed_id = uuid.UUID(feed_id)
    await session.execute(
        update(FeedSource)
        .where(FeedSource.id == feed_id)
        .values(enabled=~FeedSource.enabled, updated_at=func.now())
    )


async def remove(session, feed_id: uuid.UUID | str) -> None:
    if isinstance(feed_id, str):
        feed_id = uuid.UUID(feed_id)
    await session.execute(delete(FeedSource).where(FeedSource.id == feed_id))


async def bulk_insert_defaults(session, defaults) -> int:
    """Semeia a tabela a partir dos defaults de config/feeds.py.

    `defaults` é um iterável de objetos com atributos name/url/region/hint.
    Ignora URLs que já existem. Retorna quantos foram inseridos.
    """
    existing = {
        row[0]
        for row in (await session.execute(select(FeedSource.url))).all()
    }
    inserted = 0
    for pos, d in enumerate(defaults, start=1):
        if d.url in existing:
            continue
        session.add(
            FeedSource(
                name=d.name,
                url=d.url,
                region=d.region,
                hint=Category(d.hint),
                enabled=True,
                position=pos,
            )
        )
        inserted += 1
    if inserted:
        await session.flush()
    return inserted
