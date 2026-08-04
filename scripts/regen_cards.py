"""Regenera SOMENTE a imagem do card (JPEG) das notícias já salvas.

Diferente de `reprocess.py`, este script NÃO chama a OpenAI (não gasta tokens):
usa o `ig_title`/`categoria`/fonte que já estão no banco e apenas roda o
`build_card_jpeg` de novo, subindo por cima do card antigo no Storage.

Use depois de mexer no layout do card (ex.: título que encolhe para caber em
vez de cortar com "…"). Como o upload é upsert em `{article_id}.jpg`, a URL
pública (`image_url`) continua a mesma — só o arquivo muda.

Uso:
    python scripts/regen_cards.py            # só quem já tem card (image_url)
    python scripts/regen_cards.py --all      # todas as notícias
    python scripts/regen_cards.py --limit 5  # no máximo 5

Requer Storage configurado (Supabase). Em modo mock o card vai para o disco
local — útil para inspecionar, mas não é a URL pública real.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from ianoticias.config.settings import settings
from ianoticias.db.engine import SessionLocal
from ianoticias.db.models import Article
from ianoticias.repositories import articles as repo
from ianoticias.services.image_card import build_card_jpeg
from ianoticias.services.storage import upload_card_image


async def main(only_with_card: bool, limit: int | None) -> None:
    if not settings.has_storage:
        print(
            "AVISO: Storage em modo mock — os cards serão gravados localmente, "
            "não na URL pública. (Configure Supabase para regerar de verdade.)\n"
        )

    async with SessionLocal() as session:
        rows = list((await session.execute(select(Article))).scalars().all())

        alvo = [a for a in rows if not (only_with_card and not a.image_url)]
        if limit:
            alvo = alvo[:limit]
        print(f"{len(alvo)} de {len(rows)} notícias terão o card regerado.\n")

        done = skip = 0
        for a in alvo:
            try:
                jpeg = await asyncio.to_thread(
                    build_card_jpeg,
                    title=a.ig_title or a.title_original or "",
                    category=a.category.value,
                    source_url=a.source_url or "",
                    source_name=a.source_name or "",
                    ig_content=a.ig_content or "",
                    source_image_url=a.source_image_url,
                )
                url = await upload_card_image(article_id=str(a.id), image_bytes=jpeg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERRO  {(a.ig_title or '')[:48]!r}: {type(exc).__name__}: {exc}")
                skip += 1
                continue

            # A URL é estável (upsert), mas garante consistência no banco.
            if url and url != a.image_url:
                await repo.set_image_url(session, a.id, url)
                a.image_url = url
            print(f"  OK    {(a.ig_title or '')[:48]!r}")
            done += 1

        await session.commit()
        print(f"\nConcluído: {done} cards regerados, {skip} com erro.")


if __name__ == "__main__":
    only_with_card = "--all" not in sys.argv
    limit = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        limit = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else None
    asyncio.run(main(only_with_card, limit))
