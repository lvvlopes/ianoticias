"""Troca um token de CURTA duração por um de LONGA duração (~60 dias) e lista
as Páginas + contas Instagram Business associadas — imprimindo os valores
prontos para IG_USER_ID e IG_ACCESS_TOKEN.

Passo a passo:
  1) Abra o Graph API Explorer:
       https://developers.facebook.com/tools/explorer/
     - Selecione seu app (o mesmo do META_APP_ID).
     - Em "Permissions", adicione:
         instagram_basic, instagram_content_publish,
         pages_show_list, pages_read_engagement, business_management
     - Clique "Generate Access Token" e autorize.
     - Copie o token gerado (é de curta duração, ~1-2h).
  2) Rode:
       python scripts/ig_token.py <TOKEN_DE_CURTA_DURACAO>

O script imprime:
  - o token de LONGA duração (use em IG_ACCESS_TOKEN)
  - o ID da conta Instagram Business (use em IG_USER_ID)
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ianoticias.config.settings import settings  # noqa: E402

GRAPH = f"https://graph.facebook.com/{settings.graph_api_version}"


def main(short_token: str) -> None:
    if not settings.meta_app_id or not settings.meta_app_secret:
        print("META_APP_ID / META_APP_SECRET não configurados no .env.")
        return

    with httpx.Client(timeout=30) as c:
        # 1) Curta → Longa duração
        r = c.get(
            f"{GRAPH}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": short_token,
            },
        )
        data = r.json()
        if "access_token" not in data:
            print("Falha na troca do token:")
            print(data)
            return
        long_token = data["access_token"]
        print("=" * 64)
        print("TOKEN DE LONGA DURAÇÃO (use em IG_ACCESS_TOKEN):")
        print(long_token)
        print(f"(expira em ~{data.get('expires_in', 5184000) // 86400} dias)")
        print("=" * 64)

        # 2) Páginas do usuário (o token de página derivado não expira)
        r = c.get(f"{GRAPH}/me/accounts", params={"access_token": long_token})
        pages = r.json().get("data", [])
        if not pages:
            print("Nenhuma Página encontrada. Confirme que sua conta administra")
            print("uma Página do Facebook conectada à conta Instagram Business.")
            return

        print("\nPáginas e contas Instagram associadas:")
        for pg in pages:
            page_id = pg.get("id")
            page_token = pg.get("access_token", "")
            name = pg.get("name", "?")
            # conta IG Business ligada à página
            ig = c.get(
                f"{GRAPH}/{page_id}",
                params={"fields": "instagram_business_account", "access_token": long_token},
            ).json()
            ig_id = (ig.get("instagram_business_account") or {}).get("id")
            print("-" * 64)
            print(f"Página: {name}  (id {page_id})")
            if ig_id:
                print(">>> RECOMENDADO — cole estas duas linhas no .env")
                print("    (o Page token NÃO expira; melhor que o de 60 dias):")
                print(f"IG_USER_ID={ig_id}")
                print(f"IG_ACCESS_TOKEN={page_token}")
            else:
                print("  (sem conta IG Business ligada a esta Página)")
                print(f"  Page token: {page_token}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/ig_token.py <TOKEN_DE_CURTA_DURACAO>")
        print("(gere o token no Graph API Explorer — veja o topo deste arquivo)")
        sys.exit(1)
    main(sys.argv[1])
