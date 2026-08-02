# IANoticias

Crie um projeto chamado "IANoticias": um portal de curadoria automática de notícias de
IA, com resumo via LLM em formato de post de Instagram e opção de publicar no Instagram.
Todo o projeto em Python.

## Stack (obrigatório)

- Python 3.12 + FastAPI (ASGI), pronto para deploy na Vercel (runtime Python).
  Entrypoint em `app.py` com a instância `app = FastAPI()` (a Vercel detecta isso).
- UI server-side com Jinja2 + HTMX + Tailwind (via Play CDN para simplicidade).
- Banco: Supabase (Postgres). Acesso via SQLAlchemy 2.0 async (driver asyncpg).
  Fornecer também um arquivo `migrations/001_init.sql` para rodar no SQL Editor do Supabase.
- LLM: OpenAI (SDK oficial `openai`), usando structured output (response_format JSON).
  Modelo configurável por env `OPENAI_MODEL` (default um modelo custo-eficiente).
- IMPORTANTE: manter dependências enxutas (limite de bundle de 500MB, sem tree-shaking).
  NÃO usar LangChain. Só: fastapi, uvicorn, sqlalchemy, asyncpg, openai, feedparser,
  trafilatura, pillow, httpx, jinja2, python-dotenv, supabase (para Storage).

## Objetivo do produto

Buscar notícias dos portais de notícias mais relevantes e conceituados do Brasil e do
mundo, filtrar as das últimas 24h, classificar em 3 categorias, trazer ~4 por categoria,
resumir cada uma em formato de post de Instagram (título + conteúdo) e permitir publicar
no Instagram. A home exibe as notícias AGRUPADAS POR DIA.

## Categorias (enum no banco)

1. "ia"          -> Notícias de IA (geral): pesquisa, modelos, mercado, produtos, política/
   regulação, uso de IA em qualquer setor. É a categoria "guarda-chuva" e o fallback quando
   a notícia é sobre IA mas NÃO é especificamente desenvolvimento nem gerência de projeto.

2. "eng_dev_ia"  -> Desenvolvimento de Software com IA: SOMENTE conteúdo de desenvolvimento
   de software — código, linguagens, frameworks, SDKs, bibliotecas, APIs, arquitetura de
   software, engenharia de software, ferramentas de dev, releases/updates de dev, práticas
   de programação e uso de IA no ato de programar (coding assistants, geração de código).
   NÃO entra aqui: tech geral de consumo (gadgets, smartphones), notícia genérica de IA,
   nem gerência de projeto.

3. "gestao_ia"   -> Gerência de Projeto de Software com IA: SOMENTE conteúdo de gerência/
   gestão de projeto de software — gestão de projetos e produtos de software, PMO, PMP,
   metodologias ágeis (Scrum/Kanban), entrega e delivery, liderança de engenharia,
   estimativas/planejamento, e uso de IA aplicado a esses processos de gestão.
   NÃO entra aqui: notícia de código/desenvolvimento, nem notícia genérica de IA.

Regra de decisão (usada pelo LLM na classificação): se a notícia for sobre IA mas não se
encaixar ESTRITAMENTE em "eng_dev_ia" ou "gestao_ia", classificar como "ia". Se não for
sobre nenhuma das 3, marcar relevante=false.

## Fontes (`app/config/feeds.py`)

Lista curada e consolidada de fontes reputadas (Brasil + mundo, imprensa geral + veículos
de tecnologia/engenharia/gestão), organizada pelas 3 categorias do produto. Cada feed
segue a estrutura:

    { name, url, region: "br"|"world", hint: "ia"|"eng_dev_ia"|"gestao_ia" }

O campo `hint` é apenas a categoria PROVÁVEL da fonte; a classificação final de cada
matéria é feita pelo LLM no pipeline de ingestão (uma fonte geral pode gerar notícias de
qualquer uma das 3 categorias — ex.: um post do .NET Blog pode virar "eng_dev_ia" e uma
release da OpenAI pode virar "ia"). Fácil de adicionar/remover.

Convenção de RSS: onde o endpoint de feed já está confirmado/padronizado, a `url` aponta
para o RSS/Atom. Onde o RSS nativo não foi confirmado, a fonte fica como `# TODO` comentado
(confirmar endpoint antes de ativar; se não houver RSS, usar fallback ou remover).

### 1. Notícias de IA (geral) — hint "ia"

Mundo (RSS confirmado/padrão):
- The Verge (AI)           — https://www.theverge.com/rss/index.xml
- MIT Technology Review    — https://www.technologyreview.com/feed/
- Wired                    — https://www.wired.com/feed/rss
- MIT News                 — https://news.mit.edu/rss/feed
- VentureBeat (AI)         — https://venturebeat.com/category/ai/feed/
- TechCrunch (AI)          — https://techcrunch.com/category/artificial-intelligence/feed/
- AI News                  — https://www.artificialintelligence-news.com/feed/
- Ars Technica (AI)        — https://arstechnica.com/ai/feed/
- Analytics Vidhya         — https://www.analyticsvidhya.com/blog/feed/
- Import AI (Jack Clark)   — https://importai.substack.com/feed
- Hacker News              — https://news.ycombinator.com/rss
- Hugging Face Blog        — https://huggingface.co/blog/feed.xml
- OpenAI                   — https://openai.com/news/rss.xml
- Google (AI)              — https://blog.google/technology/ai/rss/

Mundo (# TODO confirmar RSS):
# - AI Magazine            — https://aimagazine.com
# - Analytics Insight      — https://www.analyticsinsight.net
# - AI Weekly (newsletter) — https://aiweekly.co
# - Future Tools           — https://futuretools.io/news
# - The Batch (DeepLearning.AI) — https://www.deeplearning.ai/the-batch/
# - TLDR AI (newsletter)   — https://tldr.tech/ai
# - Anthropic              — https://www.anthropic.com/news
# - Meta AI                — https://ai.meta.com/blog/
# - Microsoft AI           — https://blogs.microsoft.com/ai/

Brasil (RSS confirmado/padrão):
- G1 Tecnologia            — https://g1.globo.com/rss/g1/tecnologia/
- Olhar Digital            — https://olhardigital.com.br/feed/
- Tecnoblog                — https://tecnoblog.net/feed/
- Canaltech                — https://canaltech.com.br/rss/
- Tecmundo                 — https://www.tecmundo.com.br/rss
- Folha Artificial (newsletter) — https://folhaartificial.substack.com/feed

Brasil (# TODO confirmar RSS):
# - AINEWS                 — https://ainews.net.br
# - IA Brasil Notícias     — https://iabrasilnoticias.com.br
# - CNN Brasil (IA)        — https://www.cnnbrasil.com.br/tudo-sobre/inteligencia-artificial/

### 2. Engenharia / Desenvolvimento de Software com IA — hint "eng_dev_ia"

ESCOPO: SOMENTE conteúdo de desenvolvimento de software (código, frameworks,
arquitetura, engenharia com IA, releases de linguagens/SDKs/ferramentas de dev).
NÃO incluir tech geral de consumo nem gerência de projeto.

Mundo (RSS confirmado/padrão):
- InfoQ                    — https://feed.infoq.com/
- The New Stack            — https://thenewstack.io/feed/
- SD Times                 — https://sdtimes.com/feed/
- Developer Tech News      — https://www.developer-tech.com/feed/
- .NET Blog                — https://devblogs.microsoft.com/dotnet/feed/
- GitHub Blog              — https://github.blog/feed/

Mundo (# TODO confirmar RSS):
# - InfoWorld              — https://www.infoworld.com/index.rss
# - GitHub Trending        — https://github.com/trending  (sem RSS oficial; usar serviço alternativo)

Brasil (# TODO confirmar RSS):
# - iMasters               — https://imasters.com.br/feed
# - Alura (blog)           — https://www.alura.com.br/artigos
# - ComputerWeekly Brasil  — https://www.computerweekly.com/br  (usar a seção de desenvolvimento de software)

### 3. Gerência / Gestão de Software com IA — hint "gestao_ia"

ESCOPO: SOMENTE conteúdo de gerência/gestão de projeto de software (PMO, metodologias
ágeis, entrega, liderança de engenharia, PMP/ferramentas de PM com IA).
NÃO incluir notícias de desenvolvimento/código nem tech geral.

Mundo (RSS confirmado/padrão):
- InfoQ (Culture & Methods) — https://feed.infoq.com/culture-methods/

Mundo (# TODO confirmar RSS):
# - The Digital Project Manager — https://thedigitalprojectmanager.com/feed/
# - LeadDev                — https://leaddev.com/rss
# - PMI                    — https://www.pmi.org/  (seção IA: /learning/ai-in-project-management)
# - ProjectManagement.com  — https://www.projectmanagement.com/
# - Toptal (PM blog)       — https://www.toptal.com/project-managers/blog

Brasil (# TODO confirmar RSS):
# - PMI Brasil             — https://pmi.org.br  (avaliar também capítulos regionais do PMI)
# Observação: conteúdo BR dedicado a gerência de projeto de software com IA é escasso;
# PMI Brasil é a fonte mais próxima. Fontes de dev/tech geral NÃO entram nesta categoria.

## Acionamento manual (sem cron)

A busca de notícias é disparada MANUALMENTE pelo usuário, não por agendamento.
- Na home, incluir um botão "Buscar Notícias" que chama `POST /api/ingest` via HTMX.
- Enquanto processa, o botão mostra estado de carregando (ex.: "Buscando..." desabilitado)
  e, ao terminar, exibe um resumo do resultado (ex.: "12 notícias novas, 3 por categoria")
  e recarrega a lista.
- NÃO criar vercel.json com "crons". Sem Vercel Cron.
- A rota `POST /api/ingest` deve ser protegida por sessão/senha simples de admin (não
  deixar pública, para evitar disparos indevidos e gasto de API OpenAI).

## Pipeline de ingestão (rota `POST /api/ingest`)

Protegida por sessão/senha de admin. Passos:
1. Ler os feeds RSS/Atom com `feedparser`.
2. Extrair o texto completo de cada matéria com `trafilatura` (fetch + extração do corpo
   limpo). Se falhar, usar o resumo do próprio feed.
3. Deduplicar por URL canônica (hash sha256 da URL). Pular o que já existe no banco.
4. Manter só itens com published_at nas últimas 24h.
5. Para cada item novo, chamar a OpenAI UMA vez com response_format JSON pedindo:
   { relevante: bool, categoria: "ia"|"eng_dev_ia"|"gestao_ia"|null,
     ig_titulo: str, ig_conteudo: str, hashtags: [str] }
   Regras do prompt:
   - PT-BR.
   - Classificar na categoria correta, aplicando escopo ESTRITO:
     * "eng_dev_ia": SOMENTE desenvolvimento de software (código, linguagens, frameworks,
       SDKs, APIs, arquitetura/engenharia de software, ferramentas de dev, releases de dev,
       coding assistants). NÃO usar para tech geral de consumo nem gerência de projeto.
     * "gestao_ia": SOMENTE gerência de projeto de software (PMO, PMP, ágil/Scrum/Kanban,
       delivery, liderança de engenharia, planejamento/estimativas, e IA aplicada a esses
       processos). NÃO usar para notícia de código nem IA genérica.
     * "ia": notícia sobre IA que não se encaixa ESTRITAMENTE nas duas acima (fallback).
   - Se irrelevante ou fora das 3, relevante=false.
   - ig_titulo: chamada curta e forte (máx ~80 caracteres).
   - ig_conteudo: 3 a 4 frases, REESCRITAS com palavras próprias (NUNCA copiar frases do
     original), tom informativo para público dev/tech.
   - hashtags: 4 a 8.
   - Responder SOMENTE JSON.
6. Persistir os relevantes. Depois marcar como `featured` os ~4 mais recentes/relevantes
   por categoria do dia; o resto fica salvo mas fora do topo.
7. Retornar um JSON com o resumo do que foi processado (para a UI mostrar).
DICA: se a lista de feeds crescer, dividir o processamento internamente para não estourar
o tempo de execução da função na Vercel.

## Modelo de dados (SQLAlchemy + migration SQL)

Tabela `articles`:
- id (uuid pk), source_name, source_url (text unique)  // URL canônica = dedup
- title_original (text)
- category (enum: ia | eng_dev_ia | gestao_ia)
- ig_title (text), ig_content (text), hashtags (text[])
- image_url (text null)         // URL pública do card no Supabase Storage
- published_at (timestamptz), fetched_at (timestamptz)
- day (date)                    // para agrupar na home
- featured (bool default false)
- ig_status (enum: draft | posted, default draft), ig_post_id (text null)
- created_at (timestamptz default now())
Índices: (day), (category), unique(source_url).

## Card de imagem (necessário para o Instagram)

- Módulo que gera um PNG 1080x1080 com Pillow: ig_title sobre fundo com gradiente +
  marca "IANoticias" + badge da categoria.
- Salvar em /tmp e fazer UPLOAD para um bucket público do Supabase Storage;
  gravar a URL pública em `image_url`. (O Instagram exige image_url pública e estável.)

## UI (rota `GET /`)

- Mobile-first, Tailwind, visual limpo de feed de notícias.
- Botão "Buscar Notícias" no topo (dispara POST /api/ingest via HTMX, com estado de loading).
- Notícias AGRUPADAS POR DIA (mais recente primeiro), com cabeçalho da data.
- Dentro do dia, filtro pelas 3 categorias via HTMX (badge colorido por categoria).
- Card: ig_title, ig_content, fonte, categoria, link "Ler matéria completa" (abre
  source_url em nova aba) e botão "Postar no Instagram" com o status (draft/posted).
- Itens `featured` no topo de cada dia/categoria.

## Integração Instagram (rota `POST /api/instagram/publish`)

Body { article_id }. Usa Meta Graph API (Instagram Business/Creator + Página do Facebook):
1) cria container: POST /{IG_USER_ID}/media com image_url (o card) + caption
   (caption = ig_title + "\n\n" + ig_content + "\n\n" + hashtags + "\n\nFonte: " + source_url)
2) publica: POST /{IG_USER_ID}/media_publish com o creation_id
3) grava ig_post_id e seta ig_status="posted".
Tratar erros da API; proteger o endpoint. Deixar TODO comentado sobre o token de longa
duração da Meta.

## Variáveis de ambiente (`.env.example`)

DATABASE_URL (Supabase Postgres), SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
SUPABASE_STORAGE_BUCKET, OPENAI_API_KEY, OPENAI_MODEL,
IG_USER_ID, IG_ACCESS_TOKEN, META_APP_ID, META_APP_SECRET,
ADMIN_PASSWORD, PUBLIC_SITE_URL

## Boas práticas de curadoria (implementar e documentar)

- Sempre creditar a fonte e linkar o original; nunca republicar o texto completo.
- Resumos reescritos com palavras próprias (curtos), nunca cópia condensada.
- Respeitar robots.txt/ToS; comentar isso no extractor.

## Entregáveis

- Projeto FastAPI completo, organizado (app/, templates/, static/, migrations/).
- `app.py` com a instância `app` (entrypoint Vercel) e `requirements.txt`.
- Modelos SQLAlchemy + `migrations/001_init.sql` pronto pro Supabase.
- `app/config/feeds.py` com a lista starter (as fontes da seção "Fontes" acima).
- Rotas: POST /api/ingest, POST /api/instagram/publish, GET / (home).
- `.env.example` completo.
- README em PT-BR: criar projeto Supabase + rodar migration + criar bucket público,
  configurar env, deploy na Vercel, e como usar o botão "Buscar Notícias" para popular
  o portal; criar app Meta e conectar conta IG Business (incluindo o passo do token de
  longa duração).
- Modo mock/seed para rodar a UI localmente sem chamar APIs externas.

Comece pela estrutura de pastas e schema, depois o pipeline (rota /api/ingest), depois a
UI com o botão "Buscar Notícias", depois o card de imagem e por fim a integração com o
Instagram. Explique brevemente cada etapa enquanto constrói.
