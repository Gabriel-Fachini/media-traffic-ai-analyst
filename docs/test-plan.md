# Test Plan

## Objetivo

Estabelecer uma camada de confianca automatizada alinhada aos criterios de `case.md`, migrando a validacao que estava espalhada em `scripts/` para uma estrategia sustentavel com `pytest`.

O plano tambem funciona como checkpoint de seguranca do projeto: ele separa o que ja esta protegido por testes do que ainda precisa ser coberto antes das proximas iteracoes, especialmente nas frentes de produto.

## Estrategia

- `poetry run verify`
  - gate rapido sem testes
  - cobre lint, compilacao sintatica e type-check
- `poetry run pytest`
  - suite deterministica padrao
  - cobre regras de roteamento, contratos, workflow e API sem depender de providers externos
- `poetry run pytest -m live`
  - suite opt-in com BigQuery e/ou LLM reais
  - valida integracao de ambiente perto da entrega
- `poetry run pytest --run-live`
  - modo combinado
  - executa a suite local e inclui os testes `live` no mesmo run

## Estado atual validado

- `poetry run verify`
  - valido como gate local rapido
  - cobre `ruff`, `compileall` e `pyright`
- `poetry run pytest`
  - suite deterministica funcional
  - hoje cobre router basico, contracts basicos, analyzers, workflow principal e API
- `poetry run pytest -m live`
  - suite opt-in ja estruturada
  - ainda depende de execucao final com ambiente configurado para virar checkpoint de entrega

## Principio de priorizacao

- Prioridade 0
  - testes que protegem diretamente os criterios de maior peso do `case.md`: arquitetura do agente, backend e visao de produto
- Prioridade 1
  - testes que aumentam robustez em contratos, infraestrutura e cenarios negativos relevantes
- Prioridade 2
  - testes de acabamento, ergonomia e confianca complementar

## Matriz de cobertura

| Criterio de avaliacao | Cobertura automatizada | Origem migrada de `scripts/` | Lacunas / observacoes |
| --- | --- | --- | --- |
| Arquitetura do Agente | Router basico, workflow com short-circuits, merge temporal, follow-up estrategico/diagnostico, continuidade por `thread_id`, reset de campos overwrite-style, API com `TestClient` | `manual_validate_router_dates.py`, `manual_validate_router_semantics.py`, `manual_validate_graph_responses.py`, `manual_validate_api.py` | Ainda faltam casos de refusal do router, follow-up de `ambiguous_metric`, merge apos `invalid_dates` e branches de erro do workflow |
| Qualidade do Backend Python | Validacoes Pydantic de `QueryRequest` e `Settings`, metadata HTTP, `X-Debug`, timeout estruturado, gate `ruff + compileall + pyright` | `manual_validate_api.py` | Ainda faltam validadores dos contratos de router/tools, cenarios negativos adicionais da API e wrappers de infraestrutura |
| Engenharia de Dados (SQL) | Testes unitarios dos analyzers com `BigQueryClient` fake, verificando parametros, uso de SQL parametrizada e mapeamento de rows; testes `live` executando queries reais | `manual_validate_tools.py`, `smoke_test_bigquery.py` | Nao mede performance absoluta da query; ainda faltam testes unitarios do wrapper `BigQueryClient` e checkpoint `live` final no ambiente real |
| Visao de Produto | Hoje a suite cobre follow-ups estrategicos/diagnosticos, short-circuits por falta de datas e respostas finais nao vazias em fluxos validos | `manual_validate_graph_responses.py`, `manual_validate_api.py` | Ainda faltam provas automatizadas de out-of-scope, unsupported metric/source, comparacao entre canais e cenarios que vao sustentar as proximas melhorias de produto |

## Suite por camada

### Unit

- Router:
  - coberto hoje:
    - datas brasileiras e relativas
    - prioridade de `invalid_dates`
    - aliases semanticos de receita
    - clarificacao guiada para metrica ambigua
  - faltante prioritario:
    - datas ISO `YYYY-MM-DD`
    - `empty_question`
    - `out_of_scope` generico
    - `unsupported_metric`
    - `unsupported_dimension`
    - `unsupported_traffic_source`
    - comparacao suportada entre canais
    - datas explicitas invertidas (`start_date > end_date`)
    - garantia de que perguntas sem escopo analitico nao entram em clarificacao indevida
- Tools:
  - coberto hoje:
    - parametros `@start_date`, `@end_date`, `@traffic_source`
    - mapping para `TrafficVolumeOutput` e `ChannelPerformanceOutput`
  - faltante prioritario:
    - wrapper `BigQueryClient` convertendo `SettingsError`, `DefaultCredentialsError` e `GoogleAPIError` em erro tratado
    - `smoke_test_thelook_dataset()` retornando fallback seguro quando nao houver linhas
- Contratos:
  - coberto hoje:
    - `QueryRequest`
    - `Settings`
  - faltante prioritario:
    - consistencia de `RouterDecision`
    - parsing e ordenacao de datas em `DateRangeInput`
    - normalizacao de `traffic_source` nos contratos das tools

### Integration

- Workflow LangGraph com tools fake e synthesis fake:
  - coberto hoje:
    - execucao de tool correta por intencao
    - short-circuit sem tool
    - merge de follow-up temporal por `missing_dates`
    - follow-up estrategico sem nova consulta
    - follow-up diagnostico sem nova consulta
    - reset de campos overwrite-style entre turnos
  - faltante prioritario:
    - merge apos `invalid_dates`
    - merge apos `ambiguous_metric`
    - follow-up que deve permanecer fora de escopo sem contexto analitico previo
    - erro de tool retornando `TEMPORARY_TOOL_FAILURE_MESSAGE`
    - tool esperada ausente
    - timeout do synthesizer propagado como `LlmTimeoutError`
    - falha nao-timeout do synthesizer retornando `TEMPORARY_LLM_FAILURE_MESSAGE`
    - preservacao de `ToolMessage.artifact` como payload de debug interno
- API FastAPI com `TestClient`:
  - coberto hoje:
    - `/health`
    - `/query` com `thread_id` gerado e preservado
    - `X-Debug`
    - timeout estruturado
    - erro 422 para payload invalido
  - faltante prioritario:
    - payload com campo extra rejeitado
    - `debug` ausente quando `X-Debug` nao e enviado
    - filtragem de erros malformados em `_build_debug_info_from_state()`
    - erro 500 sem `debug` quando o header nao estiver ativo

### Live

- BigQuery real:
  - coberto hoje:
    - smoke curto do dataset
    - cenarios fixos das tools em janeiro/2024
  - faltante prioritario:
    - checkpoint final de execucao com ambiente real antes da entrega
- LLM real:
  - coberto hoje:
    - `build_tool_enabled_llm()` emitindo `tool_calls`
  - faltante prioritario:
    - smoke de fallback entre provider/modelo quando configurado
- End-to-end real:
  - coberto hoje:
    - `invoke_analytics_graph(...)`
    - `/query` via FastAPI com ambiente configurado
  - faltante prioritario:
    - rodada final com perguntas de demo que reflitam a visao de produto esperada

## Backlog priorizado de testes faltantes

### Prioridade 0

- Router:
  - refusals e guardrails de produto: `unsupported_metric`, `unsupported_dimension`, `unsupported_traffic_source`, `out_of_scope` puro e `empty_question`
  - datas ISO e datas invertidas
  - comparacao entre canais suportados
- Workflow:
  - merge de follow-up apos `invalid_dates`
  - merge de follow-up apos `ambiguous_metric`
  - branches de erro: tool falhando, tool ausente, falha temporaria do synthesizer, timeout do synthesizer
- API:
  - cenarios negativos que comprovem contrato e debug apenas quando solicitado
- Live:
  - checkpoint real de BigQuery + provider LLM antes da entrega final

### Prioridade 1

- Contratos:
  - validadores de `RouterDecision`
  - validadores de `DateRangeInput` e `ToolInputBase`
- Infraestrutura:
  - `BigQueryClient`
  - `build_analytics_llm()` e `build_tool_enabled_llm()` com e sem fallback
- Workflow/API:
  - casos de debug com payload de erro parcialmente invalido
  - follow-up sem contexto analitico anterior permanecendo fora de escopo

### Prioridade 2

- CLI:
  - smoke tests de `_build_request()`, `_extract_error_response()` e `_submit_question()` com `httpx` fake
- Produto:
  - harness de regressao com perguntas de demo para verificar respostas nao vazias, recusas curtas e follow-ups uteis
- Entrega:
  - quando o README final estiver pronto, smoke de setup documentado para reduzir risco de reproducao pelo avaliador

## Mapeamento dos scripts migrados

| Script antigo | Destino principal |
| --- | --- |
| `manual_validate_router_dates.py` | `tests/unit/test_router.py` |
| `manual_validate_router_semantics.py` | `tests/unit/test_router.py` |
| `manual_validate_tools.py` | `tests/unit/test_tools.py` + `tests/live/test_live_validation.py` |
| `smoke_test_bigquery.py` | `tests/live/test_live_validation.py` |
| `tool_binding.py` | `tests/live/test_live_validation.py` |
| `manual_validate_graph_responses.py` | `tests/integration/test_workflow.py` + `tests/live/test_live_validation.py` |
| `manual_validate_api.py` | `tests/integration/test_api.py` + `tests/live/test_live_validation.py` |

## Criterios de aceite

- `poetry run verify` passa
- `poetry run pytest` passa sem ambiente externo
- `poetry run pytest -m live` passa quando credenciais e chaves estiverem configuradas
- `poetry run pytest --run-live` passa quando o ambiente `live` estiver configurado
- os testes de Prioridade 0 passam
- `agents.md` e este documento refletem o comportamento real do codigo
- a suite automatizada oferece um checkpoint confiavel para continuar as melhorias de produto sem regressao silenciosa
