"""Lista curada de feeds RSS/Atom de portais reputados.

Estrutura de cada feed:

    Feed(name, url, region: "br" | "world", hint: "ia" | "eng_dev_ia" | "gestao_ia")

O `hint` é apenas a categoria PROVÁVEL da fonte — sugestão para o LLM. A
classificação final de cada matéria é feita pelo modelo no pipeline de
ingestão, com as regras estritas em `ianoticias/services/llm.py`. Assim,
uma fonte marcada como "ia" pode gerar notícia "eng_dev_ia" (ex.: um post
do OpenAI Blog sobre um SDK), e vice-versa.

Convenção de RSS:
- Onde o endpoint está confirmado, `Feed(...)` fica ativo.
- Onde o RSS nativo NÃO foi confirmado (ou o site não tem RSS aberto), a
  fonte fica como `# TODO:` comentado — confirmar antes de ativar.

Para desativar temporariamente um feed, comente a linha.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Region = Literal["br", "world"]
Hint = Literal["ia", "eng_dev_ia", "gestao_ia"]


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    region: Region
    hint: Hint


FEEDS: list[Feed] = [
    # ==========================================================================
    # 1) NOTÍCIAS DE IA (guarda-chuva — hint "ia")
    # ==========================================================================

    # ------------------------- Mundo (RSS confirmado) --------------------------
    Feed("The Verge (AI)",        "https://www.theverge.com/rss/index.xml",                    "world", "ia"),
    Feed("MIT Technology Review", "https://www.technologyreview.com/feed/",                    "world", "ia"),
    Feed("Wired",                 "https://www.wired.com/feed/rss",                            "world", "ia"),
    Feed("MIT News",              "https://news.mit.edu/rss/feed",                             "world", "ia"),
    Feed("VentureBeat (AI)",      "https://venturebeat.com/category/ai/feed/",                 "world", "ia"),
    Feed("TechCrunch (AI)",       "https://techcrunch.com/category/artificial-intelligence/feed/", "world", "ia"),
    Feed("AI News",               "https://www.artificialintelligence-news.com/feed/",         "world", "ia"),
    Feed("Ars Technica (AI)",     "https://arstechnica.com/ai/feed/",                          "world", "ia"),
    Feed("Analytics Vidhya",      "https://www.analyticsvidhya.com/blog/feed/",                "world", "ia"),
    Feed("Import AI",             "https://importai.substack.com/feed",                        "world", "ia"),
    Feed("Hacker News",           "https://news.ycombinator.com/rss",                          "world", "ia"),
    Feed("Hugging Face Blog",     "https://huggingface.co/blog/feed.xml",                      "world", "ia"),
    Feed("OpenAI",                "https://openai.com/news/rss.xml",                           "world", "ia"),
    Feed("Google (AI)",           "https://blog.google/technology/ai/rss/",                    "world", "ia"),

    # ---------------------- Mundo (# TODO confirmar RSS) -----------------------
    # TODO: AI Magazine                 — https://aimagazine.com
    # TODO: Analytics Insight           — https://www.analyticsinsight.net
    # TODO: AI Weekly (newsletter)      — https://aiweekly.co
    # TODO: Future Tools                — https://futuretools.io/news
    # TODO: The Batch (DeepLearning.AI) — https://www.deeplearning.ai/the-batch/
    # TODO: TLDR AI (newsletter)        — https://tldr.tech/ai
    # TODO: Anthropic                   — https://www.anthropic.com/news
    # TODO: Meta AI                     — https://ai.meta.com/blog/
    # TODO: Microsoft AI                — https://blogs.microsoft.com/ai/

    # ------------------------- Brasil (RSS confirmado) -------------------------
    Feed("G1 Tecnologia",     "https://g1.globo.com/rss/g1/tecnologia/",       "br", "ia"),
    Feed("Olhar Digital",     "https://olhardigital.com.br/feed/",             "br", "ia"),
    Feed("Tecnoblog",         "https://tecnoblog.net/feed/",                   "br", "ia"),
    Feed("Canaltech",         "https://canaltech.com.br/rss/",                 "br", "ia"),
    Feed("Tecmundo",          "https://www.tecmundo.com.br/rss",               "br", "ia"),
    Feed("Folha Artificial",  "https://folhaartificial.substack.com/feed",     "br", "ia"),

    # ---------------------- Brasil (# TODO confirmar RSS) ----------------------
    # TODO: AINEWS               — https://ainews.net.br
    # TODO: IA Brasil Notícias   — https://iabrasilnoticias.com.br
    # TODO: CNN Brasil (IA)      — https://www.cnnbrasil.com.br/tudo-sobre/inteligencia-artificial/

    # ==========================================================================
    # 2) ENGENHARIA / DEV DE SOFTWARE COM IA (hint "eng_dev_ia")
    # Escopo estrito: SOMENTE código, frameworks, SDKs, arquitetura, dev tools.
    # ==========================================================================

    # ------------------------- Mundo (RSS confirmado) --------------------------
    Feed("InfoQ",                "https://feed.infoq.com/",                    "world", "eng_dev_ia"),
    Feed("The New Stack",        "https://thenewstack.io/feed/",               "world", "eng_dev_ia"),
    Feed("SD Times",             "https://sdtimes.com/feed/",                  "world", "eng_dev_ia"),
    Feed("Developer Tech News",  "https://www.developer-tech.com/feed/",       "world", "eng_dev_ia"),
    Feed(".NET Blog",            "https://devblogs.microsoft.com/dotnet/feed/", "world", "eng_dev_ia"),
    Feed("GitHub Blog",          "https://github.blog/feed/",                  "world", "eng_dev_ia"),

    # ---------------------- Mundo (# TODO confirmar RSS) -----------------------
    # TODO: InfoWorld       — https://www.infoworld.com/index.rss  (RSS legado, validar)
    # TODO: GitHub Trending — https://github.com/trending           (sem RSS oficial)

    # ---------------------- Brasil (# TODO confirmar RSS) ----------------------
    # TODO: iMasters              — https://imasters.com.br/feed
    # TODO: Alura (blog)          — https://www.alura.com.br/artigos
    # TODO: ComputerWeekly Brasil — https://www.computerweekly.com/br
    #        (usar a seção de desenvolvimento de software)

    # ==========================================================================
    # 3) GERÊNCIA / GESTÃO DE PROJETO DE SOFTWARE COM IA (hint "gestao_ia")
    # Escopo estrito: SOMENTE PMO, ágil, delivery, liderança de engenharia,
    # gestão de projeto/produto de software.
    # ==========================================================================

    # ------------------------- Mundo (RSS confirmado) --------------------------
    Feed("InfoQ — Culture & Methods", "https://feed.infoq.com/culture-methods/", "world", "gestao_ia"),

    # ---------------------- Mundo (# TODO confirmar RSS) -----------------------
    # TODO: The Digital Project Manager — https://thedigitalprojectmanager.com/feed/
    # TODO: LeadDev                     — https://leaddev.com/rss
    # TODO: PMI                         — https://www.pmi.org/learning/ai-in-project-management
    # TODO: ProjectManagement.com       — https://www.projectmanagement.com/
    # TODO: Toptal (PM blog)            — https://www.toptal.com/project-managers/blog

    # ---------------------- Brasil (# TODO confirmar RSS) ----------------------
    # TODO: PMI Brasil — https://pmi.org.br  (avaliar também capítulos regionais)
    # Nota: conteúdo BR dedicado a gerência de projeto de software com IA é escasso.
    # Fontes de dev/tech geral NÃO entram nesta categoria.
]
