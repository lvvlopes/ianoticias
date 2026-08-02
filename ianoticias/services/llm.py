"""Chamada única ao OpenAI por matéria, com structured output (JSON).

Retorno esperado do modelo:
    {
        "relevante": bool,
        "categoria": "ia" | "eng_dev_ia" | "gestao_ia" | null,
        "ig_titulo": str,
        "ig_conteudo": str,
        "hashtags": list[str]
    }

Se `settings.mock_llm` estiver ligado, gera um resumo determinístico offline —
útil para desenvolver a UI/pipeline sem gastar tokens.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from ianoticias.config.settings import settings

Categoria = Literal["ia", "eng_dev_ia", "gestao_ia"]


@dataclass
class LLMResult:
    relevante: bool
    categoria: Categoria | None
    ig_titulo: str
    ig_conteudo: str
    hashtags: list[str]


DEFAULT_SYSTEM_PROMPT = (
    "Você é um editor de um portal brasileiro de notícias sobre Inteligência "
    "Artificial. Sua tarefa é ler uma matéria, classificá-la aplicando REGRAS "
    "ESTRITAS de escopo e produzir um post curto de Instagram em português do "
    "Brasil. Responda SOMENTE com JSON válido, sem qualquer texto fora do JSON."
)

DEFAULT_USER_TEMPLATE = """\
Analise a matéria abaixo e devolva JSON com os campos:

- relevante: bool.
    true  → a matéria trata de IA (pesquisa, modelos, mercado, produtos,
            política/regulação, uso em qualquer setor, desenvolvimento de
            software com IA, ou gerência de projeto de software com IA).
    false → não trata de IA, é irrelevante, ou não se encaixa em nenhuma das
            3 categorias abaixo.

- categoria: escolha UMA das três, aplicando escopo ESTRITO:

    "eng_dev_ia" → SOMENTE quando o foco central for DESENVOLVIMENTO DE
    SOFTWARE: código, linguagens de programação, frameworks, SDKs, APIs,
    bibliotecas, arquitetura/engenharia de software, ferramentas de dev,
    releases de produtos para desenvolvedores, práticas de programação e
    uso de IA no ato de programar (coding assistants, geração de código).
    NÃO usar para: tech geral de consumo (gadgets, smartphones, wearables),
    notícia genérica de IA (novo modelo, corrida de mercado, regulação),
    nem gerência de projeto.

    "gestao_ia" → SOMENTE quando o foco central for GERÊNCIA/GESTÃO DE
    PROJETO DE SOFTWARE: gestão de projetos e produtos de software, PMO,
    PMP, metodologias ágeis (Scrum/Kanban), entrega e delivery, liderança
    de engenharia, estimativas/planejamento, e uso de IA aplicado a esses
    processos de gestão.
    NÃO usar para: notícia de código/desenvolvimento, nem notícia genérica
    de IA.

    "ia" → notícia sobre IA que não se encaixa ESTRITAMENTE em "eng_dev_ia"
    nem em "gestao_ia". É a categoria guarda-chuva e o FALLBACK padrão.
    Em caso de dúvida entre "ia" e uma das outras duas, escolha "ia".

    null → apenas quando relevante=false.

- ig_titulo: chamada curta e forte em PT-BR, máx. ~80 caracteres.

- ig_conteudo: DOIS parágrafos em PT-BR, separados por uma linha em branco
  (use "\\n\\n" entre eles). O leitor deve entender a notícia POR COMPLETO
  sem precisar abrir o link original.
  * 1º parágrafo (contexto e fatos): o que aconteceu, quem está envolvido e
    os dados concretos da matéria (números, nomes, declarações). 3 a 4 frases.
  * 2º parágrafo (por que importa): o significado, as implicações e o que
    muda na prática para o público dev/tech. 2 a 3 frases.
  REESCREVA tudo com palavras próprias — NUNCA copie frases do original.
  Tom informativo e jornalístico.

- hashtags: 4 a 8 hashtags relevantes em português (ou termos técnicos em
  inglês), sem o símbolo #.

Categoria PROVÁVEL da fonte (apenas dica — você decide, aplicando as regras
estritas acima): {hint}

TÍTULO ORIGINAL: {title}
FONTE: {source_name} ({source_url})

TEXTO EXTRAÍDO:
{body}
"""

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _slugify_hashtag_seed(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", text)
    return slug[:20] or "iaNoticias"


def _mock_result(title: str, hint: str | None) -> LLMResult:
    categoria: Categoria = (hint or "ia")  # type: ignore[assignment]
    return LLMResult(
        relevante=True,
        categoria=categoria,
        ig_titulo=(title[:75] + "…") if len(title) > 78 else title,
        ig_conteudo=(
            "Resumo mock gerado localmente para desenvolvimento da UI. Nenhuma "
            "chamada ao LLM foi feita; os dados são fictícios apenas para testar "
            "o layout. Ligue MOCK_LLM=0 e configure a OPENAI_API_KEY para gerar "
            "resumos reais.\n\n"
            "Com a OpenAI ativa, este campo vira dois parágrafos: o primeiro com "
            "o contexto e os fatos da matéria, e o segundo explicando por que "
            "aquilo importa para quem trabalha com tecnologia."
        ),
        hashtags=["IA", "Tecnologia", "Noticias", _slugify_hashtag_seed(title)],
    )


def _coerce_categoria(raw) -> Categoria | None:
    if raw in ("ia", "eng_dev_ia", "gestao_ia"):
        return raw
    return None


def _render_user_prompt(template: str, **kwargs) -> str:
    """Formata o template do usuário tolerando chaves ausentes/extras.

    O texto é editável pelo admin; se ele apagar um placeholder ou digitar
    `{algo}` que não conhecemos, não queremos quebrar a ingestão inteira.
    """
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # Fallback: concatena o contexto no fim do template cru.
        contexto = (
            f"\n\nTÍTULO ORIGINAL: {kwargs.get('title', '')}\n"
            f"FONTE: {kwargs.get('source_name', '')} ({kwargs.get('source_url', '')})\n"
            f"CATEGORIA PROVÁVEL: {kwargs.get('hint', 'nenhuma')}\n\n"
            f"TEXTO EXTRAÍDO:\n{kwargs.get('body', '')}"
        )
        return template + contexto


async def summarize_for_instagram(
    *,
    title: str,
    source_name: str,
    source_url: str,
    body: str,
    hint: str | None = None,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> LLMResult:
    """Chama a OpenAI (ou mock) e devolve o LLMResult validado.

    `system_prompt` e `user_template` permitem sobrescrever os defaults com os
    textos configurados na tela /admin. Se None, usa os defaults do código.
    """
    if settings.mock_llm or not settings.openai_api_key:
        # Simula latência mínima para não mudar o comportamento assíncrono.
        await asyncio.sleep(0)
        return _mock_result(title, hint)

    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    usr_template = user_template or DEFAULT_USER_TEMPLATE

    client = _get_client()
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": _render_user_prompt(
                    usr_template,
                    hint=hint or "nenhuma",
                    title=title,
                    source_name=source_name,
                    source_url=source_url,
                    body=body or "(sem texto extraído — use o título como referência)",
                ),
            },
        ],
        temperature=0.4,
    )

    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Resposta corrompida — trata como irrelevante para não bagunçar o feed.
        return LLMResult(
            relevante=False, categoria=None, ig_titulo="", ig_conteudo="", hashtags=[]
        )

    hashtags = data.get("hashtags") or []
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = [str(h).lstrip("#").strip() for h in hashtags if str(h).strip()][:8]

    return LLMResult(
        relevante=bool(data.get("relevante")),
        categoria=_coerce_categoria(data.get("categoria")),
        ig_titulo=str(data.get("ig_titulo") or "").strip()[:120],
        ig_conteudo=str(data.get("ig_conteudo") or "").strip(),
        hashtags=hashtags,
    )
