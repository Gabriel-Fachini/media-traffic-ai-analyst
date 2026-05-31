# Refatoracao de Arquitetura — Media Traffic AI Analyst

> Documento de planejamento. Define a arquitetura-alvo do repositorio, o
> diagnostico que a motiva e o plano de migracao incremental. Nenhuma mudanca de
> comportamento esta prevista: todo o trabalho descrito aqui e refactor puro,
> com `poetry run verify` e `poetry run pytest` verdes a cada passo.

## 1. Motivacao

O projeto nao tem uma arquitetura explicita. Nao existem camadas com fronteira
definida, entao responsabilidade vaza de arquivo em arquivo e tres modulos
concentram metade da base de codigo. O objetivo desta refatoracao e introduzir
uma **arquitetura em camadas (layered) com regra de dependencia clara**, que
torne o repositorio legivel, manutenivel e uma vitrine de senioridade.

Regra unica que governa tudo:

```
api / cli  -->  agent  -->  core
                  ^
              infra (injetada; nunca importada pelo core)
```

Dependencias apontam para dentro. `core` e puro (sem LangChain, FastAPI ou
rede). `infra` adapta o mundo externo e e injetada nas bordas, nunca importada
pelo dominio.

## 2. Diagnostico do estado atual

### 2.1 God files

Tres arquivos somam ~2360 linhas, cerca de metade do projeto, cada um com
multiplas responsabilidades:

| Arquivo | Linhas | Responsabilidades misturadas |
|---|---|---|
| `app/graph/workflow.py` | 988 | state schema, tipo de erro, ~12 helpers de mensagem, orquestracao do router, heranca de datas, 3 nodes, builder do grafo, cache, entrypoints publicos (`invoke`/`astream`) |
| `app/cli.py` | 718 | render rich (panels), parsing SSE, cliente HTTP, comandos, animacao de texto |
| `app/main.py` | 654 | rotas FastAPI, adapter SSE, extracao de observabilidade, builders de debug |

### 2.2 Acoplamento e fronteiras vazadas

- `app/main.py:107` redefine `_get_current_turn_messages` — copia divergente do
  mesmo helper em `app/graph/workflow.py:342` (assinaturas diferentes). Risco de
  divergencia silenciosa.
- `app/main.py:322` `_message_content_to_text` e quase identico a
  `app/graph/workflow.py:112` `_content_to_text`. Duplicado.
- `app/graph/workflow.py:34` importa `_extract_relative_date_range` (funcao
  privada, prefixo `_`) de `date_normalizer`. Abstracao vazando: "privado" usado
  cross-module.
- Logica de data espalhada em tres lugares sem dono: `llm_router.classify` ->
  `workflow._apply_date_normalizer` -> `workflow._inherit_dates_from_thread` ->
  `date_normalizer`.

### 2.3 Pasta `utils/` sem sentido

- `app/utils/config.py` guarda `Settings`. Config nao e util; `utils` vira
  lixeira semantica.
- `Settings.apply_runtime_environment()` (`config.py:125`) muta `os.environ`
  global como efeito colateral de um getter cacheado (`get_settings`). Schema,
  validacao e side-effect de processo no mesmo objeto.

### 2.4 Cruft e drift

- `response_llm` "retido para compatibilidade" (`workflow.py:649`). Projeto de
  portfolio, sem consumidor externo. Morto.
- SQL hardcoda `bigquery-public-data.thelook_ecommerce.users`
  (`channel_performance_analyzer.py:20`) em vez de derivar de `DATASET_ID` do
  catalogo. Catalogo e query podem divergir.
- `LlmTimeoutError` default `source="insight_synthesizer"` (`llm.py:27`) e o
  `Literal` em `DebugError` (`api.py:84`) referenciam um node que nao existe
  mais (a sintese acontece no node `agent`). Naming fossil.
- `agent_node` e `agent_node_async` (`workflow.py:710,755`) duplicam verbatim o
  bloco de guard de iteracoes.
- `app/schema_catalog.py` solto na raiz de `app/`, fora de qualquer pacote de
  dominio.

## 3. Arquitetura-alvo

```
app/
  core/                    # puro: sem LangChain, FastAPI, rede
    schema_catalog.py      # movido da raiz
    dates.py               # date_normalizer, API publica (sem _ vazando)
    errors.py              # ToolExecutionError, LlmTimeoutError
    analytics/
      models.py            # era schemas/tools.py
      queries.py           # SQL; dataset vem do catalogo
      traffic_volume.py
      channel_performance.py
    router/
      decision.py          # era schemas/router.py (RouterDecision)
      classifier.py        # era graph/llm_router.py
      date_resolution.py   # _apply_date_normalizer + _inherit_dates (1 dono)

  agent/                   # orquestracao LangGraph (era graph/)
    state.py
    messages.py            # _content_to_text + turn helpers (1 fonte)
    prompts.py
    nodes.py               # preprocess + agent + tool_executor
    graph.py               # build/compile/cache + invoke/astream

  api/                     # era main.py, fatiado
    routes.py
    sse.py
    observability.py
    schemas.py             # era schemas/api.py
    deps.py

  cli/                     # era cli.py, fatiado
    app.py
    sse_client.py
    rendering.py

  infra/                   # era utils/, corrigido
    config.py              # Settings (schema puro)
    env.py                 # apply_runtime_environment isolado
    bigquery.py
    llm.py
```

### 3.1 O que cada camada resolve

- **`core/`** — testavel sem mock de LLM/HTTP. `dates.py` expoe API publica, o
  que elimina o import de funcao `_privada` cross-module. `router/date_resolution.py`
  vira o dono unico da resolucao de datas, hoje tripartida.
- **`agent/`** — orquestracao LangGraph isolada. `messages.py` e fonte unica dos
  helpers de mensagem (mata os dois duplicados). Guard de iteracao extraido para
  uma funcao, uma copia so.
- **`api/`** e **`cli/`** — bordas de entrega, fatiadas por eixo (rotas vs SSE vs
  observabilidade; loop vs parsing vs render).
- **`infra/`** — separa schema de config da mutacao de ambiente.
  `get_settings()` volta a ser puro; quem precisa do side-effect chama
  `infra/env.py` explicitamente.
- **`utils/`** deletado. `schema_catalog.py` sai da raiz de `app/`.

## 4. Mapeamento origem -> destino

| Origem | Destino |
|---|---|
| `app/utils/config.py` (Settings) | `app/infra/config.py` |
| `app/utils/config.py` (apply_runtime_environment) | `app/infra/env.py` |
| `app/clients/bigquery_client.py` | `app/infra/bigquery.py` |
| `app/graph/llm.py` | `app/infra/llm.py` |
| `app/graph/llm.py` (LlmTimeoutError) | `app/core/errors.py` |
| `app/graph/workflow.py` (ToolExecutionError) | `app/core/errors.py` |
| `app/graph/workflow.py` (state) | `app/agent/state.py` |
| `app/graph/workflow.py` (helpers de mensagem) | `app/agent/messages.py` |
| `app/graph/workflow.py` (nodes) | `app/agent/nodes.py` |
| `app/graph/workflow.py` (build/invoke/astream) | `app/agent/graph.py` |
| `app/graph/workflow.py` (resolucao de datas) | `app/core/router/date_resolution.py` |
| `app/graph/llm_router.py` | `app/core/router/classifier.py` |
| `app/graph/prompts.py` | `app/agent/prompts.py` |
| `app/graph/date_normalizer.py` | `app/core/dates.py` |
| `app/schema_catalog.py` | `app/core/schema_catalog.py` |
| `app/schemas/router.py` | `app/core/router/decision.py` |
| `app/schemas/tools.py` | `app/core/analytics/models.py` |
| `app/tools/traffic_volume_analyzer.py` | `app/core/analytics/traffic_volume.py` |
| `app/tools/channel_performance_analyzer.py` | `app/core/analytics/channel_performance.py` |
| SQL inline dos analyzers | `app/core/analytics/queries.py` |
| `app/schemas/api.py` | `app/api/schemas.py` |
| `app/main.py` | `app/api/{routes,sse,observability,deps}.py` |
| `app/cli.py` | `app/cli/{app,sse_client,rendering}.py` |

## 5. Plano de migracao incremental

Cada passo e auto-contido. Gate obrigatorio ao fim de cada um:

```
poetry run verify
poetry run pytest
```

Refactor puro: nenhuma mudanca de comportamento observavel. Os testes existentes
sao a rede de seguranca; ajustar apenas imports nos testes quando o passo mover
um modulo.

### Passo 1 — Cruft (baixo risco, sem mexer em fronteira)

- [ ] Remover param morto `response_llm` de `build_analytics_graph` e dos testes.
- [ ] Renomear `insight_synthesizer` -> `agent` em `LlmTimeoutError` default e no
      `Literal` de `DebugError`.
- [ ] Deduplicar `_content_to_text` / `_message_content_to_text` em uma fonte.
- [ ] Deduplicar `_get_current_turn_messages` (workflow vs main).
- [ ] Extrair o guard de iteracoes duplicado em `agent_node`/`agent_node_async`.
- [ ] SQL dos analyzers passa a derivar tabelas de `DATASET_ID` do catalogo.

### Passo 2 — `utils/` -> `infra/` e split config/env

- [ ] Mover `Settings` para `app/infra/config.py`.
- [ ] Isolar `apply_runtime_environment` em `app/infra/env.py`; `get_settings`
      volta a ser puro.
- [ ] Mover `bigquery_client.py` -> `app/infra/bigquery.py` e `llm.py` ->
      `app/infra/llm.py`.
- [ ] Deletar `app/utils/`.

### Passo 3 — `graph/` -> `agent/` + `core/`

- [ ] Quebrar `workflow.py` em `agent/state.py`, `agent/messages.py`,
      `agent/nodes.py`, `agent/graph.py`.
- [ ] Mover `llm_router.py` -> `core/router/classifier.py` e
      `schemas/router.py` -> `core/router/decision.py`.
- [ ] Mover resolucao de datas para `core/router/date_resolution.py` (dono unico).
- [ ] Mover `date_normalizer.py` -> `core/dates.py` e promover
      `_extract_relative_date_range` a API publica.
- [ ] Mover `prompts.py` -> `agent/prompts.py`.

### Passo 4 — Dominio analytics

- [ ] Mover `schema_catalog.py` -> `core/schema_catalog.py`.
- [ ] Mover `schemas/tools.py` -> `core/analytics/models.py`.
- [ ] Mover analyzers -> `core/analytics/`.
- [ ] Extrair SQL inline -> `core/analytics/queries.py`.

### Passo 5 — `main.py` -> `api/`

- [ ] Fatiar em `api/routes.py`, `api/sse.py`, `api/observability.py`,
      `api/deps.py`.
- [ ] Mover `schemas/api.py` -> `api/schemas.py`.

### Passo 6 — `cli.py` -> `cli/`

- [ ] Fatiar em `cli/app.py`, `cli/sse_client.py`, `cli/rendering.py`.

## 6. Definicao de pronto

- [ ] Arvore de pastas reflete a arquitetura-alvo da secao 3.
- [ ] `app/utils/` nao existe mais.
- [ ] Nenhum arquivo de aplicacao acima de ~300 linhas sem justificativa.
- [ ] `core/` nao importa LangChain, FastAPI nem clientes de rede.
- [ ] Zero import de funcao `_privada` cross-module.
- [ ] Zero helper duplicado entre camadas.
- [ ] `poetry run verify` e `poetry run pytest` verdes.
- [ ] `CLAUDE.md` e `README.md` atualizados para os novos caminhos.
- [ ] Entrypoints do `pyproject.toml` (CLI/app) apontando para os novos modulos.
```
