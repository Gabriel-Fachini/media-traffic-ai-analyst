# Resultados do checklist de teste

### C1.3

```bash
voce > Receita por canal entre 2024-01-01 e 2024-03-31
╭────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────╮
│  resolved_question:                                                                                 │
│  Receita por canal entre 2024-01-01 e 2024-03-31                                                    │
│                                                                                                     │
│  router_intent: out_of_scope  →  short-circuit: refusal:unsupported_dimension                       │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭───────────────────────────────────────────── Analista ──────────────────────────────────────────────╮
│                                                                                                     │
│  No MVP atual eu so consigo analisar trafego, pedidos e receita por canal (traffic_source).         │
│  Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em     │
│  YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com periodos relativos suportados.                             │
│                                                                                                     │
│  tools: nenhuma  |  contexto: 1 mensagem                                                            │
│                                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### C1.4

Retornou resposta bem estruturada com dados. O dataset é atualizado todo dia com novos dados.

### D1.1

A resposta foi essa, não consigo definir se passou ou não. Testei novamente agora com a mesma pergunta e deu certo. Não sei o que aconteceu.

```bash
No último mês considerado, o canal Search trouxe 751 usuários.                                     │
│                                                                                                     │
│  Isso indica um volume relevante e concentrado em um único canal. Para Growth, vale olhar se esse   │
│  nível de entrada está consistente ao longo dos meses ou se foi uma alta pontual. Para Midia,       │
│  Search segue como um canal importante de aquisição de tráfego, então faz sentido acompanhar sua    │
│  participação e comparar com os demais canais antes de qualquer ajuste de prioridade. 
```

### D1.2

Não conseguiu performar essa análise.

```bash
  voce > Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-03-31? E por que?
╭────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────╮
│  resolved_question:                                                                                 │
│  Qual dos canais tem a melhor performance entre 2024-01-01 e 2024-03-31? E por que?                 │
│                                                                                                     │
│  router_intent: out_of_scope  →  short-circuit: refusal:unsupported_dimension                       │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭───────────────────────────────────────────── Analista ──────────────────────────────────────────────╮
│                                                                                                     │
│  No MVP atual eu so consigo analisar trafego, pedidos e receita por canal (traffic_source).         │
│  Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em     │
│  YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com periodos relativos suportados.                             │
│                                                                                                     │
│  tools: nenhuma  |  contexto: 1 mensagem                                                            │
│                                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D1.3

Não entendi como testar.

### D2.2

Não deu certo. Verifique debug abaixo

```bash
voce > Qual o ROAS do Search ontem ?
╭────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────╮
│  resolved_question:                                                                                 │
│  Qual o ROAS do Search ontem ?                                                                      │
│                                                                                                     │
│  router_intent: out_of_scope  →  short-circuit: refusal:unsupported_metric                          │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭───────────────────────────────────────────── Analista ──────────────────────────────────────────────╮
│                                                                                                     │
│  No MVP atual eu so consigo analisar volume de trafego, pedidos e receita por canal com base no     │
│  schema disponivel. Reformule a pergunta sem metricas como ROAS, CAC, CTR ou outras metricas que    │
│  nao existem no dataset atual.                                                                      │
│                                                                                                     │
│  tools: nenhuma  |  contexto: 1 mensagem                                                            │
│                                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D2.3

A resposta foi correta, porém não explicou o motivo (que não existe campanhas na base de dados). Não sei se isso é aceitável ou se a resposta deveria ser mais completa.

### D3.3

Resposta correta. NO fim, ele sugere montar uma análise/plano de ação baseado nos dados, o que é ótimo. Porém, ao pedir para retornar essa sugestão ele retorna out_of_scope. Deveria continuar a conversa normalmente, não recusar.

```bash
voce > Monte essa analise e me retorne
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  Monte essa analise e me retorne                                                                                                                                                                                                             │
│                                                                                                                                                                                                                                              │
│  router_intent: out_of_scope  →  short-circuit: refusal:out_of_scope                                                                                                                                                                         │
│                                                                                                                                                                                                                                              │
│  agent_tool_calls (LLM decidiu):                                                                                                                                                                                                             │
│    [1] traffic_volume_analyzer                                                                                                                                                                                                               │
│      start_date: 2026-04-14                                                                                                                                                                                                                  │
│      end_date: 2026-04-21                                                                                                                                                                                                                    │
│      traffic_source: Search                                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  Consigo ajudar apenas com analises de trafego, pedidos e receita por canal no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com         │
│  periodos relativos suportados.                                                                                                                                                                                                              │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 7 mensagens                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D3.4

Ele não conseguiu responder.

```bash
voce > por que organic ficou abaixo de search ?
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  por que organic ficou abaixo de search ?                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
│  router_intent: out_of_scope  →  short-circuit: refusal:unsupported_dimension                                                                                                                                                                │
│                                                                                                                                                                                                                                              │
│  agent_tool_calls (LLM decidiu):                                                                                                                                                                                                             │
│    [1] traffic_volume_analyzer                                                                                                                                                                                                               │
│      start_date: 2026-03-01                                                                                                                                                                                                                  │
│      end_date: 2026-03-31                                                                                                                                                                                                                    │
│      traffic_source: Search                                                                                                                                                                                                                  │
│    [2] traffic_volume_analyzer                                                                                                                                                                                                               │
│      start_date: 2026-03-01                                                                                                                                                                                                                  │
│      end_date: 2026-03-31                                                                                                                                                                                                                    │
│      traffic_source: Organic                                                                                                                                                                                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  No MVP atual eu so consigo analisar trafego, pedidos e receita por canal (traffic_source). Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com periodos  │
│  relativos suportados.                                                                                                                                                                                                                       │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 8 mensagens                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D4.4

Respondeu correto mas ficou faltando cifrão da receita. Não dá pra saber se é dolares ou reais.

### D4.5

Começou certo mas houve um `out_of_scope` no follow-up. Veja o debug:

```bash
voce > volume de trafego este mes
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  volume de trafego este mes                                                                                                                                                                                                                  │
│                                                                                                                                                                                                                                              │
│  router_intent: traffic_volume                                                                                                                                                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  Claro — para eu trazer o volume de tráfego deste mês, preciso de uma coisa antes: você quer o volume total ou comparar por canal (ex.: Search, Organic, Facebook)?                                                                          │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 2 mensagens                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

voce > total
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  total                                                                                                                                                                                                                                       │
│                                                                                                                                                                                                                                              │
│  router_intent: out_of_scope  →  short-circuit: refusal:out_of_scope                                                                                                                                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  Consigo ajudar apenas com analises de trafego, pedidos e receita por canal no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com         │
│  periodos relativos suportados.                                                                                                                                                                                                              │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 3 mensagens                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D4.6

Ele não interpretou a pergunta corretamente. Veja o debug:

```bash
voce > Receita por canal no ultimo mes
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  Receita por canal no ultimo mes                                                                                                                                                                                                             │
│                                                                                                                                                                                                                                              │
│  router_intent: out_of_scope  →  short-circuit: refusal:unsupported_dimension                                                                                                                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  No MVP atual eu so consigo analisar trafego, pedidos e receita por canal (traffic_source). Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com periodos  │
│  relativos suportados.                                                                                                                                                                                                                       │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 1 mensagem                                                                                                                                                                                                     │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### D4.7

Ele entendeu a pergunta mas não conseguiu resolver o período de "últimos 7 dias" no follow-up. O periodo relativo estava na primeira mensagem. Veja o debug:

```bash
voce > Usuarios nos ultimos 7 dias
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  Usuarios nos ultimos 7 dias                                                                                                                                                                                                                 │
│                                                                                                                                                                                                                                              │
│  router_intent: out_of_scope  →  short-circuit: refusal:out_of_scope                                                                                                                                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  Consigo ajudar apenas com analises de trafego, pedidos e receita por canal no dataset atual. Reformule a pergunta nesse escopo e, quando a consulta depender de dados, informe o periodo em YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou com         │
│  periodos relativos suportados.                                                                                                                                                                                                              │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 1 mensagem                                                                                                                                                                                                     │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

voce > quero uma analise de trafego
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────── Debug Execucao ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  resolved_question:                                                                                                                                                                                                                          │
│  quero uma analise de trafego                                                                                                                                                                                                                │
│                                                                                                                                                                                                                                              │
│  router_intent: traffic_volume  →  short-circuit: clarification:missing_dates                                                                                                                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────── Analista ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                                                                                                                                                                              │
│  Preciso que voce informe o periodo para eu consultar os dados. Voce pode usar YYYY-MM-DD, DD/MM/AAAA, DD/MM/AA ou periodos relativos como ontem, este mes, ultimo mes e ultimos 7 dias.                                                     │
│                                                                                                                                                                                                                                              │
│  tools: nenhuma  |  contexto: 2 mensagens                                                                                                                                                                                                    │
│                                                                                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
