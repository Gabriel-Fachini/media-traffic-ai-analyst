# CASE

## 1. Contexto do Negócio

O time de Mídia e Growth da nossa empresa precisa monitorar constantemente a qualidade do tráfego que chega ao nosso e-commerce. Atualmente, os analistas perdem muito tempo cruzando dados de usuários (origem do tráfego) com dados de vendas (pedidos realizados) para entender o ROI real de cada canal.

Seu objetivo é construir o MVP de um Agente de IA Autônomo que atue como um "Analista Júnior de Mídia". Este agente deve ser capaz de entender perguntas em linguagem natural, consultar um data warehouse real, processar as informações e fornecer insights acionáveis — não apenas números brutos.

## 2. O Dataset

Você utilizará o dataset público do Google BigQuery: `thelook_ecommerce`.

Este dataset simula uma loja de roupas. Para este desafio, as tabelas essenciais são:

- `bigquery-public-data.thelook_ecommerce.users`: Contém a coluna `traffic_source` (ex: Search, Organic, Facebook), que usaremos como proxy para nossos canais de mídia.
- `bigquery-public-data.thelook_ecommerce.orders`: Contém os pedidos realizados, datas e status.
- `bigquery-public-data.thelook_ecommerce.order_items`: Contém os valores de venda (`sale_price`) para cálculo de receita.

**Nota:** O candidato deverá usar suas próprias credenciais do GCP (conta gratuita) para consultar o dataset público.

## 3. Requisitos Técnicos (Obrigatórios)

O candidato deve demonstrar senioridade na escolha da arquitetura dentro da stack definida:

### Backend & Orquestração de IA

- Linguagem: Python 3.10+.
- Framework Web: FastAPI ou Flask.
- Framework de IA: Obrigatório o uso de um orquestrador como LangChain, LangGraph ou LlamaIndex.
- Arquitetura de Agentes: A solução **NÃO** pode ser apenas um prompt gigante enviando dados para a LLM. Você deve implementar o conceito de Tool Calling (Function Calling). O agente deve decidir quando precisa usar uma ferramenta para consultar o banco de dados.

### Dados & Engenharia

- Integração com BigQuery usando a biblioteca cliente Python oficial.
- Queries SQL eficientes e seguras (parametrizadas para evitar injection, se aplicável).

## 4. Requisitos Funcionais

### Análise de Volume de Tráfego

Exemplos de perguntas do usuário:

- "Como foi o volume de usuários vindos de 'Search' no último mês?"
- "Qual dos canais tem a melhor performance? E por que?"

**Comportamento esperado:**  
O agente identifica a intenção, chama uma ferramenta Python que executa uma query no BigQuery (filtrando a tabela `users` por data e `traffic_source`), retorna os dados para a LLM, que formula uma resposta em linguagem natural.

## 5. Critérios de Avaliação

| Ponto de Avaliação         | Descrição                                                                                                                                           | Peso |
|----------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|------|
| Arquitetura do Agente      | Implementou Tool Calling corretamente? Separou a lógica de prompt da lógica de execução de código? Usou bem o framework escolhido (LangChain/Graph)? | Alto |
| Qualidade do Backend Python| Uso de tipagem (Pydantic/Type hints), estrutura de pastas limpa (MVC ou Clean Arch), tratamento de erros nas chamadas ao BigQuery e LLM.            | Alto |
| Engenharia de Dados (SQL)  | As queries SQL escritas para consultar o thelook são eficientes? Demonstram conhecimento de JOINs e agregações?                                     | Médio|
| Visão de Produto           | A resposta final da IA é útil para um gerente de mídia ou é apenas um despejo de dados técnicos? O sistema lida com perguntas fora do escopo?       | Alto |

## 6. Entregáveis

1. Link do repositório público no GitHub.
2. Um `README.md` excelente, contendo:
   - Instruções claras de setup (como instalar dependências e onde colocar as chaves de API da OpenAI/Anthropic e as credenciais do Google Cloud).
   - Um diagrama simples ou explicação da arquitetura do agente (quais tools foram criadas e por quê).