# IANoticias

Portal em Python de **curadoria automática de notícias de IA** — lê RSS de
portais reputados (BR + mundo), filtra as últimas 24h, classifica em 3
categorias, resume cada notícia via LLM em formato de post de Instagram, gera
um card 1080×1080 e permite publicar direto no IG. A home mostra as notícias
**agrupadas por dia**.

- **Backend:** FastAPI + SQLAlchemy 2.0 (async, asyncpg)
- **UI:** Jinja2 + HTMX + Tailwind (Play CDN)
- **Banco:** Supabase Postgres
- **Storage:** Supabase Storage (bucket público) — para o card
- **LLM:** OpenAI (structured output JSON)
- **Deploy:** Vercel (runtime Python) — entrypoint em `app.py`

> **Sem cron.** A ingestão é disparada manualmente pelo botão "Buscar Notícias"
> na home (rota protegida por sessão de admin).

---

## 1. Setup do Supabase

1. Crie um projeto em <https://supabase.com>.
2. No **SQL Editor**, cole e rode `migrations/001_init.sql` (cria enums, tabela
   `articles` e índices) e depois `migrations/002_admin.sql` (tabelas
   `feed_sources` e `app_settings`, usadas pela tela de administração).
   Alternativa local: `python scripts/run_migration.py migrations/002_admin.sql`.
3. Em **Storage → New bucket**, crie um bucket **público** (ex.: `ianoticias-cards`).
4. Em **Project Settings → API**, copie:
   - `Project URL` → `SUPABASE_URL`
   - `service_role key` → `SUPABASE_SERVICE_ROLE_KEY`
5. Em **Project Settings → Database → Connection string**, copie a URL do
   Postgres. Duas opções:
   - **Direct** (porta 5432) — bom para rodar migrations locais.
   - **Pooler / Transaction** (porta 6543) — **recomendado para Vercel**
     (serverless). O código detecta a porta 6543 e desativa o cache de
     prepared statements do asyncpg automaticamente.
   - Prefixe o driver: `postgresql+asyncpg://...`.

## 2. Configurar variáveis de ambiente

Copie `.env.example` para `.env` e preencha. Campos obrigatórios para rodar o
pipeline real: `DATABASE_URL`, `OPENAI_API_KEY`, `ADMIN_PASSWORD`,
`SESSION_SECRET`.

Para desenvolver localmente **sem chamar APIs externas**, use os mocks:

```env
MOCK_LLM=1        # resumo determinístico em vez de OpenAI
MOCK_IG=1         # simula a publicação no Instagram
MOCK_STORAGE=1    # salva o card em static/mock_cards/ (URL local)
```

## 3. Rodar localmente

```bash
python -m venv .venv
. .venv/Scripts/activate         # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
```

Popular com dados de demonstração e subir o servidor:

```bash
python -m ianoticias.seed
uvicorn app:app --reload
```

Os itens de demo linkam para as páginas reais de notícias das fontes (não
geram 404). Para remover dados de demo antigos/quebrados e re-semear:

```bash
python -m ianoticias.seed --purge
```

Abra <http://localhost:8000>. Para usar o botão **Buscar Notícias**, entre em
`/login` com a senha do `ADMIN_PASSWORD`.

## 4. Deploy na Vercel

- Faça push para um repositório Git e conecte na Vercel.
- A Vercel detecta o `app.py` (instância `app = FastAPI()`) via
  `@vercel/python`. O `vercel.json` já roteia `/static/*` para os arquivos
  estáticos e todo o resto para o handler.
- Configure todas as envs do `.env.example` em **Project → Settings →
  Environment Variables**.
- Não há `crons` — a atualização é sempre manual.

**Atenção ao timeout** da função (Hobby ~10s, Pro ~60s). O pipeline usa cap
por execução (`INGEST_MAX_ITEMS`) e devolve `cap_reached: true` no resumo
quando ainda há matérias pendentes — basta clicar em **Buscar Notícias** de
novo.

## 5. Meta / Instagram

Para publicar de verdade no Instagram você precisa de:

1. Uma **Página do Facebook** conectada a uma **conta Instagram
   Business/Creator**.
2. Um **app no Meta for Developers** (<https://developers.facebook.com/apps/>).
3. Um **token de acesso de usuário** com os escopos
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement` e `business_management`.
4. Trocar o token de curta duração por um **token de longa duração** (~60d):
   ```
   GET https://graph.facebook.com/v21.0/oauth/access_token?
       grant_type=fb_exchange_token
       &client_id={META_APP_ID}
       &client_secret={META_APP_SECRET}
       &fb_exchange_token={SHORT_TOKEN}
   ```
   Cole o token retornado em `IG_ACCESS_TOKEN`.
5. Descubra seu `IG_USER_ID`:
   ```
   GET /me/accounts               → pega o page id
   GET /{page_id}?fields=instagram_business_account
                                    → devolve o IG_USER_ID
   ```

> **TODO documentado no código** (`app/services/instagram.py`): agendar a
> renovação automática do token de longa duração antes dos 60 dias.

## 6. Fluxo de uso

1. Admin abre `/login`, entra com `ADMIN_PASSWORD`.
2. Clica em **Buscar Notícias** → dispara `POST /api/ingest` via HTMX.
3. O pipeline: lê feeds → dedup → filtra 24h → **valida o link (HEAD/GET, só
   passa quem responde 2xx)** → 1 chamada OpenAI por item
   (`response_format=json_object`) → salva relevantes → gera card PNG e sobe
   para o Storage → recomputa `featured` do dia. A validação de link roda
   ANTES do LLM (economiza tokens) e evita links quebrados no portal; pode ser
   desligada com `INGEST_VALIDATE_LINKS=0`.
4. A UI recarrega a lista com o resumo (ex.: "Salvas 8 notícias").
5. Em cada card, botão **Postar no Instagram** dispara
   `POST /api/instagram/publish`, que cria o container e publica.

### Tela de administração (`/admin`)

Logado como admin, o link **Admin** aparece no menu. A tela permite:

- **Fontes de busca** (editável): adicionar/editar/ativar/excluir feeds
  RSS/Atom, com região (BR/Mundo) e categoria-dica. Persistido em
  `feed_sources`. Na primeira abertura, a tabela é semeada com a lista de
  `ianoticias/config/feeds.py`. A partir daí, o pipeline lê **do banco**.
- **Regras do LLM** (editável): os dois prompts (system + user template) que
  classificam e resumem cada matéria. Placeholders disponíveis: `{hint}`,
  `{title}`, `{source_name}`, `{source_url}`, `{body}`. Botão **Restaurar
  padrão** volta aos textos do código. Persistido em `app_settings`.
- **Regras do pipeline** (somente leitura): janela de 24h, dedup por SHA-256,
  cap por execução, fuso, modelo OpenAI etc. — configuráveis apenas por
  variáveis de ambiente, não pela tela.

Se você nunca abrir o `/admin`, o comportamento é idêntico ao padrão do código
(fallback automático para `config/feeds.py` e os prompts default).

## 7. Boas práticas de curadoria

- **Sempre creditar a fonte** e linkar o original (`Ler matéria completa`).
- **Nunca republicar** o texto completo. O corpo extraído por `trafilatura`
  serve apenas como input do LLM e é descartado; salvamos só o resumo
  **reescrito** com palavras próprias.
- O extractor respeita `robots.txt` sempre que o host o define. Antes de
  adicionar novos feeds, revise os **Termos de Uso** do portal — alguns
  proíbem republicação ainda que o resumo seja reescrito.
- Resumos são curtos (3–4 frases), tom informativo para público dev/tech.

## 8. Estrutura de arquivos

```
IANoticias/
├── app.py                   # entrypoint Vercel: app = FastAPI()
├── vercel.json              # sem crons
├── requirements.txt
├── migrations/              # 001_init.sql, 002_admin.sql (rodar no Supabase)
├── scripts/run_migration.py # aplica um .sql via asyncpg (uso local)
├── static/fonts/            # fontes do card (Space Grotesk / JetBrains Mono)
├── static/hero/             # imagens de fundo das thumbs (default.jpg, etc.)
├── templates/               # Jinja2 (base, index, login, admin, partials)
└── ianoticias/              # pacote interno (renomeado p/ não conflitar com app.py)
    ├── config/              # settings.py, feeds.py (defaults de fonte)
    ├── db/                  # engine.py, models.py
    ├── repositories/        # articles.py, feeds_repo.py, settings_repo.py
    ├── services/            # feeds, extractor, dedup, llm, image_card,
    │                        # storage, instagram, pipeline, config_store
    ├── security/auth.py     # sessão de admin
    ├── routers/             # home, ingest, instagram, admin
    ├── templating.py        # objeto Jinja2 compartilhado
    └── seed.py              # dados fake para dev
```
