"""Extração do texto principal + imagem de destaque da matéria com trafilatura.

Boas práticas / curadoria:
- Trafilatura respeita normalmente o robots.txt do host quando `fetch_url` é
  usado, mas cabe ao operador verificar os ToS de cada portal antes de expandir
  a lista. Aqui usamos apenas título + resumo reescritos por IA e SEMPRE
  linkamos a fonte original — não republicamos o texto extraído.
- O texto extraído serve APENAS como input do LLM e é descartado; nunca é
  persistido no banco nem exibido.
- A imagem de destaque (og:image) é usada como fundo do card do Instagram e
  como thumb na home, sempre com crédito/linck à fonte original.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import trafilatura

_MAX_CHARS = 6000  # limita input ao LLM (economia de tokens)

# Meta tags de imagem social, em ordem de preferência.
_IMG_META_PATTERNS = [
    r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']',
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
]


@dataclass
class Extracted:
    text: str
    image_url: str | None


def _find_lead_image(html: str, base_url: str) -> str | None:
    """Procura og:image / twitter:image no HTML e resolve URL relativa."""
    for pat in _IMG_META_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            raw = (m.group(1) or "").strip()
            if raw:
                # Resolve caminhos relativos (//cdn..., /img/...).
                if raw.startswith("//"):
                    raw = "https:" + raw
                elif raw.startswith("/"):
                    raw = urljoin(base_url, raw)
                if raw.startswith(("http://", "https://")):
                    return raw
    return None


def _extract_sync(url: str) -> Extracted:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return Extracted("", None)
    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
        favor_precision=True,
    ) or ""
    image = _find_lead_image(downloaded, url)
    return Extracted(text=text[:_MAX_CHARS], image_url=image)


async def extract_article(url: str, fallback_summary: str = "") -> Extracted:
    """Retorna texto (corpo limpo ou resumo do feed) + imagem de destaque."""
    result = await asyncio.to_thread(_extract_sync, url)
    text = result.text if result.text and len(result.text.strip()) >= 200 else (fallback_summary or "").strip()
    return Extracted(text=text, image_url=result.image_url)
