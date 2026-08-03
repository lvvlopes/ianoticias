# Configuração — OpenAI (classificação e resumo)

O IANoticias usa a OpenAI para, em **uma chamada por matéria**, classificar
a notícia e produzir um post pronto de Instagram (título + resumo em 2
parágrafos + hashtags).

## 1. Gerar chave

<https://platform.openai.com/api-keys> → **Create new secret key** → copie.

```env
OPENAI_API_KEY=sk-proj-...
```

## 2. Escolher o modelo

```env
OPENAI_MODEL=gpt-5.4-nano
```

⚠️ **Use o ID EXATO do modelo** — minúsculo, com hífens, sem espaço. IDs
comuns:
- `gpt-4o-mini` (barato, muito confiável)
- `gpt-5.4-nano` (mais novo, se sua conta tiver acesso)
- Qualquer outro listado em <https://platform.openai.com/docs/models>

Errado: `GPT-5.4 Nano` (maiúsculo, espaço) → cada chamada retorna
`model_not_found` → nenhuma notícia é salva.

## 3. Validar antes de rodar o pipeline

```bash
python scripts/diag_llm.py
```

Faz **uma** chamada de teste e imprime:
- ✓ modelo válido → o pipeline vai funcionar.
- Erro da API (`model_not_found`, quota, chave inválida) → mostra o texto exato.

## 4. Modo mock (offline, sem gastar tokens)

Para desenvolver a UI sem chamar OpenAI:

```env
MOCK_LLM=1
```

Cada matéria vira um resumo determinístico fake. Ligue apenas em dev; em
produção deixe `MOCK_LLM=0` (default) ou remova a linha.

## 5. Regras que vão para o LLM

O prompt está em `ianoticias/services/llm.py`, constantes
`DEFAULT_SYSTEM_PROMPT` e `DEFAULT_USER_TEMPLATE`. **Não precisa editar o
código** para ajustar: a tela `/admin` tem um editor de prompt que salva
no banco (`app_settings`), com prioridade sobre os defaults. Botão
**"Restaurar padrão"** volta ao texto do código.

O que o prompt exige:
- **Classificação estrita** em uma das 3 categorias (`ia`, `eng_dev_ia`,
  `gestao_ia`) — o LLM segue regras específicas de escopo definidas no prompt.
- **Título** com máximo ~80 caracteres.
- **Conteúdo em 2 parágrafos** (fatos + implicações), autossuficiente — o
  leitor deve entender sem clicar no link.
- **4 a 8 hashtags** em PT-BR (ou termos técnicos em inglês).
- **Resposta em JSON válido** (`response_format={"type": "json_object"}`).

## 6. Reprocessar notícias antigas com prompt novo

Se você mudou o prompt e quer regerar resumos de notícias já salvas:

```bash
python scripts/reprocess.py --limit 5   # testa com 5 primeiro
python scripts/reprocess.py             # só as que ainda têm 1 parágrafo
python scripts/reprocess.py --all       # todas
```

Custa 1 chamada OpenAI por matéria. As matérias novas (próximo Buscar
Notícias) já nascem com o prompt atual.

## 7. Custos e limites

- **`gpt-4o-mini`**: ~$0.15/1M tokens input, ~$0.60/1M output. Um ingest
  de 20 matérias consome ~5-15 mil tokens totais — centavos.
- **Cap por execução** (`INGEST_MAX_ITEMS`, default 12) limita quantas
  chamadas fazem por clique — proteção contra estouro de conta.
- O **pré-filtro** por palavras-chave (`INGEST_PREFILTER=1`) descarta lixo
  óbvio (games, gadgets) **antes** do LLM — economia significativa.

## 8. Erros comuns

| Erro | Causa | Correção |
|------|-------|----------|
| `model_not_found` | ID do modelo errado (espaço, case) | Use ID exato |
| `insufficient_quota` | Sem crédito | Adicione método de pagamento na OpenAI |
| `rate_limit_exceeded` | Muitas chamadas rápido | Reduza `Semaphore(4)` no pipeline ou aguarde |
| Resposta cortada / JSON inválido | Prompt exigindo demais para o modelo | Simplifique prompt ou aumente `max_tokens` (via prompt) |

## Variáveis desta integração

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
MOCK_LLM=0
INGEST_MAX_ITEMS=12
INGEST_PREFILTER=1
```
