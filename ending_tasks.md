# Tarefas Priorizadas — Fechamento de Gaps

> Tarefas ordenadas por urgência e impacto na avaliação. Cada tarefa indica o critério afetado, o esforço estimado e o que deve ser entregue.

---

## 🔴 P0 — Obrigatório para entrega

### T1 — README.md completo

**Critérios afetados:** Todos (entregável obrigatório explícito no case.md §6)
**Esforço:** ~30 min
**Impacto:** Extremo — é a primeira coisa que o avaliador lê

O README deve conter:

1. **Título e descrição curta** — o que é o projeto, em uma frase
2. **Diagrama de arquitetura** — Mermaid diagram mostrando o fluxo:
   - `Pergunta → Router → [Tool Executor | Short-Circuit] → Insight Synthesizer → Resposta`
   - Indicar que o Router é determinístico (sem custo de LLM) e o Synthesizer usa LLM
3. **Explicação das tools criadas e por quê:**
   - `traffic_volume_analyzer` — volume de usuários por canal (query na tabela `users`)
   - `channel_performance_analyzer` — pedidos e receita por canal (JOIN `users → orders → order_items`)
   - Por que duas tools separadas: separação de responsabilidade, queries otimizadas para cada métrica
4. **Instruções de setup:**
   - Pré-requisitos (Python 3.10+, Poetry, conta GCP gratuita)
   - `poetry install`
   - Como obter credenciais GCP e colocar em `credentials/google.json`
   - Como configurar chaves de API (OpenAI ou Anthropic)
   - Copiar `.env.example` para `.env` e preencher
   - `poetry run fastapi dev` para API
   - `poetry run analyst-chat` para CLI
5. **Exemplos de uso** — 2-3 perguntas com output esperado (pode ser log real da CLI)
6. **Decisões arquiteturais relevantes:**
   - Router heurístico vs. LLM-driven e o trade-off
   - SQL parametrizada
   - Suporte a multi-turn via `thread_id`
7. **Limitações conhecidas** — o que o MVP não faz (ex: métricas derivadas como ROAS, filtro por status do pedido)

**Definição de pronto:** Avaliador consegue subir o projeto do zero seguindo apenas o README.

---

### T2 — Verificar que o repositório está público no GitHub

**Critérios afetados:** Entregável obrigatório (case.md §6)
**Esforço:** 1 min
**Impacto:** Blocker — sem acesso público, não há avaliação

- Acessar `https://github.com/<user>/media-traffic-ai-analyst` em aba anônima
- Se privado, tornar público nas Settings do repo

**Definição de pronto:** URL acessível sem autenticação.

---

## 🟡 P1 — Alto impacto na nota

### T3 — Demonstrar ciclo completo de tool calling LLM-driven

**Critério afetado:** Arquitetura do Agente (peso Alto)
**Esforço:** ~1-2h
**Impacto:** Alto — o case diz *"o agente deve decidir quando precisa usar uma ferramenta"*

O gap atual: o `build_tool_enabled_llm` faz `.bind_tools()` mas o grafo nunca usa um nó onde o LLM decide chamar a tool. O fluxo é `router heurístico → invocação direta → síntese`. Isso funciona bem, mas pode não demonstrar tool calling como o avaliador espera.

**Opções (escolher uma):**

**Opção A — Refatorar o grafo para usar tool calling nativo (recomendado)**
- Substituir o nó `tool_executor` por um nó `agent` que recebe o LLM com tools bound
- O LLM recebe a pergunta + system prompt e decide se/qual tool chamar
- O resultado da tool volta para o LLM que sintetiza a resposta
- O router heurístico pode continuar existindo como fast-path para short-circuits (fora de escopo, clarificações), mas o caminho feliz passa pelo LLM com tools

**Opção B — Documentar a decisão no README (menor esforço, menor impacto)**
- Explicar que o router heurístico é uma escolha de design para:
  - Reduzir custo de tokens (não gasta LLM para classificar)
  - Garantir determinismo no roteamento
  - Manter latência baixa
- Mencionar que o `build_tool_enabled_llm` existe como extensão para cenários LLM-driven

> [!IMPORTANT]
> A Opção A é mais segura para a avaliação. O case usa a frase "Tool Calling (Function Calling)" como requisito técnico obrigatório (§3), não como nice-to-have. Um router puramente regex pode ser interpretado como ausência de tool calling.

**Definição de pronto:** O avaliador consegue ver no debug ou no código que o LLM decide chamar uma tool, recebe o resultado e formula a resposta.

---

### T4 — Incluir exemplo real de sessão no README

**Critérios afetados:** Visão de Produto (peso Alto)
**Esforço:** ~15 min
**Impacto:** Alto — mostra o produto funcionando sem o avaliador precisar rodar

- Rodar 3-4 perguntas pela CLI com `--debug`
- Capturar as perguntas do case.md §4:
  - `"Como foi o volume de usuarios vindos de Search no ultimo mes?"`
  - `"Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-03-31? E por que?"`
- Capturar um follow-up conversacional
- Capturar uma recusa de fora de escopo
- Colar output formatado no README como sessão de exemplo

**Definição de pronto:** README contém bloco de código com sessão real mostrando perguntas → respostas.

---

### T5 — Validar respostas nas perguntas exatas do case

**Critério afetado:** Visão de Produto (peso Alto)
**Esforço:** ~20 min
**Impacto:** Alto — são as perguntas que o avaliador provavelmente vai testar

Executar manualmente as perguntas do case.md §4 e verificar:

| Pergunta do case | Verificar |
|---|---|
| `"Como foi o volume de usuarios vindos de 'Search' no ultimo mes?"` | Retorna dados, insight acionável, não despejo técnico |
| `"Qual dos canais tem a melhor performance? E por que?"` | Ranking com interpretação, responde o "por quê" |

Para cada uma: a resposta deve ser algo que um gerente de mídia entenderia e acharia útil.

**Definição de pronto:** Ambas as perguntas retornam respostas de qualidade business-grade.

---

## 🟢 P2 — Diferencial competitivo

### T6 — Adicionar ticket médio como métrica derivada

**Critério afetado:** Engenharia de Dados, Visão de Produto
**Esforço:** ~15 min
**Impacto:** Médio — enriquece o insight financeiro sem nova tool

- Adicionar campo `avg_ticket` (`total_revenue / total_orders`) no `ChannelPerformanceRow`
- Ou calcular via `ROUND(SUM(sale_price) / COUNT(DISTINCT order_id), 2)` na query
- Atualizar o `ChannelPerformanceOutput` schema
- O Insight Synthesizer já vai usar automaticamente via prompt

**Definição de pronto:** Resposta de performance inclui ticket médio quando relevante.

---

### T7 — Filtrar pedidos cancelados/devolvidos da receita

**Critério afetado:** Engenharia de Dados, Visão de Produto
**Esforço:** ~10 min
**Impacto:** Médio — demonstra atenção a qualidade de dados

- Adicionar `WHERE o.status NOT IN ('Cancelled', 'Returned')` na query de channel performance
- Ou documentar como limitação conhecida no README se não quiser arriscar regressão

**Definição de pronto:** Receita reportada não inclui pedidos cancelados, ou limitação documentada.

---

### T8 — Mencionar limitações conhecidas no README

**Critério afetado:** Visão de Produto
**Esforço:** ~5 min
**Impacto:** Baixo-Médio — demonstra maturidade de engenharia

Seção curta no README listando:
- Métricas não deriváveis (ROAS, CAC, CTR) — não estão no dataset
- Persistência de conversa é em memória (perde estado ao reiniciar)
- Sem UI web neste MVP
- `traffic_source` singular no filtro (comparações usam canal nulo)

**Definição de pronto:** Seção "Limitações" no README.

---

## Ordem de Execução Sugerida

```
T2 (1 min)  →  T1 (30 min)  →  T3 (1-2h)  →  T5 (20 min)  →  T4 (15 min)
                                                                    ↓
                                              T6 (15 min)  →  T7 (10 min)  →  T8 (5 min)
```

**Tempo total estimado:** ~3h para P0+P1, ~30 min adicionais para P2.

> [!TIP]
> T1 e T3 são os dois itens com maior retorno. T1 porque é entregável obrigatório e T3 porque afeta o critério de peso mais alto do desafio. Se tiver que escolher apenas dois, faça esses.
