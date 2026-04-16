# Plano Geral de Tarefas de Implantação

## Sprint Básica: Core da Solução (Backend e API)

### Fase 1: Setup da Base e Clients

**Foco:** Garantir estrutura do repositório, dependências, credenciais e a conexão com a base via pacote google oficial.

- [ ] 1.1 Configurar o gerenciador de dependências (`poetry` sugerido) e carregar bibliotecas core (`fastapi`, `langgraph`, `google-cloud-bigquery`, `pydantic`).
- [ ] 1.2 Criar um arquivo `.env` para carregar `GOOGLE_APPLICATION_CREDENTIALS` e `OPENAI_API_KEY`.
- [ ] 1.3 Implementar `utils.config.py` para mapear variáveis de ambiente.
- [ ] 1.4 Criar a classe `BigQueryClient` para instanciar a API e configurar testes manuais com queries fixas a fim de atestar o sucesso do acesso ao Dataset via service account.

### Fase 2: Implementando Funções Essenciais (Tools Analytics)

**Foco:** Fornecer os "braços" executores de consultas parametrizadas do BigQuery isoladas.

- [ ] 2.1 Definir via Pydantic o modelo `Input` e de `Output` de cada tool, formatando as datas esperadas.
- [ ] 2.2 Desenvolver a tool SQL Python `traffic_volume_analyzer`. (Envolve agregação simples de `users` e `traffic_source`).
- [ ] 2.3 Desenvolver a tool SQL Python `channel_performance_analyzer`. (Fazendo o agrupamento robusto da `users`, `orders`, `order_items` por revenue de cada source de Marketing).
- [ ] 2.4 Testar manualmente a extração destas views com queries simples e validação direta no terminal.

### Fase 3: Acessando e Orquestrando em Grafo

**Foco:** Amarrar os conectores utilizando motor IA para orquestrar as ferramentas por inferência autônoma.

- [ ] 3.1 Importar o LLM Node (GPT via Langchain/Langgraph bindings) e vincular a declaração de inputs das Tools (o `bind_tools()`).
- [ ] 3.2 Construir o `StateGraph` central e os nós da rede do Analista Júnior de Mídia (Nodes de: Conversação, Direcionador, Resposta Final Compilada).
- [ ] 3.3 Escrever a instrução base (`SystemPrompt`) restritiva e moldar a inibição inteligente de negação de "Perguntas Fora de Escopo".
- [ ] 3.4 Verificar se respostas de tabelas puras são ingeridas e retornadas corretamente pelo motor textual.

### Fase 4: O Serviço Web API

**Foco:** Entregar resiliência de endpoints sob o FastAPI.

- [ ] 4.1 Definir esquemas para as Requests do usuário final no Swagger (`pydantic routers`).
- [ ] 4.2 Injetar o nó Graph já rodando e compilar o retorno em JSON com formatação `answer`, e os `metadata` identificando as ferramentas atuando nos bastidores do sistema.
- [ ] 4.3 Capturar as chamadas em caso de TimeOut do LLM e devolver um erro 500 sem arrebentar a execução.

### Fase 5: Interação em Terminal e Apresentação

**Foco:** Validar o fluxo fim-a-fim com interação simples via terminal e empacotar para o testador da vaga.

- [ ] 5.1 Criar um modo simples de interação em terminal (CLI) para enviar perguntas e imprimir respostas do agente.
- [ ] 5.2 Avaliar e limpar os outputs, checar formatação Pt-BR correta de números e clareza do insight.
- [ ] 5.3 Elaborar um `README.md` esmerado que liste um passo a passo objetivo: (1) Onde gerar chave JSON do cloud, (2) onde colocar no ambiente (3) como invocar scripts/CLI e API e (4) uma arquitetura visual final.

### Backlog Pós-MVP: UI Web (Opcional)

**Foco:** Evolução de experiência após validação do núcleo funcional.

- [ ] B1 Avaliar adoção de Streamlit (ou alternativa) para camada web.
- [ ] B2 Implementar chat web consumindo a API já pronta.
