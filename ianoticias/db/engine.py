"""Engine async (asyncpg) + sessionmaker.

Cuidados específicos para Supabase/serverless:
- Quando a connection string usa o pooler PgBouncer (porta 6543, transaction
  mode), o asyncpg NÃO pode usar prepared statements com cache. Detectamos a
  porta 6543 e desligamos o cache.
- Parseamos a DATABASE_URL com urlparse e reconstruímos com URL.create(), pois
  o parser interno do SQLAlchemy pode embaralhar hostname/senha quando a senha
  tem caracteres especiais (@, #, /, :, %) — vimos isso quebrar a resolução
  de DNS na prática.
- pool_pre_ping evita conexões mortas entre invocações da função.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from urllib.parse import unquote, urlparse

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ianoticias.config.settings import settings

# Construção preguiçosa: não pagamos o custo (nem exigimos DATABASE_URL) até o
# primeiro uso. Isso evita quebrar o import em cold start / dev sem DB.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _to_sqlalchemy_url(raw: str) -> URL:
    """Converte a DATABASE_URL do Supabase em um URL do SQLAlchemy limpo.

    Usa urlparse para pegar os componentes e monta com URL.create(), que já
    faz o encoding correto internamente — evita o SQLA reinterpretar chars
    especiais na senha e sujar o hostname.
    """
    # Normaliza o scheme para o driver certo, mas parseamos como "postgresql://"
    # p/ evitar que urlparse trate "+asyncpg" como parte do host.
    parseable = raw
    if parseable.startswith("postgres://"):
        parseable = "postgresql://" + parseable[len("postgres://") :]
    if parseable.startswith("postgresql+asyncpg://"):
        parseable = "postgresql://" + parseable[len("postgresql+asyncpg://") :]

    u = urlparse(parseable)
    if not u.hostname:
        raise RuntimeError(f"DATABASE_URL inválida: sem hostname ({raw!r})")

    return URL.create(
        drivername="postgresql+asyncpg",
        username=unquote(u.username) if u.username else None,
        password=unquote(u.password) if u.password else None,
        host=u.hostname,
        port=u.port,
        database=(u.path or "/").lstrip("/") or None,
    )


def _build_engine() -> AsyncEngine:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Preencha o .env (veja .env.example)."
        )
    url = _to_sqlalchemy_url(settings.database_url)

    connect_args: dict = {}
    # PgBouncer (transaction mode) reusa conexões de servidor entre transações,
    # então prepared statements com nome fixo colidem ("DuplicatePreparedStatement").
    # Correção robusta (recomendada pela doc do SQLAlchemy p/ pgbouncer):
    #   1) desligar o cache de statements do asyncpg (statement_cache_size=0);
    #   2) gerar um NOME ÚNICO por prepared statement (name_func com uuid).
    is_pooler = (url.port == 6543) or ("pgbouncer=true" in settings.database_url)
    if is_pooler:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid.uuid4()}__"
        )

    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def SessionLocal() -> AsyncSession:  # noqa: N802 — mantém API pública
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency do FastAPI: fornece uma AsyncSession por request."""
    async with SessionLocal() as session:
        yield session
