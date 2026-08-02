"""Objeto de templates Jinja2 compartilhado entre os routers.

Também expõe os mapeamentos de identidade visual por categoria (cores, kickers,
gradientes de thumb) que são reaproveitados pela UI e pelo card do Instagram.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

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

templates.env.globals.update(
    CATEGORY_LABELS=CATEGORY_LABELS,
    CATEGORY_KICKERS=CATEGORY_KICKERS,
    CATEGORY_COLORS=CATEGORY_COLORS,
    CATEGORY_THUMB_CLASS=CATEGORY_THUMB_CLASS,
    CATEGORIES_ORDERED=CATEGORIES_ORDERED,
    CATEGORY_SECTION_TITLES=CATEGORY_SECTION_TITLES,
    now=datetime.now,
)
