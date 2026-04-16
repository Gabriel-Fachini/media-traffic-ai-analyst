# Relatório Oficial de Requisitos (MVP - AI Analyst)

## 1. Contexto do Projeto

O sistema tem como principal alvo fornecer aos analistas de Performance e Growth um Agente Lógico Autônomo com interface humanizada. Seu objetivo é substituir queries repetitivas que cruzam o volume de usuários com as receitas dos canais (Facebook, Google, SEO) por uma interface amigável que atúe gerando relatórios simplificados.

Nesta fase do MVP, a interacao com o agente sera realizada via terminal (CLI) para simplificar o desenvolvimento e a validacao manual. A camada de UI web (ex.: Streamlit) fica para evolucao futura.

## 2. Requisitos Funcionais de Aplicação (RFA)

* **RFA01 (Router e Direcionamento):** O Agente deve processar o texto, identificar as intenções primariamente com LLMs e encaminhar as diretivas a ferramentas locais utilizando a interface de *Function/Tool Calling*. Prompting simples onde toda base de dados é jogada por texto não será tolerado.
* **RFA02 (Análise de Volume):** A rede deverá acionar uma busca no GCP reportando a contagem orgânica bruta de acessos (volume mensal/diário do `traffic_source`).
* **RFA03 (Avaliação de Receita):** A rede deverá ser capaz de mesclar tabelas. Precisa identificar origens ativas em compras finalizadas, consolidar os pedidos e mostrar a somatória resultante do canal.
* **RFA04 (Geração de NLP Insight):** Após a busca, as tabelas não devem ser retornadas sozinhas. A LLM precisa mastigar o resultado analítico e apresentar as tendências (por ex., "A pesquisa Orgânica dominou, mas o Ticket subiu no Facebook.").
* **RFA05 (Escopo Limitado de Risco):** Mensagens como "Como fazer um bolo" ou "Qual a receita bruta de outra empresa" devem desencadear um contorno em que o assistente nega a avaliação educadamente.

## 3. Requisitos Não Funcionais Críticos (RNF)

* **Stack Python:** Execução sobre a engine `Python 3.10+`.
* **Framework Web:** O encapsulamento em API deve ser feito em `FastAPI`.
* **Interface Inicial do MVP:** A interacao deve ser simples via terminal/CLI nesta fase. UI web nao e obrigatoria no MVP inicial.
* **Orquestrador LLM:** Uso de motor como `LangGraph`, `LangChain` ou `LlamaIndex` para reger os prompts e histórico das invocações.
* **Camada de Dados:** Queries executadas puramente utilizando o `google-cloud-bigquery` de forma padronizada via Prepared Statements para proteção contra Injection SQL.
* **Organização de Código:** Código bem formatado obedecendo as boas práticas de Tipagem (Type Hinting) e validação (`Pydantic`).
* **Erros de Camada Lógica:** Falhas temporárias em qualquer conexão (OpenAI ou Google) devem causar recusa elegante em vez de `500 Server Error` expondo `stack trace` na aplicação.

## 4. Requisitos Exigidos para Entrega do Desafio

* Documentação baseada em arquivo de escopo direto no repositório final (`README.md`).
* Guia para clonar o repositório, instalar os `requirements.txt`/`poetry` da engine, e declarar como anexar credenciais obrigatórias da Cloud em `.env`.
* Diagramação mínima descobrindo o trajeto Agente -> Google.
* Link livre acessível dentro de projeto Git público.
