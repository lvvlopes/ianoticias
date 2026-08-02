"""Pré-filtro barato de relevância (sem LLM).

Muitos feeds reputados são GENÉRICOS (The Verge, Wired, G1, Ars...) e publicam
muito conteúdo que não é de IA (games, gadgets, cinema, política). Sem um filtro
prévio, esse ruído de alto volume consome o cap por execução e o orçamento da
OpenAI antes de chegar ao conteúdo de IA — e o LLM acaba rejeitando tudo.

Este módulo faz um corte rápido por palavras-chave no título + resumo. É
propositalmente PERMISSIVO: na dúvida, deixa passar (o LLM faz a classificação
estrita depois). O objetivo é só remover o obviamente-fora-de-tema.

Feeds de fontes inerentemente de IA (labs, blogs de ML) podem pular o filtro
via `bypass=True` — tudo que publicam é candidato.
"""
from __future__ import annotations

import re

# Sinais fortes de IA (PT + EN). Usamos regex com bordas para reduzir falso
# positivo. Evitamos o bare "ia" (casa com "dia", "seria", etc.).
_KEYWORDS = [
    r"\bA\.?I\.?\b",                 # AI / A.I.
    r"\bartificial intelligence\b",
    r"intelig[êe]ncia artificial",
    r"\bmachine learning\b",
    r"aprendizado de m[áa]quina",
    r"\bdeep learning\b",
    r"\bLLMs?\b",
    r"large language model",
    r"modelos? de linguagem",
    r"\bGPT\b", r"\bGPT-?\d", r"\bChatGPT\b",
    r"\bgenerative\b", r"generativ[ao]",
    r"\bneural\b", r"rede neural",
    r"\bOpenAI\b", r"\bAnthropic\b", r"\bClaude\b", r"\bGemini\b",
    r"\bLlama\b", r"\bMistral\b", r"\bHugging ?Face\b", r"\bGrok\b",
    r"\bcopilot\b", r"\bcopiloto\b",
    r"\bagentes? de IA\b", r"\bAI agents?\b", r"\bagentic\b",
    r"\btransformer\b", r"\bdiffusion\b", r"\bmidjourney\b", r"\bdall-?e\b",
    r"\bprompt(s|ing)?\b", r"fine-?tun", r"\bRAG\b", r"\bembeddings?\b",
    r"\bMLOps\b", r"\bNLP\b", r"vis[ãa]o computacional", r"computer vision",
    r"\bDeepMind\b", r"\bNVIDIA\b", r"\bAGI\b",
    r"redes? neurais", r"\bquantiza[çc][ãa]o\b",
    r"\bIA\b(?=\s|$|[,.;:!?])",      # "IA" isolado (maiúsculo), com fronteira
]
_PATTERN = re.compile("|".join(_KEYWORDS), re.IGNORECASE)


def looks_relevant(title: str, summary: str = "") -> bool:
    """True se título/resumo contêm sinal de IA. Permissivo por design."""
    haystack = f"{title or ''}\n{summary or ''}"
    return bool(_PATTERN.search(haystack))
