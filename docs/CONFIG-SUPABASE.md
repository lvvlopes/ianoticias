# Configuração — Supabase (banco + Storage)

O IANoticias usa Supabase para **duas** coisas: **Postgres** (dados) e **Storage**
(cards de imagem do Instagram). Este guia cobre criação, migrations, buckets,
chaves, connection string, e todas as armadilhas que já enfrentamos.

## 1. Criar o projeto

<https://supabase.com> → **New project**. Guarde a senha do banco (aparece
uma única vez). Aguarde ~2 min o provisionamento.

## 2. Rodar as migrations

Abra **SQL Editor → New query** e execute, **na ordem**:

| Arquivo                          | O que cria |
|----------------------------------|------------|
| `migrations/001_init.sql`        | Enums (`category`, `ig_status`), tabela `articles`, índices |
| `migrations/002_admin.sql`       | Tabelas `feed_sources` e `app_settings` (tela `/admin`) |
| `migrations/003_source_image.sql`| Coluna `articles.source_image_url` |

Alternativa local (via asyncpg, usa `DATABASE_URL` do `.env`):

```bash
python scripts/run_migration.py migrations/001_init.sql
python scripts/run_migration.py migrations/002_admin.sql
python scripts/run_migration.py migrations/003_source_image.sql
```

> Toda nova migration futura é só criar `migrations/NNN_*.sql` e rodar.

## 3. Criar o bucket público para o card

**Storage → New bucket** → nome `ianoticias-cards` → **Public bucket LIGADO** ✅
→ Create.

⚠️ **Público é obrigatório.** O Instagram só publica quando consegue baixar a
`image_url` — e ele bate sem autenticação em
`{SUPABASE_URL}/storage/v1/object/public/{bucket}/{arquivo}`.
Bucket privado devolve `400 + JSON` em vez da imagem, e a Meta responde
com "Only photo or video can be accepted as media type" (mensagem enganosa).

Para conferir se está público, abra no navegador uma URL do card gerado:
`https://SEU_REF.supabase.co/storage/v1/object/public/ianoticias-cards/qualquer.jpg`
Se vier `application/json` com `statusCode`, o bucket é privado.

## 4. Pegar as chaves e a Project URL

**Settings → API**:
- **Project URL** → `SUPABASE_URL` (formato `https://<ref>.supabase.co`).
- **Legacy API keys → service_role** → `SUPABASE_SERVICE_ROLE_KEY`.

⚠️ **Use a `service_role` LEGADA (JWT `eyJ...`), não a nova (`sb_secret_...`).**
O Storage do Supabase ainda valida o Bearer como JWT em algumas rotas —
`sb_secret_...` falha com **"Invalid Compact JWS"**. A `service_role` JWT
funciona em todos os serviços e é o padrão de backend.

### Como confirmar que a chave é do projeto certo

A `service_role` guarda o `project ref` dentro do JWT. Diagnóstico:

```bash
python -c "import os,json,base64; from urllib.parse import urlparse; from dotenv import load_dotenv; load_dotenv(r'.env'); k=os.getenv('SUPABASE_SERVICE_ROLE_KEY',''); p=k.split('.')[1]; p+='='*(-len(p)%4); d=json.loads(base64.urlsafe_b64decode(p)); print('role :', d.get('role')); print('ref  :', d.get('ref')); print('URL  :', urlparse(os.getenv('SUPABASE_URL')).hostname)"
```

- `role` **precisa** ser `service_role` (não `anon`).
- `ref` da chave **precisa** bater com o subdomínio do `SUPABASE_URL`.
Se divergirem, sua chave é de **outro projeto** — pegue a `service_role` do
projeto correto ou ajuste `SUPABASE_URL`.

## 5. Connection string do Postgres

**Settings → Database → Connection string**. Há 3 abas:

| Aba                     | Porta | Use quando |
|-------------------------|------|------------|
| **Direct connection**   | 5432 | Migrations e scripts locais só |
| **Transaction pooler**  | 6543 | **Padrão para app / Vercel** |
| **Session pooler**      | 5432 | Não usamos |

Copie a URL do **Transaction pooler** e:

1. Troque o scheme `postgresql://` por `postgresql+asyncpg://` (o código
   também faz isso automaticamente, mas o `.env.example` mostra explícito).
2. Substitua `[YOUR-PASSWORD]` pela senha do banco.
3. Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`, `%`), faça
   URL-encoding:
   ```bash
   python -c "import urllib.parse; print(urllib.parse.quote('SUA_SENHA', safe=''))"
   ```

Formato final:
```env
DATABASE_URL=postgresql+asyncpg://postgres.SEU_REF:SENHA_ENCODED@aws-0-REGIAO.pooler.supabase.com:6543/postgres
```

### PgBouncer + asyncpg — bug que já resolvemos

Com o Transaction pooler (PgBouncer), asyncpg **não pode** usar prepared
statements normais. O `ianoticias/db/engine.py` detecta a porta 6543 e
aplica automaticamente:

- `statement_cache_size=0` (desliga cache);
- `prepared_statement_name_func` com UUID (nomes únicos, sem colisão);
- **`NullPool`** — cada request abre/fecha sua conexão (elimina o problema
  do statement preparado numa conexão e executado em outra depois do reset
  do PgBouncer).

Você **não precisa** configurar nada disso à mão — só usar a URL do pooler.
Se aparecer `InvalidSQLStatementNameError: prepared statement ... does not
exist`, a causa é essa e a solução acima já está no código.

## 6. Verificar tudo com um só comando

```
GET https://SEU_APP.vercel.app/api/_diag
```

Ativo por padrão, sem segredos, devolve JSON com `has_database_url`,
`has_storage`, `db_ping: "ok (1)"`, lista de fontes/imagens no bundle, etc.
Perfeito pra confirmar se o Supabase está conectando no runtime da Vercel.

## Variáveis desta integração

```env
DATABASE_URL=postgresql+asyncpg://postgres.REF:SENHA@aws-0-REGIAO.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....
SUPABASE_STORAGE_BUCKET=ianoticias-cards
```
