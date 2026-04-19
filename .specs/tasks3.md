# Backlog Extra de Evolucao do Projeto

## Objetivo

Registrar melhorias extras que podem aumentar a maturidade do projeto e a aderencia a vaga, mas que **nao devem competir com as tarefas priorizadas em `tasks2.md`**.

Este arquivo representa um backlog complementar para ser executado **somente se sobrar tempo depois das melhorias diretamente ligadas aos criterios de avaliacao do desafio**.

## Regra de priorizacao

- `tasks2.md` continua sendo o plano principal.
- Este `tasks3.md` deve ser tratado como backlog extra.
- Nenhum item abaixo deve atrasar a entrega das melhorias que aumentam a pontuacao do case.
- A interface React e explicitamente tratada aqui como extra.

## Quando ativar este backlog

Somente iniciar estas tarefas se:

- as melhorias principais de produto, arquitetura, backend e SQL do `tasks2.md` estiverem concluídas, ou
- restar tempo livre real apos a estabilizacao do core do projeto.

## Meta geral

Evoluir o MVP de "case tecnico forte" para "ferramenta interna com potencial real de produto", aproximando o projeto das expectativas descritas na vaga sem desviar do foco principal da entrega.

## Bloco Extra 1: Flexibilidade Avancada de Produto

**Motivacao:** tornar o agente mais util em perguntas semiestrategicas e menos dependente de consultas rigidamente estruturadas.

- [ ] E1.1 Criar um modo consultivo mais sofisticado para perguntas como "o que posso fazer para crescer o organico?".
- [ ] E1.2 Permitir respostas hibridas, combinando recomendacao geral com convite opcional para aprofundar com dados.
- [ ] E1.3 Criar um pequeno "playbook" interno de recomendacoes de Growth, SEO e CRO para orientar respostas consultivas sem cair em genericidade total.
- [ ] E1.4 Melhorar o comportamento conversacional para follow-ups abertos, sem exigir imediatamente um novo formato estrito de pergunta.

**Valor esperado**

- Melhora a percepcao de visao de produto.
- Aproxima o agente do comportamento de uma ferramenta interna real.

## Bloco Extra 2: Novas Tools com Outras Tabelas do Dataset

**Motivacao:** explorar de forma curada tabelas adicionais do `thelook_ecommerce`, ampliando a profundidade analitica sem virar exploracao irrestrita do dataset.

### Tabelas extras candidatas

- `events`
- `products`
- `inventory_items`
- `distribution_centers` (menor prioridade)

### Possiveis tools extras

- [ ] E2.1 `channel_funnel_analyzer`
  - Usa `events` para mostrar etapas como `home`, `product`, `cart`, `purchase` e `cancel` por canal.
- [ ] E2.2 `landing_page_analyzer`
  - Usa `events.uri` para identificar paginas ou rotas com maior entrada por canal.
- [ ] E2.3 `category_performance_analyzer`
  - Usa `products` e `order_items` para analisar receita ou pedidos por categoria, marca ou departamento.
- [ ] E2.4 `returns_analyzer`
  - Usa `orders` e `order_items` para avaliar devolucoes e possivel degradacao de qualidade por canal.
- [ ] E2.5 `repeat_purchase_analyzer`
  - Usa `orders` por `user_id` para medir recorrencia por canal.

**Valor esperado**

- Enriquece o diagnostico de "por que" um canal performa bem ou mal.
- Demonstra mais senioridade analitica e melhor aproveitamento do warehouse.

## Bloco Extra 3: Novos Nos do Grafo

**Motivacao:** deixar o fluxo mais modular, mais robusto e mais proximo de uma arquitetura de agente voltada a produto.

- [ ] E3.1 Criar um `policy_guard_node` para centralizar recusas de PII, colunas sensiveis e perguntas fora de governanca.
- [ ] E3.2 Criar um `time_resolution_node` para resolver periodos relativos e janelas temporais mais ambigas.
- [ ] E3.3 Criar um `capability_planner_node` para decidir se a pergunta precisa de uma ou varias tools.
- [ ] E3.4 Criar um `insight_enricher_node` para calcular deltas, ranking, gargalos e outliers antes da sintese textual.
- [ ] E3.5 Criar um `action_recommendation_node` para transformar achados em proximas acoes sugeridas.

**Valor esperado**

- Reduz acoplamento no grafo principal.
- Melhora a leitura de senioridade arquitetural.

## Bloco Extra 4: Interface Web React

**Motivacao:** aumentar aderencia a vaga, que menciona interfaces funcionais para MVPs, sem desviar do foco de entrega do desafio.

- [ ] E4.1 Criar uma interface React simples consumindo o endpoint `/query`.
- [ ] E4.2 Preservar `thread_id` entre interacoes para simular uma conversa continua.
- [ ] E4.3 Exibir `answer`, `tools_used`, estados de loading e erros tratados.
- [ ] E4.4 Implementar uma experiencia visual simples, responsiva e sem exageros de design.
- [ ] E4.5 Manter a UI como camada fina, sem duplicar regras de negocio do backend.

**Valor esperado**

- Aproxima o projeto da descricao da vaga.
- Melhora demonstracao em entrevista e percepcao de MVP utilizavel.

## Bloco Extra 5: Operacionalizacao e Escalabilidade

**Motivacao:** mostrar maturidade alem do case e preparar um caminho plausivel para deploy.

- [ ] E5.1 Containerizar a aplicacao com `Docker`.
- [ ] E5.2 Preparar um caminho simples de deploy para `Cloud Run`.
- [ ] E5.3 Documentar configuracao minima de ambiente para execucao fora da maquina local.
- [ ] E5.4 Separar configuracoes de desenvolvimento, validacao e producao de forma mais explicita.

**Valor esperado**

- Aumenta aderencia a vaga, que menciona cloud e producao.
- Torna o projeto mais convincente como software de verdade.

## Bloco Extra 6: Integracoes e Camada de Conhecimento

**Motivacao:** aproximar o projeto do contexto da vaga, que fala de conectores, automacoes e cultura AI-First.

- [ ] E6.1 Avaliar uma camada simples de conhecimento recuperavel para respostas consultivas, em vez de depender so da LLM.
- [ ] E6.2 Estruturar um pequeno repositório local de "playbooks" ou regras de Growth e Midia.
- [ ] E6.3 Avaliar futuras integracoes com APIs de Midia ou Analytics, sem implementa-las agora.

**Valor esperado**

- Mostra visao de produto e de plataforma.
- Abre caminho para evolucao futura sem forcar escopo agora.

## Priorizacao interna deste backlog extra

Se sobrar tempo apos `tasks2.md`, a ordem sugerida e:

1. `E3` Novos nos do grafo que reforcem modularidade
2. `E2` Uma tool extra com `events` ou `products`
3. `E1` Modo consultivo mais rico
4. `E4` Interface React simples
5. `E5` Containerizacao e deploy
6. `E6` Camada de conhecimento e integracoes futuras

## Definicao de sucesso deste backlog

Este backlog sera bem utilizado se:

- ampliar a robustez e a senioridade percebida do projeto;
- aumentar aderencia a vaga;
- nao comprometer a entrega principal do desafio;
- funcionar como evolucao consciente do MVP, e nao como inflacao de escopo.
