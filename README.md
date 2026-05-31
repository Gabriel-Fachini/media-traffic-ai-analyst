# Media Traffic AI Analyst

Agente conversacional de analytics para Mídia e Growth que interpreta perguntas em linguagem natural, consulta o dataset público `bigquery-public-data.thelook_ecommerce` via tool calling real e responde com leitura de negócio em português.

> **Projeto de portfólio.** O objetivo não é cobrir todo o domínio de analytics, e sim demonstrar engenharia de agentes LLM com decisões deliberadas: roteamento por LLM com structured output, normalização determinística onde determinismo é barato e exato, SQL sempre parametrizada, contratos Pydantic tipados ponta a ponta e um harness de avaliação (`eval`) que mede o agente antes de evoluí-lo. O roadmap de evolução está em [`PLANO_EVOLUCAO.md`](PLANO_EVOLUCAO.md).

## Stack

- **Orquestração:** LangGraph (StateGraph com checkpointing in-memory)
- **Roteamento:** classificação de intent por LLM com `with_structured_output(RouterDecision)`; normalização de datas determinística
- **API:** FastAPI
- **CLI:** `analyst-chat` — cliente conversacional que consome o stream SSE da API local
- **LLM:** OpenAI ou Anthropic (configurável por env, com fallback entre providers)
- **Dados:** Google BigQuery via cliente oficial Python, SQL parametrizada
- **Tipagem e contratos:** Pydantic v2, type hints, Pyright
- **Qualidade:** Ruff, `compileall`, pytest (unit + integration + live opt-in), eval harness do router

## O que o agente faz

- Recebe perguntas sobre tráfego, pedidos e receita por canal de mídia
- Classifica a intenção com um router LLM (structured output) que enxerga o contexto do thread, com normalização de datas determinística à parte
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

1. **preprocess (router)** — guard de pergunta vazia, classifica intent via router LLM, normaliza datas de forma determinística e emite short-circuits antes de acionar o agente
2. **agent** — LLM com `bind_tools(..., tool_choice="auto")`; decide se chama tool ou responde direto
3. **tool_executor** — executa as tools solicitadas e injeta os resultados como `ToolMessage` no histórico, voltando ao `agent` para a síntese

### Decisões de design notáveis

**Router LLM com normalização de datas determinística.** A classificação de intent, escopo e detecção de follow-up é feita por LLM com `with_structured_output(RouterDecision)` (`app/core/router/classifier.py`), recebendo o contexto do thread. A normalização de `start_date`/`end_date` permanece determinística (`app/core/dates.py` + `app/core/router/date_resolution.py`), porque data é barata, exata e testável sem gastar tokens. Híbrido consciente: delega ao LLM só o que ele faz melhor (variação de linguagem natural), mantém regra onde regra ganha. Antes do router, um guard determinístico faz short-circuit de pergunta vazia sem chamar o LLM.

**Eval antes de evoluir.** O router LLM é não-determinístico; mexer nele sem medir seria irresponsável. `tests/eval/` roda o router contra um dataset de casos (`router_cases.jsonl`) e reporta accuracy por campo, com baseline documentado — `poetry run pytest -m eval`.

**Duas tools com limites explícitos.** `traffic_volume_analyzer` e `channel_performance_analyzer` têm descrições que especificam *quando não usar*, reduzindo confusão do modelo na escolha. Uma tool por responsabilidade é melhor que uma god-tool com parâmetro `metric`.

**SQL sempre parametrizada.** Nenhum input do usuário é concatenado em query. Tudo passa por `bigquery.ScalarQueryParameter`.

**`COUNT(DISTINCT o.order_id)`.** `order_items` tem N linhas por pedido; sem DISTINCT a contagem inflaria.

**`CAST(sale_price AS NUMERIC)`.** BigQuery retorna `FLOAT64` por padrão; NUMERIC evita erro acumulado em somas de receita.

**`status = 'Complete'`.** Receita realizada exclui pedidos cancelados e devolvidos.

**Reducer `add_messages`.** O campo `messages` usa `Annotated[..., add_messages]` para append não-destrutivo — essencial para multi-turn sem sobrescrever histórico.

### Mapa de responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `app/api/routes.py` | Superfície HTTP, contratos de entrada/saída, `/query`, `/query/stream`, `X-Debug`, tratamento de timeout do LLM |
| `app/cli/app.py` | CLI conversacional via API local consumindo SSE |
| `app/agent/graph.py` | StateGraph: nodes `preprocess → agent → tool_executor`, roteamento via `Command(goto=...)`, loop de tool calling |
| `app/core/router/classifier.py` | Router LLM: `classify_question` com `with_structured_output(RouterDecision)`, contexto do thread |
| `app/core/dates.py` | Normalização determinística de datas absolutas e relativas |
| `app/agent/prompts.py` | Política conversacional, síntese de dados, follow-ups estratégicos e diagnósticos |
| `app/agent/tools.py` | Registro canônico das tools com `StructuredTool.from_function` |
| `app/core/analytics/*.py` | SQL, contratos tipados e transformação dos resultados analytics |
| `app/infra/bigquery.py` | Cliente BigQuery e encapsulamento de erros de infra |
| `app/schemas/*.py` | Shims de backward-compat dos contratos Pydantic |

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

No segundo turno o router LLM, com o contexto do thread, resolve a pergunta anterior junto com a data recebida e executa a query completa.

### Recusa de métrica fora do schema

```
Qual foi o ROAS de Search ontem?
```

O agente responde com recusa curta explicando que ROAS não está disponível no schema atual.

### Follow-up estratégico

Turno 1: `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?`  
Turno 2: `Quais ações devemos priorizar agora?`

O segundo turno não dispara nova query. O router LLM detecta `strategy_follow_up` a partir do contexto do thread e o agente usa o histórico para gerar recomendações.

## Modo debug

Qualquer request pode incluir o header `X-Debug: true`. A resposta passa a conter:

```json
{
  "metadata": {
    "debug": {
      "resolved_question": "...",
      "router_intent": "channel_performance",
      "agent_tool_calls": [...],
      "observability": {
        "latency_ms": 187,
        "llm_call_count": 3,
        "tool_call_count": 1,
        "tools_used": ["channel_performance_analyzer"],
        "token_usage": {
          "input_tokens": 50,
          "output_tokens": 32,
          "total_tokens": 82
        }
      }
    }
  }
}
```

Com `POST /query/stream`, o mesmo modo debug aparece no evento SSE final (`event: final`), permitindo que a CLI ou um front capturem os sinais de observabilidade do turno sem depender do payload cru do LangGraph.

## Validação

```bash
# Lint + type check + compileall
poetry run verify

# Suite determinística (sem BigQuery nem LLM real)
poetry run pytest

# Smoke tests com BigQuery e LLM reais (requer ambiente configurado)
poetry run pytest -m live

# Eval do router LLM: accuracy por campo contra o dataset de casos (offline)
poetry run pytest -m eval
```

Variantes com output compacto para iterações rápidas: `--agent` em qualquer dos comandos acima.

### Guardrails de desenvolvimento (Claude Code hooks)

O repositório versiona hooks do Claude Code em `.claude/` que tornam mecânicas as invariantes do projeto durante o desenvolvimento assistido por IA:

- bloqueio de leitura/edição de segredos (`.env`, `credentials/*.json`);
- bloqueio de SQL não-parametrizada em `app/core/analytics/queries.py`, `app/tools/` e no cliente BigQuery;
- `ruff check` automático no arquivo Python recém-editado.

Detalhe em [`CLAUDE.md`](CLAUDE.md) (seção *Harness do Claude Code*).

## Estrutura do repositório

```text
app/
  agent/        # workflow LangGraph, prompts e registry de tools
  api/          # FastAPI, SSE e observabilidade
  cli/          # CLI conversacional
  core/         # datas, router e analytics
  graph/        # shims de backward-compat
  infra/        # BigQuery, LLMs e settings
  schemas/      # shims de backward-compat
  tools/        # shims de backward-compat
  main.py       # entrypoint FastAPI backward-compatible
  verify.py     # gate local sem testes
tests/
  unit/
  integration/
  live/
  readiness/
  eval/         # eval harness do router LLM (accuracy por campo)
scripts/
  run_local_chat.sh       # sobe API + abre CLI com --debug
  run_readiness_checks.sh
.claude/
  hooks/        # guardrails de desenvolvimento (segredos, SQL, ruff)
```

## Limitações atuais

- Persistência apenas em RAM — reiniciar o processo apaga o contexto multi-turn
- Sem UI web
- Métricas suportadas: volume de usuários, pedidos e receita; sem ROAS, CAC, CTR, CPC, CPM
- Dataset limitado a `users`, `orders` e `order_items`
- Um `traffic_source` por tool call; comparações entre canais usam consulta agregada
