"""Objeto de templates Jinja2 compartilhado entre os routers.

Também expõe os mapeamentos de identidade visual por categoria (cores, kickers,
gradientes de thumb) que são reaproveitados pela UI e pelo card do Instagram.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from ianoticias.text_search import fold

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Rótulo curto que aparece no badge do card.
CATEGORY_LABELS = {
    "ia": "IA",
    "eng_dev_ia": "Eng · Dev com IA",
    "gestao_ia": "Gestão com IA",
}

# Kicker acima do título (versão longa, para o hero e para o card do Instagram).
CATEGORY_KICKERS = {
    "ia": "Pesquisa · IA",
    "eng_dev_ia": "Engenharia · Software com IA",
    "gestao_ia": "Gestão · Software com IA",
}

# Cor de acento (hex) — usada no card do Instagram e no ponto do filtro.
CATEGORY_COLORS = {
    "ia": "#F4B223",          # dourado (marca)
    "eng_dev_ia": "#5A44DC",  # roxo
    "gestao_ia": "#1E9E68",   # verde
}

# Classe do gradiente da thumb do card na home (definida no CSS do base).
CATEGORY_THUMB_CLASS = {
    "ia": "g-ia",
    "eng_dev_ia": "g-eng",
    "gestao_ia": "g-gestao",
}

# Categorias na ordem editorial e cabeçalhos das seções.
CATEGORIES_ORDERED = ("ia", "eng_dev_ia", "gestao_ia")
CATEGORY_SECTION_TITLES = {
    "ia": "Inteligência Artificial",
    "eng_dev_ia": "Engenharia de Software com IA",
    "gestao_ia": "Gestão de Software com IA",
}


def highlight(text: str | None, terms: list[str] | None) -> Markup:
    """Envolve em <mark> os trechos que casam com os termos buscados.

    Compara sobre a versão "dobrada" (sem acento, minúscula) do texto, que tem
    o mesmo comprimento do original — por isso os índices encontrados valem
    para recortar o texto que o leitor vê, com acento e caixa preservados.
    """
    if not text or not terms:
        return escape(text or "")

    folded = fold(text)
    if len(folded) != len(text):  # normalização mudou o tamanho: não arrisca
        return escape(text)

    # 1) coleta as faixas casadas
    spans: list[tuple[int, int]] = []
    for term in terms:
        start = folded.find(term)
        while start != -1:
            spans.append((start, start + len(term)))
            start = folded.find(term, start + 1)
    if not spans:
        return escape(text)

    # 2) funde faixas sobrepostas (termos podem se cruzar)
    spans.sort()
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    # 3) remonta o texto escapando tudo que não é a tag <mark>
    out: list[str] = []
    cursor = 0
    for start, end in merged:
        out.append(str(escape(text[cursor:start])))
        out.append(f"<mark>{escape(text[start:end])}</mark>")
        cursor = end
    out.append(str(escape(text[cursor:])))
    return Markup("".join(out))


templates.env.filters["highlight"] = highlight

templates.env.globals.update(
    CATEGORY_LABELS=CATEGORY_LABELS,
    CATEGORY_KICKERS=CATEGORY_KICKERS,
    CATEGORY_COLORS=CATEGORY_COLORS,
    CATEGORY_THUMB_CLASS=CATEGORY_THUMB_CLASS,
    CATEGORIES_ORDERED=CATEGORIES_ORDERED,
    CATEGORY_SECTION_TITLES=CATEGORY_SECTION_TITLES,
    now=datetime.now,
)
