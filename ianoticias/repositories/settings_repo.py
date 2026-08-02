"""Acesso a dados das configurações chave/valor (tabela app_settings)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ianoticias.db.models import AppSetting


async def get(session, key: str) -> str | None:
    return await session.scalar(select(AppSetting.value).where(AppSetting.key == key))


async def get_many(session, keys: list[str]) -> dict[str, str]:
    stmt = select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_(keys))
    rows = await session.execute(stmt)
    return {k: v for k, v in rows.all()}


async def set(session, key: str, value: str) -> None:
    """Upsert (INSERT ... ON CONFLICT) de uma chave."""
    stmt = pg_insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppSetting.key],
        set_={"value": value, "updated_at": func.now()},
    )
    await session.execute(stmt)


async def delete(session, key: str) -> None:
    obj = await session.get(AppSetting, key)
    if obj is not None:
        await session.delete(obj)
