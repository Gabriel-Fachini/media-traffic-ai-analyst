# Checklist Manual de Testes — Validação Pré-Entrega

> **Como usar:** Suba a API com `poetry run fastapi dev` e use a CLI com `poetry run analyst-chat --debug`.
> Marque cada item como ✅ (passa), ⚠️ (parcial) ou ❌ (falha) conforme resultado.

---

## A — Arquitetura do Agente

### A.1 Tool Calling Funciona End-to-End

| # | Teste | Pergunta / Ação | Resultado Esperado | Status |
|---|---|---|---|---|
| A1.1 | Tool `traffic_volume_analyzer` é chamada | `"Quantos usuarios vieram de Search entre 2024-01-01 e 2024-01-31?"` | `tools_used: ["traffic_volume_analyzer"]`, resposta com user_count | ✅ |
| A1.2 | Tool `channel_performance_analyzer` é chamada | `"Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?"` | `tools_used: ["channel_performance_analyzer"]`, resposta com receita | ✅ |
| A1.3 | Ambas tools com canal nulo | `"Quais canais trouxeram mais usuarios entre 2024-01-01 e 2024-01-31?"` | `tools_used` contém tool, resultado com múltiplos canais | ✅ |
| A1.4 | Comparação entre canais | `"Compare Search e Organic entre 2024-01-01 e 2024-01-31."` | `tools_used: ["channel_performance_analyzer"]`, resposta com comparação | ✅ |

### A.2 Router Classifica Intent Corretamente (verificar via debug)

| # | Teste | Pergunta | Intent esperado no debug | Status |
|---|---|---|---|---|
| A2.1 | Volume de tráfego | `"Volume de trafego de Search nos ultimos 30 dias"` | `traffic_volume` | ✅ |
| A2.2 | Performance financeira | `"Qual canal vendeu mais no ultimo mes?"` | `channel_performance` | ✅ |
| A2.3 | Ambíguo | `"Como foi Search nos ultimos 7 dias?"` | `ambiguous_analytics` + clarificação | ✅ |
| A2.4 | Fora de escopo | `"Qual o clima em São Paulo?"` | `out_of_scope` + recusa educada | ✅ |

### A.3 Separação Prompt vs. Execução

| # | Verificação | Como validar | Status |
|---|---|---|---|
| A3.1 | Prompts isolados em `prompts.py` | Abrir [prompts.py](file:///Users/gabriel_fachini/Desktop/repos/media-traffic-ai-analyst/app/graph/prompts.py) — não deve ter lógica de execução | ✅ |
| A3.2 | Tools isoladas em `tools/` | Abrir [tools/](file:///Users/gabriel_fachini/Desktop/repos/media-traffic-ai-analyst/app/tools/) — SQL e lógica de dados separada | ✅ |
| A3.3 | Orquestração no grafo | Abrir [workflow.py](file:///Users/gabriel_fachini/Desktop/repos/media-traffic-ai-analyst/app/graph/workflow.py) — nós do grafo não contêm SQL | ✅ |

---

## B — Qualidade do Backend Python

### B.1 API Funcional

<<<<<<< Updated upstream
| # | Teste | Como testar | Resultado Esperado | Status |
|---|---|---|---|---|
| B1.1 | Health check | `curl http://localhost:8000/health` | `{"status":"ok","environment":"dev"}` | ✅ |
| B1.2 | Query válida | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"Receita de Search entre 2024-01-01 e 2024-01-31"}'` | 200 com `answer`, `tools_used`, `metadata` | ✅ |
| B1.3 | Query vazia | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":""}'` | 422 Validation Error | ✅ |
| B1.4 | Debug header | Repetir B1.2 com `-H "X-Debug: true"` | `metadata.debug` populado com `resolved_question` e `router_decision` | ✅ |
| B1.5 | Thread continuidade | Usar `thread_id` retornado de B1.2 em nova request | `thread_id_source: "provided"`, `context_message_count` > anterior | ✅ |
=======
| Item | O que precisa estar provado | Como validar | Status |
| --- | --- | --- | --- |
| Python 3.10+ | Projeto roda na stack pedida | Conferir `pyproject.toml` e ambiente local | ⬜ |
| FastAPI ou Flask | Superfície HTTP real existe | `poetry run fastapi dev` e `/health` | ⬜ |
| Orquestrador de IA | Não é prompt único; há orquestração explícita | Conferir `app/graph/workflow.py` | ⬜ |
| Tool Calling | O agente decide quando chamar ferramenta | Ver seção 4.2, testes T1-T4 abaixo | ⬜ |
| Separação prompt vs execução | Prompt, workflow e tools estão separados | Revisão rápida em `app/graph/prompts.py`, `app/graph/workflow.py`, `app/tools/` | ⬜ |
>>>>>>> Stashed changes

### B.2 Tratamento de Erros

| # | Teste | Como testar | Resultado Esperado | Status |
|---|---|---|---|---|
| B2.1 | Payload inválido | `curl -X POST http://localhost:8000/query -d '{}'` | 422 com detalhe de campo faltando | ✅ |
| B2.2 | Campo extra rejeitado | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"teste","extra":"field"}'` | 422 `extra inputs are not permitted` | ✅ |

### B.3 Verificação Estática

| # | Teste | Comando | Resultado Esperado | Status |
|---|---|---|---|---|
| B3.1 | Lint + type check | `poetry run verify` | 0 erros em todos os estágios | ✅ |
| B3.2 | Testes determinísticos | `poetry run pytest` | Todos passam sem BigQuery/LLM | ✅ |

---

## C — Engenharia de Dados (SQL)

### C.1 Queries Retornam Dados Corretos

| # | Teste | Pergunta | O que verificar | Status |
|---|---|---|---|---|
| C1.1 | Volume com um canal | `"Usuarios de Facebook entre 2024-01-01 e 2024-03-31"` | Retorna apenas Facebook, user_count > 0 | ✅ |
| C1.2 | Volume todos os canais | `"Volume de usuarios entre 2024-01-01 e 2024-03-31"` | Retorna múltiplos canais (Search, Organic, Facebook, etc.) | ✅ |
| C1.3 | Performance com JOIN | `"Receita por canal entre 2024-01-01 e 2024-03-31"` | `total_orders` e `total_revenue` por canal, ordenados | ✅ |
| C1.4 | Período sem dados | `"Receita de Search ontem"` (se today > 2025) | Resposta tratada (mensagem de "sem dados" ou resultado 0), sem crash | ✅ |

### C.2 Segurança SQL

| # | Verificação | Como validar | Status |
|---|---|---|---|
| C2.1 | Parametrização | Código usa `bigquery.ScalarQueryParameter` em todas as queries | ✅ |
| C2.2 | Sem concatenação | Nenhum f-string com input de usuário na SQL | ✅ |

---

## D — Visão de Produto

### D.1 Respostas São Úteis (não despejo técnico)

| # | Teste | Pergunta | O que avaliar na resposta | Status |
|---|---|---|---|---|
| D1.1 | Insight acionável | `"Como foi o volume de usuarios vindos de Search no ultimo mes?"` | Resposta menciona tendência ou sinal, não apenas número bruto | ✅ |
| D1.2 | Ranking com interpretação | `"Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-03-31? E por que?"` | Ranking + interpretação de negócio, não tabela crua | ✅ |
| D1.3 | Linguagem de negócio | Qualquer resposta com dados | Em pt-BR, sem SQL exposta, sem jargão técnico | ✅ |

### D.2 Tratamento de Fora de Escopo

| # | Teste | Pergunta | Resultado Esperado | Status |
|---|---|---|---|---|
| D2.1 | Tema totalmente fora | `"Me conta uma piada"` | Recusa educada, sem tool call | ✅ |
| D2.2 | Métrica não suportada | `"Qual o ROAS de Search ontem?"` | Recusa explicando que ROAS não está no dataset | ✅ |
| D2.3 | Campanha não suportada | `"Qual campanha deu mais lucro no Facebook ontem?"` | Recusa explicando que campanha/lucro não existe no schema | ✅ |
| D2.4 | Canal não suportado | `"Trafego de TikTok no ultimo mes"` | Recusa informando canais suportados | ✅ |
| D2.5 | Sem período | `"Quantos usuarios vieram de Search?"` | Pede esclarecimento de período, não falha silenciosamente | ✅ |

### D.3 Fluxo Conversacional Multi-Turn

| # | Teste | Sequência | Resultado Esperado | Status |
|---|---|---|---|---|
| D3.1 | Clarificação de data | 1: `"Quantos usuarios vieram de Search?"` → 2: `"nos ultimos 7 dias"` | Turno 2 merge com turno 1 e retorna dados | ✅ |
| D3.2 | Clarificação de métrica | 1: `"Como foi Search nos ultimos 7 dias?"` (se ambíguo) → 2: `"receita"` ou `"usuarios"` | Turno 2 resolve ambiguidade e retorna dados corretos | ✅ |
| D3.3 | Follow-up estratégico | 1: Qualquer query com dados → 2: `"O que fazer para melhorar esse canal?"` | Resposta com sugestões baseadas no contexto anterior | ✅ |
| D3.4 | Follow-up diagnóstico | 1: Query com dados → 2: `"Por que Search ficou abaixo de Organic?"` | Interpretação/hipótese baseada nos dados, não recusa | ✅ |

### D.4 Formatos Temporais

| # | Teste | Pergunta | Resultado Esperado | Status |
|---|---|---|---|---|
| D4.1 | ISO | `"Usuarios de Search entre 2024-01-01 e 2024-01-31"` | Dados do período correto | ✅ |
| D4.2 | BR DD/MM/AAAA | `"Usuarios de Search entre 01/01/2024 e 31/01/2024"` | Mesmo resultado de D4.1 | ✅ |
| D4.3 | BR DD/MM/AA | `"Usuarios de Search entre 01/01/24 e 31/01/24"` | Mesmo resultado de D4.1 | ✅ |
| D4.4 | Relativo — ontem | `"Receita de Search ontem"` | Datas resolvidas para ontem | ✅ |
| D4.5 | Relativo — este mês | `"Volume de trafego este mes"` | start_date = dia 1 do mês atual | ✅ |
| D4.6 | Relativo — último mês | `"Receita por canal no ultimo mes"` | Período do mês anterior completo | ✅ |
| D4.7 | Relativo — últimos N dias | `"Usuarios nos ultimos 7 dias"` | 7 dias corridos a partir de hoje | ✅ |

---

## E — Entregáveis

| # | Verificação | Status |
|---|---|---|
| E1 | Repositório está público no GitHub | ✅ |
| E2 | README.md com instruções de setup (dependências, chaves API, credenciais GCP) | ⬜ |
| E3 | README.md com diagrama ou explicação da arquitetura | ⬜ |
| E4 | README.md com explicação das tools criadas e por quê | ⬜ |
| E5 | `.env.example` com todas as variáveis documentadas | ✅ |

---

## Resumo de Prioridade

| Prioridade | Item | Impacto |
|---|---|---|
| 🔴 P0 | E2, E3, E4 — README completo | Critério de entregável obrigatório |
| 🔴 P0 | E1 — Repo público | Não entregável sem isso |
| 🟡 P1 | A1.1-A1.4 — Tool calling funciona end-to-end | Critério de peso Alto |
| 🟡 P1 | D1.1-D1.3 — Respostas são úteis e insight-driven | Critério de peso Alto |
| 🟡 P1 | D2.1-D2.5 — Fora de escopo bem tratado | Critério de peso Alto |
| 🟢 P2 | D3.1-D3.4 — Multi-turn conversacional | Diferencial |
| 🟢 P2 | D4.1-D4.7 — Formatos temporais | Robustez |
