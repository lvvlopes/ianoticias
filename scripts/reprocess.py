"""Reprocessa notícias já salvas com o PROMPT ATUAL do LLM.

Útil depois de mudar o prompt (ex.: resumo passou de 3-4 frases para 2 parágrafos):
regenera ig_title / ig_content / hashtags das matérias existentes.

Como funciona: re-baixa o texto da fonte (o corpo não é armazenado, por
copyright) e chama a OpenAI de novo com o prompt do banco.

Uso:
    python scripts/reprocess.py            # só as que ainda estão em 1 parágrafo
    python scripts/reprocess.py --all      # todas as notícias
    python scripts/reprocess.py --limit 5  # no máximo 5 (economiza tokens)

Requer MOCK_LLM=0 e OPENAI_API_KEY válido no .env.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from ianoticias.config.settings import settings
from ianoticias.db.engine import SessionLocal
from ianoticias.db.models import Article
from ianoticias.services.config_store import load_llm_config
from ianoticias.services.extractor import extract_article
from ianoticias.services.llm import summarize_for_instagram


async def main(only_old: bool, limit: int | None) -> None:
    if settings.mock_llm or not settings.openai_api_key:
        print("MOCK_LLM ligado ou sem OPENAI_API_KEY — o reprocess geraria mock. Abortando.")
        return

    async with SessionLocal() as session:
        cfg = await load_llm_config(session)
        rows = list((await session.execute(select(Article))).scalars().all())

        alvo = [a for a in rows if not (only_old and "\n\n" in (a.ig_content or ""))]
        if limit:
            alvo = alvo[:limit]
        print(f"{len(alvo)} de {len(rows)} notícias serão reprocessadas.\n")

        done = skip = 0
        for a in alvo:
            try:
                ex = await extract_article(a.source_url)
                llm = await summarize_for_instagram(
                    title=a.title_original or a.ig_title,
                    source_name=a.source_name,
                    source_url=a.source_url,
                    body=ex.text,
                    hint=a.category.value,
                    system_prompt=cfg.system_prompt,
                    user_template=cfg.user_template,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ERRO  {a.ig_title[:48]!r}: {type(exc).__name__}: {exc}")
                skip += 1
                continue

            if not llm.relevante or not llm.ig_conteudo:
                print(f"  pula  {a.ig_title[:48]!r} (irrelevante/sem conteúdo)")
                skip += 1
                continue

            a.ig_title = llm.ig_titulo or a.ig_title
            a.ig_content = llm.ig_conteudo
            if llm.hashtags:
                a.hashtags = llm.hashtags
            # se o card já foi gerado, zera para regenerar no próximo publish
            paras = a.ig_content.count("\n\n") + 1
            print(f"  OK    {a.ig_title[:48]!r} · {paras} parágrafo(s)")
            done += 1

        await session.commit()
        print(f"\nConcluído: {done} reprocessadas, {skip} puladas.")


if __name__ == "__main__":
    only_old = "--all" not in sys.argv
    limit = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        limit = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else None
    asyncio.run(main(only_old, limit))
