# Media Traffic AI Analyst - Agents Blueprint

## 1. Objetivo atual

Entregar um MVP funcional de um agente de analytics para Midia e Growth, capaz de:

- entender perguntas em linguagem natural sobre trafego, pedidos e receita por canal;
- consultar dados reais do dataset `bigquery-public-data.thelook_ecommerce`;
- responder em linguagem natural com tool calling, sem depender de um prompt monolitico;
- sustentar uma camada de confianca com verificacoes automatizadas e smoke tests opt-in.

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
- Formatos temporais suportados no roteamento:
  - `YYYY-MM-DD`
  - `DD/MM/AAAA`
  - `DD/MM/AA`
  - `ontem`, `este mes`, `ultimo mes`, `ultimos N dias`
- Follow-ups suportados:
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

Responsabilidades atuais:

- classificar a intencao da pergunta;
- normalizar `traffic_source`, `start_date` e `end_date`;
- decidir entre:
  - `traffic_volume`
  - `channel_performance`
  - `strategy_follow_up`
  - `diagnostic_follow_up`
  - `ambiguous_analytics`
  - `out_of_scope`
- emitir short-circuit com mensagem pronta quando houver:
  - pergunta vazia
  - fora de escopo
  - dimensao nao suportada
  - metrica nao suportada
  - canal nao suportado
  - datas ausentes
  - datas invalidas
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

### 4.4 Insight Synthesizer Agent

- sintetiza a resposta final em pt-BR a partir do resultado estruturado das tools;
- trata follow-ups estrategicos e diagnosticos com prompts dedicados;
- converte falhas temporarias de LLM em resposta tratada.

### 4.5 Scope Guard Agent

- continua responsavel por recusas curtas e educadas;
- hoje a decisao pode vir tanto por fora de escopo quanto por dimensoes/metricas ausentes do schema.

## 5. Fluxo orquestrado atual

Fluxo padrao via API/CLI:

1. Start
2. Router Agent
3. Branch:
   - `traffic_volume` -> `traffic_volume_analyzer`
   - `channel_performance` -> `channel_performance_analyzer`
   - `strategy_follow_up` -> Insight Synthesizer
   - `diagnostic_follow_up` -> Insight Synthesizer
   - short-circuit -> mensagem pronta
4. Quando houve consulta de dados: Insight Synthesizer
5. Retorno para API

Observacoes importantes:

- o grafo usa `thread_id` para retomar contexto em memoria;
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

## 9. Mapeamento com as fases

- Fase 1: setup, config e BigQuery client implementados
- Fase 2: tools implementadas
- Fase 3: orquestracao LangGraph implementada
- Fase 4: exposicao FastAPI implementada
- Fase 5: CLI implementada
- Entrega final ainda pendente:
  - consolidacao do `README.md`
  - acabamento final dos materiais de entrega

## 10. Diretrizes de escopo atuais

- Priorizar implementacao simples e incremental.
- Manter `traffic_source` singular no contrato das tools.
- Comparacoes entre canais devem continuar preferindo consulta agregada com sintese na camada final.
- Nao incluir UI web nesta fase.
- Nao incluir observability/custos como eixo principal do MVP.
- `README.md` continua reservado para consolidacao final, salvo pedido explicito do usuario.

## 11. Definition of Done atual de `agents.md`

- estado real do projeto documentado;
- fronteiras de escopo atuais explicitas;
- contratos e limitacoes operacionais registradas;
- pipeline de verificacao e estrategia de testes automatizados documentadas.
