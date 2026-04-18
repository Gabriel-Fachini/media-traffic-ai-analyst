# Media Traffic AI Analyst - Agents Blueprint

## 1. Objetivo

Inicializar a definicao dos agentes do MVP para responder perguntas de Midia e Growth com base em dados reais do BigQuery, usando tool calling e resposta em linguagem natural.

## 2. Escopo do Produto

- Dominio: analise de trafego e receita por canal (Search, Organic, Facebook, etc.) no dataset thelook_ecommerce.
- Fonte de dados: bigquery-public-data.thelook_ecommerce (users, orders, order_items).
- Saida esperada: insight util para negocio, nao apenas tabela bruta.
- Fora de escopo: perguntas gerais (ex.: culinaria), dados de outras empresas e qualquer resposta sem base de tool.
- Interacao atual do MVP: terminal/CLI.
- UI web (ex.: Streamlit) fica para evolucao pos-MVP.

## 3. Requisitos de Plataforma

- Linguagem: Python 3.10+
- API: FastAPI
- Interface inicial: terminal/CLI (sem UI web nesta fase)
- Orquestrador: LangGraph (preferencial)
- Dados: google-cloud-bigquery com queries parametrizadas
- Validacao: Pydantic + type hints
- Resiliencia: falhas de LLM ou GCP devem retornar recusa elegante

## 4. Mapa de Agentes

### 4.1 Router Agent

Responsabilidade:

- Interpretar a pergunta, identificar intencao e extrair parametros (traffic_source, start_date, end_date).
- Decidir qual tool chamar ou quando negar por fora de escopo.

Entradas:

- question: str

Saidas:

- intent: traffic_volume | channel_performance | out_of_scope
- normalized_params: {traffic_source?, start_date, end_date}

Regras:

- Nunca inventar metricas.
- Se faltar data, pedir clarificacao ou aplicar padrao explicito de periodo.

### 4.2 Traffic Volume Analyzer Agent

Responsabilidade:

- Executar analise de volume de usuarios por traffic_source.

Tool:

- traffic_volume_analyzer(TrafficVolumeInput)

Query base:

- Agregacao em users com COUNT(DISTINCT id), filtro por periodo e source opcional.

Saida esperada:

- Lista agregada por canal com user_count.

### 4.3 Channel Performance Analyzer Agent

Responsabilidade:

- Executar analise financeira por canal (pedidos e receita).

Tool:

- channel_performance_analyzer(ChannelPerformanceInput)

Query base:

- Join users -> orders -> order_items
- Metricas: total_orders e total_revenue por traffic_source

Saida esperada:

- Ranking de canais por receita no periodo.

### 4.4 Insight Synthesizer Agent

Responsabilidade:

- Traduzir resultado tecnico para insight de negocio claro e acionavel.

Entradas:

- Dados retornados pelas tools
- Contexto da pergunta

Saida:

- answer em linguagem natural
- leitura de tendencia + comparacao entre canais

Regras:

- Nao retornar dump cru de SQL/tabela como resposta final.
- Explicar sinal principal e possivel implicacao para Growth.

### 4.5 Scope Guard Agent

Responsabilidade:

- Responder com recusa educada para pedidos fora do dominio.

Exemplos de gatilho:

- "Como fazer um bolo?"
- "Qual a receita de outra empresa?"

Saida:

- Mensagem curta, educada, orientando o escopo valido.

## 5. Fluxo Orquestrado (LangGraph)

Fluxo de uso atual: pergunta enviada via terminal/CLI para a API.

1. Start
2. Router Agent
3. Branch:
   - traffic_volume -> Traffic Volume Analyzer Agent
   - channel_performance -> Channel Performance Analyzer Agent
   - out_of_scope -> Scope Guard Agent
4. Se houve consulta de dados: Insight Synthesizer Agent
5. Retorno para API

## 6. Contratos de Dados (MVP)

### 6.1 Input das Tools

- TrafficVolumeInput:
  - traffic_source: Optional[str]
  - start_date: date
  - end_date: date

- ChannelPerformanceInput:
  - traffic_source: Optional[str]
  - start_date: date
  - end_date: date

### 6.2 Contrato HTTP

- QueryRequest:
  - question: str (max 1000)

- QueryResponse:
  - answer: str
  - tools_used: list[str]
  - metadata: dict (opcional no MVP inicial)

## 7. Politica de Seguranca e Confiabilidade

- Usar somente SQL parametrizada (Prepared Statements).
- Proibir concatenacao direta de SQL com input do usuario.
- Capturar GoogleAPIError e timeout de LLM.
- Em erro temporario, retornar mensagem tratada (sem stack trace).

## 8. Politica de Prompt Base

System prompt recomendado:

- O agente atua como Analista Junior de Midia focado no dataset thelook_ecommerce.
- Nao discute topicos fora de negocio de trafego/receita.
- Nao responde sem consultar tool quando pergunta depende de dado.

## 9. Mapeamento com as Specs

- requirements.md:
  - RFA01: Router Agent + tool calling
  - RFA02: Traffic Volume Analyzer Agent
  - RFA03: Channel Performance Analyzer Agent
  - RFA04: Insight Synthesizer Agent
  - RFA05: Scope Guard Agent

- design.md:
  - Fluxo em grafo, contratos Pydantic, SQL parametrizada, fallback de erro

- tasks.md:
  - Fase 1: setup de ambiente, config e BigQueryClient
  - Fase 2: implementacao das tools
  - Fase 3: orquestracao no LangGraph
  - Fase 4: exposicao via FastAPI
  - Fase 5: interacao em terminal (CLI) e README final
  - Backlog pos-MVP: UI web opcional (avaliar Streamlit)

## 10. Definition of Done do agents.md (inicial)

- Estrutura de agentes definida e alinhada com requisitos.
- Fronteiras de escopo explicitas.
- Contratos de entrada/saida descritos para iniciar implementacao.

## 10.1 Pipeline de Validacao Durante o Desenvolvimento

- Antes de considerar uma alteracao tecnica concluida, executar:
  - `poetry run ruff check app scripts`
  - `python3 -m compileall app scripts`
  - `poetry run pyright`
- Quando a alteracao tocar tools BigQuery, preferir tambem validacao manual com:
  - `poetry run python scripts/manual_validate_tools.py`
- Quando a alteracao tocar binding/orquestracao de tools, validar pelo menos:
  - execucao direta das tools
  - smoke test de `bind_tools()` confirmando `tool_calls`

## 11. Skills Ativas (Fase Atual)

- langchain-ai/langchain-skills@langgraph-fundamentals
- wshobson/agents@prompt-engineering-patterns
- wshobson/agents@sql-optimization-patterns

Objetivo do uso:

- LangGraph fundamentals para estruturar o grafo de agentes com estado e roteamento claro.
- Prompt engineering patterns para aumentar consistencia de roteamento e qualidade da resposta final.
- SQL optimization patterns para manter queries legiveis, eficientes e seguras no BigQuery.

## 12. Diretrizes de Escopo Atual (MVP Simples)

- Priorizar implementacao simples e incremental.
- Nao incluir observability nesta fase (tracing, monitoramento e avaliacao automatizada).
- Nao incluir estimativa ou controle de custos nesta fase (uso previsto em free tier).
- Nao implementar testes automatizados no MVP inicial; validacao sera manual.
- Nao implementar Streamlit/UI web nesta fase; interacao sera via terminal/CLI.
- Manter `traffic_source` singular no contrato das tools durante o MVP.
- Quando houver comparacao entre canais, preferir uma consulta agregada por periodo e comparar os canais na camada de sintese antes de ampliar o schema.
- Nao atualizar `README.md` durante a implementacao incremental. O README deve ser consolidado no fim do projeto, na fase de entrega, salvo pedido explicito do usuario para antecipar alguma mudanca.
