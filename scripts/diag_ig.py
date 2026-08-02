"""Mostra por que a publicação no Instagram está (ou não) em modo mock,
e opcionalmente faz um teste real contra a Meta Graph API.

Uso:
    python scripts/diag_ig.py            # só mostra o estado da config
    python scripts/diag_ig.py --publish  # tenta publicar um card de teste real
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ianoticias.config.settings import settings  # noqa: E402


def show_state() -> None:
    print("Estado da configuração do Instagram:")
    print(f"  MOCK_IG            = {settings.mock_ig}   (precisa ser False p/ postar de verdade)")
    print(f"  IG_USER_ID         = {'(preenchido)' if settings.ig_user_id else '(VAZIO)'}")
    print(f"  IG_ACCESS_TOKEN    = {'(preenchido)' if settings.ig_access_token else '(VAZIO)'}")
    print(f"  GRAPH_API_VERSION  = {settings.graph_api_version}")
    print(f"  → has_instagram    = {settings.has_instagram}   (só posta de verdade se True)")
    print()
    print(f"  MOCK_STORAGE       = {settings.mock_storage}   (precisa ser False: a Meta exige image_url PÚBLICA)")
    print(f"  SUPABASE_URL       = {'(preenchido)' if settings.supabase_url else '(VAZIO)'}")
    print(f"  SERVICE_ROLE_KEY   = {'(preenchido)' if settings.supabase_service_role_key else '(VAZIO)'}")
    print(f"  STORAGE_BUCKET     = {settings.supabase_storage_bucket}")
    print(f"  → has_storage      = {settings.has_storage}")
    print("-" * 60)
    if settings.mock_ig:
        print("DIAGNÓSTICO: MOCK_IG está LIGADO → simula sucesso sem postar. Ponha MOCK_IG=0.")
    elif not (settings.ig_user_id and settings.ig_access_token):
        print("DIAGNÓSTICO: falta IG_USER_ID e/ou IG_ACCESS_TOKEN → cai no mock.")
    elif not settings.has_storage:
        print("DIAGNÓSTICO: Storage em mock/vazio. O card não fica com URL pública e a Meta recusa.")
    else:
        print("Config parece OK para postar de verdade. Rode com --publish para testar.")


async def test_publish() -> None:
    from ianoticias.db.engine import SessionLocal
    from ianoticias.repositories import articles as repo
    from ianoticias.services import instagram as ig
    from ianoticias.services.image_card import build_card_jpeg
    from ianoticias.services.storage import upload_card_image

    async with SessionLocal() as session:
        items = await repo.list_for_home(session)
        if not items:
            print("Sem artigos no banco para testar. Rode o ingest antes.")
            return
        art = items[0]
        print(f"Testando com: {art.ig_title!r}")

        # Sempre regenera (garante JPEG novo, ignorando PNG antigo já salvo).
        jpeg = await asyncio.to_thread(
            build_card_jpeg,
            title=art.ig_title,
            category=art.category.value,
            source_url=art.source_url,
            source_name=art.source_name,
            ig_content=art.ig_content,
            source_image_url=getattr(art, "source_image_url", None),
        )
        image_url = await upload_card_image(article_id=str(art.id), image_bytes=jpeg)
        print(f"Card JPEG gerado e enviado: {image_url}")

        caption = ig.build_caption(
            ig_title=art.ig_title, ig_content=art.ig_content,
            hashtags=list(art.hashtags or []), source_url=art.source_url,
        )
        print("\n--- Legenda ---")
        print(caption)
        comment = ig.build_first_comment(list(art.hashtags or []))
        if comment:
            print("\n--- 1º comentário (hashtags) ---")
            print(comment)
        print("-" * 40)
        try:
            result = await ig.publish(image_url=image_url, caption=caption)
            if str(result.media_id).startswith("mock_"):
                print(f"⚠ Retornou id MOCK ({result.media_id}) — NÃO postou. Veja o diagnóstico acima.")
            else:
                print(f"✓ PUBLICADO de verdade. media_id = {result.media_id}")
                if comment:
                    cid = await ig.post_comment(media_id=result.media_id, message=comment)
                    print(f"  1º comentário: {'postado (' + cid + ')' if cid else 'falhou/desligado'}")
        except ig.InstagramError as exc:
            print(f"✗ ERRO da Meta Graph API: {exc}")


if __name__ == "__main__":
    show_state()
    if "--publish" in sys.argv:
        print("=" * 60)
        asyncio.run(test_publish())
