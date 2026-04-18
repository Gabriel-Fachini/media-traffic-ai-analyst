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

## Stack

- Python 3.10+
- Poetry
- FastAPI
- LangGraph
- Pydantic
- google-cloud-bigquery

## Setup do Ambiente (Fase 1)

### 1) Pre-requisitos

- Python 3.10+ instalado
- Poetry instalado
- Credenciais GCP (arquivo JSON de service account)
- Chave de API para ao menos um provider LLM suportado (`OpenAI` ou `Anthropic`)

### 2) Instalar dependencias

```bash
poetry install
```

### 3) Configurar variaveis de ambiente

O projeto inclui o arquivo `.env.example`. Copie-o para criar o seu `.env`:

```bash
cp .env.example .env
```

Edite o `.env` com seus valores reais (não versionado):

```env
GCP_PROJECT_ID=seu-project-id
GOOGLE_APPLICATION_CREDENTIALS=credentials/google.json
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sua-chave-openai

# Opcional: fallback de modelo/provider
LLM_FALLBACK_PROVIDER=anthropic
LLM_FALLBACK_MODEL=seu-modelo-anthropic
ANTHROPIC_API_KEY=sua-chave-anthropic
```

Configuracao minima:

- Se `LLM_PROVIDER=openai`, `OPENAI_API_KEY` e obrigatoria.
- Se `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` e obrigatoria.
- O fallback so e ativado quando `LLM_FALLBACK_PROVIDER` e `LLM_FALLBACK_MODEL` estiverem definidos.
- O grafo continua usando a mesma interface de tool calling para ambos os providers.

### 4) Validar acesso ao BigQuery (smoke test)

```bash
poetry run python scripts/smoke_test_bigquery.py
```

Se tudo estiver correto, voce vera um retorno com `[OK]` e o total de usuarios no periodo testado.

### 5) Subir API local

```bash
poetry run fastapi dev
```

### 6) Testar endpoint de health

```bash
curl http://127.0.0.1:8000/health
```

## Controle de Custo (Free Tier)

Para minimizar risco de cobranca, use os controles no GCP:

1. Limite por query na UI do BigQuery.
1. Quota diaria no projeto GCP.
1. Budget e alertas no Billing.

Boas praticas adicionais:

- Use `LIMIT` nas consultas exploratorias.
- Sempre rode `Dry run` antes de queries novas.
- Mantenha o `Processing location` em `US` para o dataset publico.

## Estrutura Atual

- .specs/requirements.md
- .specs/design.md
- .specs/tasks.md
- app/main.py
- app/utils/config.py
- app/clients/bigquery_client.py
- scripts/smoke_test_bigquery.py
- agents.md
- case.md

## Dataset

- Fonte: bigquery-public-data.thelook_ecommerce
- Tabelas principais:
  - users
  - orders
  - order_items

## Proximos Passos

1. Definir schemas Pydantic de entrada/saida das tools
2. Implementar tools `traffic_volume_analyzer` e `channel_performance_analyzer`
3. Montar o fluxo de roteamento no LangGraph
4. Expor endpoint principal de consulta
5. Criar CLI de consulta fim-a-fim
