# Media Traffic AI Analyst

MVP de um agente de IA para analise de trafego e receita por canal de midia com dados reais do BigQuery, usando tool calling e resposta em linguagem natural.

## Status

Projeto em fase inicial de implementacao (MVP).

## Objetivo

Reduzir o trabalho manual de analistas de Midia e Growth na analise de canais (Search, Organic, Facebook etc.), combinando:

- interpretacao de perguntas em linguagem natural
- consultas SQL parametrizadas no BigQuery
- sintese de insights de negocio (nao apenas tabelas)

## Escopo Atual do MVP

- Interacao simples via terminal/CLI
- API em FastAPI
- Orquestracao com LangGraph
- Integracao com BigQuery via cliente oficial Python
- Validacao manual de resultados

## Fora de Escopo Nesta Fase

- UI web (ex.: Streamlit)
- Observability (tracing/monitoramento)
- Estimativa e controle de custos
- Testes automatizados

## Dataset

- Fonte: bigquery-public-data.thelook_ecommerce
- Tabelas principais:
  - users
  - orders
  - order_items

## Arquitetura (Resumo)

1. Usuario faz pergunta via CLI
2. Router Agent identifica intencao
3. Tool de analise executa query no BigQuery
4. Insight Synthesizer retorna resposta em linguagem natural
5. API responde com answer e tools_used

## Stack

- Python 3.10+
- FastAPI
- LangGraph
- Pydantic
- google-cloud-bigquery

## Estrutura Atual

- .specs/requirements.md
- .specs/design.md
- .specs/tasks.md
- agents.md
- case.md

## Proximos Passos

1. Estruturar o backend inicial (config, cliente BigQuery, schemas)
2. Implementar tools de analise (volume e performance por canal)
3. Montar o grafo de agentes no LangGraph
4. Expor endpoint principal via FastAPI
5. Validar fluxo fim-a-fim no terminal/CLI

## Nota

A camada web pode ser adicionada em uma fase posterior sem alterar o nucleo de negocio, reaproveitando API e agentes ja implementados.