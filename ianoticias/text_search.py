"""Parsing e normalização de texto para a busca do portal.

Compartilhado entre o repositório (monta o SQL) e o templating (destaca os
termos encontrados), por isso vive fora das duas camadas.

Sintaxe aceita na caixa de busca:
    agentes openai        -> precisa conter "agentes" E "openai"
    "modelo de raciocinio" -> frase exata (entre aspas)
    -google               -> exclui resultados que contenham "google"
"""
from __future__ import annotations

import re

# Tradução acento -> letra base. Mantém 1:1 entre caracteres (o Postgres usa a
# mesma tabela via translate()), então os índices de um texto "dobrado"
# continuam válidos no texto original — é isso que permite o highlight.
ACCENT_SRC = "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ"
ACCENT_DST = "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"
assert len(ACCENT_SRC) == len(ACCENT_DST)

_FOLD_TABLE = str.maketrans(ACCENT_SRC, ACCENT_DST)

# Um token é: uma frase entre aspas (com `-` opcional na frente) ou uma palavra.
_TOKEN_RE = re.compile(r'-?"[^"]*"|\S+')


def fold(text: str) -> str:
    """Minúsculas e sem acento — mesma normalização aplicada no SQL."""
    return text.translate(_FOLD_TABLE).lower()


def parse_query(raw: str | None) -> tuple[list[str], list[str]]:
    """Quebra a busca em (termos exigidos, termos excluídos).

    Os termos voltam já normalizados por `fold`.
    """
    include: list[str] = []
    exclude: list[str] = []
    for token in _TOKEN_RE.findall(raw or ""):
        negated = token.startswith("-")
        if negated:
            token = token[1:]
        term = token.strip('"').strip().lstrip("#")
        if not term:
            continue
        (exclude if negated else include).append(fold(term))
    return include, exclude


def like_pattern(term: str) -> str:
    """`%termo%` com os curingas do LIKE escapados (escape char = `\`)."""
    escaped = term.replace("\\", "\\\\").replace("%", "\%").replace("_", "\_")
    return f"%{escaped}%"
