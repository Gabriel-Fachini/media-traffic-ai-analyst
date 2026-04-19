# Plano de Melhorias para Buscar Nota Maxima no Case

## Objetivo

Organizar as proximas melhorias do MVP com foco direto nos criterios de avaliacao do `case.md`, sem ampliar o escopo de forma desnecessaria e sem atualizar o `README.md` a cada ajuste incremental.

## Regras deste plano

- Manter o MVP simples e incremental.
- Preservar o contrato atual de `traffic_source` singular.
- Nao introduzir UI web nesta etapa.
- Manter os scripts de validacao manual existentes.
- Adicionar testes automatizados principalmente com `pytest`, cobrindo o que mais afeta a percepcao de qualidade.
- Deixar a atualizacao do `README.md` para o fechamento final da entrega.

## Ordem sugerida de execucao

1. Fechar os gaps mais visiveis de produto.
2. Tornar a arquitetura do roteamento mais explicita.
3. Aumentar a robustez de backend com testes e tratamento de erros.
4. Reforcar a defesa tecnica das queries SQL.
5. Atualizar o `README.md` apenas no fim, refletindo o estado final real do projeto.

## Criterio 1: Arquitetura do Agente

**Meta de percepcao:** deixar evidente para o avaliador que existe uma arquitetura deliberada de agente, com roteamento claro, tool calling real e separacao entre interpretacao, execucao e sintese.

- [ ] 1.1 Criar um contrato explicito de decisao do roteador, com campos como `intent`, `normalized_params`, `needs_clarification` e `refusal_reason`.
- [ ] 1.2 Extrair a logica de interpretacao e normalizacao da pergunta para um modulo proprio, reduzindo a concentracao de responsabilidade em `app/graph/workflow.py`.
- [ ] 1.3 Fazer o `workflow.py` consumir a decisao estruturada do roteador, em vez de depender apenas de condicoes espalhadas no proprio arquivo.
- [ ] 1.4 Padronizar o fluxo conceitual como `Router -> Tool Executor -> Insight Synthesizer -> API/CLI`.
- [ ] 1.5 Adicionar testes automatizados com `pytest` para o roteamento, cobrindo pelo menos: volume, performance, fora de escopo, falta de datas, datas invalidas e comparacao entre canais.

### **Definicao de pronto para este criterio**

- O avaliador consegue enxergar rapidamente onde a pergunta e interpretada, onde a tool e escolhida e onde a resposta final e sintetizada.
- O comportamento de roteamento fica provado por testes automatizados curtos e objetivos.

## Criterio 2: Qualidade do Backend Python

**Meta de percepcao:** mostrar codigo maduro, bem tipado, previsivel e resiliente.

- [ ] 2.1 Criar handlers centralizados de excecao no FastAPI para falhas conhecidas, como erros de BigQuery, configuracao e timeout do LLM.
- [ ] 2.2 Adicionar suite automatizada com `pytest`, separando ao menos:
  - testes unitarios de schemas e normalizacao de entrada
  - testes de roteamento/grafo com doubles controlados
  - testes leves da API com `TestClient` e dependency override
- [ ] 2.3 Subir gradualmente a regua de tipagem do projeto, saindo de `pyright` em `basic` para um modo mais rigoroso nas pastas mais criticas.
- [ ] 2.4 Garantir que os modulos de suporte continuem import-safe, evitando efeitos colaterais em importacoes usadas por testes e scripts.
- [ ] 2.5 Consolidar um comando unico de validacao local que rode lint, compilacao, type-check e testes automatizados.

### **Definicao de pronto para este criterio**

- O backend continua simples, mas com prova objetiva de robustez.
- Falhas esperadas nao vazam como comportamento confuso ou stack trace exposto.

## Criterio 3: Engenharia de Dados (SQL)

**Meta de percepcao:** transmitir que as queries nao estao apenas funcionando, mas que refletem criterio tecnico e entendimento do dataset.

- [ ] 3.1 Revisar e documentar explicitamente as decisoes de negocio das queries atuais:
  - por que `users.created_at` representa o volume de aquisicao
  - por que `orders.created_at` representa o periodo da analise financeira
  - por que `COUNT(DISTINCT o.order_id)` evita supercontagem
  - por que `SUM(oi.sale_price)` e a medida usada para receita
- [ ] 3.2 Validar se a semantica de "pedidos realizados" no case deve permanecer baseada em pedidos criados ou se exige filtro adicional por status.
- [ ] 3.3 Padronizar comentarios curtos nas queries para registrar pontos tecnicos que um avaliador olharia numa code review.
- [ ] 3.4 Criar uma validacao manual curta para evidenciar legibilidade e seguranca da query, sem transformar o MVP em um projeto de observabilidade.
- [ ] 3.5 Preservar SQL parametrizada como regra obrigatoria e deixar isso evidente no codigo e nos testes.

### **Definicao de pronto para este criterio**

- As queries seguem simples, seguras e justificadas.
- Existe uma resposta clara para qualquer pergunta de banca sobre join, agregacao, duplicidade e recorte temporal.

## Criterio 4: Visao de Produto

**Meta de percepcao:** fazer o sistema parecer um analista junior util, e nao apenas um executor tecnico de queries.

- [ ] 4.1 Implementar interpretacao de periodos relativos frequentes, como `ultimo mes`, `ultimos 7 dias`, `ontem` e `este mes`, normalizando para datas ISO antes do tool calling.
- [ ] 4.2 Melhorar a camada de sintese para reduzir respostas genericas e aumentar respostas ancoradas em fatos do proprio resultado.
- [ ] 4.3 Antes da sintese final, calcular fatos estruturados uteis, como lider do periodo, segundo colocado, diferenca absoluta e participacao relativa quando fizer sentido.
- [ ] 4.4 Reforcar recusas elegantes para:
  - metricas fora do schema, como ROI, ROAS, CTR e CAC
  - pedidos de PII ou colunas fora do contrato de produto
  - perguntas fora do dominio de midia/growth
- [ ] 4.5 Melhorar mensagens de clarificacao para que sejam curtas, objetivas e parecam parte natural da experiencia conversacional.

### **Definicao de pronto para este criterio**

- O agente responde melhor aos exemplos do case.
- A resposta final traz leitura de negocio e nao apenas repeticao dos numeros retornados pela tool.

## Fechamento da entrega (README por ultimo)

**Meta de percepcao:** alinhar apresentacao e implementacao somente quando a base tecnica estiver estabilizada.

- [ ] 5.1 Atualizar o `README.md` apenas depois que as melhorias tecnicas acima estiverem concluidas.
- [ ] 5.2 Remover mensagens de "fase inicial" e "proximos passos" que contradigam o estado real do repositorio.
- [ ] 5.3 Registrar setup real, comandos reais de validacao, arquitetura real do agente e exemplos reais de uso.
- [ ] 5.4 Incluir um diagrama simples e fiel do fluxo final, sem descrever funcionalidades ainda nao entregues.

### **Definicao de pronto para este criterio**

- O `README.md` passa a reforcar a percepcao de entrega, em vez de enfraquece-la.
- A documentacao vira espelho do que o codigo realmente faz.

## Priorizacao pratica recomendada

- [ ] P1 Implementar periodos relativos e melhorar a sintese final.
- [ ] P2 Estruturar melhor o roteador e reduzir a concentracao de responsabilidade em `workflow.py`.
- [ ] P3 Adicionar testes automatizados com `pytest` para roteamento, API e fluxos criticos.
- [ ] P4 Centralizar tratamento de erros e subir a regua de tipagem.
- [ ] P5 Revisar e justificar melhor as queries do ponto de vista de negocio e SQL.
- [ ] P6 Atualizar o `README.md` somente no fechamento final.
