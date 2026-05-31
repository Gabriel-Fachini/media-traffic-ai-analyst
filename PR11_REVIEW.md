# Review do PR 11 — Refatoração de Arquitetura

## Escopo revisado

- PR: `#11 refactor: arquitetura em camadas (core/agent/api/cli/infra)`
- Base remota: `23c2c62`
- Head revisado: `cb9d3a4`
- Plano de referência: `REFATORACAO_ARQUITETURA.md`
- Patch total do PR: 68 arquivos, 5089 adições, 4068 remoções
- Refatoração arquitetural propriamente dita: commits `f9be4fc..cb9d3a4`

O PR também carrega cinco commits anteriores à refatoração (`a8d2f26..a219a11`) com LangSmith, streaming SSE, CLI e mudanças de contexto multi-turn. Por isso, os achados abaixo distinguem:

1. regressões introduzidas pelos movimentos arquiteturais;
2. desvios do blueprint que permaneceram após a refatoração;
3. problemas já existentes antes do passo 1, mas ainda incompatíveis com a definição de pronto.

## Resultado executivo

**Recomendação: solicitar mudanças antes do merge.**

`poetry run verify --agent` passa, mas não cobre importabilidade da aplicação. Em processo Python limpo, `from app.main import app` falha com import circular. A API não inicia pelo entrypoint documentado.

Além disso:

- o hook que deveria impedir SQL interpolada deixou de cobrir os novos caminhos canônicos;
- `core/` não é puro e continua dependendo de LangChain, Google Cloud e `infra/`;
- o eval offline documentado foi removido e `poetry run pytest -m eval` não executa teste algum;
- a suíte padrão continua vermelha: `6 failed, 60 passed, 8 skipped`.

## Achados bloqueadores

### 1. CRITICAL — Import circular impede startup da API

**Arquivos:** `app/agent/graph.py:31`, `app/graph/__init__.py:4-5`

`app.agent.graph` é agora módulo canônico, mas importa `get_analytics_tools` pelo pacote legado `app.graph.tools`. Para carregar esse submódulo, Python executa `app/graph/__init__.py`, que reimporta `app.agent.graph` antes de sua inicialização terminar.

Reprodução:

```bash
poetry run python -c "from app.main import app"
```

Resultado:

```text
ImportError: cannot import name 'astream_analytics_graph_events' from partially initialized module 'app.agent.graph'
```

O mesmo erro ocorre com:

```bash
poetry run python -m app.api.routes
```

Antes da refatoração, tanto `23c2c62` quanto `a219a11` importavam `app.main` corretamente em processo limpo.

**Impacto:** `fastapi dev`, `fastapi run` e qualquer consumidor direto de `app.main:app` ficam bloqueados. Os testes não detectam isso porque importam `app.graph.workflow` antes de `app.main`, alterando a ordem de inicialização.

**Correção:** mover registro de tools para módulo canônico fora de `app.graph` (por exemplo, `app/agent/tools.py`) e fazer shims legados apontarem para ele. Módulos canônicos não devem importar pacotes de compatibilidade.

### 2. HIGH — Hook de SQL não-parametrizada não protege mais os arquivos canônicos

**Arquivo:** `.claude/hooks/guard_sql.py:24`

O hook continua protegendo apenas:

```python
GUARDED = ("app/tools/", "bigquery_client.py")
```

Após a refatoração, SQL vive em `app/core/analytics/queries.py` e execução BigQuery em `app/infra/bigquery.py`. Escrita insegura nesses caminhos passa pelo hook.

Reprodução:

```text
app/core/analytics/queries.py + SQL = f"SELECT ... {user_input}" -> exit 0
app/tools/example.py          + SQL = f"SELECT ... {user_input}" -> exit 2
```

**Impacto:** a invariante “SQL sempre parametrizada” deixou de ser mecanicamente garantida justamente nos arquivos ativos.

**Correção:** atualizar caminhos protegidos e permitir apenas interpolação conhecida de `DATASET_ID`. Preferir validação estrutural ou allowlist explícita para constantes internas.

### 3. MEDIUM — Shims de backward compatibility perderam exports públicos

**Arquivos:** `app/graph/date_normalizer.py:3-49`, `app/graph/prompts.py:3-8`

O blueprint afirma que shims preservam imports existentes, mas dois símbolos públicos deixaram de ser reexportados:

```bash
poetry run python -c "from app.graph.date_normalizer import LAST_YEAR_PATTERN"
poetry run python -c "from app.graph.prompts import format_schema_catalog"
```

Ambos falham com `ImportError`. Antes da refatoração, símbolos existiam no módulo legado.

**Impacto:** consumidores internos ou externos que usam API antiga quebram apesar da promessa de compatibilidade.

**Correção:** reexportar símbolos no shim ou documentar quebra intencional e remover promessa de backward compatibility.

## Desvios do blueprint

### 4. HIGH — `core/` não é puro e importa dependências externas e `infra/`

**Arquivos:** `app/core/router/classifier.py:5-9`, `app/core/router/date_resolution.py:3`, `app/core/analytics/traffic_volume.py:3-7`, `app/core/analytics/channel_performance.py:5-13`

O plano define `core/` como domínio puro: sem LangChain, FastAPI, rede ou import de `infra/`. A implementação mantém:

- `langchain_core.messages` em router e resolução de datas;
- `app.infra.llm` e `app.infra.config` no classifier;
- `google.cloud.bigquery` e `app.infra.bigquery` nos analyzers.

Os analyzers também instanciam `BigQueryClient()` internamente (`traffic_volume.py:14`, `channel_performance.py:20`), portanto não são funções puras.

**Impacto:** fronteira principal da arquitetura não existe de fato. Testar domínio ainda exige SDKs externos ou mocks de infra.

**Correção:** deixar `core/` com contratos, regras, SQL e transformação de dados. Mover integração LLM/BigQuery para adapters em `agent/` ou `infra/`, injetando portas tipadas.

### 5. MEDIUM — `get_settings()` continua com side effect global

**Arquivo:** `app/infra/env.py:28-33`

O plano exige `get_settings()` puro e chamada explícita de `apply_runtime_environment()`. Implementação ainda valida settings e muta `os.environ` dentro do getter cacheado.

**Impacto:** leitura de configuração continua alterando estado global do processo; testes e consumidores não controlam quando side effects acontecem.

**Correção:** retornar somente `Settings` no getter. Aplicar ambiente em composition root explícito.

### 6. MEDIUM — Módulos canônicos continuam dependendo de shims legados

**Arquivos:** `app/agent/graph.py:31`, `app/infra/llm.py:112`

`app.agent.graph` e `app.infra.llm` importam `app.graph.tools`, que deveria existir apenas para backward compatibility. Isso causou o ciclo de startup e mantém dependência apontando para camada antiga.

**Correção:** criar destino canônico para tool registry e reduzir `app/graph/tools.py` a re-export.

### 7. MEDIUM — Definição de pronto estrutural não foi atingida

**Arquivos:** `app/agent/nodes.py:18-32`, `app/cli/sse_client.py:12-23`, `app/agent/state.py:20`, `app/infra/llm.py:20`

Itens do plano ainda abertos:

- `app/agent/nodes.py` tem 539 linhas, acima do alvo de ~300 sem justificativa;
- vários módulos importam funções privadas cross-module (`_build_debug_error`, `_resolve_question`, `_animate_text`, `_submit_question`, etc.);
- `app/core/errors.py` planejado não existe;
- `ToolExecutionError` ficou em `app/agent/state.py`;
- `LlmTimeoutError` ficou em `app/infra/llm.py`.

**Impacto:** god file menor, mas fronteiras internas continuam frágeis e API privada vaza entre módulos.

**Correção:** extrair tool executor, router helpers e runtime errors para módulos canônicos pequenos; promover helpers compartilhados a API pública ou encapsular uso.

## Qualidade, eval e observabilidade

### 8. HIGH — Eval offline foi removido, mas continua documentado como gate obrigatório

**Arquivos:** `README.md:64`, `README.md:233-237`, `CLAUDE.md:272-277`, `PLANO_EVOLUCAO.md:68`, `PLANO_EVOLUCAO.md:250`

O PR remove:

- `tests/eval/test_router_eval.py`;
- marker `eval` de `pyproject.toml`;
- `tests/deterministic_router.py`;
- `tests/unit/test_router.py`.

Mas documentação ainda promete eval offline com baseline e threshold:

```bash
poetry run pytest -m eval
```

Resultado atual:

```text
74 deselected / 0 selected
exit code 5
```

LangSmith opt-in não substitui gate offline: depende de ambiente externo, LLM real e inspeção remota.

**Impacto:** princípio “eval antes de evoluir” deixa de ser verificável localmente; comando publicado falha.

**Correção:** restaurar runner offline ou substituir documentação e gate por comando funcional com threshold automatizado.

### 9. MEDIUM — Script LangSmith não faz skip limpo sem ambiente

**Arquivo:** `scripts/eval_router_langsmith.py:7-10`, `scripts/eval_router_langsmith.py:158-160`

Docstring promete exit `0` quando LangSmith não está configurado. Porém `_langsmith_configured()` chama `get_settings()`, que valida provider padrão antes do guard.

Reprodução sem env:

```bash
env -i PATH="$PATH" PYTHONPATH="$PWD" .venv/bin/python scripts/eval_router_langsmith.py
```

Resultado:

```text
app.infra.config.SettingsError: Variavel obrigatoria ausente no ambiente: OPENAI_API_KEY.
```

**Correção:** verificar variáveis LangSmith sem construir settings validados ou separar validação parcial da configuração de tracing.

### 10. HIGH — Eval LangSmith não funciona como gate de regressão

**Arquivo:** `scripts/eval_router_langsmith.py:197-209`

Mesmo quando experimento roda, script imprime nome do experimento e sempre retorna `0`. Não existe threshold local, leitura de resultado agregado ou falha quando target produz erros.

**Impacto:** substituir eval offline por esse script remove bloqueio automático de regressões. Experimento pode terminar com falhas de parsing ou score abaixo do baseline sem quebrar pipeline.

**Correção:** verificar erros de runs e comparar métricas com thresholds versionados antes de retornar sucesso.

### 11. MEDIUM — Observabilidade subconta chamadas LLM, tokens e tool calls

**Arquivo:** `app/api/observability.py:46-58`, `app/api/observability.py:73-80`

Contador percorre apenas `AIMessage` armazenadas no estado. Chamada LLM do router não vira `AIMessage`, logo não entra em `llm_call_count` nem em tokens. Em turno normal com router + tool selection + synthesis, debug reporta `2` chamadas em vez de `3`.

Além disso, `tool_call_count=len(tools_used)` usa lista deduplicada de nomes. Duas execuções da mesma tool contam como uma.

**Impacto:** camada de observabilidade publicada não representa custo nem atividade real do turno.

**Correção:** registrar métricas do router e número bruto de execuções no estado ou callbacks; manter `tools_used` deduplicado apenas como dimensão separada.

### 12. HIGH — Stream SSE perde espaços entre tokens

**Arquivo:** `app/api/sse.py:70-72`

Filtro usa `text_delta.strip()` para decidir emissão. Chunks contendo somente espaço ou quebra de linha são descartados:

```text
"Hello" -> {"text_delta": "Hello"}
" "     -> None
"world" -> {"text_delta": "world"}
```

Cliente concatena deltas diretamente e renderiza `Helloworld`.

**Correção:** emitir qualquer delta não vazio; não usar `strip()` para conteúdo incremental.

### 13. MEDIUM — Stream SSE emite snapshot final duplicado

**Arquivo:** `app/api/sse.py:75-98`

Fallback de `on_chain_stream` não deduplica snapshots. No stream real do grafo fake determinístico, mesma resposta final aparece duas vezes:

```text
token {"text": "SYNTH::traffic_volume_analyzer::..."}
token {"text": "SYNTH::traffic_volume_analyzer::..."}
```

**Impacto:** CLI redesenha resposta duplicada e consumidores podem tratar snapshot repetido como novo conteúdo.

**Correção:** emitir fallback somente quando não houve deltas de chat model ou deduplicar texto final por turno.

### 14. MEDIUM — CLI encerra em SSE malformado

**Arquivo:** `app/cli/sse_client.py:49`, `app/cli/sse_client.py:63`

`_iter_sse_events()` chama `json.loads()` sem capturar `JSONDecodeError`. Resposta truncada ou payload inválido derruba `analyst-chat` com stack trace.

**Correção:** converter decode failure em erro de stream renderizável e encerrar turno sem matar sessão.

### 15. MEDIUM — README não foi atualizado para arquitetura nova

**Arquivo:** `README.md:62`, `README.md:82-91`, `README.md:249-270`

README ainda apresenta caminhos antigos como canônicos:

- `app/cli.py`;
- `app/graph/workflow.py`;
- `app/graph/llm_router.py`;
- `app/clients/bigquery_client.py`;
- `app/tools/*.py`;
- estrutura antiga sem `core/`, `agent/`, `api/`, `infra/` e pacote `cli/`.

**Impacto:** vitrine do portfólio descreve arquitetura anterior e contradiz objetivo do PR.

**Correção:** atualizar mapa de responsabilidades, árvore e comandos válidos.

### 16. HIGH — Harness readiness chama opção pytest inexistente

**Arquivo:** `scripts/run_readiness_checks.sh:31`, `scripts/run_readiness_checks.sh:34`

Script executa:

```bash
poetry run pytest ... --agent
```

Pytest não registra essa opção em `tests/conftest.py`.

Resultado:

```text
pytest: error: unrecognized arguments: --agent
```

Esse problema já existia antes da refatoração, mas invalida comando documentado em `CLAUDE.md:244-253` e `README.md:237`.

**Correção:** implementar plugin pytest para output compacto ou remover flag dos comandos pytest.

## Dívida funcional pré-existente ainda aberta

Os itens abaixo não nasceram nos commits `f9be4fc..cb9d3a4`, mas impedem afirmar que definição de pronto foi cumprida.

### 17. HIGH — Suíte padrão permanece vermelha

Comando:

```bash
poetry run pytest
```

Resultado no head revisado:

```text
6 failed, 60 passed, 8 skipped
```

Falhas:

- `tests/integration/test_api.py::test_query_debug_includes_router_decision_and_resolved_question`
- `tests/integration/test_workflow.py::test_graph_merges_date_follow_up_from_same_thread`
- `tests/integration/test_workflow.py::test_graph_routes_anaphoric_strategy_follow_up_without_new_tool_execution`
- `tests/integration/test_workflow.py::test_graph_routes_contextual_comparison_follow_up_without_new_tool_execution`
- `tests/readiness/test_readiness_suite.py::test_api_surface_covers_thread_context_and_debug`
- `tests/readiness/test_readiness_suite.py::test_graph_merges_missing_dates_follow_up`

Essas falhas já aparecem no commit pré-refactor `a219a11`. O PR melhorou duas falhas ambientais de health check no workspace principal, mas não deixa `pytest` verde.

### 18. MEDIUM — Normalização determinística de produção ignora datas explícitas

**Arquivo:** `app/core/router/date_resolution.py:16-23`

`apply_date_normalizer()` detecta sinal temporal, mas chama apenas `extract_relative_date_range()`. Parser explícito existe em `app/core/dates.py:98-126`, porém não é usado no fluxo de produção.

Consequências:

- range ISO ou brasileiro depende do LLM;
- data inválida explícita depende do LLM;
- range invertido depende do LLM;
- função `inherit_dates_from_thread()` também herda apenas períodos relativos.

Esse comportamento já existia antes da refatoração, mas contradiz documentação de normalização determinística.

**Correção:** promover parser explícito a API pública e aplicar validação determinística antes/depois do router.

### 19. MEDIUM — Herança de datas relativas recalcula janela no turno seguinte

**Arquivo:** `app/core/router/date_resolution.py:56-65`

`inherit_dates_from_thread()` relê texto humano anterior e chama `extract_relative_date_range()` sem `reference_date`. Isso usa `date.today()` novamente. Uma conversa atravessando meia-noite muda significado de `ontem`, `este mês` e janelas móveis.

**Impacto:** follow-up pode consultar período diferente daquele resolvido no turno anterior.

**Correção:** persistir intervalo normalizado no checkpoint e herdar datas resolvidas, não reprocessar texto relativo.

## Matriz da definição de pronto

| Item do plano | Status | Evidência |
|---|---|---|
| Árvore reflete arquitetura-alvo | Parcial | pastas existem, mas canônicos dependem de shims e `core/` depende de `infra/` |
| `app/utils/` removido | OK | pacote removido |
| Nenhum arquivo > ~300 linhas sem justificativa | Falha | `app/agent/nodes.py` tem 539 linhas |
| `core/` sem LangChain, FastAPI ou rede | Falha | imports em router e analytics |
| Zero import privado cross-module | Falha | imports privados em `agent/nodes.py` e `cli/sse_client.py` |
| Zero helper duplicado | Parcial | duplicatas principais removidas; não foi feita prova automatizada |
| `poetry run verify` e `poetry run pytest` verdes | Falha | verify verde; pytest com 6 falhas |
| `CLAUDE.md` e README atualizados | Falha | README segue arquitetura antiga; CLAUDE cita arquivos removidos |
| Entrypoints funcionam | Falha | `app.main:app` quebra por ciclo; `analyst-chat --help` funciona |

## Validações executadas

| Comando | Resultado |
|---|---|
| `poetry run verify --agent` | OK |
| `git diff --check 23c2c62...HEAD` | OK |
| `poetry run pytest` | Falha: `6 failed, 60 passed, 8 skipped` |
| `poetry run pytest --agent` | Falha: opção inexistente |
| `poetry run pytest -m eval` | Falha: `0 selected`, exit `5` |
| `poetry run analyst-chat --help` | OK |
| `poetry run python -c "from app.main import app"` | Falha: import circular |
| `poetry run python -m app.api.routes` | Falha: import circular |
| `bash scripts/run_readiness_checks.sh --verify` | Falha: opção pytest `--agent` inexistente |
| LangSmith script sem env | Falha: `SettingsError` em vez de skip |
| Probe do hook SQL nos caminhos novos | Falha: SQL interpolada em `app/core/analytics/queries.py` passa |
| Probe SSE com chunk `" "` | Falha: delta descartado |
| Stream SSE real com fake determinístico | Falha: snapshot final emitido duas vezes |
| Probe CLI com SSE JSON inválido | Falha: `JSONDecodeError` não tratado |

## Ordem recomendada de correção

1. Remover dependência canônica em `app.graph.tools` e restaurar startup da API.
2. Atualizar `guard_sql.py` para caminhos ativos.
3. Definir fronteira real de `core/` e mover adapters externos para fora.
4. Restaurar gate de eval funcional e corrigir skip LangSmith.
5. Corrigir SSE: preservar whitespace, deduplicar snapshot e tratar payload malformado.
6. Corrigir observabilidade para incluir router e execuções reais.
7. Resolver suíte padrão vermelha.
8. Atualizar README, CLAUDE e harness readiness.
