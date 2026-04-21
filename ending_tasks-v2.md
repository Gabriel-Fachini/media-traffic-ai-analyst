# Tarefas Priorizadas — Fechamento dos Testes Manuais

> Priorizacao refeita a partir do que realmente falhou em `results.md`.
> Esta lista substitui a ordem anterior, que ainda estava generica demais e
> misturava backlog do case com bugs reais observados no produto.

---

## 🔴 P0 — Corrigir bugs que fazem o agente recusar perguntas validas ou quebrar o multi-turn

### T1 — Corrigir falsos `unsupported_dimension` no router

**Testes afetados:** `C1.3`, `D1.2`, `D3.4`, `D4.6`
**Impacto:** Muito alto
**Por que sobe para o topo:** hoje perguntas centrais do MVP, inclusive exemplos muito proximos do case, estao sendo recusadas como se estivessem fora de escopo.

**Causa-raiz provavel**

- O parser de dimensao esta amplo demais e captura trechos invalidos da frase.
- Exemplos observados:
  - `Receita por canal entre ...` vira algo como `canal_entre`
  - `Receita por canal no ultimo mes` vira `canal_no`
  - `Qual dos canais ... E por que?` faz o router interpretar `por que` como se fosse `por <dimensao>`
- Depois disso, `_question_requests_unsupported_dimension()` derruba a pergunta com `unsupported_dimension`.

**Como resolver**

1. Restringir a extracao de dimensao a tokens realmente suportados.
2. Ignorar stopwords e marcadores temporais como `entre`, `no`, `nos`, `de`, `ate`.
3. Garantir que `por que` nunca seja interpretado como `por <dimensao>`.
4. Adicionar testes de regressao para as frases que hoje falham.

**Definicao de pronto:** perguntas como `Receita por canal...`, `Qual dos canais tem a melhor performance...` e `por que organic ficou abaixo de search?` deixam de cair em recusa.

---

### T2 — Corrigir follow-ups que dependem do contexto anterior

**Testes afetados:** `D3.3`, `D3.4`, `D4.5`
**Impacto:** Muito alto
**Por que sobe para o topo:** quebra a principal promessa conversacional do MVP. O usuario recebe uma analise valida, tenta continuar a conversa, e o sistema responde `out_of_scope`.

**Causa-raiz provavel**

- O fluxo so reconhece follow-up quando a nova pergunta tem anchors explicitos demais.
- Comandos anaforicos como `Monte essa analise e me retorne` nao sao tratados como continuidade.
- Quando a analise anterior foi multi-canal, a guarda `question_introduces_new_traffic_source()` trata `Organic` ou `Search` como "nova pergunta", bloqueando o follow-up diagnostico.
- O sistema tambem nao sabe continuar um follow-up curto depois de uma clarificacao aberta pelo proprio agent.

**Como resolver**

1. Permitir follow-ups anaforicos quando houver contexto analitico valido no thread.
2. Se a analise anterior foi agregada por varios canais, nao tratar mencoes de canal como troca automatica de assunto.
3. Reforcar o caminho de `strategy_follow_up` e `diagnostic_follow_up` para comparacoes entre canais.
4. Adicionar testes de integracao cobrindo `Monte essa analise e me retorne` e `por que organic ficou abaixo de search?`.

**Definicao de pronto:** depois de uma analise valida, o usuario consegue pedir plano de acao, aprofundamento ou diagnostico sem receber recusa generica.

---

### T3 — Aceitar perguntas agregadas de volume sem canal explicito

**Testes afetados:** `D4.7`
**Impacto:** Alto
**Por que entra em P0:** hoje uma pergunta valida para o produto cai fora de escopo mesmo trazendo metrica e periodo corretos.

**Causa-raiz provavel**

- O router so reconhece `traffic_volume` quando existe contexto explicito de canal/fonte.
- `Usuarios nos ultimos 7 dias` traz periodo valido e uma metrica suportada, mas nao tem `canal` nem `trafego` no texto.
- O resultado e `out_of_scope`, mesmo sendo um caso que deveria rodar com `traffic_source=None`.

**Como resolver**

1. Tratar `usuarios` + periodo valido como consulta agregada de volume.
2. Permitir `traffic_volume_analyzer` com `traffic_source=None` nesse caminho.
3. Adicionar cobertura para perguntas curtas sem canal explicito.

**Definicao de pronto:** `Usuarios nos ultimos 7 dias` retorna dados agregados por canal em vez de recusa.

---

## 🟡 P1 — Corrigir inconsistencias de experiencia e qualidade da resposta

### T4 — Evitar clarificacoes desnecessarias do agent quando o router ja resolveu a intencao

**Testes afetados:** `D4.5`
**Impacto:** Alto
**Por que ainda nao e P0:** o fluxo principal existe, mas o agent esta reabrindo duvidas desnecessarias e criando uma conversa que o proprio sistema depois nao sabe concluir.

**Causa-raiz provavel**

- O router classifica `volume de trafego este mes` corretamente.
- Mesmo assim, o agent pede `voce quer o volume total ou comparar por canal?`.
- Isso indica que o agent ainda esta reinterpretando a pergunta do zero, sem usar o `intent` e os `normalized_params` ja resolvidos no router.

**Como resolver**

1. Passar o resultado estruturado do router para o prompt do agent.
2. Instruir explicitamente o agent a nao pedir nova clarificacao quando o periodo e a intencao ja estiverem resolvidos.
3. Cobrir com teste de integracao a pergunta `volume de trafego este mes`.

**Definicao de pronto:** a pergunta valida ja dispara tool call e resposta final no primeiro turno.

---

### T5 — Refinar recusas para explicar a ausencia real no schema

**Testes afetados:** `D2.3`
**Impacto:** Medio
**Por que fica em P1:** nao bloqueia o uso do produto, mas deixa a recusa menos util para o avaliador e para o usuario final.

**Leitura atual**

- A recusa esta conceitualmente correta.
- O problema e que ela nao explica bem por que `campanha` e `lucro` nao cabem no schema atual.

**Como resolver**

1. Distinguir melhor metrica ausente de granularidade/dimensao ausente.
2. Explicar explicitamente quando o schema nao tem campanhas, anuncios ou lucro.
3. Sugerir a alternativa suportada mais proxima, como `receita por canal` ou `pedidos por canal`.

**Definicao de pronto:** a recusa ensina por que a pergunta nao cabe no MVP e orienta a reformulacao correta.

---

### T6 — Padronizar a apresentacao de receita e o criterio de resposta business-grade

**Testes afetados:** `D4.4`, `D1.3`
**Impacto:** Medio
**Por que fica em P1:** e polimento importante, mas nao impede o produto de responder.

**Causa-raiz provavel**

- O sintetizador nao obriga indicacao explicita de moeda em respostas financeiras.
- O checklist tambem nao deixou observavel o que conta como "linguagem de negocio", entao parte da avaliacao ficou subjetiva.

**Como resolver**

1. Padronizar respostas de receita com moeda explicita, idealmente `US$`.
2. Definir melhor o criterio de aprovacao para "linguagem de negocio".
3. Revalidar exemplos olhando so a resposta final, sem misturar debug na avaliacao.

**Definicao de pronto:** respostas financeiras deixam clara a unidade monetaria e o criterio de aprovacao fica objetivo.

---

## 🟢 P2 — Reclassificar e monitorar, sem abrir tarefa de implementacao agora

### T7 — Reclassificar falsos negativos do checklist manual

**Itens:** `C1.4`, `D1.1`, `D2.2`

**Leitura**

- `C1.4`: o proprio `results.md` registra que a resposta veio correta; o ❌ nao representa bug funcional confirmado.
- `D1.1`: no reteste a resposta veio boa; tratar como instabilidade a monitorar, nao como bug fechado.
- `D2.2`: a recusa de `ROAS` ja explica que a metrica nao existe no dataset atual, entao o comportamento esta aceitavel.

**Acao**

- Revalidar esses itens depois das correcoes P0/P1.
- Nao gastar implementacao dedicada neles antes de fechar os bugs estruturais.

---

## Ordem de Execucao Sugerida

```text
T1 -> T2 -> T3 -> T4 -> T5 -> T6
```

**Revalidacao recomendada apos cada bloco**

- Depois de `T1`: `C1.3`, `D1.2`, `D4.6`
- Depois de `T2`: `D3.3`, `D3.4`
- Depois de `T3` e `T4`: `D4.5`, `D4.7`
- Depois de `T5` e `T6`: `D2.3`, `D4.4`, `D1.3`
- No fim: reclassificar `C1.4`, `D1.1`, `D2.2`

**Resumo executivo**

- O problema mais serio hoje nao esta na SQL nem na infra.
- O maior gargalo esta no entendimento da linguagem natural e na continuidade da conversa.
- Se `T1` e `T2` forem corrigidas primeiro, boa parte dos ❌ atuais deve desaparecer junto.
