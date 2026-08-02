"""Diagnóstico do funil de ingestão SEM chamar a OpenAI.

Mostra quantas matérias sobram em cada etapa:
  feeds lidos → últimas 24h → não-duplicados → link OK

Uso: python scripts/diag_ingest.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permite rodar como `python scripts/diag_ingest.py` (raiz no path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ianoticias.config.settings import settings
from ianoticias.db.engine import SessionLocal
from ianoticias.repositories import articles as repo
from ianoticias.services.config_store import load_active_feeds
from ianoticias.services.dedup import canonical_url
from ianoticias.services.feeds import fetch_all_feeds
from ianoticias.services.link_check import build_client, is_reachable
from ianoticias.services.relevance import looks_relevant


async def main() -> None:
    feeds = await load_active_feeds()
    print(f"Fontes ativas: {len(feeds)}")

    entries = await fetch_all_feeds(feeds)
    print(f"1) Entries lidas dos feeds: {len(entries)}")
    if not entries:
        print("   -> NENHUM feed retornou itens. Provável: rede/feed fora do ar,")
        print("      ou nenhuma fonte ativa. Verifique a lista em /admin.")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    fresh = [e for e in entries if e.published_at >= cutoff]
    print(f"2) Nas últimas 24h: {len(fresh)}  (descartadas por idade: {len(entries) - len(fresh)})")
    if not fresh:
        mais_recente = max(e.published_at for e in entries)
        print(f"   -> Nenhuma nas últimas 24h. Mais recente encontrada: {mais_recente.isoformat()}")
        print("      Se você roda esporadicamente, aumente a janela ou rode com feeds mais ativos.")

    # dedup contra o banco
    seen = {}
    for e in fresh:
        k = canonical_url(e.url)
        if k not in seen or e.published_at > seen[k].published_at:
            seen[k] = e
    async with SessionLocal() as session:
        already = await repo.existing_urls(session, list(seen.keys()))
    novos = [e for e in seen.values() if canonical_url(e.url) not in already]
    print(f"3) Novos (não duplicados): {len(novos)}  (já no banco: {len(already)})")
    if not novos:
        print("   -> Tudo que veio já estava salvo. Normal se você já rodou antes.")
        return

    # pré-filtro de relevância
    print(f"4) Pré-filtro de tema (INGEST_PREFILTER={int(settings.prefilter_relevance)}):")
    if settings.prefilter_relevance:
        on_topic = [e for e in novos if looks_relevant(e.title, e.summary)]
        print(f"   No tema (IA): {len(on_topic)}  (cortadas fora de tema: {len(novos) - len(on_topic)})")
        print("   Amostra do que PASSOU no pré-filtro:")
        for e in on_topic[:10]:
            print(f"     • [{e.feed.hint}] {e.title[:80]}")
        novos = on_topic
    if not novos:
        print("   -> Nada passou no tema. Verifique se há fontes de IA ativas.")
        return

    # validação de link numa amostra
    print(f"5) Validação de link (INGEST_VALIDATE_LINKS={int(settings.validate_links)}):")
    if not settings.validate_links:
        print("   validação DESLIGADA — todos passariam.")
    sample = novos[:12]
    client = build_client()
    ok = dead = 0
    try:
        for e in sample:
            reachable = await is_reachable(client, e.url, timeout=settings.ingest_feed_timeout)
            ok += reachable
            dead += (not reachable)
            print(f"   [{'OK  ' if reachable else 'DEAD'}] {e.url[:90]}")
    finally:
        await client.aclose()
    print(f"   Amostra de {len(sample)}: OK={ok}  DEAD={dead}")
    if dead and not ok:
        print("   -> TODOS os links deram DEAD. Provável causa: HEAD bloqueado, timeout")
        print("      curto, ou SSL/rede. Tente INGEST_VALIDATE_LINKS=0 para confirmar.")


if __name__ == "__main__":
    asyncio.run(main())
