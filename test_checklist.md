# Checklist Final de Validação — Readiness para Entrega

> Objetivo: validar se o projeto está realmente pronto para entrega contra os critérios de `case.md`, não apenas se "funciona no meu ambiente".
>
> Como usar:
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
| P1 | Multi-turn / `thread_id` demonstrado manualmente | ✅ |
| P1 | `X-Debug` demonstra observabilidade suficiente para depuração | ✅ |

### 1.2 Evidência automatizada atual

| Evidência | Comando | Resultado esperado | Status |
| --- | --- | --- | --- |
| Gate estático | `poetry run verify --agent` | `ruff`, `compileall` e `pyright` em `OK` | ✅ |
| Suite determinística | `poetry run pytest --agent` | Suite local passa sem depender de BigQuery/LLM reais | ✅ |
| Suite live | `poetry run pytest -m live` | Passa ou faz skip limpo quando ambiente não está configurado | ✅ |

---

## 2. Requisitos de `case.md`

### 2.1 Backend e orquestração de IA

| Item | O que precisa estar provado | Como validar | Status |
| --- | --- | --- | --- |
| Python 3.10+ | Projeto roda na stack pedida | Conferir `pyproject.toml` e ambiente local | ⬜ |
| FastAPI ou Flask | Superfície HTTP real existe | `poetry run fastapi dev` e `/health` | ⬜ |
| Orquestrador de IA | Não é prompt único; há orquestração explícita | Conferir `app/graph/workflow.py` | ⬜ |
| Tool Calling | O agente decide quando chamar ferramenta | Testes A1 e A2 abaixo | ⬜ |
| Separação prompt vs execução | Prompt, workflow e tools estão separados | Revisão rápida em `app/graph/prompts.py`, `app/graph/workflow.py`, `app/tools/` | ⬜ |

### 2.2 Dados e engenharia

| Item | O que precisa estar provado | Como validar | Status |
| --- | --- | --- | --- |
| BigQuery oficial | Integração usa cliente Python oficial | Conferir `app/clients/bigquery_client.py` | ⬜ |
| SQL parametrizada | Não há concatenação de input de usuário na query | Revisão rápida em `app/tools/*.py` | ⬜ |
| JOINs e agregações | `users`, `orders` e `order_items` estão sendo usados corretamente | Perguntas de receita/performance e revisão da tool | ⬜ |

### 2.3 Critérios de avaliação

| Critério | O que precisa ficar claro para o avaliador | Status |
| --- | --- | --- |
| Arquitetura do Agente | O fluxo `preprocess -> agent -> tool_executor -> agent` está compreensível e demonstrável | ⬜ |
| Qualidade do Backend Python | Tipagem, contratos, tratamento de erro e estrutura estão limpos | ⬜ |
| Engenharia de Dados | Queries fazem sentido para o MVP e retornam dados corretos | ⬜ |
| Visão de Produto | As respostas ajudam um time de Mídia/Growth, sem despejo técnico | ⬜ |

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

---

## 4. Checklist Manual da Superfície de Produto

### 4.1 API e CLI

> Suba a API com `poetry run fastapi dev`.
>
> Use a CLI com `poetry run analyst-chat --debug`.

| # | Teste | Ação | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| S1 | Health check | `curl http://127.0.0.1:8000/health` | `status=ok` | P0 | ✅ |
| S2 | Query HTTP válida | POST `/query` com pergunta de receita | `200`, `answer`, `tools_used`, `metadata` | P0 | ✅ |
| S3 | Payload inválido | POST `/query` com `question=""` | `422` | P0 | ⬜ |
| S4 | `X-Debug` | Repetir S2 com `X-Debug: true` | `metadata.debug` preenchido | P1 | ✅ |
| S5 | CLI conversa com API | Abrir `analyst-chat` e enviar uma pergunta simples | Resposta renderizada sem stack trace | P0 | ✅ |
| S6 | `thread_id` | Fazer 2 turnos no mesmo thread | `context_message_count` cresce | P1 | ✅ |

### 4.2 Tool Calling e consultas com dados

| # | Cenário | Pergunta | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | Volume por canal | `Como foi o volume de usuarios vindos de Search no ultimo mes?` | `traffic_volume_analyzer` | P0 | ✅ |
| T2 | Receita por canal | `Qual foi a receita de Search entre 2024-01-01 e 2024-01-31?` | `channel_performance_analyzer` | P0 | ✅ |
| T3 | Ranking geral | `Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-01-31?` | tool financeira com `traffic_source` nulo | P0 | ✅ |
| T4 | Comparação entre canais | `Compare Search e Organic entre 2024-01-01 e 2024-01-31.` | comparação útil em linguagem natural | P0 | ⬜ |

### 4.3 Clarificações e ambiguidade

| # | Cenário | Sequência | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| C1 | Falta de período | `Qual foi a receita de Search?` | pede período, não quebra | P0 | ✅ |
| C2 | Follow-up de período | `Qual foi a receita de Search?` → `Entre 2024-01-01 e 2024-01-31.` | merge correto e execução da tool | P0 | ✅ |
| C3 | Métrica ambígua | `Como o Search performou ontem?` | agente pede clarificação entre volume e performance financeira | P0 | ✅ |
| C4 | Resposta à ambiguidade | `Como o Search performou ontem?` → `volume de usuarios` | preserva `ontem` e chama `traffic_volume_analyzer` | P0 | ✅ |
| C5 | Resposta à ambiguidade | `Como o Search performou ontem?` → `receita` | preserva `ontem` e chama `channel_performance_analyzer` | P0 | ✅ |

### 4.4 Follow-ups com contexto

| # | Cenário | Sequência | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | Diagnóstico | `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?` → `O que explica essa concentracao?` | não cai em `out_of_scope`; responde com leitura diagnóstica | P0 | ✅ |
| F2 | Estratégia | `Como foi a receita dos canais entre 2024-01-01 e 2024-01-31?` → `Quais acoes devemos priorizar agora?` | não cai em `out_of_scope`; responde com leitura estratégica | P0 | ✅ |
| F3 | Follow-up adicional | após F1 ou F2, fazer mais 1-2 perguntas naturais | continuidade consistente no mesmo thread | P1 | ✅ |

### 4.5 Fora de escopo e guardrails

| # | Cenário | Pergunta | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| O1 | Fora de escopo puro | `Me conta uma piada` | recusa curta e educada, sem tool call | P0 | ✅ |
| O2 | Métrica ausente | `Qual foi o ROAS de Search ontem?` | recusa coerente com schema | P0 | ✅ |
| O3 | Dimensão ausente | `Qual campanha deu mais lucro no Facebook ontem?` | recusa coerente com schema | P0 | ✅ |
| O4 | Data inválida | `Qual foi a receita de Search em 31/02/2026?` | clarificação por data inválida | P0 | ⬜ |
| O5 | Intervalo invertido | `Qual foi a receita de Search entre 2024-02-10 e 2024-01-10?` | clarificação por data inválida/invertida | P1 | ⬜ |

### 4.6 Formatos temporais

| # | Cenário | Pergunta | Resultado esperado | Prioridade | Status |
| --- | --- | --- | --- | --- | --- |
| D1 | ISO | `Usuarios de Search entre 2024-01-01 e 2024-01-31` | datas corretas | P1 | ⬜ |
| D2 | BR longa | `Usuarios de Search entre 01/01/2024 e 31/01/2024` | datas corretas | P1 | ⬜ |
| D3 | BR curta | `Usuarios de Search entre 01/01/24 e 31/01/24` | datas corretas | P1 | ⬜ |
| D4 | Relativo ontem | `Receita de Search ontem` | resolve para um dia | P1 | ⬜ |
| D5 | Este mês | `Volume de trafego este mes` | resolve início do mês atual | P1 | ⬜ |
| D6 | Último mês | `Receita por canal no ultimo mes` | resolve mês anterior completo | P1 | ⬜ |
| D7 | Últimos N dias | `Usuarios nos ultimos 7 dias` | resolve janela correta | P1 | ⬜ |

---

## 5. Qualidade da Resposta Final

> Avaliar não só se “retornou algo”, mas se a resposta ajuda um gerente de Mídia/Growth.

| # | Critério | O que observar | Prioridade | Status |
| --- | --- | --- | --- | --- |
| R1 | Linguagem | Resposta em pt-BR, sem SQL exposta | P0 | ✅ |
| R2 | Utilidade | Há insight acionável, não só despejo de números | P0 | ✅ |
| R3 | Coerência | Não inventa métricas, canais, campanhas ou causalidade | P0 | ✅ |
| R4 | Leitura de negócio | Traz implicação para Growth/Mídia | P0 | ✅ |
| R5 | Follow-up | Quando não sabe a causa, explicita hipótese vs observação | P1 | ⬜ |

---

## 6. Dados e SQL

| # | Verificação | Como validar | Prioridade | Status |
| --- | --- | --- | --- | --- |
| Q1 | `traffic_volume_analyzer` consulta `users` corretamente | revisão de código + teste T1 | P0 | ⬜ |
| Q2 | `channel_performance_analyzer` faz JOIN entre `users`, `orders` e `order_items` | revisão de código + teste T2/T3 | P0 | ⬜ |
| Q3 | SQL parametrizada | revisar uso de parâmetros na construção das queries | P0 | ⬜ |
| Q4 | Sem concatenação de input na SQL | revisão de código | P0 | ⬜ |
| Q5 | Ferramentas reais no BigQuery | `pytest -m live` ou smoke manual com credenciais | P1 | ⬜ |

---

## 7. Entregáveis Finais

| # | Item | O que precisa ser checado | Prioridade | Status |
| --- | --- | --- | --- | --- |
| E1 | GitHub público | repositório acessível publicamente | P0 | ⬜ |
| E2 | README setup | dependências, `poetry`, credenciais GCP e chaves de LLM | P0 | ⬜ |
| E3 | README arquitetura | explicação clara do agente e das tools | P0 | ⬜ |
| E4 | README execução | como subir API, usar CLI e rodar testes | P0 | ⬜ |
| E5 | `.env.example` | variáveis mínimas documentadas | P1 | ⬜ |
| E6 | Evidência live | se possível, incluir checkpoint final com ambiente real | P1 | ⬜ |

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
