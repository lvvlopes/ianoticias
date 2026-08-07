# Configuração — Meta (Facebook + Instagram)

Para publicar de verdade no Instagram você precisa: uma **conta IG
Business/Creator** conectada a uma **Página do Facebook**, um **app** no
Meta for Developers, e um **token de acesso** com as permissões certas.
Este guia cobre tudo, com as armadilhas que já enfrentamos.

## 1. Pré-requisitos na conta

1. **Conta Instagram**: mude para **Business** ou **Creator** (Configurações
   do IG → Conta → Trocar para conta profissional). Pessoal não publica via API.
2. **Página do Facebook**: crie uma (grátis) se ainda não tiver.
3. **Conectar IG ↔ Página**: no Instagram, Configurações → Meta Business
   Suite → conecte a Página.

## 2. Criar o app no Meta for Developers

<https://developers.facebook.com/apps/> → **Create App** → tipo **Business**.

Depois, no seu app:
- **Add products** → adicione **Instagram Graph API** (produto obrigatório
  para publicar).
- **App Settings → Basic**: copie **App ID** e **App Secret**.

Preencha no `.env`:
```env
META_APP_ID=1234567890
META_APP_SECRET=abcdef...
```

## 3. Gerar o token de acesso (a parte complicada)

Você **não configura o token direto**; gera um token curto no Graph API
Explorer e depois nossa CLI troca por um de longa duração (ou pelo token
de Página, que não expira).

### Passo 3.1 — Token curto no Graph API Explorer

<https://developers.facebook.com/tools/explorer/>:

1. **Meta App**: selecione **seu app**.
2. **User or Page**: `User Token`.
3. **Permissions**: adicione todas:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
   - `business_management`
   - `instagram_manage_comments` (só se quiser postar hashtags no 1º comentário)
4. **Generate Access Token** → autorize a conta no popup → **Copy**.

⚠️ Esse token dura **~1 hora**. Vá direto ao passo 3.2 antes que ele morra.

### Passo 3.2 — Trocar por token de LONGA duração (via script)

```bash
python scripts/ig_token.py COLE_O_TOKEN_CURTO_AQUI
```

O script (usando `META_APP_ID`/`META_APP_SECRET` do `.env`):

1. Troca o curto por um **de longa duração** (~60 dias).
2. Lista suas Páginas + contas Instagram associadas.
3. Imprime **duas linhas prontas** para colar no `.env`:
   ```
   IG_USER_ID=1784...
   IG_ACCESS_TOKEN=EAA...    ← token de PÁGINA (não expira)
   ```

**Recomendado usar o token de Página** — ele é derivado do token de usuário
de longa duração mas **não expira**. Melhor que o de 60 dias.

Se o script imprimir `(sem conta IG Business ligada)`, o problema é na
ligação IG↔Página (passo 1) — reveja lá.

### Passo 3.3 — Colar no `.env` e reiniciar

```env
IG_USER_ID=17841412638816722
IG_ACCESS_TOKEN=EAA...
GRAPH_API_VERSION=v21.0
```

## 4. Renovação do token

- **Token de Página**: não expira. Só regere se você trocar de app ou revogar
  permissões.
- **Token de longa duração (60d)**: o código tem **refresh automático**.
  Ao publicar, se o token guardado no banco (`app_settings.ig.access_token`)
  tem mais de 45 dias, é renovado via `fb_exchange_token` antes da
  publicação. Também tem um botão **"Renovar token agora"** em `/admin`.

## 5. Requisitos do card (Instagram é chato)

- **Formato**: JPEG (PNG dá "Only photo or video can be accepted as media type").
- **Proporção**: 1:1 (quadrado 1080×1080 é o usado). 4:5 e 1.91:1 também são
  aceitos, quadrado é o mais seguro.
- **URL da imagem**: pública HTTPS. Não pode ser localhost, não pode ser
  privada, não pode redirecionar para HTML/JSON.

Tudo isso é resolvido pelo `image_card.py` (sempre JPEG) + Storage público
(ver [CONFIG-SUPABASE.md](CONFIG-SUPABASE.md)).

## 6. Legenda otimizada (para crescer no IG)

O `services/instagram.py:build_caption` monta:

```
<título>

<parágrafo 1>

<parágrafo 2>

👉 Siga @seuperfil para IA todo dia · 💾 Salve · 🔁 Compartilhe

📖 Matéria completa no link da bio
Fonte: <URL>
```

E `build_first_comment` monta um **primeiro comentário** com as hashtags
(deixa a legenda limpa e move o efeito de descoberta pro comentário).

Configuração:
```env
IG_HANDLE=seuperfil               # sem @
IG_BRAND_HASHTAG=IANoticias       # sem #
IG_HASHTAGS_IN_COMMENT=1          # 0 = hashtags na legenda
```

## 7. Fluxo real de publicação (o que acontece por baixo)

Ao clicar **Postar IG** ou chamar `POST /api/instagram/publish`:

1. **Refresh oportunista** do token se estiver com >45 dias.
2. **Gera** o card JPEG 1080×1080 (`build_card_jpeg`).
3. **Upload** para o Storage do Supabase → devolve URL pública.
4. **Cria container** na Graph API:
   `POST /{IG_USER_ID}/media` com `image_url` + `caption`.
5. **Publica**: `POST /{IG_USER_ID}/media_publish` com `creation_id`.
6. **Se `IG_HASHTAGS_IN_COMMENT=1`**: `POST /{media_id}/comments` com as
   hashtags (best-effort — não derruba o post se falhar).
7. Marca `ig_status='posted'` e grava `ig_post_id`.

Todas as chamadas Meta têm **retry com backoff** (3 tentativas, 0.5→1→2s)
para tolerar soluços de rede.

## 8. Erros comuns e como debugar

Quando o publish falha, o navegador mostra `alert()` com a mensagem exata
retornada pela Meta (código do middleware no `templates/base.html`). Os
mais frequentes:

| Erro Meta | O que é | Como resolver |
|-----------|---------|---------------|
| `Session has expired on ...` | Token expirou | Rode `scripts/ig_token.py` de novo (você usou um curto) |
| `Only photo or video can be accepted as media type` | Bucket privado ou imagem não-JPEG | Torne o bucket público, confirme JPEG |
| `Media URL invalid or unreachable` | Meta não consegue baixar a URL | Bucket privado, DNS quebrado, ou HTTP em vez de HTTPS |
| `Media ID is not available` | Publish disparado antes da Meta terminar de processar o container da imagem | Já resolvido no código: `_wait_for_container_ready` faz polling de `status_code` até `FINISHED` antes do publish |
| `(#4) Application request limit reached` | Rate limit (~25 posts/24h) | Aguarde 1h ou reduza volume |
| `Signature verification failed` (Storage) | Chave é de outro projeto | Ver [CONFIG-SUPABASE.md § 4](CONFIG-SUPABASE.md) |
| `Falha de rede após 3 tentativas` | Rede local ou firewall/antivírus | Teste em outra rede |

## 9. Diagnóstico rápido

```bash
python scripts/diag_ig.py             # confere config
python scripts/diag_ig.py --publish   # tenta publicar de verdade e mostra o erro
```

O `--publish` regenera o card, sobe pro Storage e chama a Meta com o primeiro
artigo do banco. Erros aparecem exatos.

## Variáveis desta integração

```env
IG_USER_ID=17841...
IG_ACCESS_TOKEN=EAA...
META_APP_ID=1534...
META_APP_SECRET=d68d...
GRAPH_API_VERSION=v21.0

IG_HANDLE=seuperfil
IG_BRAND_HASHTAG=IANoticias
IG_HASHTAGS_IN_COMMENT=1
```
