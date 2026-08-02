"""Leitura dos feeds RSS/Atom com feedparser.

IMPORTANTE: `feedparser.parse(url)` faz o download internamente e NÃO tem
timeout — um feed lento/fora do ar pendura a ingestão inteira (e estoura o
tempo da função na Vercel). Por isso baixamos o conteúdo com httpx (timeout
rígido por feed) e passamos os bytes já baixados ao feedparser.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import httpx

from ianoticias.config.feeds import FEEDS, Feed
from ianoticias.config.settings import settings

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 IANoticias/1.0"
)


@dataclass(frozen=True)
class FeedEntry:
    feed: Feed
    title: str
    url: str
    summary: str
    published_at: datetime  # sempre tz-aware (UTC)


def _to_datetime(entry) -> datetime | None:
    """Extrai published/updated de uma entry do feedparser como datetime UTC."""
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            try:
                # feedparser retorna time.struct_time em UTC.
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _parse_one(feed: Feed, timeout: float) -> list[FeedEntry]:
    """Baixa (com timeout) e parseia um feed. Nunca levanta — [] em erro."""
    try:
        resp = httpx.get(
            feed.url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
        resp.raise_for_status()
        # Passa os BYTES já baixados — feedparser não faz rede aqui.
        parsed = feedparser.parse(resp.content)
    except Exception:  # noqa: BLE001 — rede/parse têm edge cases variados
        return []

    entries: list[FeedEntry] = []
    for entry in getattr(parsed, "entries", []) or []:
        url = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        if not url or not title:
            continue
        published = _to_datetime(entry)
        if not published:
            continue
        summary = (getattr(entry, "summary", "") or "").strip()
        entries.append(
            FeedEntry(
                feed=feed,
                title=title,
                url=url,
                summary=summary,
                published_at=published,
            )
        )
    return entries


async def fetch_all_feeds(feeds: Iterable[Feed] | None = None) -> list[FeedEntry]:
    """Lê todos os feeds em paralelo (feedparser é síncrono → to_thread).

    `feeds=None` usa a lista default do código (config/feeds.py). Uma lista
    vazia é respeitada como vazia (ex.: admin desativou todas as fontes).
    """
    feeds = list(FEEDS if feeds is None else feeds)
    timeout = float(settings.ingest_feed_timeout)
    tasks = [asyncio.to_thread(_parse_one, f, timeout) for f in feeds]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [entry for group in results for entry in group]
