# Imagens das thumbs dos cards

Cada card de notícia tem uma **thumb** no topo com uma imagem-base tingida
pela cor da editoria (dourado para IA, roxo para Eng/Dev, verde para
Gestão). O CSS está em `templates/base.html`, seções `.thumb` e `.g-*`.

## Como colocar sua imagem

**Modo simples (uma imagem para todas as categorias)** — salve como:

    static/hero/default.jpg

Recomendado: 1600x900px ou maior, JPG comprimido (< 300 KB). O CSS aplica
um overlay escuro + blend com a cor da editoria, então imagens com bom
contraste e áreas de foco central funcionam melhor. Fotos abstratas tech,
wireframes, "cérebro digital", circuitos etc. combinam com o estilo.

**Modo avançado (imagem diferente por editoria)** — para variar por
categoria, salve com estes nomes:

    static/hero/ia.jpg
    static/hero/eng_dev_ia.jpg
    static/hero/gestao_ia.jpg

O CSS tenta a específica primeiro e cai para `default.jpg` se não achar.

## Formatos aceitos

Qualquer formato que o browser aceite (JPG, PNG, WebP). Se usar WebP,
troque a extensão nos arquivos e no CSS.

## Comportamento

- **Se o article já tem um card do Instagram gerado** (`image_url` no
  banco): a thumb mostra a arte do IG (que já tem título grande) — a
  imagem-base é escondida nesse caso.
- **Se não tem card ainda**: mostra a imagem-base com tinting da editoria.
- **Se você não colocar nenhum arquivo**: o CSS cai no gradiente radial
  colorido (o design original), sem imagem.

## Direitos

Não commite imagens sem licença. Opções livres:
- <https://unsplash.com>
- <https://pexels.com>
- Imagens geradas por IA (respeitando os termos do gerador).
