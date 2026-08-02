# Fontes do card do Instagram

O gerador (`ianoticias/services/image_card.py`) usa a mesma tipografia do portal:

| Uso                 | Fonte preferida            | Fallback 1        | Fallback 2         |
| ------------------- | -------------------------- | ----------------- | ------------------ |
| Título (grande)     | `SpaceGrotesk-Bold.ttf`    | `Inter-Bold.ttf`  | `DejaVuSans-Bold.ttf` |
| Wordmark IANoticias | `SpaceGrotesk-Bold.ttf`    | `Inter-Bold.ttf`  | `DejaVuSans-Bold.ttf` |
| Kicker / badge      | `JetBrainsMono-SemiBold.ttf` | `DejaVuSansMono-Bold.ttf` | `DejaVuSansMono.ttf` |
| Rodapé / tagline    | `JetBrainsMono-Medium.ttf` ou `JetBrainsMono-Regular.ttf` | `DejaVuSansMono.ttf` | — |

Se nada for encontrado, o código cai para `ImageFont.load_default()`
(bitmap pequeno, feio, mas não quebra).

## Como preencher (rápido)

Baixe as fontes com licença livre (SIL Open Font License) e coloque os TTF
neste diretório com os nomes acima:

- **Space Grotesk** — <https://fonts.google.com/specimen/Space+Grotesk>
  Baixe o zip, extraia `SpaceGrotesk-Bold.ttf` e `SpaceGrotesk-Medium.ttf`.
- **JetBrains Mono** — <https://fonts.google.com/specimen/JetBrains+Mono>
  Extraia `JetBrainsMono-SemiBold.ttf` e `JetBrainsMono-Medium.ttf`.
- **Inter** (fallback opcional) — <https://rsms.me/inter/>

### Alternativa mínima (sem baixar nada)

Se você quer testar já e não pode baixar fontes, use a DejaVu que costuma
vir instalada no sistema. Copie os arquivos do sistema para cá com estes nomes:

- `DejaVuSans-Bold.ttf`
- `DejaVuSansMono-Bold.ttf`
- `DejaVuSansMono.ttf`

**Não commite fontes proprietárias** (Arial, Segoe UI, SF Pro, etc.).
