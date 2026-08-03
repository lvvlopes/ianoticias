"""Geração do card 1080x1080 (PNG) para o post do Instagram.

Segue a identidade visual do portal (IANoticias / SINAL-style):
  - Fundo hero (#111017) com radiais coloridos e ruído sutil.
  - Kicker mono no topo (categoria) com traço dourado à esquerda.
  - Título grande em Space Grotesk (fallback Inter / DejaVuSans-Bold).
  - Rodapé com wordmark IANoticias + "sinal" (barras douradas) e URL.
  - Cor de acento por categoria (dourado, roxo, verde).

Fontes esperadas em `static/fonts/` (ver README lá):
  - SpaceGrotesk-Bold.ttf, SpaceGrotesk-Medium.ttf     (título / wordmark)
  - JetBrainsMono-SemiBold.ttf, JetBrainsMono-Medium.ttf (kickers / rodapé)

Se a fonte principal não estiver disponível, cai para Inter e depois para
DejaVuSans — o card continua funcional, só perde a estética afinada.
"""
from __future__ import annotations

import random
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ianoticias.config.settings import settings
from ianoticias.templating import (
    CATEGORY_COLORS,
    CATEGORY_KICKERS,
    CATEGORY_LABELS,
)

CARD_SIZE = (1080, 1080)
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
FONT_DIR = _STATIC_DIR / "fonts"
DEFAULT_BG = _STATIC_DIR / "hero" / "default.jpg"
# Imagem-base fixa do card do Instagram (arte de marca; sem texto sobreposto).
INSTAGRAM_BG = _STATIC_DIR / "hero" / "intagram.jpg"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 IANoticias/1.0"
)

# Paleta (espelha as CSS vars do template).
INK = (17, 16, 23)          # --hero
INK_2 = (27, 26, 36)        # --hero-2
GOLD = (244, 178, 35)       # --gold
GOLD_DEEP = (181, 129, 15)  # --gold-deep
PAPER = (237, 236, 230)     # --hero-text


# ---------------------------------------------------------------------------
# Fontes: pilha ordenada por preferência, cai para PIL default se nada existir.
# ---------------------------------------------------------------------------
DISPLAY_BOLD_CHAIN = (
    "SpaceGrotesk-Bold.ttf",
    "Inter-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)
DISPLAY_MED_CHAIN = (
    "SpaceGrotesk-Medium.ttf",
    "SpaceGrotesk-Bold.ttf",
    "Inter-Medium.ttf",
    "Inter-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)
MONO_SEMI_CHAIN = (
    "JetBrainsMono-SemiBold.ttf",
    "JetBrainsMono-Medium.ttf",
    "DejaVuSansMono-Bold.ttf",
    "DejaVuSansMono.ttf",
)
MONO_REG_CHAIN = (
    "JetBrainsMono-Medium.ttf",
    "JetBrainsMono-Regular.ttf",
    "DejaVuSansMono.ttf",
)


def _system_font_paths(bold: bool) -> list[str]:
    """Fontes do sistema como fallback (Windows/Linux/Mac). Bold vs regular."""
    if bold:
        return [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
    return [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]


def _load_font(chain: tuple[str, ...], size: int):
    # 1) TTFs empacotados em static/fonts (identidade de marca, se presentes).
    for name in chain:
        path = FONT_DIR / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    # 2) Fontes do sistema (Arial/Segoe/DejaVu) — mantém o tamanho correto.
    bold = any(("Bold" in n or "SemiBold" in n) for n in chain)
    for sp in _system_font_paths(bold):
        try:
            return ImageFont.truetype(sp, size=size)
        except OSError:
            continue
    # 3) Default do Pillow, JÁ dimensionado (Pillow >= 10.1 aceita size).
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antigo
        return ImageFont.load_default()


def _hex_rgb(hx: str) -> tuple[int, int, int]:
    hx = hx.lstrip("#")
    return tuple(int(hx[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Composição do fundo
# ---------------------------------------------------------------------------
def _radial_layer(
    size: tuple[int, int],
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    alpha: float,
) -> tuple[Image.Image, Image.Image]:
    """Devolve (overlay, mask) para colar via `img.paste(overlay, mask=mask)`.

    O overlay é chapado na cor. A máscara é um círculo cheio na posição/raio
    dado, borrado (Gaussian) para virar um radial gradient suave.
    """
    overlay = Image.new("RGB", size, color)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    a = max(0, min(255, int(255 * alpha)))
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=a)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=radius * 0.55))
    return overlay, mask


def _build_hero_bg(category: str) -> Image.Image:
    """Fundo hero: base escura + 3 radiais coloridos + ruído + vinheta."""
    W, H = CARD_SIZE

    # Base: gradiente diagonal sutil entre INK_2 (topo-esq) e INK (baixo-dir).
    base = Image.new("RGB", CARD_SIZE, INK)
    grad = Image.new("RGB", CARD_SIZE, INK_2)
    diag = Image.new("L", CARD_SIZE, 0)
    d = ImageDraw.Draw(diag)
    for i in range(0, W + H, 8):
        v = int(255 * (1 - i / (W + H)))
        d.line([(i, 0), (0, i)], fill=v)
    diag = diag.filter(ImageFilter.GaussianBlur(radius=60))
    base.paste(grad, mask=diag)

    # Camadas radiais. A cor da categoria puxa o radial dominante.
    accent = _hex_rgb(CATEGORY_COLORS.get(category, "#F4B223"))
    layers = [
        # (center_ratio, radius_ratio, color, alpha)
        ((0.12, 0.08), 0.95, GOLD, 0.28),
        ((0.92, 0.20), 0.85, (90, 68, 220), 0.30),   # roxo
        ((0.78, 1.05), 1.10, (30, 158, 104), 0.20),  # verde
        # radial da categoria, forte e centralizado
        ((0.55, 0.35), 0.80, accent, 0.32),
    ]
    for (cxr, cyr), rr, color, alpha in layers:
        ov, msk = _radial_layer(
            CARD_SIZE,
            (int(W * cxr), int(H * cyr)),
            int(min(W, H) * rr),
            color,
            alpha,
        )
        base.paste(ov, mask=msk)

    # Grid de linhas horizontais bem sutis no topo.
    grid = Image.new("L", CARD_SIZE, 0)
    dg = ImageDraw.Draw(grid)
    for y in range(0, H, 44):
        dg.line([(0, y), (W, y)], fill=22)
    # Máscara que desvanece de cima para baixo
    fade = Image.new("L", CARD_SIZE, 0)
    df = ImageDraw.Draw(fade)
    for y in range(H):
        df.line([(0, y), (W, y)], fill=max(0, 180 - int(180 * y / (H * 0.6))))
    grid = Image.composite(grid, Image.new("L", CARD_SIZE, 0), fade)
    grid_rgb = Image.new("RGB", CARD_SIZE, PAPER)
    base.paste(grid_rgb, mask=grid)

    # Ruído fino (~4% opacidade), gerado num tile 6x6 e escalonado por NEAREST.
    tile = 6
    rand = random.Random(hash(category) & 0xFFFF)
    noise_small = Image.new("L", (tile, tile))
    noise_small.putdata([rand.randint(0, 255) for _ in range(tile * tile)])
    noise = noise_small.resize(CARD_SIZE, Image.NEAREST)
    # Multiplica de leve a base pelo canal de ruído
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    base = Image.blend(base, noise_rgb, 0.05)

    # Vinheta sutil nos cantos: escurece bordas
    vignette = Image.new("L", CARD_SIZE, 0)
    dv = ImageDraw.Draw(vignette)
    dv.ellipse((-W * 0.15, -H * 0.15, W * 1.15, H * 1.15), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=120))
    black = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    inverted = Image.eval(vignette, lambda v: 255 - v)
    base.paste(black, mask=Image.eval(inverted, lambda v: int(v * 0.35)))

    return base


# ---------------------------------------------------------------------------
# Elementos tipográficos
# ---------------------------------------------------------------------------
def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        w = draw.textlength(trial, font=font)
        if w <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _fit_title(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int
) -> tuple[list[str], ImageFont.ImageFont, int]:
    """Escolhe o maior tamanho de fonte que caiba no bounding box do título."""
    for size in (96, 88, 80, 72, 64, 58, 52):
        font = _load_font(DISPLAY_BOLD_CHAIN, size)
        lines = _wrap_lines(draw, text, font, max_width)
        line_h = int(size * 1.08)
        if len(lines) * line_h <= max_height:
            return lines, font, line_h
    # Último recurso: aceita ultrapassar
    font = _load_font(DISPLAY_BOLD_CHAIN, 48)
    return _wrap_lines(draw, text, font, max_width), font, int(48 * 1.08)


def _draw_kicker(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    """Traço dourado + eyebrow mono na cor gold, tudo caixa alta."""
    font = _load_font(MONO_SEMI_CHAIN, 24)
    dash_w, dash_h = 60, 4
    draw.rectangle((x, y + 12, x + dash_w, y + 12 + dash_h), fill=GOLD)
    draw.text(
        (x + dash_w + 20, y),
        text.upper(),
        fill=GOLD,
        font=font,
    )


def _draw_signal(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """Sinal estático (7 barras) na cor gold-deep, altura variando."""
    heights = [10, 20, 32, 44, 32, 22, 14]
    bar_w = 5
    gap = 4
    base_y = y + 44
    for i, h in enumerate(heights):
        bx = x + i * (bar_w + gap)
        draw.rectangle((bx, base_y - h, bx + bar_w, base_y), fill=GOLD_DEEP)


def _short_source(url: str) -> str:
    """Extrai domínio limpo (sem www.) de uma URL para mostrar no card."""
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Fundo: imagem da fonte (og:image) → default.jpg → gradiente
# ---------------------------------------------------------------------------
def _download_image(url: str, timeout: float = 8.0) -> Image.Image | None:
    try:
        r = httpx.get(
            url, timeout=timeout, follow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "image/*,*/*"},
        )
        r.raise_for_status()
        im = Image.open(BytesIO(r.content))
        im.load()
        return im.convert("RGB")
    except Exception:  # noqa: BLE001 — imagem é best-effort
        return None


def _cover(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Recorte 'cover' centralizado, levemente puxado para o topo."""
    return ImageOps.fit(im, size, method=Image.LANCZOS, centering=(0.5, 0.4))


def _load_background(category: str, source_image_url: str | None) -> Image.Image:
    im = _download_image(source_image_url) if source_image_url else None
    if im is None and DEFAULT_BG.exists():
        try:
            im = Image.open(DEFAULT_BG).convert("RGB")
        except Exception:  # noqa: BLE001
            im = None
    if im is None:
        return _build_hero_bg(category)  # gradiente (último recurso)
    return _cover(im, CARD_SIZE)


def _scrim(size: tuple[int, int]) -> Image.Image:
    """Gradiente escuro de baixo para cima (legibilidade do texto sobre a foto)."""
    w, h = size
    col = Image.new("L", (1, h))
    px = col.load()
    for y in range(h):
        t = max(0.0, (y - h * 0.26) / (h * 0.74))  # escurece a partir de ~26%
        px[0, y] = int(min(1.0, t) * 242)
    scrim = Image.new("RGBA", size, (8, 8, 12, 255))
    scrim.putalpha(col.resize(size))
    return scrim


def _wrap_to_lines(draw, text, font, max_width, max_lines) -> list[str]:
    words = (text or "").split()
    lines: list[str] = []
    cur: list[str] = []
    truncated = False
    for word in words:
        trial = " ".join(cur + [word])
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur.append(word)
        else:
            lines.append(" ".join(cur))
            cur = [word]
            if len(lines) == max_lines:
                truncated = True
                break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    elif cur:
        truncated = True
    if truncated and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + "…"
    return lines


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------
# Cor de acento da arte (teal do template intagram.jpg) e rótulos "NOTÍCIAS X".
TEAL = (43, 224, 196)
TITLE_WHITE = (247, 248, 246)
SOURCE_GRAY = (196, 205, 204)
CATEGORY_POST_LABEL = {
    "ia": "NOTÍCIAS IA",
    "eng_dev_ia": "NOTÍCIAS DEV",
    "gestao_ia": "NOTÍCIAS PROJETO DE SOFTWARE",
}


def _load_instagram_bg(category: str) -> Image.Image:
    """Fundo do card: imagem fixa intagram.jpg → default.jpg → fundo sólido rápido.

    O fallback é intencionalmente BARATO (Image.new) porque `_build_hero_bg` faz
    filtros/blurs pesados em pixel e pode explodir o tempo de função na Vercel.
    """
    import logging
    log = logging.getLogger(__name__)
    for path in (INSTAGRAM_BG, DEFAULT_BG):
        try:
            if path.exists():
                return _cover(Image.open(path).convert("RGB"), CARD_SIZE)
            log.warning("image_card: fundo ausente em %s", path)
        except Exception as exc:  # noqa: BLE001
            log.warning("image_card: falha ao abrir %s: %s", path, exc)
    # Último recurso: fundo sólido na cor de acento da categoria (barato).
    log.warning("image_card: usando fundo sólido de fallback para categoria %s", category)
    return Image.new("RGB", CARD_SIZE, _hex_rgb(CATEGORY_COLORS.get(category, "#111017")))


def _text_scrim(size: tuple[int, int]) -> Image.Image:
    """Escurece a coluna da esquerda (onde vai o texto), desvanecendo à direita.
    Garante legibilidade do título sobre qualquer imagem de fundo."""
    w, h = size
    row = Image.new("L", (w, 1))
    px = row.load()
    for x in range(w):
        t = 1.0 - max(0.0, (x - w * 0.10) / (w * 0.62))  # forte à esq, some ~72%
        px[x, 0] = int(max(0.0, min(1.0, t)) * 200)
    scrim = Image.new("RGBA", size, (6, 10, 12, 255))
    scrim.putalpha(row.resize(size))
    return scrim


def _draw_tracked(draw, pos, text, font, fill, tracking: int = 0) -> int:
    """Desenha texto com espaçamento entre letras (letter-spacing). Retorna largura."""
    x, y = pos
    start = x
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += int(draw.textlength(ch, font=font)) + tracking
    return x - start - tracking if text else 0


def _tracked_width(draw, text, font, tracking: int = 0) -> int:
    w = 0
    for ch in text:
        w += int(draw.textlength(ch, font=font)) + tracking
    return max(0, w - tracking)


def build_card_jpeg(
    *,
    title: str = "",
    category: str,
    source_url: str = "",
    source_name: str = "",
    ig_content: str = "",
    source_image_url: str | None = None,
) -> bytes:
    """Card 1080x1080 sobre a arte fixa intagram.jpg (topo "IA EM FOCO" já embutido).

    Sobrepõe: pílula da categoria (NOTÍCIAS IA/DEV/PROJETO DE SOFTWARE), traço,
    título da notícia (branco, bold) e a fonte no rodapé.

    JPEG (não PNG): a API de publicação do Instagram só aceita JPEG.
    """
    base = _load_instagram_bg(category).convert("RGBA")
    base = Image.alpha_composite(base, _text_scrim(CARD_SIZE))
    img = base.convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    margin = 56
    title_max_w = 620  # largura da coluna de texto (deixa a arte respirar à direita)

    # --- Pílula da categoria (contorno) ---------------------------------------
    pill_font = _load_font(DISPLAY_MED_CHAIN, 27)
    label = CATEGORY_POST_LABEL.get(category, CATEGORY_LABELS.get(category, category).upper())
    track = 3
    tw = _tracked_width(draw, label, pill_font, track)
    tb = draw.textbbox((0, 0), "M", font=pill_font)
    th = tb[3] - tb[1]
    ppx, ppy = 30, 17
    pill_y = 348
    px1, py1 = margin, pill_y
    px2, py2 = px1 + tw + 2 * ppx, py1 + th + 2 * ppy
    radius = (py2 - py1) // 2
    draw.rounded_rectangle((px1, py1, px2, py2), radius=radius, outline=TEAL, width=2)
    _draw_tracked(draw, (px1 + ppx, py1 + ppy - tb[1]), label, pill_font, TEAL, track)

    # --- Traço de acento -------------------------------------------------------
    accent_y = py2 + 30
    draw.rounded_rectangle((margin, accent_y, margin + 92, accent_y + 6), radius=3, fill=TEAL)

    # --- Título (bold, branco, com sombra p/ legibilidade) ---------------------
    title_font = _load_font(DISPLAY_BOLD_CHAIN, 60)
    lines = _wrap_to_lines(draw, title, title_font, title_max_w, 4)
    line_h = 74
    y = accent_y + 34
    for ln in lines:
        draw.text((margin + 2, y + 3), ln, font=title_font, fill=(0, 0, 0, 150))  # sombra
        draw.text((margin, y), ln, font=title_font, fill=TITLE_WHITE)
        y += line_h

    # --- Fonte no rodapé (nome do veículo; cai para o domínio) -----------------
    src = (source_name or "").strip() or (_short_source(source_url) if source_url else "")
    if src:
        foot_font = _load_font(DISPLAY_MED_CHAIN, 24)
        foot_y = CARD_SIZE[1] - 96
        draw.rounded_rectangle((margin, foot_y + 14, margin + 40, foot_y + 18), radius=2, fill=TEAL)
        _draw_tracked(
            draw, (margin + 60, foot_y), f"FONTE · {src.upper()}", foot_font, SOURCE_GRAY, 2
        )

    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True, progressive=True)
    return buf.getvalue()
