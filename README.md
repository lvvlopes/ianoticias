# IANoticias

Portal em Python de **curadoria automática de notícias de IA** — lê RSS de
portais reputados (BR + mundo), filtra as últimas 24h, classifica em 3
categorias, resume cada notícia via LLM em formato de post de Instagram, gera
um card 1080×1080 e permite publicar direto no IG. A home mostra as notícias
**agrupadas por dia**.

- **Backend:** FastAPI + SQLAlchemy 2.0 (async, asyncpg)
- **UI:** Jinja2 + HTMX + CSS próprio (visual editorial)
- **Banco:** Supabase Postgres
- **Storage:** Supabase Storage (bucket público) — para o card
- **LLM:** OpenAI (structured output JSON)
- **Deploy:** Vercel (runtime Python) — entrypoint em `app.py`

> **Sem cron.** A ingestão é disparada manualmente pelo botão "Buscar Notícias"
> na home (rota protegida por sessão de admin).

---

## Guias de configuração

Cada integração tem seu passo a passo detalhado, com todas as armadilhas
que aprendemos:

| Guia | Cobre |
|------|-------|
| **[CONFIG-SUPABASE.md](docs/CONFIG-SUPABASE.md)** | Criar projeto, rodar migrations, bucket público, chave `service_role` legada (JWT), connection string do pooler, workaround PgBouncer + NullPool |
| **[CONFIG-OPENAI.md](docs/CONFIG-OPENAI.md)** | Chave, escolha do modelo (ID exato), prompt de classificação, custos, reprocessar notícias antigas |
| **[CONFIG-META-INSTAGRAM.md](docs/CONFIG-META-INSTAGRAM.md)** | Conta Business + Página, app Meta, permissões, gerar token de Página (que não expira), renovação, legenda otimizada |
| **[CONFIG-VERCEL.md](docs/CONFIG-VERCEL.md)** | Deploy inicial, `vercel.json` com `includeFiles`, envs, timeouts, `/api/_diag` para debug |

Depois de configurar tudo, o endpoint **`GET /api/_diag`** confirma se o
runtime enxerga banco, Storage, Instagram, fontes e imagens (retorna JSON,
sem segredos).

---

## Rodar localmente

```bash
python -m venv .venv
. .venv/Scripts/activate         # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha (mínimo: `DATABASE_URL`,
`OPENAI_API_KEY`, `ADMIN_PASSWORD`, `SESSION_SECRET`).

Para desenvolver a UI **sem chamar APIs externas**, use os mocks:

```env
MOCK_LLM=1        # resumo determinístico em vez de OpenAI
MOCK_IG=1         # simula a publicação no Instagram
MOCK_STORAGE=1    # salva o card em static/mock_cards/ (URL local)
```

Popule com dados de demo e suba:

```bash
python -m ianoticias.seed
uvicorn app:app --reload
```

Abra <http://localhost:8000>. Para usar o botão **Buscar Notícias**, entre em
`/login` com a senha do `ADMIN_PASSWORD`.

---

## Fluxo de uso

1. Admin abre `/login`, entra com `ADMIN_PASSWORD`.
2. Clica **Buscar Notícias** → dispara `POST /api/ingest` via HTMX.
3. O pipeline: lê feeds → dedup → filtra 24h → **valida o link** (2xx) →
   **pré-filtro por palavra-chave** → 1 chamada OpenAI por item → salva
   relevantes → recomputa `featured` do dia.
4. A UI recarrega a lista com o resumo (ex.: "Salvas 8 notícias").
5. Em cada card, botão **Postar IG** dispara `POST /api/instagram/publish`,
   que gera o card, sobe pro Storage, cria o container na Graph API e publica.

### Tela de administração (`/admin`)

Logado como admin, o link **Admin** aparece no menu. Permite:

- **Fontes de busca** (editável): CRUD dos feeds RSS/Atom. Persistido em
  `feed_sources`. Se a tabela está vazia, é semeada a partir de
  `ianoticias/config/feeds.py`.
- **Regras do LLM** (editável): system prompt + user template. Persistido em
  `app_settings`. Placeholders: `{hint}`, `{title}`, `{source_name}`,
  `{source_url}`, `{body}`. Botão **Restaurar padrão** volta ao código.
- **Regras do pipeline** (somente leitura): janela de 24h, dedup, cap, fuso —
  ajustáveis apenas por env.
- **Token do Instagram** (auto-renovável): status + botão "Renovar agora".

---

## Boas práticas de curadoria

- **Sempre creditar a fonte** e linkar o original.
- **Nunca republicar** o texto completo. O corpo extraído por `trafilatura`
  serve apenas como input do LLM e é descartado; salvamos só o resumo
  **reescrito** com palavras próprias.
- O extractor respeita `robots.txt` sempre que o host o define. Antes de
  adicionar novos feeds, revise os **Termos de Uso** do portal.
- Resumos em **2 parágrafos** (fatos + implicações), tom informativo para
  público dev/tech.

---

## Estrutura de arquivos

```
IANoticias/
├── app.py                     # entrypoint Vercel: app = FastAPI()
├── vercel.json                # includeFiles + roteamento
├── requirements.txt
├── docs/                      # SPEC + guias de configuração (Supabase, OpenAI, Meta, Vercel)
├── migrations/                # 001_init, 002_admin, 003_source_image
├── scripts/
│   ├── run_migration.py       # aplica um .sql via asyncpg
│   ├── diag_ingest.py         # funil de ingestão (feeds → 24h → dedup → filtro)
│   ├── diag_llm.py            # testa OpenAI (chave + modelo)
│   ├── diag_ig.py             # testa Storage + publicação Instagram
│   ├── ig_token.py            # troca token curto por token de Página (não expira)
│   └── reprocess.py           # regenera resumo de notícias antigas
├── static/
│   ├── fonts/                 # DejaVu (SIL OFL), bundlada para acentos no card
│   └── hero/                  # imagens de fundo (intagram.jpg, default.jpg)
├── templates/                 # Jinja2 (base, index, login, admin, partials)
└── ianoticias/                # pacote interno (renomeado p/ não conflitar com app.py)
    ├── config/                # settings.py, feeds.py (defaults)
    ├── db/                    # engine.py (NullPool + PgBouncer safe), models.py
    ├── repositories/          # articles, feeds_repo, settings_repo
    ├── services/              # feeds, extractor, dedup, llm, image_card,
    │                          # storage, instagram, pipeline, config_store,
    │                          # link_check, relevance
    ├── security/auth.py       # sessão de admin
    ├── routers/               # home, ingest, instagram, admin
    ├── templating.py          # objeto Jinja2 compartilhado
    └── seed.py                # dados de demo p/ dev
```
