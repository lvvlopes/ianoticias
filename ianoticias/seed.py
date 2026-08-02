"""Popula o banco com dados de DEMONSTRAÇÃO para desenvolver a UI sem APIs.

Uso:
    python -m ianoticias.seed            # insere os itens de demo (pula existentes)
    python -m ianoticias.seed --purge    # remove os itens de demo antigos e re-semeia

IMPORTANTE: os itens de demo agora linkam para as PÁGINAS REAIS de notícias das
fontes (que resolvem normalmente), para nunca exibir link quebrado no portal.
O conteúdo textual é ilustrativo (marcado como "[demo]").
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from ianoticias.config.settings import settings
from ianoticias.db.engine import SessionLocal
from ianoticias.db.models import Article, Category
from ianoticias.repositories import articles as repo

TZ = ZoneInfo(settings.timezone)

# URLs quebradas de versões antigas do seed — removidas no --purge.
LEGACY_DEMO_URLS = [
    "https://openai.com/news/exemplo-mock-1",
    "https://www.anthropic.com/news/exemplo-mock-2",
    "https://feed.infoq.com/exemplo-mock-3",
    "https://leaddev.com/exemplo-mock-4",
]

# Itens de demo apontando para páginas REAIS que resolvem (índices de notícias).
FAKE = [
    (
        "OpenAI News",
        "https://openai.com/news/",
        "[demo] Novo modelo é anunciado",
        Category.ia,
        "Novo modelo promete acelerar tarefas do dia a dia",
        "Um novo modelo foi apresentado com foco em raciocínio e uso de ferramentas. "
        "A empresa destaca melhorias de custo e latência. "
        "A liberação começa para clientes API e depois chega ao chat. "
        "Ainda há debate sobre limites e avaliações independentes.",
        ["IA", "OpenAI", "Modelos", "GenAI"],
    ),
    (
        "Anthropic News",
        "https://www.anthropic.com/news",
        "[demo] Atualização de segurança de agentes",
        Category.ia,
        "Agentes de IA ganham novas travas de segurança",
        "Novas políticas restringem ações destrutivas por padrão. "
        "A ideia é aumentar a confiança para tarefas com efeitos no mundo real. "
        "Devs podem configurar overrides caso a caso. "
        "O time também documentou riscos comuns e mitigações.",
        ["IA", "Anthropic", "Agentes", "Seguranca"],
    ),
    (
        "InfoQ",
        "https://www.infoq.com/",
        "[demo] Copilotos de código em produção",
        Category.eng_dev_ia,
        "Como times estão medindo o impacto real de copilotos de código",
        "Métricas de aceitação de sugestões nem sempre refletem produtividade. "
        "Times maduros combinam pesquisa qualitativa com dados de PRs. "
        "Feedback rápido do dev é o sinal mais consistente. "
        "Ainda é cedo para provar ROI em toda a organização.",
        ["Engenharia", "Copilot", "Produtividade", "DX"],
    ),
    (
        "LeadDev",
        "https://leaddev.com/",
        "[demo] Liderança e IA",
        Category.gestao_ia,
        "Liderança técnica precisa reaprender roadmap com IA",
        "Ciclos ficaram mais curtos e experimentos mais baratos. "
        "Liderar bem exige revisar processos de discovery e QA. "
        "Times pequenos entregam o que antes exigia squads grandes. "
        "A gestão de risco muda de foco quando o código muda mais rápido.",
        ["Gestao", "Lideranca", "IA", "Roadmap"],
    ),
]

DEMO_URLS = [item[1] for item in FAKE]


async def purge(session) -> int:
    """Remove itens de demo (atuais + legados quebrados). Retorna quantos."""
    urls = list({*DEMO_URLS, *LEGACY_DEMO_URLS})
    result = await session.execute(delete(Article).where(Article.source_url.in_(urls)))
    return result.rowcount or 0


async def main(do_purge: bool = False) -> None:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        if do_purge:
            removed = await purge(session)
            print(f"Purge: {removed} item(ns) de demo removido(s).")

        affected: set = set()
        for i, (source_name, url, title_orig, cat, ig_title, ig_content, tags) in enumerate(FAKE):
            published = now - timedelta(hours=i * 2)
            day = published.astimezone(TZ).date()
            if await repo.exists_by_url(session, url):
                continue
            await repo.insert_article(
                session,
                id=uuid.uuid4(),
                source_name=source_name,
                source_url=url,
                title_original=title_orig,
                category=cat,
                ig_title=ig_title,
                ig_content=ig_content,
                hashtags=tags,
                published_at=published,
                fetched_at=now,
                day=day,
            )
            affected.add(day)

        for day in affected:
            await repo.recompute_featured_for_day(session, day, per_category=settings.featured_per_category)

        await session.commit()
        print(f"Seed OK. Dias populados: {sorted(affected)}")


if __name__ == "__main__":
    asyncio.run(main(do_purge="--purge" in sys.argv))
