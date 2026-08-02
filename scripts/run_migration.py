"""Roda um arquivo .sql no banco configurado em DATABASE_URL (via asyncpg direto).

Uso:
    python scripts/run_migration.py migrations/002_admin.sql
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()


async def main(sql_path: str) -> None:
    raw = os.getenv("DATABASE_URL", "")
    u = urlparse(raw.replace("postgresql+asyncpg", "postgresql"))
    sql = Path(sql_path).read_text(encoding="utf-8")

    conn = await asyncpg.connect(
        host=u.hostname,
        port=u.port,
        user=u.username,
        password=u.password,
        database=(u.path or "/").lstrip("/"),
        ssl="require",
        statement_cache_size=0,
    )
    try:
        await conn.execute(sql)
        print(f"OK: {sql_path} aplicado.")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/run_migration.py <arquivo.sql>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
