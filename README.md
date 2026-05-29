# Media Traffic AI Analyst

Agente conversacional de analytics para Mídia e Growth que interpreta perguntas em linguagem natural, consulta o dataset público `bigquery-public-data.thelook_ecommerce` via tool calling real e responde com leitura de negócio em português.

## Stack

- **Orquestração:** LangGraph (StateGraph com checkpointing in-memory)
- **API:** FastAPI
- **CLI:** `analyst-chat` — cliente conversacional que consome a API local
- **LLM:** OpenAI ou Anthropic (configurável por env, com fallback entre providers)
- **Dados:** Google BigQuery via cliente oficial Python, SQL parametrizada
- **Tipagem e contratos:** Pydantic v2, type hints, Pyright
- **Qualidade:** Ruff, `compileall`, pytest (unit + integration + live opt-in)

## O que o agente faz

- Recebe perguntas sobre tráfego, pedidos e receita por canal de mídia
- Classifica a intenção com um router determinístico antes de acionar o LLM
- Usa tool calling real: o LLM decide *quando* chamar uma ferramenta, não executa SQL livre
- Sustenta conversas multi-turn via `thread_id` com persistência em memória
- Recusa perguntas fora do escopo de forma curta e educada
- Responde follow-ups estratégicos e diagnósticos reaproveitando o contexto do thread

**Escopos suportados:**

| Análise | Tabelas consultadas |
|---|---|
| Volume de usuários por canal | `users` |
| Total de pedidos por canal | `users → orders` |
| Receita total por canal | `users → orders → order_items` |
| Ranking e comparação entre canais | consulta agregada + síntese |

**Formatos de data aceitos:** `YYYY-MM-DD`, `DD/MM/AAAA`, `DD/MM/AA`, `ontem`, `este mês`, `último mês`, `últimos N dias`

## Arquitetura

### Fluxo principal

```mermaid
flowchart TD
    A["Usuário via API ou CLI"] --> B["preprocess: router + guardrails"]
    B -->|short-circuit| C["Resposta curta ou pedido de clarificação"]
    B -->|intent válida| D["agent: LLM com tools vinculadas"]
    D -->|tool_call| E["tool_executor"]
    E --> F["BigQuery: thelook_ecommerce"]
    F --> E
    E --> D
    D --> G["Resposta final em pt-BR"]
```

O grafo separa três responsabilidades em nodes distintos:

1. **preprocess (router)** — classifica intent, normaliza datas, emite short-circuits baratos antes de gastar LLM
2. **agent** — LLM com `bind_tools(..., tool_choice="auto")`; decide se chama tool ou responde direto
3. **tool_executor** — executa as tools solicitadas e injeta os resultados como `ToolMessage` no histórico

### Decisões de design notáveis

**Router determinístico antes do LLM.** Classificação de intent, normalização de datas e guardrails são feitos por regex em `app/graph/router.py`. Isso reduz latência, elimina custo de tokens e garante comportamento consistente em perguntas estruturais (pergunta vazia, fora do escopo, datas ausentes).

**Duas tools com limites explícitos.** `traffic_volume_analyzer` e `channel_performance_analyzer` têm descrições que especificam *quando não usar*, reduzindo confusão do modelo na escolha. Uma tool por responsabilidade é melhor que uma god-tool com parâmetro `metric`.

**SQL sempre parametrizada.** Nenhum input do usuário é concatenado em query. Tudo passa por `bigquery.ScalarQueryParameter`.

**`COUNT(DISTINCT o.order_id)`.** `order_items` tem N linhas por pedido; sem DISTINCT a contagem inflaria.

**`CAST(sale_price AS NUMERIC)`.** BigQuery retorna `FLOAT64` por padrão; NUMERIC evita erro acumulado em somas de receita.

**`status = 'Complete'`.** Receita realizada exclui pedidos cancelados e devolvidos.

**Reducer `add_messages`.** O campo `messages` usa `Annotated[..., add_messages]` para append não-destrutivo — essencial para multi-turn sem sobrescrever histórico.

### Mapa de responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | Superfície HTTP, contratos de entrada/saída, `X-Debug`, tratamento de timeout do LLM |
| `app/cli.py` | CLI conversacional via API local |
| `app/graph/workflow.py` | StateGraph: nodes `preprocess → agent → tool_executor`, loop de tool calling |
| `app/graph/router.py` | Intent, datas, `traffic_source`, guardrails, fusão de follow-ups |
| `app/graph/prompts.py` | Política conversacional, síntese de dados, follow-ups estratégicos e diagnósticos |
| `app/graph/tools.py` | Registro das tools com `StructuredTool.from_function` |
| `app/tools/*.py` | Queries SQL e mapeamento para outputs tipados |
| `app/clients/bigquery_client.py` | Cliente BigQuery e encapsulamento de erros de infra |
| `app/schemas/*.py` | Contratos Pydantic da API, router e tools |

### Tools

| Tool | Quando é usada | Saída |
|---|---|---|
| `traffic_volume_analyzer` | Volume de usuários por canal | `user_count` por `traffic_source` |
| `channel_performance_analyzer` | Pedidos, receita, ranking | `total_orders` e `total_revenue` por `traffic_source` |

## Setup

### Pré-requisitos

- Python 3.10+
- Poetry
- Credenciais do Google Cloud com acesso ao BigQuery
- Chave de API: OpenAI ou Anthropic

### Variáveis de ambiente

Crie `.env` na raiz do projeto:

```env
APP_ENV=dev
APP_DEBUG=true

GCP_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=credentials/google.json

LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sua-chave-openai
ANTHROPIC_API_KEY=

# Fallback opcional:
# LLM_FALLBACK_PROVIDER=anthropic
# LLM_FALLBACK_MODEL=claude-3-7-sonnet-latest
```

Coloque o arquivo de service account em `credentials/google.json`. O dataset consultado é público; as credenciais são necessárias apenas para autenticar a sessão BigQuery.

### Instalar dependências

```bash
poetry install
```

### Subir a API

```bash
poetry run fastapi dev --host 127.0.0.1 --port 8000
```

### Abrir a CLI

Em outro terminal:

```bash
poetry run analyst-chat --api-url http://127.0.0.1:8000/query --debug
```

### Atalho: API + CLI em um comando

```bash
./scripts/run_local_chat.sh
```

O script sobe a API, aguarda o `/health` responder, abre a CLI com `--debug` ativado e encerra a API quando a CLI for fechada.

## Exemplos de uso

### Tool calling de receita

```
Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?
```

Com `--debug`, o painel exibe `router_intent: channel_performance` e confirma a tool call.

### Clarificação de datas com continuidade multi-turn

Turno 1: `Qual foi a receita de Search?`  
Turno 2: `Entre 2024-01-01 e 2024-01-31.`

No segundo turno o router funde a pergunta anterior com a data recebida e executa a query completa.

### Recusa de métrica fora do schema

```
Qual foi o ROAS de Search ontem?
```

O agente responde com recusa curta explicando que ROAS não está disponível no schema atual.

### Follow-up estratégico

Turno 1: `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?`  
Turno 2: `Quais ações devemos priorizar agora?`

O segundo turno não dispara nova query. O router detecta `strategy_follow_up` e o LLM usa o contexto do thread para gerar recomendações.

## Modo debug

Qualquer request pode incluir o header `X-Debug: true`. A resposta passa a conter:

```json
{
  "metadata": {
    "debug": {
      "resolved_question": "...",
      "router_decision": { "intent": "channel_performance", ... },
      "agent_tool_calls": [...]
    }
  }
}
```

## Validação

```bash
# Lint + type check + compileall
poetry run verify

# Suite determinística (sem BigQuery nem LLM real)
poetry run pytest

# Smoke tests com BigQuery e LLM reais (requer ambiente configurado)
poetry run pytest -m live
```

Variantes com output compacto para iterações rápidas: `--agent` em qualquer dos comandos acima.

## Estrutura do repositório

```text
app/
  clients/      # BigQuery client e erros de infraestrutura
  graph/        # router, prompts, binding de tools, workflow LangGraph
  schemas/      # contratos Pydantic
  tools/        # queries SQL e analyzers
  cli.py        # CLI conversacional
  main.py       # API FastAPI
  verify.py     # gate local sem testes
tests/
  unit/
  integration/
  live/
  readiness/
scripts/
  run_local_chat.sh       # sobe API + abre CLI com --debug
  run_readiness_checks.sh
docs/
  workflow.md   # explicação detalhada do StateGraph
```

## Limitações atuais

- Persistência apenas em RAM — reiniciar o processo apaga o contexto multi-turn
- Sem UI web
- Métricas suportadas: volume de usuários, pedidos e receita; sem ROAS, CAC, CTR, CPC, CPM
- Dataset limitado a `users`, `orders` e `order_items`
- Um `traffic_source` por tool call; comparações entre canais usam consulta agregada
