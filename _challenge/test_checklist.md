# Checklist Final de Validação — Readiness para Entrega

> Objetivo: validar se o projeto está realmente pronto para entrega contra os critérios de `case.md`, não apenas se "funciona no meu ambiente".
>
> Como usar:
>
> 1. Rode os gates automatizados.
> 2. Execute o checklist manual em ordem.
> 3. Marque cada item como `✅`, `⚠️` ou `❌`.
> 4. Só considere o projeto pronto quando todos os itens `P0` estiverem em `✅`.

---

## 1. Gate de Aceite

### 1.1 Condição mínima para considerar "pronto"

| Prioridade | Condição | Status |
| --- | --- | --- |
| P0 | `poetry run verify --agent` passa | ✅ |
| P0 | `poetry run pytest --agent` passa | ✅ |
| P0 | API sobe e responde em `/health` e `/query` | ✅ |
| P0 | CLI `analyst-chat` funciona contra a API local | ✅ |
| P0 | Tool Calling real está demonstrável | ✅ |
| P0 | Perguntas fora de escopo são tratadas corretamente | ✅ |
| P0 | Respostas com dados trazem leitura útil de negócio, não apenas números | ✅ |
| P0 | README final cobre setup, credenciais e arquitetura | ⬜ |
| P0 | Repositório público no GitHub pronto para envio | ✅ |
| P1 | `pytest -m live` passa com ambiente configurado | ✅ |
| P1 | Multi-turn / `thread_id` demonstrado e coberto por `pytest` | ✅ |
| P1 | `X-Debug` demonstrado e coberto por `pytest` | ✅ |

### 1.2 Evidência automatizada atual

| Evidência | Comando | Resultado esperado | Status |
| --- | --- | --- | --- |
| Gate estático | `poetry run verify --agent` | `ruff`, `compileall` e `pyright` em `OK` | ✅ |
| Suite determinística | `poetry run pytest --agent` | Suite local passa sem depender de BigQuery/LLM reais | ✅ |
| Suite live | `poetry run pytest -m live` | Passa ou faz skip limpo quando ambiente não está configurado | ✅ |

### 1.3 Mapa de automação

| Camada | Comando | Cobre | Observação |
| --- | --- | --- | --- |
| Readiness rápido | `poetry run pytest tests/readiness/test_readiness_suite.py --agent` | S1-S4, S6, T1-T3, C1-C5, F1-F2, O1-O5, D1-D7, Q1-Q4 | determinístico e rápido |
| Readiness live | `poetry run pytest -m "readiness and live" --agent` | tool calling real, tools reais no BigQuery, graph/API com ambiente real | opt-in por ambiente |
| Wrapper opcional | `scripts/run_readiness_checks.sh [--verify] [--live] [--full]` | mesma trilha de readiness com atalho local | útil para regressão curta |
| Manual obrigatório | checklist manual abaixo | S5, T4, R1-R5, README final e conferência pública do repo | não vale automatizar tudo |

---

## 2. Requisitos de `case.md`

### 2.1 Backend e orquestração de IA

| Item | O que precisa estar provado | Como validar | Status |
| --- | --- | --- | --- |
| Python 3.10+ | Projeto roda na stack pedida | Conferir `pyproject.toml` e ambiente local | ⬜ |
| FastAPI ou Flask | Superfície HTTP real existe | `poetry run fastapi dev` e `/health` | ⬜ |
| Orquestrador de IA | Não é prompt único; há orquestração explícita | Conferir `app/graph/workflow.py` | ⬜ |
| Tool Calling | O agente decide quando chamar ferramenta | Ver seção 4.2, testes T1-T4 abaixo | ⬜ |
| Separação prompt vs execução | Prompt, workflow e tools estão separados | Revisão rápida em `app/graph/prompts.py`, `app/graph/workflow.py`, `app/tools/` | ⬜ |

### 2.2 Dados e engenharia

| # | Teste | Como testar | Resultado Esperado | Status |
|---|---|---|---|---|
| B1.1 | Health check | `curl http://localhost:8000/health` | `{"status":"ok","environment":"dev"}` | ✅ |
| B1.2 | Query válida | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"Receita de Search entre 2024-01-01 e 2024-01-31"}'` | 200 com `answer`, `tools_used`, `metadata` | ✅ |
| B1.3 | Query vazia | `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":""}'` | 422 Validation Error | ✅ |
| B1.4 | Debug header | Repetir B1.2 com `-H "X-Debug: true"` | `metadata.debug` populado com `resolved_question` e `router_decision` | ✅ |
| B1.5 | Thread continuidade | Usar `thread_id` retornado de B1.2 em nova request | `thread_id_source: "provided"`, `context_message_count` > anterior | ✅ |

---

## 3. Gate Automatizado

### 3.1 Verificação local obrigatória

| # | Comando | Resultado esperado | Status |
| --- | --- | --- | --- |
| G1 | `poetry run verify --agent` | Tudo `OK` | ✅ |
| G2 | `poetry run pytest --agent` | Suite determinística passa | ✅ |
| G3 | `poetry run analyst-chat --help` | CLI sobe e mostra ajuda | ✅ |

### 3.2 Verificação live antes da entrega

> Rodar somente com `GOOGLE_APPLICATION_CREDENTIALS` e chave de provider configuradas.

| # | Comando | Resultado esperado | Status |
| --- | --- | --- | --- |
| L1 | `poetry run pytest -m live` | Live smoke passa ou faz skip limpo por ambiente | ✅ |
| L2 | `poetry run pytest --run-live --agent` | Suite local + live sem surpresas | ⬜ |
| L3 | `poetry run pytest -m "readiness and live" --agent` | Gate live curto passa quando ambiente estiver pronto | ✅ |

---

## 4. Checklist Manual da Superfície de Produto

### 4.1 API e CLI

> Suba a API com `poetry run fastapi dev`.
>
> Use a CLI com `poetry run analyst-chat --debug`.

| # | Prioridade | Teste | Ação | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| S1 | P0 | Health check | `curl http://127.0.0.1:8000/health` | `status=ok` | ✅ |
| S2 | P0 | Query HTTP válida | POST `/query` com pergunta de receita | `200`, `answer`, `tools_used`, `metadata` | ✅ |
| S3 | P0 | Payload inválido | POST `/query` com `question=""` | `422` | ✅ |
| S4 | P1 | `X-Debug` | Repetir S2 com `X-Debug: true` | `metadata.debug` preenchido | ✅ |
| S5 | P0 | CLI conversa com API | Abrir `analyst-chat` e enviar uma pergunta simples | Resposta renderizada sem stack trace | ✅ |
| S6 | P1 | `thread_id` | Fazer 2 turnos no mesmo thread | `context_message_count` cresce | ✅ |

### 4.2 Tool Calling e consultas com dados

| # | Prioridade | Cenário | Pergunta | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | P0 | Volume por canal | `Como foi o volume de usuarios vindos de Search no ultimo mes?` | `traffic_volume_analyzer` | ✅ |
| T2 | P0 | Receita por canal | `Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?` | `channel_performance_analyzer` | ✅ |
| T3 | P0 | Ranking geral | `Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-01-31?` | tool financeira com `traffic_source` nulo | ✅ |
| T4 | P0 | Comparação entre canais | `Compare Search e Organic entre 2024-01-01 e 2024-01-31.` | comparação útil em linguagem natural | ⬜ |

### 4.3 Clarificações e ambiguidade

| # | Prioridade | Cenário | Sequência | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| C1 | P0 | Falta de período | `Qual foi a receita de Search?` | pede período, não quebra | ✅ |
| C2 | P0 | Follow-up de período | `Qual foi a receita de Search?` → `Entre 2024-01-01 e 2024-01-31.` | merge correto e execução da tool | ✅ |
| C3 | P0 | Métrica ambígua | `Como o Search performou ontem?` | agente pede clarificação entre volume e performance financeira | ✅ |
| C4 | P0 | Resposta à ambiguidade | `Como o Search performou ontem?` → `volume de usuarios` | preserva `ontem` e chama `traffic_volume_analyzer` | ✅ |
| C5 | P0 | Resposta à ambiguidade | `Como o Search performou ontem?` → `receita` | preserva `ontem` e chama `channel_performance_analyzer` | ✅ |

### 4.4 Follow-ups com contexto

| # | Prioridade | Cenário | Sequência | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | P0 | Diagnóstico | `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?` → `O que explica essa concentracao?` | não cai em `out_of_scope`; responde com leitura diagnóstica | ✅ |
| F2 | P0 | Estratégia | `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?` → `Quais acoes devemos priorizar agora?` | não cai em `out_of_scope`; responde com leitura estratégica | ✅ |
| F3 | P1 | Follow-up adicional | após F1 ou F2, fazer mais 1-2 perguntas naturais | continuidade consistente no mesmo thread | ✅ |

### 4.5 Fora de escopo e guardrails

| # | Prioridade | Cenário | Pergunta | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| O1 | P0 | Fora de escopo puro | `Me conta uma piada` | recusa curta e educada, sem tool call | ✅ |
| O2 | P0 | Métrica ausente | `Qual foi o ROAS de Search ontem?` | recusa coerente com schema | ✅ |
| O3 | P0 | Dimensão ausente | `Qual campanha deu mais lucro no Facebook ontem?` | recusa coerente com schema | ✅ |
| O4 | P0 | Data inválida | `Qual foi a receita de Search em 31/02/2026?` | clarificação por data inválida | ✅ |
| O5 | P1 | Intervalo invertido | `Qual foi a receita de Search entre 2024-02-10 e 2024-01-10?` | clarificação por data inválida/invertida | ✅ |

### 4.6 Formatos temporais

| # | Prioridade | Cenário | Pergunta | Resultado esperado | Status |
| --- | --- | --- | --- | --- | --- |
| D1 | P1 | ISO | `Usuarios de Search entre 2024-01-01 e 2024-01-31` | datas corretas | ✅ |
| D2 | P1 | BR longa | `Usuarios de Search entre 01/01/2024 e 31/01/2024` | datas corretas | ✅ |
| D3 | P1 | BR curta | `Usuarios de Search entre 01/01/24 e 31/01/24` | datas corretas | ✅ |
| D4 | P1 | Relativo ontem | `Receita de Search ontem` | resolve para um dia | ✅ |
| D5 | P1 | Este mês | `Volume de trafego este mes` | resolve início do mês atual | ✅ |
| D6 | P1 | Último mês | `Receita por canal no ultimo mes` | resolve mês anterior completo | ✅ |
| D7 | P1 | Últimos N dias | `Usuarios nos ultimos 7 dias` | resolve janela correta | ✅ |

---

## 5. Qualidade da Resposta Final

> Avaliar não só se “retornou algo”, mas se a resposta ajuda um gerente de Mídia/Growth.

| # | Prioridade | Critério | O que observar | Status |
| --- | --- | --- | --- | --- |
| R1 | P0 | Linguagem | Resposta em pt-BR, sem SQL exposta | ✅ |
| R2 | P0 | Utilidade | Há insight acionável, não só despejo de números | ✅ |
| R3 | P0 | Coerência | Não inventa métricas, canais, campanhas ou causalidade | ✅ |
| R4 | P0 | Leitura de negócio | Traz implicação para Growth/Mídia | ✅ |
| R5 | P1 | Follow-up | Quando não sabe a causa, explicita hipótese vs observação | ⬜ |

---

## 6. Dados e SQL

| # | Prioridade | Verificação | Como validar | Status |
| --- | --- | --- | --- | --- |
| Q1 | P0 | `traffic_volume_analyzer` consulta `users` corretamente | revisão de código + readiness + teste T1 | ✅ |
| Q2 | P0 | `channel_performance_analyzer` faz JOIN entre `users`, `orders` e `order_items` | revisão de código + readiness + teste T2/T3 | ✅ |
| Q3 | P0 | SQL parametrizada | readiness + revisão curta das queries | ✅ |
| Q4 | P0 | Sem concatenação de input na SQL | readiness + revisão de código | ✅ |
| Q5 | P1 | Ferramentas reais no BigQuery | `pytest -m live` ou smoke manual com credenciais | ✅ |

---

## 7. Entregáveis Finais

| # | Prioridade | Item | O que precisa ser checado | Status |
| --- | --- | --- | --- | --- |
| E1 | P0 | GitHub público | repositório acessível publicamente | ✅ |
| E2 | P0 | README setup | dependências, `poetry`, credenciais GCP e chaves de LLM | ⬜ |
| E3 | P0 | README arquitetura | explicação clara do agente e das tools | ⬜ |
| E4 | P0 | README execução | como subir API, usar CLI e rodar testes | ⬜ |
| E5 | P1 | `.env.example` | variáveis mínimas documentadas | ⬜ |
| E6 | P1 | Evidência live | se possível, incluir checkpoint final com ambiente real | ⬜ |

---

## 8. Decisão Final

### 8.1 Go / No-Go

| Resultado | Critério |
| --- | --- |
| GO | Todos os itens `P0` em `✅` |
| GO com ressalva | Todos os `P0` em `✅` e apenas itens `P1` restantes que não bloqueiem a demo |
| NO-GO | Qualquer item `P0` em `⚠️` ou `❌` |

### 8.2 Registro final da entrega

Preencher no momento do fechamento:

| Campo | Valor |
| --- | --- |
| Data da validação final | ⬜ |
| `poetry run verify --agent` | ⬜ |
| `poetry run pytest --agent` | ⬜ |
| `poetry run pytest -m live` | ⬜ |
| README final revisado | ⬜ |
| Repo público conferido | ⬜ |
| Status final | ⬜ |
| Observações finais | ⬜ |
