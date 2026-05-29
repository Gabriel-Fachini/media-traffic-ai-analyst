# Plano de Estudo — 3 Dias até Entrevista

Foco: dominar código próprio, justificar decisões, antecipar perguntas Sr Data Scientist + Especialista TI.

---

## Dia 1 — Código + LangGraph + Tool Calling

### Manhã (3h) — Releitura crítica

Lê na ordem, sem IA, anotando dúvidas:

1. `app/main.py` — contratos HTTP, `X-Debug`, tratamento `LlmTimeoutError`.
2. `app/graph/workflow.py` — `build_analytics_graph`, nodes `preprocess/agent/tool_executor`, guard `_MAX_AGENT_ITERATIONS=3`, merge follow-up.
3. `app/graph/router.py` — intents, normalização datas, clarification reasons.
4. `app/graph/llm.py` — provider, fallback, `bind_tools(tool_choice="auto")`.
5. `app/graph/tools.py` — `StructuredTool.from_function`, descrições.
6. `app/tools/channel_performance_analyzer.py` + `traffic_volume_analyzer.py` — SQL linha por linha.
7. `app/clients/bigquery_client.py`, `app/schemas/`.

Desenha em papel fluxo de 1 pergunta: HTTP → preprocess → router → agent → tool_executor → BQ → agent síntese → resposta. Sem README.

### Tarde (3h) — LangGraph + Tool Calling fundamentos

Conceitos obrigatórios:

- **StateGraph, nodes, Command, START/END** — papel de cada no grafo.
- **`TypedDict` + `Annotated[..., add_messages]`** — reducer pattern, append não-destrutivo.
- **MemorySaver / checkpointer / `thread_id`** — multi-turn em memória, some no restart.
- **Tool Calling**: LLM recebe JSON schema → retorna `AIMessage.tool_calls` → `tool_executor` roda → `ToolMessage` volta → agent sintetiza.
- **`tool_choice="auto"` vs `required` vs `none`** — auto permite resposta direta sem tool em follow-ups.
- **`StructuredTool.from_function` + `args_schema` Pydantic** — schema vira JSON enviado ao LLM, validação automática.
- **LangGraph vs LangChain AgentExecutor** — controle explícito do loop, short-circuits, guard de iteração, debug.

Docs: https://langchain-ai.github.io/langgraph/

### Noite (1h) — Pydantic

`BaseModel`, `model_dump`, `model_validate`, validators. Diferença vs dataclass. Por que escolheu (validação runtime, JSON schema gratuito pras tools).

---

## Dia 2 — SQL/BigQuery + Router + Backend

### Manhã (3h) — SQL/BigQuery (alta prioridade — Sr Data Scientist)

Saber explicar linha-por-linha `channel_performance_analyzer.py`:

- **`COUNT(DISTINCT o.order_id)`** — `order_items` tem N linhas por pedido; sem DISTINCT super-conta.
- **`SUM(CAST(oi.sale_price AS NUMERIC))`** — NUMERIC vs FLOAT64: precisão decimal, evita erro acumulado.
- **`COALESCE(u.traffic_source, 'Unknown')` + `LOWER(...)`** — NULL handling + case-insensitive.
- **`o.status = 'Complete'`** — receita realizada, exclui cancelled/returned.
- **`ScalarQueryParameter`** — parametrizado, previne SQL injection.
- **JOIN `users → orders → order_items` INNER** — só usuários que compraram (LEFT incluiria usuários sem pedido, irrelevante p/ receita).
- **`ORDER BY total_revenue DESC, total_orders DESC`** — tiebreaker.

BigQuery conceitos:

- **Billing**: bytes scanned. `SELECT *` proibido, projetar só colunas necessárias.
- **Partitioning/clustering** — não controla em dataset público, mas saber existe.
- **Dry run** (`--dry_run`) — estimar custo antes.

Variações mentais:

- Ticket médio: `SUM(sale_price) / COUNT(DISTINCT order_id)`.
- Conversion rate por canal: `users com pedido / total users` por `traffic_source` (precisa LEFT JOIN aqui).

### Tarde (3h) — Router determinístico + FastAPI

**Router (1.5h)**:

- Por que router fora do LLM: custo (regex grátis vs chamada LLM), latência, determinismo, guardrails consistentes.
- Intents: `traffic_volume`, `channel_performance`, `ambiguous_analytics`, `out_of_scope`, `strategy_follow_up`, `diagnostic_follow_up`.
- Normalização datas: `YYYY-MM-DD`, `DD/MM/AAAA`, `ontem`, `ultimos N dias`, `este mes`.
- `needs_clarification` + `clarification_reason`: missing_dates, invalid_dates, ambiguous_metric.
- Merge follow-up temporal e clarificação ambígua (`workflow.py` ~760–824).

**Backend (1.5h)**:

- FastAPI vs Flask: tipagem nativa, OpenAPI auto, validação Pydantic, async.
- Estrutura: `clients/` infra, `graph/` orquestração, `tools/` negócio+SQL, `schemas/` contratos, `utils/` config.
- Camadas de erro: `BigQueryClientError` (infra) → `ToolExecutionError` (graph) → `LlmTimeoutError` (provider) → HTTP estruturado.
- `verify`: ruff + compileall + pyright. Pyright > mypy: rápido, melhor inferência.

### Noite (1h) — LLM + visão de produto

- Temperature=0: determinismo, anti-alucinação.
- Provider fallback (`with_fallbacks`): OpenAI primário, Anthropic fallback.
- Multi-turn via `thread_id`: follow-up "quais ações priorizar?" reusa contexto sem nova query.
- Política conversacional em `app/graph/prompts.py`: pt-BR, leitura negócio, follow-up estratégico vs diagnóstico.
- Produto = "Analista Júnior", não query runner. Deliverable é insight, não tabela.

---

## Dia 3 — Simulação + Checklist + Revisão

### Manhã (2h) — Hands-on

1. `./scripts/run_local_chat.sh --debug` → roda 4 cenários README seção 5.
2. `poetry run pytest` + `poetry run verify` — sabe o que cada um cobre.
3. Pra cada cenário, narra em voz alta o fluxo interno.

### Tarde (3h) — Simulação entrevista

Responde em voz alta, gravando 3min cada:

- **"Explica arquitetura em 2 minutos."** → FastAPI recebe pergunta → preprocess roda router determinístico → se short-circuit, responde; senão agent (LLM com tools) decide tool → tool_executor roda SQL parametrizado BQ → agent sintetiza pt-BR. Multi-turn via thread_id + MemorySaver.

- **"Tool calling vs SQL gerado pela LLM?"** → segurança (anti-injection), custo previsível, queries auditáveis, schemas validados, testável deterministicamente.

- **"Métrica nova (ROAS)?"** → router recusa via `unsupported_dimension`. Adicionar = nova intent + tool + schema + prompt. ROAS precisa tabela de custos, não existe em thelook.

- **"Como escalaria?"** → Redis/Postgres checkpointer, cache queries idênticas, BQ slot reservation, fila async, observability (Langfuse/OTel).

- **"Maior fraqueza?"** → persistência in-memory, router regex frágil pra PT livre, sem cache, sem rate limit, dataset 3 tabelas.

- **"Onde IA ajudou, onde refez?"** → honesto: scaffold + regex inicial com IA; arquitetura, tool boundary, SQL, prompts dirigiu tu. Ajusta pra verdade.

- **"Como sabe que receita está certa?"** → DISTINCT em order_id, status=Complete, CAST NUMERIC, INNER JOIN coerente.

### Noite (2h) — Checklist final

#### Termos (definir em 1 frase)

Tool Calling, LangGraph StateGraph, reducer `add_messages`, Checkpointer/MemorySaver/thread_id, StructuredTool/args_schema/tool_choice=auto, Pydantic BaseModel, ScalarQueryParameter, COUNT(DISTINCT), INNER vs LEFT JOIN, NUMERIC vs FLOAT64, Router determinístico/short-circuit, Guardrails, `with_fallbacks`, Temperature 0, RAG (saber definir mesmo não usado), Pyright/ruff, FastAPI vs Flask.

#### Decisões a justificar

1. LangGraph vs AgentExecutor — controle loop + guard 3 iter.
2. Router determinístico antes LLM — custo/latência/determinismo.
3. Tools fixas vs LLM-gera-SQL — segurança/custo/auditoria.
4. 2 tools (volume vs performance) vs 1 mega — descrições precisas, LLM escolhe melhor.
5. `tool_choice="auto"` — permite follow-up sem nova query.
6. MemorySaver in-memory — escopo MVP; sabe trocar p/ Redis.
7. FastAPI — tipagem + Pydantic + OpenAPI.
8. Temperature=0 — determinismo analítico.
9. pt-BR + leitura negócio — produto é analista.
10. CLI consome própria API — mesmo contrato de cliente real.
11. Fallback OpenAI↔Anthropic — resiliência.
12. `status='Complete'` — receita realizada.
13. `COUNT(DISTINCT order_id)` — anti over-count join.
14. `CAST AS NUMERIC` — precisão decimal.
15. Limitações explícitas (sem ROAS, sem UI, sem persistência durável) — maturidade de escopo.

#### Sinal extra por entrevistador

- **Sr Data Scientist**: SQL fundo, viés dataset, soundness. "Como sabe receita correta?" → DISTINCT + status=Complete + NUMERIC + JOIN logic.
- **Especialista TI**: arquitetura, segurança, deploy, custo, observability. Saber: credenciais segregadas, SQL parametrizado, fallback provider, deploy em Cloud Run/Functions, custo/request (tokens LLM + BQ bytes).

#### Última hora antes da call

- Abre `app/graph/workflow.py` + `app/tools/channel_performance_analyzer.py` em abas.
- Diagrama mermaid README na cabeça.
- Roda `./scripts/run_local_chat.sh` 1x — confirma OK.
- 3 melhorias futuras prontas: durable checkpointer, eval suite, cache queries.

---

## Material de Apoio

Aviso: URLs específicas de vídeos do YouTube mudam. Onde não tenho certeza absoluta, dou **busca sugerida** em vez de link direto. Cola no YouTube.

### Docs oficiais (links confiáveis)

**LangGraph / LangChain**
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- LangGraph tutorial agent básico: https://langchain-ai.github.io/langgraph/tutorials/introduction/
- LangGraph concepts (state, nodes, edges, checkpointer): https://langchain-ai.github.io/langgraph/concepts/
- LangChain Tool Calling: https://python.langchain.com/docs/concepts/tool_calling/
- StructuredTool: https://python.langchain.com/docs/how_to/custom_tools/

**Pydantic**
- Docs v2: https://docs.pydantic.dev/latest/
- Migração v1→v2: https://docs.pydantic.dev/latest/migration/

**FastAPI**
- Tutorial: https://fastapi.tiangolo.com/tutorial/
- Async + concurrency: https://fastapi.tiangolo.com/async/

**BigQuery**
- Python client: https://cloud.google.com/python/docs/reference/bigquery/latest
- Query parameters (anti-injection): https://cloud.google.com/bigquery/docs/parameterized-queries
- Best practices custo: https://cloud.google.com/bigquery/docs/best-practices-costs
- Dataset thelook_ecommerce: https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce

**Providers LLM**
- OpenAI function calling: https://platform.openai.com/docs/guides/function-calling
- Anthropic tool use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use

### Artigos

- "ReAct: Synergizing Reasoning and Acting" (paper original do padrão agente): https://arxiv.org/abs/2210.03629
- Anthropic — "Building effective agents": https://www.anthropic.com/research/building-effective-agents
- LangChain blog — agents vs chains: https://blog.langchain.dev/

### YouTube — PT-BR (canais + buscas)

Cola busca no YouTube (não invento URL de vídeo específico):

**LangChain / LangGraph (PT-BR)**
- Canal **Asimov Academy** — busca: `LangChain português`, `LangGraph agente`
- Canal **Diolinux / Asimov / Hashtag Treinamentos** — busca: `agente IA python tool calling`
- Busca geral: `LangGraph tutorial português`, `criar agente LLM python`

**FastAPI (PT-BR)**
- Canal **Eduardo Mendes (Dunossauro)** — playlist FastAPI completa. Busca: `Dunossauro FastAPI`
- Canal **Otávio Miranda** — busca: `Otavio Miranda FastAPI`

**Pydantic (PT-BR)**
- Busca: `Pydantic v2 português`, `Dunossauro Pydantic`

**BigQuery + SQL (PT-BR)**
- Canal **Téo Me Why** — busca: `Teo Me Why BigQuery`, `Teo Me Why SQL`
- Canal **Programação Dinâmica** — busca: `BigQuery SQL português`
- Busca: `BigQuery custo otimização português`

**Conceitos de Agente / RAG (PT-BR)**
- Canal **Asimov Academy** — busca: `RAG português`, `agente IA`
- Canal **Filipe Deschamps** — busca: `Filipe Deschamps LLM agente`

### YouTube — EN (qualidade maior em alguns tópicos)

**LangGraph (essencial — oficial)**
- Canal oficial **LangChain** no YouTube — busca: `LangChain LangGraph deep dive`, `LangGraph tool calling`, `LangGraph multi-agent`
- Busca: `LangGraph from scratch`, `LangGraph state graph tutorial`

**Tool Calling fundamentos**
- Busca: `OpenAI function calling tutorial`, `Anthropic tool use Claude`

**Agentes — conceitos**
- Canal **Andrej Karpathy** — busca: `Karpathy LLM agents`
- Canal **AI Engineer** — busca: `AI Engineer agents production`

**BigQuery avançado**
- Canal oficial **Google Cloud Tech** — busca: `BigQuery best practices`, `BigQuery cost optimization`

**FastAPI prod**
- Canal **ArjanCodes** — busca: `ArjanCodes FastAPI`
- Canal **TechWithTim** — busca: `FastAPI tutorial`

### Ordem sugerida de consumo (se tempo curto)

**Prioridade 1 (Dia 1)**
1. LangGraph concepts (docs) — 30min.
2. YouTube EN: `LangGraph tool calling tutorial` — 1 vídeo de ~30min.
3. LangChain Tool Calling docs — 20min.

**Prioridade 2 (Dia 2)**
1. BigQuery parameterized queries doc — 15min.
2. YouTube PT: `Teo Me Why BigQuery` — 1 vídeo.
3. FastAPI tutorial (skim, já usa) — 20min.

**Prioridade 3 (Dia 3)**
1. Anthropic "Building effective agents" — 30min leitura.
2. ReAct paper (skim seções 1-3) — 20min.

### Cheat-sheet de busca rápida durante estudo

Se trava em algo, busca exatamente:
- "langgraph add_messages reducer"
- "langgraph checkpointer thread_id"
- "langchain bind_tools tool_choice auto"
- "bigquery scalar query parameter python"
- "pydantic model_dump model_validate v2"
- "fastapi pydantic response_model"
