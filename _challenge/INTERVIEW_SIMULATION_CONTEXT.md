# Contexto e Roteiro para Simulação de Entrevista Técnica

> **Uso:** este arquivo é o briefing para um agente de IA externo simular uma entrevista técnica com o candidato **Gabriel Fachini** para a vaga de **Technology Specialist (AI & Automation) — Monks**. O agente deve usar o contexto da Seção 1 para entender o projeto entregue, e a Seção 2 como banco de perguntas. O agente NÃO deve revelar respostas; deve fazer perguntas, ouvir, pedir aprofundamento e desafiar inconsistências.

---

## 1. Contexto do Projeto Entregue

### 1.1 A Vaga (Monks — Technology Specialist AI & Automation)

- Modelo: remoto, efetivo, área de Mídias Pagas / Núcleo de Inovação.
- Foco: construir agentes de IA e automações que substituem fluxos manuais em Mídia/Operações; cultura AI‑First; intersecção Engenharia × Produto.
- Stack esperada: Python backend, LangChain/LangGraph/LlamaIndex, FastAPI/Flask, Pandas, BigQuery, GCP (Cloud Run/Functions), Tool Calling, RAG, APIs Meta/Google Ads.
- Diferenciais: Apps Script, React/Next, Vector DBs, Make/n8n.

### 1.2 O Case

Construir MVP de **Agente de IA Autônomo** que atua como **Analista Júnior de Mídia**:
- Recebe perguntas em linguagem natural.
- Cruza `users.traffic_source` com `orders`/`order_items` no dataset público `bigquery-public-data.thelook_ecommerce`.
- Responde com insight de negócio, não com tabela bruta.
- **Obrigatório:** Python 3.10+, FastAPI/Flask, LangChain/LangGraph/LlamaIndex, **Tool Calling real**, SQL parametrizada via cliente oficial BigQuery, sem prompt monolítico.
- Critérios avaliados: Arquitetura do Agente (Alto), Backend Python (Alto), SQL (Médio), Visão de Produto (Alto).

### 1.3 Entrega Implementada — Resumo Técnico

**Stack escolhida:** Python 3.10+, FastAPI, LangGraph, Pydantic, `google-cloud-bigquery`, OpenAI (com fallback Anthropic), Poetry, pyright, ruff.

**Superfícies expostas:**
- `GET /health` e `POST /query` (FastAPI)
- CLI `analyst-chat` que consome a própria API (mesmo contrato de cliente real)
- Header `X-Debug` retorna `resolved_question`, `router_intent`, `agent_tool_calls`, erros estruturados
- `thread_id` opcional → continuidade multi-turn via `MemorySaver` (in‑memory, some no restart)

**Grafo LangGraph** (`app/graph/workflow.py`):
```
preprocess (router + guardrails)
    ├─ short-circuit → resposta curta / pedido de clarificação
    └─ intent válida → agent (LLM com tools)
                         ├─ tool_call → tool_executor → BigQuery → agent
                         └─ resposta final pt-BR
```
- Loop `preprocess → agent → tool_executor → agent` com guard `_MAX_AGENT_ITERATIONS=3`.
- `bind_tools(..., tool_choice="auto")` → LLM decide se chama tool ou responde direto (importante para follow-ups).
- Reducer pattern: state usa `Annotated[..., add_messages]` para append não-destrutivo de mensagens.
- Campos overwrite-style (`final_answer`, `tools_used`) resetados a cada turno para não vazar entre checkpoints.

**Router determinístico** (`app/graph/router.py`, ~30KB — peça grande):
- Intents: `traffic_volume`, `channel_performance`, `strategy_follow_up`, `diagnostic_follow_up`, `ambiguous_analytics`, `out_of_scope`.
- Normaliza datas: `YYYY-MM-DD`, `DD/MM/AAAA`, `DD/MM/AA`, `ontem`, `este mes`, `ultimo mes`, `ultimos N dias`.
- Emite short-circuits para: pergunta vazia, fora de escopo, dimensão/métrica/canal não suportados, datas ausentes/inválidas, ambiguidade volume vs financeira.
- Funde pergunta anterior com atual em follow-ups de clarificação (mesmo `thread_id`).
- **Razão da escolha:** custo (regex grátis vs chamada LLM), latência, determinismo, guardrails consistentes.

**Tools** (`app/graph/tools.py`):
- `StructuredTool.from_function(...)` com `args_schema` Pydantic → JSON schema enviado ao LLM, validação automática.
- `traffic_volume_analyzer(start_date, end_date, traffic_source?)` → `users`, `COUNT(DISTINCT id)`.
- `channel_performance_analyzer(start_date, end_date, traffic_source?)` → `users → orders → order_items`, `COUNT(DISTINCT order_id)`, `SUM(CAST(sale_price AS NUMERIC))`.
- Descrições explicitam **quando NÃO usar** (anti-confusão entre as duas tools).
- Apenas um `traffic_source` por chamada; comparações entre canais usam consulta agregada (`traffic_source=None`) e síntese final.

**SQL — decisões a defender:**
- `COUNT(DISTINCT o.order_id)` — `order_items` tem N linhas/pedido; sem DISTINCT super-conta.
- `CAST(sale_price AS NUMERIC)` — precisão decimal, evita erro acumulado de FLOAT64.
- `o.status = 'Complete'` — receita realizada, exclui cancelled/returned.
- `COALESCE(traffic_source, 'Unknown')` + `LOWER(...)` — NULL handling + case-insensitive.
- `INNER JOIN users → orders → order_items` — para receita, só usuários que compraram. (Conversion rate exigiria LEFT JOIN.)
- `bigquery.ScalarQueryParameter` em tudo — anti SQL injection.
- `ORDER BY total_revenue DESC, total_orders DESC` — tiebreaker.
- Filtro por `DATE(o.created_at)` em performance (data do pedido), `DATE(created_at)` em volume (data de signup do usuário) — **distinção semântica importante**.

**LLM** (`app/graph/llm.py`):
- Provider configurável via env (`LLM_PROVIDER=openai|anthropic`).
- `temperature=0` para determinismo analítico.
- `with_fallbacks([fallback_model])` — resiliência entre providers.
- `LlmTimeoutError` customizado → captura `TimeoutError`, `httpx.TimeoutException`, `OpenAIAPITimeoutError`, `AnthropicAPITimeoutError` → vira HTTP 500 estruturado em `main.py`.

**Camadas de erro:**
- `BigQueryClientError` (infra) → `ToolExecutionError` (graph) → `LlmTimeoutError` (provider) → `ErrorResponse` HTTP.
- Debug mode não vaza stack trace bruto.

**Contratos Pydantic** (`app/schemas/`):
- `QueryRequest`: `question: str` (max 1000, não vazia), `thread_id: Optional[str]`.
- `QueryResponse`: `answer`, `tools_used: list[str]`, `metadata: QueryMetadata`.
- `QueryMetadata`: `thread_id`, `thread_id_source` ("generated"|"provided"), `context_message_count`, `debug: DebugInfo | None`.
- Tools input/output tipados (`TrafficVolumeInput/Output`, `ChannelPerformanceInput/Output`).

**Pipeline de verificação:**
- `poetry run verify` = `ruff check` + `compileall` + `pyright`.
- `poetry run pytest` = suite determinística (unit + integration, sem BQ/LLM real).
- `poetry run pytest -m live` = smoke opt-in com BQ e LLM reais.
- Estrutura: `tests/unit`, `tests/integration`, `tests/live`, `tests/readiness`.

**Limitações intencionais (admitidas no README):**
- Sem persistência durável (restart apaga contexto multi-turn).
- Sem UI web.
- Sem métricas fora do schema (ROAS, CAC, CTR, CPC, CPM).
- Dataset limitado a `users`, `orders`, `order_items`.
- Um `traffic_source` por tool call.
- Sem cache, sem rate limit, sem observability.

### 1.4 Estrutura do Repositório

```
app/
  clients/bigquery_client.py    # cliente oficial BQ + BigQueryClientError
  graph/
    workflow.py                  # StateGraph, nodes preprocess/agent/tool_executor
    router.py                    # intents, datas, guardrails (regex)
    prompts.py                   # política conversacional, síntese, follow-ups
    llm.py                       # provider + fallback + bind_tools
    tools.py                     # StructuredTool registry
  tools/
    traffic_volume_analyzer.py
    channel_performance_analyzer.py
  schemas/                       # contratos Pydantic
  main.py                        # FastAPI
  cli.py                         # analyst-chat
  verify.py                      # ruff + compileall + pyright
tests/{unit,integration,live,readiness}
scripts/run_local_chat.sh        # sobe API + abre CLI debug
docs/{workflow.md,test_checklist.md,results.md}
```

### 1.5 Dúvidas Reais do Candidato (de `perguntas.md`)

Tópicos que o candidato ainda quer firmar — entrevistador pode (e deve) tocar:
1. Agent node próprio vs LangGraph ReAct agent pré-fabricado.
2. Por que não há edge explícito com constante `END` em algumas transições.
3. Tradeoff router determinístico vs router ML/LLM-based.
4. Mecânica do router: como classifica intent, é node ou não.
5. Versionamento LangGraph (v1 → v2).
6. Como justificar decisões de tecnologia dentro das opções permitidas.
7. Variação de query para conversion rate (LEFT JOIN).
8. O que é eval suite.
9. O que é LRU cache, como funciona.

---

## 2. Roteiro de Entrevista — Banco de Perguntas

> **Instruções para o agente entrevistador:**
> - Mistura perguntas de blocos diferentes; não siga linear.
> - Para cada resposta, faça 1-2 follow-ups que aprofundem ("por que não X?", "como você defenderia se eu disser que Y é melhor?").
> - Se o candidato titubear, ofereça pista mínima e veja se ele constrói sozinho.
> - Cronometre: respostas-arquitetura ≤ 2min, respostas-detalhe ≤ 1min.
> - Ao final, peça auto-avaliação: "onde você se sentiu mais frágil?".
> - Tom: senior, exigente mas respeitoso, sem pegadinha barata.

### Bloco A — Visão geral & onboarding (5 min)

1. Explique em até 2 minutos o que o projeto faz e a arquitetura.
2. Desenhe (verbalmente) o fluxo de uma pergunta válida do usuário até a resposta final.
3. Quais decisões de arquitetura você considera as mais importantes desta entrega?
4. Qual parte do código você tem mais orgulho? Qual parte refaria primeiro?

### Bloco B — Arquitetura de Agentes & LangGraph (Peso ALTO)

5. Por que LangGraph e não o `AgentExecutor` do LangChain ou um `create_react_agent` pronto?
6. Você implementou um agent node próprio em vez do ReAct prebuilt — qual foi a motivação? O que ganhou em controle e o que perdeu em conveniência?
7. Explique o reducer pattern com `Annotated[..., add_messages]`. Por que isso importa para multi-turn?
8. Como funciona o `MemorySaver` e o `thread_id`? O que acontece com o contexto se o processo reiniciar?
9. Como você trocaria o `MemorySaver` por persistência durável em produção? (Esperado: Postgres/Redis checkpointer.)
10. Por que `tool_choice="auto"` e não `"required"`? Em que cenário `auto` é decisivo?
11. O `_MAX_AGENT_ITERATIONS=3` existe por quê? O que acontece se o LLM ficar pingando tool calls em loop?
12. Em alguns pontos do grafo você não usa edge explícito com `END`. Por quê é seguro / como o LangGraph resolve isso?
13. Diferencie StateGraph, node, edge, conditional edge, e `Command`. Onde cada um aparece no seu código?
14. Por que separar `preprocess`, `agent` e `tool_executor` em nodes distintos em vez de juntar tudo?
15. Como você debugaria um caso em que o agent escolhe a tool errada?

### Bloco C — Tool Calling (Peso ALTO)

16. Explique Tool Calling em uma frase, e depois em 5 frases.
17. Por que você não deixou a LLM gerar SQL livremente? Liste pelo menos 3 motivos.
18. O que `StructuredTool.from_function` faz internamente? O que vai parar no payload enviado ao LLM?
19. Por que duas tools separadas (volume e performance) em vez de uma só com parâmetro `metric`? E o inverso, por que não uma tool por métrica?
20. As descrições das tools dizem **"não use para X"**. Por que isso? O que muda na taxa de acerto da LLM?
21. Como você testa que a tool boundary está clara para o modelo? (Esperado: eval suite, fixtures, asserts em `agent_tool_calls`.)
22. Se eu te pedir para adicionar uma terceira tool (ex.: `customer_segmentation_analyzer`), o que muda no código? Liste arquivos.
23. Você usa `tool_choice="auto"`. Como o agent decide responder sem chamar tool em um follow-up estratégico?

### Bloco D — Router determinístico & Guardrails (Peso ALTO)

24. Por que router determinístico antes do LLM, em vez de deixar o LLM rotear?
25. O router é um node do grafo ou roda fora? Como ele expõe a decisão para o resto do fluxo?
26. Quais intents existem? Como você definiu essa taxonomia?
27. Tradeoff: router regex vs router com classifier ML vs router LLM. Quando trocaria?
28. O regex de datas suporta `ontem`, `ultimos N dias`, `DD/MM/AA`. E português livre tipo "semana passada", "começo do mês"? Como evolui sem virar bagunça?
29. Como funciona o merge de follow-up temporal? Dê um exemplo concreto.
30. Se a pergunta é "Qual o melhor canal ontem?" — o que o router faz, passo a passo?
31. Por que `out_of_scope` e `unsupported_metric` são short-circuits, não chamadas ao LLM?

### Bloco E — Engenharia de Dados / SQL / BigQuery (Peso MÉDIO mas Sr Data Scientist vai pressionar)

32. Walk-through linha-a-linha da query em `channel_performance_analyzer.py`.
33. Por que `COUNT(DISTINCT o.order_id)` e não `COUNT(*)` ou `COUNT(o.order_id)`?
34. Por que `CAST(sale_price AS NUMERIC)` e não confiar no tipo original? Que tipo o BigQuery retorna por padrão?
35. Por que `status = 'Complete'`? O que perdemos? O que ganhamos? Cite outros valores possíveis do campo.
36. Por que `INNER JOIN` em vez de `LEFT JOIN`? Em que análise você trocaria por LEFT?
37. Você filtra `DATE(o.created_at)` em performance e `DATE(created_at)` (de `users`) em volume. Essa diferença é proposital? O que ela significa de negócio?
38. Como você calcularia **conversion rate por canal**? Por que precisa de LEFT JOIN nessa query?
39. Como você calcularia **ticket médio por canal**?
40. Custo no BigQuery: como sua query é cobrada? Como você reduziria scan? (Esperado: projetar só colunas, evitar `SELECT *`, partitioning/clustering quando aplicável, `--dry_run`.)
41. SQL injection: explique o ataque hipotético se você concatenasse `traffic_source` na string e como `ScalarQueryParameter` previne.
42. Como você validaria que a receita retornada está correta? (Esperado: spot check manual, comparar com SQL no console BQ, cross-check com soma alternativa.)

### Bloco F — Backend Python (Peso ALTO)

43. Por que FastAPI e não Flask?
44. Por que Pydantic v2 e não dataclasses ou TypedDict?
45. Como funciona o `Depends(get_settings)` e por que isso é melhor que `import` direto?
46. O `lru_cache` em `get_query_graph()` — por quê? O que acontece sem ele?
47. Você tem `BigQueryClientError`, `ToolExecutionError`, `LlmTimeoutError`. Por que classes separadas e não uma só?
48. `temperature=0` — explique. E se quiser variação criativa em síntese, mudaria?
49. `with_fallbacks([anthropic])` — quando dispara? Como você testa o fallback sem desligar a OpenAI?
50. `pyright` vs `mypy` — por que escolheu?
51. Estrutura `clients/ graph/ tools/ schemas/` — explique o critério dessa separação. É Clean Arch? MVC? Algo próprio?
52. Como você lida com secrets (API keys) hoje? E como faria em produção GCP?

### Bloco G — Visão de Produto (Peso ALTO)

53. O case avalia se a resposta é útil para **gerente de mídia** ou só "despejo de dados". Como você garantiu o lado "analista"?
54. O sistema recusa pedidos fora do escopo. Mostre um exemplo de pergunta e o que ele responde.
55. "Quais ações devemos priorizar?" — como o sistema responde **sem fazer nova query**? Por quê esse comportamento existe?
56. Onde você está deixando dinheiro na mesa em termos de produto? O que um analista humano faria que seu agente não faz?
57. Se o gerente de mídia disser "isso não é útil pra mim", quais seriam as próximas 3 iterações de produto?
58. Como você mediria "qualidade da resposta"? (Esperado: eval suite, LLM-as-judge, feedback humano, métricas de tool accuracy.)

### Bloco H — Confiabilidade, Testes & Operação (Peso MÉDIO)

59. Cobertura de testes: o que `pytest` cobre que `verify` não cobre?
60. O que são os testes **live**? Por que opt-in?
61. O que é uma **eval suite** no contexto de agentes? Como você desenharia uma para esse projeto?
62. Como você monitoraria custo de LLM e BQ em produção? Quais métricas?
63. Como você desenharia o deploy disso em **Cloud Run**? O que muda no `MemorySaver`?
64. Rate limit, retry policy, circuit breaker — quais valeriam a pena agora vs depois?
65. Observability — que sinais você instrumentaria primeiro? (Esperado: latência por node, tool call success rate, token usage, intent distribution.)

### Bloco I — Escala e Evolução (Peso MÉDIO)

66. Como esse agente atende **10 usuários simultâneos**? E **10.000**?
67. Cache: onde colocaria? Que chave usaria? Qual TTL? Cite LRU vs Redis vs nenhum.
68. Como você adicionaria **RAG** (ex.: documentação de campanhas, manuais de Mídia)?
69. Onde entraria um **vector DB**? Que tipo de pergunta isso destrava que hoje você não consegue?
70. Como integraria com **Meta Ads / Google Ads APIs**? O que muda na arquitetura?
71. Versionamento de prompt e versionamento de tool schema — como você faz em produção?

### Bloco J — Cultura AI-First & Soft Skills (alinhamento Monks)

72. A vaga fala em "converter dores manuais em agentes". Conte um exemplo concreto da sua experiência (real ou hipotético) em que substituiu um fluxo manual por agente. Quais resistências esperar do time atual?
73. Como você decide "isto vale virar agente" vs "isto continua manual"?
74. Como você prova o ROI de um agente para um stakeholder não-técnico?
75. Onde você usou IA para escrever este projeto, e onde refez à mão? Por quê?
76. Onde você discordaria de um seguidor cego de "tudo com IA"?
77. AI-First com governança e segurança de dados — dê um exemplo concreto de tradeoff que você fez nesse projeto pensando em segurança.

### Bloco K — Curveballs e perguntas profundas

78. Se eu te pedisse para remover o LangGraph e fazer com asyncio + httpx puro, dá pra fazer? O que ficaria pior?
79. Se a LLM começar a alucinar nomes de canais inexistentes (ex.: "TikTok" que não está no dataset), o que acontece hoje? Como você protege?
80. Você confia mais no router determinístico ou no LLM agent? Em que situação cada um te trai?
81. Defenda o oposto da sua escolha: **convença-me** de que era melhor ter deixado o LLM gerar SQL.
82. O que esse projeto **NÃO** prova sobre suas habilidades para a vaga?
83. Em 6 meses, o que esse projeto deveria ter virado para você considerar que evoluiu bem?
84. Em uma frase: por que a Monks deveria te contratar?

### Bloco L — Encerramento

85. Você tem alguma pergunta para mim? *(Padrão de entrevista — o candidato deve ter 2-3 prontas.)*

---

## 3. Critérios de Avaliação Sugeridos para o Agente Entrevistador

| Dimensão | Sinais positivos | Bandeiras vermelhas |
|---|---|---|
| Arquitetura de Agente | Justifica LangGraph vs alternativas; conhece reducer/checkpointer/tool_choice; sabe debugar tool boundary | Confunde LangChain com LangGraph; trata "agent" como prompt gigante; não sabe explicar `tool_choice="auto"` |
| Tool Calling | Explica JSON schema, separação prompt/execução, descrições anti-confusão | Acha que tool calling é "função que LLM chama mágicamente"; não sabe o que vai no payload |
| SQL/BQ | Defende DISTINCT, NUMERIC, status, JOIN, custo por scan | Não sabe por que DISTINCT é necessário; trata BQ como Postgres |
| Backend | Tipagem, Pydantic v2, camadas de erro, secrets | Mistura camadas, não trata timeout LLM, hardcode de secrets |
| Visão de Produto | Pensa no gerente de mídia, recusa elegante, evolução de produto | Foca só em código; não tem opinião sobre próximos passos |
| Honestidade técnica | Reconhece limitações explicitamente, sabe onde IA o ajudou e onde ele dirigiu | Vende fumaça; não admite trade-off; "tudo está perfeito" |
| Cultura AI-First | Tem opinião sobre quando NÃO usar IA; pensa governança | Hype sem governança; "IA resolve tudo" |

## 4. Materiais que o candidato deve ter à mão durante a entrevista

- `app/graph/workflow.py` aberto.
- `app/tools/channel_performance_analyzer.py` aberto.
- Diagrama mermaid do README na cabeça.
- Lista de 3 melhorias futuras: durable checkpointer, eval suite, cache de queries idênticas.
- README seção 5 ("Como corrigir em 5 minutos") como roteiro de demo.
