"""Adiciona ao banco os feeds que estão em `config/feeds.py` mas ainda não
existem em `feed_sources`. Mantém intactos os feeds que você já editou/
desativou pelo /admin (só INSERE, nunca sobrescreve).

Rode local depois de adicionar novas fontes ao config; usa o DATABASE_URL do
.env (aponta pro Supabase de produção).

Uso:
    python scripts/sync_feeds.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ianoticias.config.feeds import FEEDS
from ianoticias.db.engine import SessionLocal
from ianoticias.repositories import feeds_repo


async def main() -> None:
    async with SessionLocal() as session:
        before = await feeds_repo.count(session)
        added = await feeds_repo.bulk_insert_defaults(session, FEEDS)
        await session.commit()
        after = await feeds_repo.count(session)
    print(f"Antes: {before} feeds  |  Adicionados: {added}  |  Agora: {after}")


if __name__ == "__main__":
    asyncio.run(main())
