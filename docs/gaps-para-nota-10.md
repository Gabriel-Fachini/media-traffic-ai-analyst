# Gaps Para Nota 10 — v2 (final)

Este documento substitui a v1. Mantive apenas os itens que:

- um avaliador atento pode notar em 15-30 minutos de correcao;
- levam menos de 15 minutos cada para implementar;
- nao introduzem risco de regressao.

Tudo que nao atende esses tres criterios foi descartado.

## 1. Semantica de moeda nas respostas — ~5 min

**O que e:** as respostas falam de receita mas nao dizem que o dataset esta em dolar.
Um avaliador com perfil de dados pode notar a ambiguidade.

**O que fazer:** adicionar uma linha no system prompt do agente dizendo que
valores monetarios devem ser apresentados em USD (US$).

**Onde:** `app/graph/prompts.py`, na secao "Formato da resposta final" do
`build_conversation_system_prompt`.

**Risco:** nenhum. E uma linha de prompt.

## 2. Filtro por status de pedido na query de performance — ~10 min

**O que e:** a query `CHANNEL_PERFORMANCE_SQL` faz JOIN com `orders` mas nao
filtra por `status`. Pedidos cancelados, devolvidos e pendentes sao contados
junto com os completos. Um avaliador com perfil de engenharia de dados pode
questionar isso.

**O que fazer:** adicionar `AND o.status NOT IN ('Cancelled', 'Returned')` ou,
de forma mais conservadora, `AND o.status = 'Complete'` na clausula WHERE.

> Nota: o dataset `thelook_ecommerce` usa os status `Shipped`, `Complete`,
> `Processing`, `Cancelled` e `Returned`. O mais defensivo e filtrar pelo que
> faz sentido de negocio.

**Onde:** `app/tools/channel_performance_analyzer.py`, na constante
`CHANNEL_PERFORMANCE_SQL`.

**Risco:** baixo. A query continua parametrizada e o teste readiness continua
passando (basta atualizar a assertion do SQL se o readiness checar o texto).

## 3. Evidencia de entrega — ~10 min

**O que e:** um artefato final que mostra ao avaliador que os gates passaram
e o projeto esta validado. Isso transmite confianca e profissionalismo.

**O que fazer:** criar `docs/delivery_evidence.md` com:

- output de `poetry run verify --agent`;
- output de `poetry run pytest --agent`;
- data e hora da execucao;
- versao do Python e do Poetry usados.

**Onde:** `docs/delivery_evidence.md`

**Risco:** nenhum. E apenas documentacao.

## O que NAO fazer

- **Nao refatorar o router.** Funciona, tem cobertura, mexer agora e risco puro.
- **Nao adicionar logging.** Seria bom, mas e invasivo demais para o momento.
- **Nao refinar copy de produto.** Depende do LLM, retorno incerto.
- **Nao adicionar novas tools ou metricas.** Fora do escopo do MVP e do case.
- **Nao mexer nos testes.** A suite atual ja cobre o necessario.

## Resumo

| # | Gap | Tempo | Impacto | Risco |
|---|-----|-------|---------|-------|
| 1 | Semantica de moeda | 5 min | medio | nenhum |
| 2 | Filtro por status de pedido | 10 min | medio-alto | baixo |
| 3 | Evidencia de entrega | 10 min | alto | nenhum |

Total estimado: **~25 minutos**.

Depois disso, o projeto esta entregue. Para, descansa e submete.
