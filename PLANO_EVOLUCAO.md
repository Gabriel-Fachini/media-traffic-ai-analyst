# Plano de Evolucao - Media Traffic AI Analyst

Objetivo: elevar o projeto de "muita heuristica de linguagem bem testada" para
"agente LangChain/LangGraph medido, observavel e enxuto". O eixo central e
substituir o preprocessor deterministico (~2200 linhas de regex/frozensets em
`app/graph/router.py` + metade de `app/graph/workflow.py`) por um router
LLM-based com structured output, sustentado por um harness de eval.

## Principios de senioridade que o plano demonstra

- Trocar NLU hardcoded por classificacao LLM com contrato Pydantic.
- Hibrido consciente: manter normalizacao de data deterministica (barata, exata,
  testavel), delegar so intent/scope/follow-up ao LLM.
- Medir o agente antes de mexer nele (eval harness e pre-requisito, nao opcional).
- Observabilidade e streaming como cidadaos de primeira classe.
- Persistencia e UI por ultimo, sobre fundacao solida.

## Estado atual relevante

- Tool calling JA e LLM-based: `bind_tools(tool_choice="auto")` em
  `app/graph/llm.py:91`, loop ReAct em `app/graph/workflow.py:880`.
- Router NAO decide tool. Faz short-circuit estrutural
  (`app/graph/router.py:992`), monta guidance injetada como `SystemMessage`
  (`app/graph/workflow.py:584`) e detecta follow-up por token-matching
  (`app/graph/workflow.py:418-695`).
- Maquinaria de follow-up existe porque o router so ve a string atual, cego ao
  thread. Com historico no contexto, follow-up vira contexto natural.
- Contrato `RouterDecision` ja existe e e reutilizavel (`app/schemas/router.py`).
- Persistencia atual: `MemorySaver` (`app/graph/workflow.py:1062`), some no
  restart.

---

## Fase 0 - Eval Harness (pre-requisito)

Por que primeiro: router LLM e nao-deterministico. Mexer nele sem medir e
irresponsavel. Esta fase nao muda comportamento, so cria a rede de seguranca.

### Tarefas

- [ ] 0.1 Extrair casos de `tests/unit/test_router.py` para um dataset de eval
      (`tests/eval/router_cases.jsonl` ou `.csv`): `{question, expected_intent,
      expected_clarification_reason, expected_refusal_reason, expected_dates,
      expected_traffic_source}`.
- [ ] 0.2 Criar runner `tests/eval/test_router_eval.py` marcado `@pytest.mark.eval`
      que roda o router atual contra o dataset e calcula accuracy por campo.
- [ ] 0.3 Registrar marker `eval` em `pyproject.toml`/`conftest.py` (seguir o
      padrao existente de `live` e `--agent`).
- [ ] 0.4 Definir baseline: rodar contra o router deterministico atual e gravar
      a accuracy de referencia em `tests/eval/BASELINE.md`.
- [ ] 0.5 Adicionar threshold de regressao (ex: intent accuracy >= baseline).

### Aceite

- `poetry run pytest -m eval` roda offline (sem BigQuery) e reporta accuracy.
- Baseline do router atual documentado para comparacao na Fase 1.

---

## Fase 1 - Router LLM-based (o grande delta)

Substituir a classificacao por regex por `llm.with_structured_output(RouterDecision)`.
Manter normalizacao de data deterministica.

### Tarefas

- [ ] 1.1 Criar `app/graph/llm_router.py` com `classify_question(question,
      thread_context) -> RouterDecision` via `with_structured_output`.
- [ ] 1.2 Escrever o prompt do router: escopo valido/invalido, lista de canais
      suportados, definicao de cada intent, regra de ambiguidade
      volume-vs-financeiro. Reaproveitar a semantica ja descrita em
      `app/graph/prompts.py:86`.
- [ ] 1.3 Manter normalizacao de data deterministica: extrair as funcoes de data
      de `app/graph/router.py` (`_extract_valid_and_invalid_explicit_dates`,
      `_extract_relative_date_range`, patterns) para um modulo
      `app/graph/date_normalizer.py` e reusar. Datas continuam regex.
- [ ] 1.4 Passar contexto do thread ao router: ultimas N mensagens / ultimo
      resultado de tool, para que o router classifique follow-ups sem token lists.
- [ ] 1.5 Substituir `build_router_decision` em `_resolve_router_turn`
      (`app/graph/workflow.py:723`) pela chamada ao router LLM. Guidance continua
      sendo montada e injetada como `SystemMessage` (sem mudanca no `agent_node`).
- [ ] 1.6 Deletar a maquinaria de follow-up agora redundante: `_resolve_follow_up_intent`,
      `_infer_follow_up_intent_from_previous_context`, `_question_has_soft_*`,
      `_build_agent_clarification_follow_up_question`, merges
      (`app/graph/workflow.py:418-824`) e todos os frozensets de token em
      `app/graph/router.py:49-413`.
- [ ] 1.7 Avaliar fundir `STRATEGY_FOLLOW_UP_SYSTEM_PROMPT` e
      `DIAGNOSTIC_FOLLOW_UP_SYSTEM_PROMPT` no system prompt principal, ja que o
      agente passa a ver o thread e o intent vem do router.
- [ ] 1.8 Cache/curto-circuito barato: pergunta vazia continua tratada sem chamar
      LLM (guard deterministico antes do router).

### Aceite

- `poetry run pytest -m eval` >= baseline da Fase 0 (idealmente acima em casos
  de variacao de linguagem).
- `app/graph/router.py` reduzido a normalizacao de data + mensagens canonicas
  (alvo: < 200 linhas).
- Suite padrao `poetry run pytest` verde; `poetry run verify` limpo.
- Latencia adicional do router medida e documentada.

### Riscos e mitigacao

- +1 LLM call por turno: aceitavel; medir. Guard de vazio evita chamada inutil.
- Nao-determinismo: coberto pelo eval da Fase 0 com threshold.
- Custo: temperatura 0 (ja e o default em `app/graph/llm.py:17`) + modelo barato
  para o router (pode diferir do modelo de sintese).

---

## Fase 2 - Observabilidade e Streaming

### LangSmith (free tier serve)

Developer plan: 1 dev, 5k traces/mes, gratis. Suficiente para projeto pessoal.

### Tarefas

- [ ] 2.1 Integrar LangSmith via env (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`,
      `LANGCHAIN_PROJECT`). Opt-in, sem quebrar quem nao configurar. Documentar em
      `.env.example`.
- [ ] 2.2 Conectar a Fase 0: rodar o eval do router como dataset/experiment no
      LangSmith (opcional, gated por env).
- [ ] 2.3 Streaming no graph: expor `astream_events` do LangGraph.
- [ ] 2.4 Endpoint SSE em `app/main.py` (ex: `POST /query/stream`) emitindo
      tokens + eventos de tool call. Manter `/query` sincrono para compatibilidade.
- [ ] 2.5 CLI (`app/cli.py`) consumindo o stream: render incremental + indicacao
      de tool em execucao.
- [ ] 2.6 Formalizar o `X-Debug` atual (`app/main.py:91`) como camada de
      observabilidade (latencia, tokens, tool por turno) alem do trace remoto.

### Aceite

- Traces aparecem no LangSmith quando configurado; sem regressao quando ausente.
- `/query/stream` emite eventos incrementais; CLI mostra resposta ao vivo.

---

## Fase 3 - Tool de Visualizacao (structured output)

Adicionar tool que retorna spec de grafico estruturada; o front interpreta.

### Tarefas

- [ ] 3.1 Definir contrato Pydantic de grafico em `app/schemas/tools.py`
      (ex: `ChartSpec{type: bar|line|pie, x, y, series, title}` ou subset
      Vega-Lite). Tipado e validado.
- [ ] 3.2 Criar tool (ex: `build_chart`) ou estender os analyzers para retornarem
      `ChartSpec` opcional junto do resultado tabular. Registrar em
      `app/graph/tools.py`.
- [ ] 3.3 Atualizar o system prompt: quando o usuario pedir grafico/visual, emitir
      ChartSpec; senao manter resposta textual.
- [ ] 3.4 Propagar a spec ate a resposta da API (campo estruturado em
      `QueryResponse`/metadata) e pelo stream SSE.
- [ ] 3.5 Testes: tool de chart com client fake + validacao do contrato.

### Aceite

- Pergunta pedindo grafico retorna `ChartSpec` valido na resposta da API.
- Resposta sem pedido visual permanece textual (sem ruido).

---

## Fase 4 - Persistencia SqliteSaver

Trivial, sinal/esforco alto. Substitui RAM por arquivo local, sem infra.

### Tarefas

- [ ] 4.1 Trocar `MemorySaver` por `SqliteSaver` (ou `AsyncSqliteSaver`) em
      `get_persistent_analytics_graph` (`app/graph/workflow.py:1062`). Path
      configuravel por env, default em `./.data/checkpoints.sqlite`.
- [ ] 4.2 Garantir criacao do diretorio/arquivo no startup; adicionar ao
      `.gitignore`.
- [ ] 4.3 Teste de continuidade: thread sobrevive a recompilacao do graph.

### Aceite

- Contexto multi-turn sobrevive ao restart do processo.
- Sem mudanca no contrato HTTP.

---

## Fase 5 - Interface Visual de Chat (vitrine)

Por ultimo: tecnicamente o menos diferenciador. O sinal senior esta em consumir
o streaming (Fase 2) e renderizar tool calls + ChartSpec (Fase 3), nao num chat
estatico.

### Tarefas

- [ ] 5.1 Escolher stack leve (ex: front estatico + fetch SSE, ou framework
      minimo). Sem acoplar ao core.
- [ ] 5.2 Render incremental de tokens via SSE de `/query/stream`.
- [ ] 5.3 Render de tool calls em andamento (estado intermediario do agente).
- [ ] 5.4 Render de `ChartSpec` (Fase 3) com lib de grafico.
- [ ] 5.5 Gestao de `thread_id` no client para continuidade multi-turn.

### Aceite

- Chat funcional consumindo o stream, com graficos e visibilidade de tool calls.

---

## Ordem recomendada e dependencias

```
Fase 0 (eval)  ---->  Fase 1 (router LLM)  ---->  Fase 2 (observability+stream)
                                                      |            |
                                                      v            v
                                                 Fase 3 (chart)  Fase 4 (sqlite, independente)
                                                      |
                                                      v
                                                 Fase 5 (UI)
```

- Fase 0 bloqueia Fase 1 (rede de seguranca).
- Fase 1 e o maior delta de senioridade.
- Fase 3 depende de Fase 2 (stream) para chegar bem na UI.
- Fase 4 e independente; pode entrar a qualquer momento apos Fase 0.
- Fase 5 consome 2+3.

## Gate por fase

Toda fase fecha com:

- `poetry run verify` limpo (ruff + compileall + pyright).
- `poetry run pytest` verde.
- `poetry run pytest -m eval` >= baseline (a partir da Fase 0).
- Atualizar `CLAUDE.md`/`agents.md` com o novo estado real.
