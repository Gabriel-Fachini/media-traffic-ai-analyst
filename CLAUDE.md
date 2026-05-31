# Media Traffic AI Analyst - Agents Blueprint

## 1. Objetivo atual

Projeto de portfolio: um agente de analytics para Midia e Growth que demonstra
engenharia de agentes LLM com decisoes deliberadas, capaz de:

- entender perguntas em linguagem natural sobre trafego, pedidos e receita por canal;
- consultar dados reais do dataset `bigquery-public-data.thelook_ecommerce`;
- responder em linguagem natural com tool calling, sem depender de um prompt monolitico;
- sustentar uma camada de confianca com verificacoes automatizadas, eval harness do
  router e smoke tests opt-in.

O escopo de dominio e intencionalmente estreito; o objetivo e a qualidade de
engenharia (roteamento LLM com structured output, hibrido determinismo/LLM,
contratos tipados, SQL parametrizada, harness de avaliacao). Roadmap em
`PLANO_EVOLUCAO.md`.

## 2. Estado atual do produto

- Dominio: analise de trafego e receita por canal no dataset `thelook_ecommerce`.
- Fonte de dados: tabelas `users`, `orders` e `order_items`.
- Superficie de execucao:
  - API FastAPI com `/health` e `/query`
  - CLI `analyst-chat`, conversacional, consumindo a API local
- Persistencia conversacional atual:
  - `thread_id` opcional no contrato HTTP
  - continuidade multi-turn em memoria via `MemorySaver`
  - nao ha persistencia duravel entre reinicios do processo
- Roteamento: LLM-based via `classify_question` em `app/graph/llm_router.py`
  com `with_structured_output(RouterDecision)`; normalizacao de datas permanece
  deterministica em `app/graph/date_normalizer.py`
- Formatos temporais suportados na normalizacao de datas:
  - `YYYY-MM-DD`
  - `DD/MM/AAAA`
  - `DD/MM/AA`
  - `ontem`, `este mes`, `ultimo mes`, `ultimos N dias`
- Follow-ups suportados (classificados pelo router LLM com contexto do thread):
  - clarificacao de datas
  - clarificacao guiada de metrica ambigua
  - follow-up estrategico
  - follow-up diagnostico
- Modo debug:
  - header `X-Debug`
  - devolve `resolved_question`, `router_decision` e erros tecnicos estruturados

## 3. Requisitos de plataforma

- Linguagem: Python 3.10+
- API: FastAPI
- Interface inicial: terminal/CLI
- Orquestrador: LangGraph
- Dados: `google-cloud-bigquery` com SQL parametrizada
- Modelagem e contratos: Pydantic + type hints
- LLM:
  - provider principal configurado por ambiente
  - suporte atual a OpenAI e Anthropic
  - fallback opcional entre providers/modelos

## 4. Arquitetura atual de agentes

### 4.1 Router Agent

Implementacao: `app/graph/llm_router.py` — `classify_question(question, thread_context, settings) -> RouterDecision`

- Classificacao via LLM com `with_structured_output(RouterDecision)`.
- Contexto do thread (ultimas 6 mensagens nao-system) passado para deteccao de follow-up.
- Normalizacao de `start_date` e `end_date` permanece deterministica (`app/graph/date_normalizer.py`).
- Classificacao de intent:
  - `traffic_volume`
  - `channel_performance`
  - `strategy_follow_up`
  - `diagnostic_follow_up`
  - `ambiguous_analytics`
  - `out_of_scope`
- Short-circuits determiniscos (sem chamar LLM) para:
  - pergunta vazia (guard em `preprocess_node` antes do router)
- Short-circuits via router LLM (`needs_clarification=True` ou `refusal_reason != None`):
  - fora de escopo, dimensao nao suportada, metrica nao suportada, canal nao suportado
  - datas ausentes, datas invalidas
  - ambiguidade entre volume e performance financeira

### 4.2 Traffic Volume Analyzer Agent

- Tool: `traffic_volume_analyzer(TrafficVolumeInput)`
- Query: agregacao em `users` com `COUNT(DISTINCT id)`
- Filtros: periodo obrigatorio e `traffic_source` opcional
- Saida: `TrafficVolumeOutput`

### 4.3 Channel Performance Analyzer Agent

- Tool: `channel_performance_analyzer(ChannelPerformanceInput)`
- Query: `users -> orders -> order_items`
- Metricas: `total_orders` e `total_revenue`
- Saida: `ChannelPerformanceOutput`

### 4.4 Sintese (node `agent`)

- nao e um node separado; a sintese final em pt-BR e produzida pelo proprio node
  `agent` (LLM com `bind_tools(..., tool_choice="auto")`) apos o `tool_executor`
  injetar os `ToolMessage` no historico;
- prompts dedicados em `app/graph/prompts.py` (`build_conversation_system_prompt`)
  cobrem politica conversacional, sintese de dados e follow-ups estrategicos/diagnosticos;
- falhas temporarias de LLM (`LlmTimeoutError`) sao convertidas em resposta tratada.

### 4.5 Scope Guard (short-circuits no `preprocess`)

- nao e um node separado; recusas curtas e educadas sao emitidas como short-circuit
  dentro do node `preprocess` (`Command(goto="__end__")` com `final_answer` pronta);
- a decisao vem do router LLM (`needs_clarification` / `refusal_reason`): fora de
  escopo, dimensao/metrica/canal nao suportado, datas ausentes ou invalidas, ambiguidade.

## 5. Fluxo orquestrado atual

`StateGraph` com 3 nodes e roteamento dinamico via `Command(goto=...)`
(`app/graph/workflow.py`). Nao ha `add_conditional_edges` nem branch por intent
para analyzers separados — as analises sao tools vinculadas ao node `agent`.

Nodes e arestas:

- `START -> preprocess`
- `preprocess`:
  - guard de pergunta vazia + router LLM (`classify_question`) + normalizacao
    deterministica de datas (`date_normalizer`);
  - short-circuit (`Command(goto="__end__")`) com `final_answer` pronta para
    recusas/clarificacoes/datas invalidas;
  - caso valido: `Command(goto="agent")`.
- `agent` (LLM com `bind_tools(..., tool_choice="auto")`):
  - se o LLM emitir `tool_calls`: `Command(goto="tool_executor")`;
  - senao: resposta final em pt-BR e `Command(goto="__end__")`.
- `tool_executor`:
  - executa as tools solicitadas, injeta `ToolMessage` no historico;
  - `add_edge("tool_executor", "agent")` — loopa de volta para sintese.
- Retorno para API quando o grafo atinge `__end__`.

Observacoes importantes:

- o grafo usa `thread_id` para retomar contexto em memoria (`MemorySaver`, cache via `lru_cache`);
- campos overwrite-style como `final_answer` e `tools_used` sao resetados a cada turno para evitar vazamento entre checkpoints;
- follow-ups de clarificacao podem fundir a pergunta anterior com a atual quando o contexto for valido.

## 6. Contratos de dados atuais

### 6.1 Input das tools

- `TrafficVolumeInput`
  - `traffic_source: Optional[str]`
  - `start_date: date`
  - `end_date: date`
- `ChannelPerformanceInput`
  - `traffic_source: Optional[str]`
  - `start_date: date`
  - `end_date: date`

### 6.2 Contrato HTTP

- `QueryRequest`
  - `question: str` (max 1000, nao vazia)
  - `thread_id: Optional[str]`
- `QueryResponse`
  - `answer: str`
  - `tools_used: list[str]`
  - `metadata: QueryMetadata | None`
- `QueryMetadata`
  - `thread_id: str`
  - `thread_id_source: "generated" | "provided"`
  - `context_message_count: int`
  - `debug: DebugInfo | None`

## 7. Politica de seguranca e confiabilidade

- SQL sempre parametrizada; nao concatenar input de usuario na query.
- Falhas de BigQuery sao encapsuladas em `BigQueryClientError`.
- Timeout de LLM e convertido em erro HTTP 500 estruturado.
- O modo debug nao expoe stack trace bruto; retorna apenas diagnostico resumido.
- Persistencia atual e apenas em RAM. Reiniciar o processo elimina o contexto multi-turn.

## 8. Pipeline de validacao atual

### 8.1 Gate sem testes

Antes de considerar uma alteracao tecnica concluida, rodar:

- `poetry run verify`
- `poetry run verify --agent`
  - modo enxuto para iteracoes com agentes, mantendo apenas status por etapa e detalhes curtos em caso de falha

O comando executa:

1. `poetry run ruff check app scripts tests`
2. `python3 -m compileall app scripts tests`
3. `poetry run pyright`

### 8.2 Suite automatizada

- `poetry run pytest`
  - suite deterministica padrao
  - nao depende de BigQuery nem de providers LLM externos
- `poetry run pytest --agent`
  - mesma suite padrao com output minimizado para reduzir consumo de tokens durante iteracoes
- `poetry run pytest -m live`
  - smoke/integration tests opt-in
  - usa BigQuery e/ou providers LLM reais quando o ambiente estiver configurado
- `poetry run pytest --run-live`
  - modo combinado
  - roda a suite padrao e inclui tambem os testes `live`
- `poetry run pytest --run-live --agent`
  - modo combinado com output enxuto

### 8.3 Cobertura esperada da suite

- unit:
  - roteador
  - contratos Pydantic
  - configuracao
  - analyzers com client fake
- integration:
  - workflow LangGraph com tools e synthesis fake
  - API FastAPI com `TestClient` e dependency overrides
- live:
  - tools reais no BigQuery
  - tool binding do LLM
  - graph/API end-to-end com ambiente configurado

## 9. Mapeamento com as fases (PLANO_EVOLUCAO.md)

- Fase 0 (eval harness): concluida — `tests/eval/` com `router_cases.jsonl`,
  `test_router_eval.py` (marker `eval`), baseline documentado.
- Fase 1 (router LLM): concluida — `app/graph/llm_router.py` (classify_question),
  `app/graph/date_normalizer.py` (datas deterministicas), `app/graph/router.py`
  deletado, router deterministico movido para `tests/deterministic_router.py`.
- Fase 2 (observabilidade + streaming): pendente
- Fase 3 (tool de visualizacao): pendente
- Fase 4 (persistencia SqliteSaver): pendente
- Fase 5 (interface visual de chat): pendente

## 10. Diretrizes de escopo atuais

- Priorizar implementacao simples e incremental.
- Manter `traffic_source` singular no contrato das tools.
- Comparacoes entre canais devem continuar preferindo consulta agregada com sintese na camada final.
- Nao incluir UI web nesta fase.
- Nao incluir observability/custos como eixo principal nesta fase.
- `README.md` e a vitrine do portfolio: mantido sincronizado com o estado real.

## 11. Definition of Done atual de `agents.md`

- estado real do projeto documentado;
- fronteiras de escopo atuais explicitas;
- contratos e limitacoes operacionais registradas;
- pipeline de verificacao e estrategia de testes automatizados documentadas.

## 12. Harness do Claude Code

Config em `.claude/settings.json`; scripts em `.claude/hooks/` (Python, falham
seguro: erro proprio -> exit 0, nunca travam o trabalho).

### 12.1 Hooks ativos

| Hook | Evento | Matcher | Acao |
|---|---|---|---|
| `guard_secrets.py` | `PreToolUse` | `Read\|Edit\|Write\|NotebookEdit\|Bash` | **Bloqueia** (exit 2) leitura/edicao de `.env`, `credentials/*.json`, `google.json`; pega tambem `cat`/`head`/etc no Bash. `.env.example` liberado. Protege chaves OpenAI/Anthropic e service account GCP de vazar no contexto. |
| `guard_sql.py` | `PreToolUse` | `Edit\|Write` | **Bloqueia** (exit 2) SQL nao-parametrizada (f-string/`.format()`/`%`/concat perto de keyword SQL) em `app/tools/*.py` e `bigquery_client.py`. Torna mecanica a invariante "SQL sempre parametrizada". |
| `post_edit_ruff.py` | `PostToolUse` | `Edit\|Write` | Roda `poetry run ruff check <arquivo>` em `.py` sob `app/`/`scripts/`/`tests/`. Erros voltam como feedback (exit 2). Pyright/compileall seguem no gate manual `verify`. |
