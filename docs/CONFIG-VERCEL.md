# Configuração — Vercel (deploy)

O IANoticias roda na Vercel como uma **função Python** (`@vercel/python`) —
não é serverful, cada request cria (ou reusa) uma invocação da função.
Este guia cobre o setup e todas as pegadinhas específicas de serverless
Python que já enfrentamos.

## 1. Pré-requisito

- Código versionado em Git (GitHub, GitLab ou Bitbucket).
- `.env` **fora** do git — configurações vão no painel da Vercel.

## 2. Primeiro deploy

### Opção A — pelo painel web

1. <https://vercel.com/new> → **Import Git Repository** → escolha o repo.
2. **Framework Preset**: `Other` (a Vercel detecta `app.py` via `vercel.json`).
3. Antes de clicar Deploy, expanda **Environment Variables** e cole todas
   as variáveis do `.env.example` (ver seção 4 abaixo).
4. **Deploy**.

### Opção B — via CLI

```bash
npm install -g vercel        # precisa Node.js
vercel login                 # abre navegador
vercel                       # deploy de preview
vercel --prod                # deploy de produção
```

Depois de importado, todo `git push` para `main` dispara **redeploy
automático** em produção. Não precisa mais rodar `vercel` a cada mudança.

## 3. `vercel.json` (já commitado)

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python",
      "config": {
        "includeFiles": "{static/**,templates/**,ianoticias/**,migrations/**}"
      }
    }
  ],
  "routes": [
    { "src": "/static/(.*)", "dest": "/static/$1" },
    { "src": "/(.*)", "dest": "app.py" }
  ]
}
```

⚠️ **`includeFiles` é essencial.** Sem ele, `@vercel/python` **não** empacota
`static/` (as fontes e imagens) dentro da função — os arquivos ficam
acessíveis via HTTP (rota `/static/*`), mas o Pillow, rodando dentro da
função, tenta abrir `/var/task/static/hero/intagram.jpg` e falha. Foi por
isso que o card saía com quadrados no lugar de acentos.

## 4. Variáveis de ambiente (todas obrigatórias em produção)

Painel Vercel → **Project → Settings → Environment Variables**. Marque as três
`Environments` (Production/Preview/Development) em cada uma.

### Banco + Storage (ver [CONFIG-SUPABASE.md](CONFIG-SUPABASE.md))
```
DATABASE_URL
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET
```

### LLM
```
OPENAI_API_KEY
OPENAI_MODEL
```

### Instagram (ver [CONFIG-META-INSTAGRAM.md](CONFIG-META-INSTAGRAM.md))
```
IG_USER_ID
IG_ACCESS_TOKEN
META_APP_ID
META_APP_SECRET
GRAPH_API_VERSION
IG_HANDLE
IG_BRAND_HASHTAG
IG_HASHTAGS_IN_COMMENT
```

### App
```
ADMIN_PASSWORD
SESSION_SECRET             ← em produção, use uma string aleatória FORTE
PUBLIC_SITE_URL            ← https://SEU_APP.vercel.app
```

### Pipeline (opcionais, todos com defaults sensatos)
```
INGEST_FEED_TIMEOUT=8
INGEST_MAX_ITEMS=12
FEATURED_PER_CATEGORY=4
INGEST_VALIDATE_LINKS=1
INGEST_PREFILTER=1
```

### Diagnóstico (só quando precisar)
```
DEBUG_ERRORS=1
```
Quando ligada, um erro 500 mostra o **traceback Python** direto no navegador
em vez do "Internal Server Error" genérico. **Não deixe ligada em produção
normal** — expõe caminhos internos.

> Após adicionar/mudar env, **precisa fazer redeploy** (Vercel só relê env em
> novo build): aba **Deployments → ⋮ → Redeploy** no último. Ou faça um push
> qualquer, mesmo trivial.

## 5. Timeouts e limites

| Plano | Timeout da função | Bundle |
|-------|-------------------|--------|
| Hobby | **10s** | 250 MB (comprimido) |
| Pro   | 60s (config até 5min) | 250 MB |

O pipeline de ingest (`/api/ingest`) faz 1 chamada OpenAI **por artigo novo**;
com muitos feeds, pode estourar 10s. Ajustes:

- `INGEST_MAX_ITEMS=12` (default) — cap por clique. Quando cheio, o resumo
  do ingest mostra "cap atingido — clique novamente".
- Aumente para 20-30 no plano Pro; deixe menor no Hobby.

O `Semaphore(4)` no `pipeline.py` limita concorrência das chamadas OpenAI.

## 6. Padrões específicos de serverless

- **Sessão no filesystem?** Não. O `/var/task/` é read-only e o `/tmp/` some
  entre invocações. Cards vão para o Supabase Storage; nada é persistido no FS.
- **Pool de conexão do banco?** Usamos `NullPool` — cada request abre/fecha
  conexão. Combina com serverless e resolve bugs do PgBouncer. Ver
  [CONFIG-SUPABASE.md § 5](CONFIG-SUPABASE.md).
- **`https_only` do cookie**: o `app.py` ativa automaticamente quando detecta
  `VERCEL_ENV=production` (env que a própria Vercel injeta).
- **Cold start**: primeira request após ~1min sem uso demora 1-3s a mais.
  Normal em Python serverless.

## 7. Verificação após o deploy

1. **Home**: `https://SEU_APP.vercel.app/` deve carregar de forma estável.
2. **Health**: `https://SEU_APP.vercel.app/healthz` → `{"status":"ok"}`.
3. **Diagnóstico completo**: `https://SEU_APP.vercel.app/api/_diag` → JSON com
   `db_ping`, presença de fontes/imagens no bundle, features ativas:
   ```json
   {
     "ok": true,
     "python_env": "production",
     "fonts": ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", ...],
     "hero_files": ["default.jpg", "intagram.jpg", ...],
     "has_database_url": true,
     "has_openai": true,
     "has_storage": true,
     "has_instagram": true,
     "db_ping": "ok (1)"
   }
   ```
   Qualquer `false` ou `db_ping` com erro aponta a integração faltando.

## 8. Ver logs em produção

- Painel: **Deployments → clique no deployment → Runtime Logs → Live**.
- CLI: `vercel logs --follow` (se tiver a CLI instalada).
- Painel de request (Deployment → Requests → uma request): mostra métricas
  do request específico, **mas não o traceback** — pro traceback use os
  Runtime Logs, ou ligue `DEBUG_ERRORS=1`.

## 9. Rollback

**Deployments → ⋮** no deployment desejado → **Promote to Production**.
Rollback instantâneo, sem rebuild.
