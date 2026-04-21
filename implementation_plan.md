# Plano de Implementação: Refatoração para Padrão ReAct

## 1. Resumo e Objetivo
A arquitetura atual possui alto débito de manutenibilidade e flexibilidade devido ao forte acoplamento de decisões conversacionais via código rígido (`router.py`). O objetivo deste plano é **migrar a orquestração do LangGraph para o padrão ReAct (Reason + Act)**. A refatoração visa transferir a tomada de decisão ("quando e qual tool usar", "sintetizar resumos", "pedir clarificações temporais") do código condicional em Python para a inteligência nativa embutida na chamada do LLM via Tool Calling.

## 2. Justificativa Estratégica frente ao Desafio
O `case.md` requer: *"A solução NÃO pode ser apenas um prompt gigante enviando dados para a LLM. Você deve implementar o conceito de Tool Calling. O agente deve decidir quando precisa usar uma ferramenta para consultar o banco de dados."* 

Na implementação atual, apesar do uso de Tool Calling puro, o agente foi contornado por um Router que tenta adivinhar a `intent` antes. Adotar o padrão ReAct assegura aderência máxima ao *"State of The Art"* em Agentes, garantindo que a entrega para avaliação mostre plena maturidade na capacidade de desenhar controles de fluxo autônomos por LLMs em contraponto à sistemas monolíticos.

## 3. Ganhos Adquiridos
| Fator | Estado Atual (Router) | Novo Estado (ReAct) |
| --- | --- | --- |
| **Escalabilidade Conversacional** | Trava após 4 turnos; rígido na interpretação semântica. | Lida livremente com N interações usando abstrações fluídas graças à memória e controle próprio do LLM. |
| **Linhas de Código (Complexidade)** | ~1100 linhas entre regex, intents e workflow determinista. | Queda de aproximadamente ~60% no LOC da pasta `graph`. Código enxuto focado nos `tools` (onde brilha o back-end). |
| **Acoplamento de Regras** | Tratamento hard-coded se uma mensagem lida de "volume" para "estratégia". | Diretrizes centralizadas numa única `System Prompt` resiliente. |

## 4. Passos de Implementação

### Passo 1: Limpeza da Arquitetura (Depreciação de Arquivos)
- **Ação:** Deletar `app/schemas/router.py`. As definições duras de instâncias como `IntentType`, `RouterDecision` não serão mais necessárias na nova arquitetura.
- **Ação:** Deletar e limpar grande parte do `app/graph/router.py`. Faremos o prune de lógicas regex pesadas de datas temporais e short-circuits. Manteremos possivelmente apenas as constantes inofensivas.

### Passo 2: Consolidação da Identidade do Agente (Prompt Engineering)
- **Ação:** Refatorar o `app/graph/prompts.py`.
- **Implementação:** Unificar e reescrever a `SystemPrompt`. A nova prompt atuará como as "leis de execução" orientando como o LLM deve extrair dados de datas do usuário naturalmente, ou recusar solicitações de forma educada caso desviem do escopo ou caso o usuário peça atributos sensíveis do BQ.

### Passo 3: Refatoração do StateGraph (`workflow.py`)
- **Ação:** Reduzir o grafo para a anatomia formal ReAct:
  1. `__start__ -> agent` (Onde o LLM é injetado com o binding das ferramentas)
  2. `agent -> tools` (Executa scripts se o nó de agent contiver requisições do standard de tool calls na última mensagem)
  3. `tools -> agent` (Devolve os resultados do BQ em json limpo para a síntese)
  4. `agent -> __end__` (O LLM emite o texto final em Pt-BR quando sentir que terminou).
- **Adequação Backend:** O uso limpo dos TypedDicts de MessageHistory do LangGraph cuidará automagicamente da sobrecarga que anteriormente custava muito processamento manual na stack atual.

### Passo 4: Adequação da Camada de Testes
- **Ação:** Refatorar `tests/` para refletir as novas mudanças já que testes de assert que chamavam os intents do Router agora estarão defasados.
- **Ação:** Executar as validações definidas no nosso `tests_checklist.md` simulando requisições contínuas visando testar resiliência fluida de memória no endpoint.
