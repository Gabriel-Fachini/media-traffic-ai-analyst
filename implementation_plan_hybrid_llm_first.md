# Plano de Implementacao: Refatoracao Hibrida para Router Fino e Fluxo LLM-First

## 1. Resumo e Objetivo

A arquitetura atual acertou na base tecnica do desafio:

- FastAPI como superficie de execucao;
- LangGraph como orquestrador;
- Tool Calling real com BigQuery;
- Pydantic e tipagem forte nos contratos;
- testes automatizados cobrindo workflow, API, tools e cenarios live.

O principal problema hoje nao e a stack. O problema esta no excesso de decisao deterministica concentrada em `app/graph/router.py`, que ficou responsavel por semantica demais antes do agente de fato agir.

O objetivo deste plano e evoluir a arquitetura para um modelo **hibrido e LLM-first**, reduzindo o acoplamento do router sem abrir mao de:

- validacoes estruturais importantes;
- contratos de debug e observabilidade ja expostos pela API/CLI;
- confiabilidade em datas e guardrails do MVP;
- aderencia clara ao que o `case.md` pede.

Em vez de um rewrite total para ReAct puro, a proposta e fazer uma **refatoracao incremental**, preservando o que ja esta bom e removendo a rigidez que hoje limita a conversa.

## 2. Leitura Estrategica Frente ao Desafio

O `case.md` pede:

- uso de FastAPI ou Flask;
- uso de um orquestrador como LangGraph;
- Tool Calling real;
- separacao entre logica de execucao e prompt;
- consultas reais ao BigQuery com SQL segura;
- respostas uteis para negocio.

O desafio **nao exige**:

- chat aberto com muitos turnos livres;
- interface React;
- um ecossistema complexo de multi-agent;
- autonomia conversacional irrestrita.

Portanto, a melhor direcao tecnica nao e necessariamente um ReAct puro e maximalista. A melhor direcao e a que:

1. melhora a flexibilidade sem perder confiabilidade;
2. preserva a capacidade de explicar a arquitetura para o avaliador;
3. reduz o risco de regressao perto da entrega.

## 3. Diagnostico da Arquitetura Atual

### 3.1 O que esta bom e deve ser preservado

- `app/tools/`
  - tools pequenas, claras e orientadas ao dominio;
- `app/clients/bigquery_client.py`
  - encapsulamento correto da integracao e dos erros de BigQuery;
- `app/schemas/api.py` e `app/schemas/tools.py`
  - contratos fortes e legiveis;
- `app/main.py`
  - superficie HTTP limpa, com metadata e debug;
- `app/cli.py`
  - cliente de demo consistente para o fluxo real;
- `tests/`
  - base de seguranca relevante para evoluir sem quebrar o produto.

### 3.2 O que esta pesado demais hoje

- `app/graph/router.py`
  - excesso de heuristicas por token, regex e whitelists;
- `app/graph/workflow.py`
  - muita logica de merge e follow-up dependente da classificacao previa do router;
- decisao semantica demais acontecendo antes do LLM;
- whitelist de canais e outras restricoes que tornam o produto mais rigido do que o caso exige.

### 3.3 O que nao deve ser feito

- nao deletar imediatamente `app/schemas/router.py`;
- nao remover toda a camada estruturada de datas e guardrails;
- nao trocar validacao deterministica importante por prompt apenas;
- nao adicionar React UI ou expandir escopo de front nesta etapa;
- nao transformar o projeto em uma malha de varios agentes LLM sem necessidade.

## 4. Principio Arquitetural da Nova Versao

### Diretriz central

**Router fino + agente principal com Tool Calling + guardrails estruturais minimos.**

Em termos práticos:

- menos decisao semantica no Python;
- mais decisao de ferramenta e sintese no LLM;
- validacoes estruturais continuam deterministicas;
- follow-ups passam a depender mais do historico da conversa e menos de classificacoes fixas.

## 5. Arquitetura Alvo

### 5.1 Fluxo proposto

1. `preprocess_node`
2. `agent_node`
3. `tool_executor_node`
4. `agent_node`
5. `end`

### 5.2 Responsabilidades por camada

#### `preprocess_node`

Responsavel apenas por:

- garantir que a pergunta nao e vazia;
- identificar datas invalidas ou invertidas;
- montar `resolved_question` quando houver follow-up curto de clarificacao;
- manter um pequeno conjunto de guardrails estruturais incontestaveis.

Nao deve mais:

- classificar praticamente toda `intent`;
- decidir via heuristica qual ferramenta deve ser chamada em quase todos os casos;
- bloquear perguntas validas apenas porque a linguagem fugiu da whitelist atual.

#### `agent_node`

Responsavel por:

- entender a pergunta no contexto do thread;
- decidir se precisa chamar tool;
- decidir qual tool chamar;
- pedir clarificacao curta quando a pergunta estiver no dominio, mas incompleta;
- responder diretamente quando a pergunta for estrategica ou diagnostica com contexto suficiente;
- sintetizar a resposta final apos receber o resultado da tool.

#### `tool_executor_node`

Permanece praticamente com a mesma ideia atual:

- executa as tools pedidas pelo LLM;
- retorna `ToolMessage`;
- registra erros estruturados;
- preserva dados uteis para debug.

## 6. O que o Router Passa a Fazer

O novo router deixa de ser um classificador de produto e passa a ser um **preprocessador de seguranca e coerencia**.

### Mantemos no router

- pergunta vazia;
- parsing e validacao de datas;
- data inicial maior que data final;
- possivel merge de follow-up corretivo de datas;
- recusa de metricas claramente impossiveis no schema quando a deteccao for trivial;
- metadados tecnicos basicos para debug.

### Removemos do router

- boa parte das classificacoes por `intent`;
- follow-up estrategico e diagnostico baseados em listas extensas de tokens;
- whitelist rigida de `traffic_source`;
- grande parte das recusas baseadas em heuristica lexical.

## 7. Papel do Prompt na Nova Arquitetura

O `app/graph/prompts.py` continua central, mas com uma responsabilidade mais clara:

- definir o papel do agente;
- delimitar escopo do schema;
- orientar quando pedir clarificacao;
- orientar quando usar cada tool;
- orientar como responder com leitura de negocio;
- orientar como lidar com follow-ups sem inventar causalidade.

Ponto importante:

**o prompt nao substitui validacao estrutural de datas nem regras de seguranca simples.**

Ou seja:

- data invalida continua sendo tratada deterministicamente;
- erros evidentes de estrutura nao devem depender da boa vontade do modelo;
- prompt cuida da semantica;
- preprocess cuida da integridade minima.

## 8. Contratos que Devem Ser Preservados

Esta refatoracao nao deve quebrar os contratos que hoje ajudam a demo e a depuracao.

### Devem ser mantidos

- `QueryRequest`, `QueryResponse` e `QueryMetadata`;
- `thread_id` e `thread_id_source`;
- `context_message_count`;
- `X-Debug`;
- `DebugInfo`;
- registro de `agent_tool_calls`;
- captura de erros estruturados.

### Implicacao pratica

`app/schemas/router.py` nao precisa ser removido agora. Ele pode ser reduzido, renomeado no futuro ou simplificado, mas ainda e util como camada de debug/observabilidade enquanto a transicao acontece.

## 9. Plano Incremental de Implementacao

### Fase 1: Enxugar o Router sem quebrar o produto

- reduzir o escopo de `app/graph/router.py`;
- remover classificacoes semanticas mais frageis;
- manter apenas preprocess, datas e guardrails minimos;
- revisar whitelists desnecessarias, especialmente de canais;
- preservar `resolved_question` para follow-up de clarificacao curta.

**Resultado esperado:** menos recusas arbitrarias e menor acoplamento antes do LLM.

### Fase 2: Simplificar o Workflow

- refatorar `app/graph/workflow.py` para um fluxo mais proximo de:
  - `preprocess -> agent -> tools -> agent -> end`
- eliminar desvios hoje dedicados a intents muito especializadas;
- manter tratamento de timeout, erros temporarios e debug_errors;
- preservar reset de campos overwrite-style por turno.

**Resultado esperado:** grafo mais curto, mais explicavel e menos dependente de ramificacoes fixas.

### Fase 3: Reescrever o Prompt do Agente

- reforcar no prompt:
  - escopo exato do dataset;
  - quando usar `traffic_volume_analyzer`;
  - quando usar `channel_performance_analyzer`;
  - como pedir clarificacao curta;
  - como responder follow-ups estrategicos e diagnosticos;
  - como evitar inventar metricas, campanhas e causalidade.

**Resultado esperado:** mais inteligencia semantica indo para o agente, e menos para regex.

### Fase 4: Adaptar Testes

- migrar testes que hoje dependem fortemente de `router_intent` detalhado;
- aumentar testes orientados a comportamento:
  - pergunta valida -> tool call correta;
  - pergunta sem data -> clarificacao curta;
  - follow-up curto -> conversa continua;
  - pergunta fora do schema -> recusa coerente;
  - follow-up diagnostico e estrategico -> resposta util sem inventar fatos.

### Fase 5: Validacao Manual de Produto

- rodar os fluxos do checklist em `docs/checklist-testes-desafio.md`;
- testar 5 ou mais mensagens no mesmo `thread_id`;
- testar canais fora da whitelist antiga;
- testar a pergunta do enunciado:
  - `Qual dos canais tem a melhor performance? E por que?`

## 10. Riscos e Mitigacoes

### Risco 1: Perder confiabilidade ao mover tudo para o LLM

**Mitigacao:**
manter preprocess deterministico para datas e guardrails estruturais.

### Risco 2: Regressao na API e na CLI

**Mitigacao:**
preservar contratos de debug e metadata ja usados por `app/main.py` e `app/cli.py`.

### Risco 3: Reescrever demais perto da entrega

**Mitigacao:**
fazer a mudanca em fases, sem apagar contratos e testes logo no inicio.

### Risco 4: Melhorar semantica mas perder explicabilidade

**Mitigacao:**
manter `X-Debug`, `resolved_question`, `agent_tool_calls` e erros estruturados para demonstrar o funcionamento do agente.

## 11. O que Nao Entra Neste Plano

Itens explicitamente fora desta refatoracao:

- interface React;
- deploy/infraestrutura de producao;
- persistencia duravel entre reinicios;
- expansao para novas tabelas e novas ferramentas fora do escopo atual;
- arquitetura multi-agent com varios LLM nodes especializados.

Esses pontos podem existir como backlog extra, mas nao devem competir com a melhoria principal desta etapa.

## 12. Definicao de Sucesso

Consideraremos essa refatoracao bem-sucedida quando:

- o agente parar de depender de heuristicas extensas para perguntas validas;
- a conversa curta com follow-ups ficar mais natural;
- as tools continuarem sendo chamadas corretamente;
- datas invalidas continuarem sob controle deterministico;
- a API e a CLI preservarem seus contratos;
- a arquitetura ficar mais simples de explicar ao avaliador do desafio.

## 13. Resumo Executivo

Este plano nao propoe abandonar a arquitetura atual.

Ele propoe:

- preservar a base boa;
- reduzir a rigidez do router;
- simplificar o grafo;
- deslocar a semantica para o agente com Tool Calling;
- manter os guardrails estruturais que realmente agregam confiabilidade.

Em uma frase:

**evoluir para um fluxo LLM-first hibrido, e nao fazer um rewrite radical para ReAct puro.**
