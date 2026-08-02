"""Orquestração do POST /api/ingest.

Passos (seguindo SPEC.md § "Pipeline de ingestão"):
    1. Ler feeds RSS/Atom.
    2. Deduplicar por URL canônica (pular o que já existe no banco).
    3. Filtrar últimas 24h + limitar ao cap por execução.
    4. Para cada item: extrair corpo → chamar LLM → (se relevante) persistir.
    5. Gerar card de imagem e fazer upload (best-effort).
    6. Recomputar `featured` dos dias afetados.
    7. Retornar resumo para a UI.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ianoticias.config.settings import settings
from ianoticias.db.engine import SessionLocal
from ianoticias.db.models import Category
from ianoticias.repositories import articles as repo
from ianoticias.services.config_store import LLMConfig, load_active_feeds, load_llm_config
from ianoticias.services.dedup import canonical_url
from ianoticias.services.extractor import extract_article
from ianoticias.services.feeds import FeedEntry, fetch_all_feeds
from ianoticias.services.image_card import build_card_jpeg
from ianoticias.services.link_check import build_client, is_reachable
from ianoticias.services.llm import summarize_for_instagram
from ianoticias.services.relevance import looks_relevant
from ianoticias.services.storage import upload_card_image


@dataclass
class IngestSummary:
    fetched: int = 0                       # total de entries lidas dos feeds
    considered: int = 0                    # entries elegíveis (novas, últimas 24h)
    processed: int = 0                     # itens efetivamente enviados ao LLM
    saved: int = 0                         # itens salvos (relevantes)
    by_category: dict[str, int] = field(default_factory=lambda: {c.value: 0 for c in Category})
    skipped_duplicates: int = 0
    skipped_old: int = 0
    skipped_offtopic: int = 0              # cortado no pré-filtro (fora de tema)
    skipped_irrelevant: int = 0
    skipped_dead_link: int = 0             # link não respondeu 2xx (descartado)
    errors: int = 0
    cap_reached: bool = False              # true se atingiu INGEST_MAX_ITEMS

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "considered": self.considered,
            "processed": self.processed,
            "saved": self.saved,
            "by_category": self.by_category,
            "skipped_duplicates": self.skipped_duplicates,
            "skipped_old": self.skipped_old,
            "skipped_offtopic": self.skipped_offtopic,
            "skipped_irrelevant": self.skipped_irrelevant,
            "skipped_dead_link": self.skipped_dead_link,
            "errors": self.errors,
            "cap_reached": self.cap_reached,
        }


def _local_day(dt: datetime) -> Any:
    """Converte datetime UTC para a data no fuso configurado (America/Sao_Paulo)."""
    return dt.astimezone(ZoneInfo(settings.timezone)).date()


async def _process_entry(
    entry: FeedEntry,
    summary: IngestSummary,
    llm_config: LLMConfig,
    http_client=None,
) -> tuple[dict | None, str | None]:
    """Retorna (article_fields, error). article_fields é None se irrelevante/erro."""
    # 0) Guardrail de credibilidade: descarta link quebrado ANTES de gastar
    #    tokens no LLM. Um 404 no portal desacredita a curadoria.
    if http_client is not None:
        reachable = await is_reachable(
            http_client, entry.url, timeout=settings.ingest_feed_timeout
        )
        if not reachable:
            summary.skipped_dead_link += 1
            return None, None

    try:
        extracted = await extract_article(entry.url, fallback_summary=entry.summary)
        llm = await summarize_for_instagram(
            title=entry.title,
            source_name=entry.feed.name,
            source_url=entry.url,
            body=extracted.text,
            hint=entry.feed.hint,
            system_prompt=llm_config.system_prompt,
            user_template=llm_config.user_template,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"

    if not llm.relevante or llm.categoria is None or not llm.ig_titulo or not llm.ig_conteudo:
        summary.skipped_irrelevant += 1
        return None, None

    now = datetime.now(timezone.utc)
    fields = {
        "source_name": entry.feed.name,
        "source_url": canonical_url(entry.url),
        "title_original": entry.title,
        "category": Category(llm.categoria),
        "ig_title": llm.ig_titulo,
        "ig_content": llm.ig_conteudo,
        "hashtags": llm.hashtags,
        "source_image_url": extracted.image_url,
        "published_at": entry.published_at,
        "fetched_at": now,
        "day": _local_day(entry.published_at),
    }
    return fields, None


async def _generate_and_upload_card(article_id, fields: dict) -> str | None:
    """Best-effort: gera o card JPEG e sobe pro Storage. None se falhar/desligado."""
    try:
        jpeg = await asyncio.to_thread(
            build_card_jpeg,
            title=fields["ig_title"],
            category=fields["category"].value,
            source_url=fields.get("source_url", ""),
            source_name=fields.get("source_name", ""),
            ig_content=fields.get("ig_content", ""),
            source_image_url=fields.get("source_image_url"),
        )
        return await upload_card_image(article_id=str(article_id), image_bytes=jpeg)
    except Exception:  # noqa: BLE001 — card é opcional na ingestão
        return None


async def run_ingest() -> IngestSummary:
    summary = IngestSummary()

    # 1) Ler feeds ATIVOS do banco (semeados a partir de config/feeds.py na 1ª vez)
    active_feeds = await load_active_feeds()
    entries = await fetch_all_feeds(active_feeds)
    summary.fetched = len(entries)

    # 3a) Filtrar últimas 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    fresh = [e for e in entries if e.published_at >= cutoff]
    summary.skipped_old = len(entries) - len(fresh)

    # 2) Dedup por URL canônica (agrupa entradas duplicadas antes de bater no banco)
    seen_urls: dict[str, FeedEntry] = {}
    for e in fresh:
        key = canonical_url(e.url)
        # Fica com a entrada mais recente para uma mesma URL.
        prev = seen_urls.get(key)
        if prev is None or e.published_at > prev.published_at:
            seen_urls[key] = e
    candidates = sorted(seen_urls.values(), key=lambda e: e.published_at, reverse=True)

    async with SessionLocal() as session:
        already = await repo.existing_urls(session, list(seen_urls.keys()))
        summary.skipped_duplicates = len(already)
        candidates = [e for e in candidates if canonical_url(e.url) not in already]

        # 3a-bis) Pré-filtro de relevância ANTES do cap: remove o ruído óbvio de
        # feeds gerais (games, gadgets, cinema...) para não desperdiçar o cap e
        # o orçamento da OpenAI. O LLM faz a classificação estrita depois.
        if settings.prefilter_relevance:
            before = len(candidates)
            candidates = [e for e in candidates if looks_relevant(e.title, e.summary)]
            summary.skipped_offtopic = before - len(candidates)

        summary.considered = len(candidates)

        # 3b) Cap por execução (evita timeout na Vercel).
        cap = settings.ingest_max_items
        if len(candidates) > cap:
            summary.cap_reached = True
            candidates = candidates[:cap]

        # Prompts do LLM configurados na tela /admin (com fallback aos defaults).
        llm_config = await load_llm_config(session)

        affected_days: set = set()

        # 4) Processa em concorrência limitada (mais leve pra fetch/LLM em paralelo).
        semaphore = asyncio.Semaphore(4)
        http_client = build_client() if settings.validate_links else None

        async def _worker(entry: FeedEntry):
            async with semaphore:
                return await _process_entry(entry, summary, llm_config, http_client)

        try:
            results = await asyncio.gather(*[_worker(e) for e in candidates])
        finally:
            if http_client is not None:
                await http_client.aclose()
        summary.processed = len(results)

        for fields, error in results:
            if error:
                summary.errors += 1
                continue
            if fields is None:
                continue

            # Insere e (best-effort) gera+upa o card
            article = await repo.insert_article(session, **fields)
            image_url = await _generate_and_upload_card(article.id, fields)
            if image_url:
                await repo.set_image_url(session, article.id, image_url)

            summary.saved += 1
            summary.by_category[fields["category"].value] += 1
            affected_days.add(fields["day"])

        # 6) Recompute featured dos dias afetados
        for day in affected_days:
            await repo.recompute_featured_for_day(
                session, day, per_category=settings.featured_per_category
            )

        await session.commit()

    return summary
