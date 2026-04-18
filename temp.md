# Explicacao detalhada de `app/graph/workflow.py`

## Visao geral

Este arquivo monta o grafo principal do MVP de analytics. Ele faz quatro coisas:

1. Define o formato do estado compartilhado do LangGraph.
2. Cria funcoes auxiliares para ler mensagens e normalizar conteudo.
3. Monta o `StateGraph` com os nos de roteamento, conversa, execucao de tools e resposta final.
4. Expos uma funcao simples para o resto do projeto invocar o grafo com uma pergunta.

Mesmo que a conversa anterior tenha usado a palavra "metodo", tecnicamente aqui quase tudo sao **funcoes**. Nao existe uma classe com metodos de instancia. O ponto central do arquivo e a funcao `build_analytics_graph()`, e dentro dela existem funcoes internas que viram os nos do grafo.

## Mapa mental rapido

```mermaid
flowchart TD
    A["invoke_analytics_graph(question)"] --> B["build_analytics_graph()"]
    B --> C["router_node(state)"]
    C -->|sem pergunta ou sem datas| F["final_response_node(state)"]
    C -->|pergunta valida| D["conversation_node(state)"]
    D -->|sem tool_calls| F
    D -->|com tool_calls| E["execute_tools_node(state)"]
    E --> F
    F --> G["estado final com final_answer e tools_used"]
```

## Estrutura do arquivo

```mermaid
flowchart LR
    A["Constantes e prompts"] --> B["AnalyticsGraphState"]
    B --> C["Helpers privados"]
    C --> D["build_analytics_graph()"]
    D --> E["router_node()"]
    D --> F["conversation_node()"]
    D --> G["execute_tools_node()"]
    D --> H["final_response_node()"]
    D --> I["route_after_router()"]
    D --> J["route_after_conversation()"]
    D --> K["graph.compile()"]
    K --> L["invoke_analytics_graph()"]
```

## 1. Constantes principais

Antes das funcoes, o arquivo define algumas constantes:

- `DATE_TOKEN_PATTERN`: regex que encontra datas no formato `YYYY-MM-DD`.
- `CONVERSATION_SYSTEM_PROMPT`: prompt do LLM que decide se deve responder direto ou chamar tools.
- `FINAL_RESPONSE_SYSTEM_PROMPT`: prompt do LLM que transforma o resultado tecnico das tools em linguagem de negocio.
- `MISSING_DATES_MESSAGE`: mensagem padrao para pedir clarificacao.
- `EMPTY_QUESTION_MESSAGE`: mensagem para pergunta vazia.
- `TEMPORARY_TOOL_FAILURE_MESSAGE`: mensagem de falha tratada quando a tool quebra.

Essas constantes existem para que a logica do grafo nao fique cheia de strings soltas.

## 2. `AnalyticsGraphState`

Definido em `workflow.py`, ele e o contrato de estado compartilhado entre os nos.

Campos:

- `question`: pergunta original recebida.
- `messages`: historico das mensagens do LangChain/LangGraph.
- `next_step`: pequeno marcador interno de roteamento.
- `final_answer`: resposta textual final.
- `tools_used`: lista das tools realmente usadas.

### Visualizando o estado

```mermaid
classDiagram
    class AnalyticsGraphState {
        question: str
        messages: list[AnyMessage]
        next_step: "conversation" | "tools" | "final_response"
        final_answer: str
        tools_used: list[str]
    }
```

### O que `add_messages` faz

O campo `messages` usa `Annotated[..., add_messages]`.

Na pratica isso significa:

- quando um no retorna novas mensagens, o LangGraph faz append;
- ele nao substitui o historico inteiro por padrao.

Sem esse reducer, cada no poderia sobrescrever o historico anterior.

## 3. Funcoes helper

Essas funcoes nao sao nos do grafo. Elas ajudam os nos a trabalhar com o estado.

### 3.1 `_content_to_text(content)`

**Objetivo:** transformar qualquer formato de conteudo de mensagem em texto simples.

Ela trata tres casos:

1. Se ja for `str`, devolve diretamente.
2. Se for `list`, percorre item por item.
3. Se for qualquer outro tipo, faz `str(...)`.

Quando o item da lista for `dict`, ela tenta:

- primeiro pegar `item["text"]`;
- se nao existir, serializa o dict como JSON.

### Por que isso existe

No ecossistema LangChain, `message.content` nem sempre e uma string pura. Pode ser:

- string;
- lista de blocos;
- estruturas mistas.

Essa funcao evita espalhar essa normalizacao pelo resto do arquivo.

### Fluxo interno

```mermaid
flowchart TD
    A["content recebido"] --> B{"eh str?"}
    B -->|sim| C["retorna content"]
    B -->|nao| D{"eh list?"}
    D -->|nao| E["retorna str(content)"]
    D -->|sim| F["itera itens"]
    F --> G{"item eh str?"}
    G -->|sim| H["append item"]
    G -->|nao| I{"item eh dict?"}
    I -->|sim e tem text| J["append item['text']"]
    I -->|sim sem text| K["append json.dumps(item)"]
    I -->|nao| L["append str(item)"]
    H --> M["join com quebra de linha"]
    J --> M
    K --> M
    L --> M
```

### 3.2 `_resolve_question(state)`

**Objetivo:** descobrir qual e a pergunta do usuario a partir do estado.

Ordem de prioridade:

1. Tenta `state["question"]`.
2. Se estiver vazia, procura a ultima `HumanMessage` em `state["messages"]`.
3. Se nada funcionar, retorna string vazia.

### Por que isso existe

O grafo pode ser chamado de formas diferentes:

- passando a pergunta diretamente no estado;
- ou reaproveitando um historico de mensagens.

Essa funcao centraliza a regra de leitura da pergunta.

### Fluxo interno

```mermaid
flowchart TD
    A["state"] --> B{"state.question existe e nao esta vazia?"}
    B -->|sim| C["retorna question"]
    B -->|nao| D["varre messages de tras para frente"]
    D --> E{"achou HumanMessage com conteudo?"}
    E -->|sim| F["retorna texto da HumanMessage"]
    E -->|nao| G["retorna string vazia"]
```

### 3.3 `_extract_iso_dates(question)`

**Objetivo:** extrair tokens de data no formato `YYYY-MM-DD`.

Ela usa a regex `DATE_TOKEN_PATTERN.findall(question)`.

### Importante

Ela **nao valida semanticamente** a data. Exemplo:

- `2024-01-31` bate na regex e parece ok.
- `2024-99-99` tambem bate na regex, mesmo sendo uma data invalida.

Neste arquivo ela serve apenas como guarda rapida para saber se o usuario informou ou nao duas datas.

### 3.4 `_get_last_ai_message(messages)`

**Objetivo:** encontrar a ultima mensagem produzida pelo modelo.

Ela percorre `messages` de tras para frente e devolve o primeiro item que for `AIMessage`.

### Por que isso existe

Depois da conversa com o LLM, o sistema precisa responder perguntas como:

- o modelo pediu tool?
- o modelo respondeu diretamente?
- qual foi a ultima fala da IA?

Essa funcao evita repetir a mesma varredura em varios pontos.

### 3.5 `_collect_tool_messages(messages)`

**Objetivo:** pegar somente as `ToolMessage`.

Ela faz um filtro simples:

- se a mensagem for `ToolMessage`, entra;
- se nao for, fica fora.

### Uso principal

Ela e usada no `final_response_node()` para descobrir se houve execucao de tools e para montar o contexto que sera sintetizado.

### 3.6 `_collect_tools_used(messages)`

**Objetivo:** produzir a lista de nomes das tools usadas, sem repeticao.

Passos:

1. Percorre `messages`.
2. Ignora tudo que nao for `ToolMessage`.
3. Ignora mensagens sem `name`.
4. Usa um `set` chamado `seen` para evitar duplicatas.
5. Monta a lista final `tools_used`.

### Exemplo

Se o historico tiver:

- `ToolMessage(name="traffic_volume_analyzer")`
- `ToolMessage(name="traffic_volume_analyzer")`
- `ToolMessage(name="channel_performance_analyzer")`

O retorno sera:

```text
["traffic_volume_analyzer", "channel_performance_analyzer"]
```

### 3.7 `_serialize_tool_result(result)`

**Objetivo:** transformar o resultado Python da tool em JSON formatado.

Ela usa:

```python
json.dumps(result, ensure_ascii=False, indent=2, default=str)
```

### Por que isso existe

O `ToolMessage` precisa carregar um conteudo que seja facil de:

- armazenar no historico;
- inspecionar;
- enviar depois para o LLM sintetizador.

## 4. `build_analytics_graph(...)`

Essa e a funcao central do arquivo.

Assinatura:

```python
def build_analytics_graph(
    settings: Settings | None = None,
    *,
    tool_enabled_llm: Any | None = None,
    response_llm: Any | None = None,
    tools: tuple[BaseTool, ...] | None = None,
) -> Any:
```

## O que ela recebe

- `settings`: configuracoes da aplicacao, usadas para construir os LLMs reais.
- `tool_enabled_llm`: opcional. Permite injetar um LLM ja preparado com `bind_tools()`.
- `response_llm`: opcional. Permite injetar um LLM para sintese final.
- `tools`: opcional. Permite trocar as tools reais por doubles/stubs em testes.

## O que ela monta no inicio

### `analytics_tools`

Se o caller nao passou tools, usa `get_analytics_tools()`.

### `tools_by_name`

Transforma a tupla de tools em um dicionario:

```python
{
    "traffic_volume_analyzer": <tool>,
    "channel_performance_analyzer": <tool>,
}
```

Isso existe porque o `tool_call` do LLM chega pelo nome.

### `conversation_llm`

Se o caller nao injetou um LLM, ele usa `build_tool_enabled_llm(settings)`.

Esse e o LLM que:

- recebe a pergunta;
- pode gerar `tool_calls`.

### `synthesis_llm`

Se o caller nao injetou um LLM, ele usa `build_analytics_llm(settings)`.

Esse e o LLM que:

- nao precisa chamar tools;
- apenas transforma o resultado em resposta natural.

## Por que os nos ficam dentro dessa funcao

As funcoes `router_node`, `conversation_node`, `execute_tools_node`, `final_response_node`, `route_after_router` e `route_after_conversation` sao definidas dentro de `build_analytics_graph()` porque elas dependem do contexto montado ali:

- `tools_by_name`
- `conversation_llm`
- `synthesis_llm`

Em outras palavras, elas fecham sobre esse contexto.

## 5. Nos internos do grafo

### 5.1 `router_node(state)`

Esse e o primeiro no do grafo.

### Responsabilidade

Fazer uma validacao inicial bem barata, antes de gastar LLM ou tool.

### Logica

1. Usa `_resolve_question(state)` para descobrir a pergunta.
2. Se nao houver pergunta:
   - define `final_answer = EMPTY_QUESTION_MESSAGE`
   - define `next_step = "final_response"`
3. Se houver menos de duas datas:
   - define `final_answer = MISSING_DATES_MESSAGE`
   - define `next_step = "final_response"`
4. Se estiver tudo ok:
   - define `next_step = "conversation"`

### Intuicao

Esse no funciona como um guard clause ou middleware de entrada.

### Visual

```mermaid
flowchart TD
    A["router_node(state)"] --> B["question = _resolve_question(state)"]
    B --> C{"question vazia?"}
    C -->|sim| D["final_answer = EMPTY_QUESTION_MESSAGE"]
    D --> E["next_step = final_response"]
    C -->|nao| F{"ha pelo menos 2 datas?"}
    F -->|nao| G["final_answer = MISSING_DATES_MESSAGE"]
    G --> H["next_step = final_response"]
    F -->|sim| I["next_step = conversation"]
```

### 5.2 `conversation_node(state)`

Esse e o no que chama o LLM com tool binding.

### Responsabilidade

Produzir a proxima resposta da IA, que pode ser:

- uma resposta textual direta;
- uma resposta com `tool_calls`.

### Logica

1. Resolve a pergunta com `_resolve_question(state)`.
2. Copia `state["messages"]`.
3. Se o historico estiver vazio:
   - injeta uma `HumanMessage` com a pergunta.
4. Chama `conversation_llm.invoke(...)` com:
   - `SystemMessage(CONVERSATION_SYSTEM_PROMPT)`
   - historico atual
5. Retorna as novas mensagens para append no estado.

### Por que ela injeta `HumanMessage`

O grafo pode ser chamado apenas com `{"question": ...}` e sem historico. O LLM, no entanto, espera mensagens. Entao esse no cria a mensagem humana inicial quando necessario.

### Visual

```mermaid
sequenceDiagram
    participant G as Graph
    participant C as conversation_node
    participant L as conversation_llm

    G->>C: state
    C->>C: _resolve_question(state)
    C->>C: le messages
    alt messages vazia
        C->>C: cria HumanMessage(question)
    end
    C->>L: invoke(SystemMessage + messages)
    L-->>C: AIMessage (texto ou tool_calls)
    C-->>G: {"messages": [...novas mensagens...]}
```

### 5.3 `execute_tools_node(state)`

Esse no executa as tools pedidas pelo modelo.

### Responsabilidade

Transformar `tool_calls` do LLM em chamadas reais de funcoes Python.

### Logica

1. Le as mensagens do estado.
2. Pega a ultima `AIMessage`.
3. Se nao houver `AIMessage` ou nao houver `tool_calls`, retorna `{}`.
4. Para cada `tool_call`:
   - extrai `tool_name`;
   - extrai `tool_call_id`;
   - procura a tool em `tools_by_name`.
5. Se a tool nao existir:
   - cria um `ToolMessage` com `status="error"`.
6. Se a tool existir:
   - chama `tool.invoke(tool_call)`;
   - serializa o resultado com `_serialize_tool_result(result)`;
   - cria um `ToolMessage` com `artifact=result`.
7. Se houver excecao:
   - cria um `ToolMessage` de erro.
8. Retorna `{"messages": tool_messages}`.

### Por que ele usa `ToolMessage`

Porque no modelo mental do LangChain/LangGraph, o retorno de uma tool entra no historico como uma mensagem especial. Depois o sintetizador pode ler isso como parte do contexto.

### Visual

```mermaid
flowchart TD
    A["execute_tools_node(state)"] --> B["last_ai_message = _get_last_ai_message(messages)"]
    B --> C{"ha tool_calls?"}
    C -->|nao| D["retorna {}"]
    C -->|sim| E["itera tool_calls"]
    E --> F["acha tool por nome em tools_by_name"]
    F --> G{"tool existe?"}
    G -->|nao| H["gera ToolMessage de erro"]
    G -->|sim| I["tool.invoke(tool_call)"]
    I --> J{"execucao ok?"}
    J -->|sim| K["serializa resultado e cria ToolMessage"]
    J -->|nao| L["captura excecao e cria ToolMessage de erro"]
    H --> M["acumula tool_messages"]
    K --> M
    L --> M
    M --> N["retorna {'messages': tool_messages}"]
```

### 5.4 `final_response_node(state)`

Esse e o no que fecha o fluxo.

### Responsabilidade

Decidir qual resposta final o sistema deve devolver.

### Ele cobre quatro cenarios

#### Cenario A: ja existe `final_answer` e nao houve tool

Isso acontece, por exemplo, quando:

- a pergunta veio vazia;
- faltaram datas.

Nesse caso ele so reaproveita o que o `router_node()` ja decidiu.

#### Cenario B: alguma tool falhou

Se qualquer `ToolMessage` tiver `status == "error"`, ele devolve:

- `TEMPORARY_TOOL_FAILURE_MESSAGE`

Aqui a prioridade e robustez e mensagem tratada.

#### Cenario C: houve resultado de tool

Esse e o caso principal.

Passos:

1. Resolve a pergunta original.
2. Monta `tool_context` concatenando os resultados das `ToolMessage`.
3. Chama `synthesis_llm.invoke(...)` com:
   - `FINAL_RESPONSE_SYSTEM_PROMPT`
   - uma `HumanMessage` contendo:
     - a pergunta original
     - os resultados estruturados
4. Guarda a nova `AIMessage`.
5. Preenche:
   - `final_answer`
   - `tools_used`

#### Cenario D: nao houve tool e tambem nao havia `preset_answer`

Nesse caso ele tenta usar a ultima `AIMessage` como resposta final direta. Isso cobre, por exemplo, respostas como:

- recusa de escopo;
- resposta textual sem necessidade de consulta.

### Visual

```mermaid
flowchart TD
    A["final_response_node(state)"] --> B["tools_used = _collect_tools_used(messages)"]
    B --> C["tool_messages = _collect_tool_messages(messages)"]
    C --> D{"preset_answer existe e nao houve tool?"}
    D -->|sim| E["retorna preset_answer"]
    D -->|nao| F{"alguma tool falhou?"}
    F -->|sim| G["retorna TEMPORARY_TOOL_FAILURE_MESSAGE"]
    F -->|nao| H{"ha tool_messages?"}
    H -->|sim| I["monta tool_context"]
    I --> J["chama synthesis_llm"]
    J --> K["salva final_answer e tools_used"]
    H -->|nao| L["pega ultima AIMessage"]
    L --> M{"existe AIMessage?"}
    M -->|sim| N["usa o texto da AIMessage como resposta final"]
    M -->|nao| O["usa EMPTY_QUESTION_MESSAGE"]
```

## 6. Funcoes de roteamento

Essas funcoes nao fazem trabalho de negocio. Elas apenas ajudam o LangGraph a escolher a proxima aresta.

### 6.1 `route_after_router(state)`

Le `state["next_step"]` e devolve:

- `"conversation"`
- ou `"final_response"`

Ela existe porque o `router_node()` nao muda a estrutura do grafo; ele apenas escreve no estado qual deve ser o proximo passo.

### 6.2 `route_after_conversation(state)`

Olha a ultima `AIMessage` e decide:

- se houver `tool_calls`, retorna `"tools"`;
- caso contrario, retorna `"final_response"`.

### Visual dos dois roteadores

```mermaid
stateDiagram-v2
    [*] --> Router
    Router --> Conversation: route_after_router() == "conversation"
    Router --> FinalResponse: route_after_router() == "final_response"
    Conversation --> Tools: route_after_conversation() detecta tool_calls
    Conversation --> FinalResponse: route_after_conversation() sem tool_calls
    Tools --> FinalResponse
    FinalResponse --> [*]
```

## 7. Montagem do grafo

Ainda dentro de `build_analytics_graph()`:

1. Cria `graph = StateGraph(AnalyticsGraphState)`.
2. Registra os nos:
   - `router`
   - `conversation`
   - `tools`
   - `final_response`
3. Registra as arestas:
   - `START -> router`
   - `router -> conversation | final_response`
   - `conversation -> tools | final_response`
   - `tools -> final_response`
   - `final_response -> END`
4. Chama `graph.compile()`.

### Visual completo do grafo

```mermaid
flowchart TD
    S([START]) --> R["router"]
    R -->|next_step = conversation| C["conversation"]
    R -->|next_step = final_response| F["final_response"]
    C -->|AIMessage com tool_calls| T["tools"]
    C -->|AIMessage sem tool_calls| F
    T --> F
    F --> E([END])
```

## 8. `invoke_analytics_graph(question, settings=None)`

Essa e a funcao publica mais simples do arquivo.

### Responsabilidade

Permitir que outro modulo faca:

```python
result = invoke_analytics_graph("Qual foi o volume de Search entre 2024-01-01 e 2024-01-31?")
```

sem precisar saber como o `StateGraph` e montado internamente.

### Passos

1. Chama `build_analytics_graph(settings)`.
2. Executa `graph.invoke({"question": question})`.
3. Faz cast para `AnalyticsGraphState`.
4. Retorna o estado final.

### Em termos de arquitetura

Se `build_analytics_graph()` e o "composition root" do arquivo, `invoke_analytics_graph()` e a fachada simples para consumo externo.

## 9. Exemplo ponta a ponta

Pergunta:

```text
Qual foi o volume de usuarios de Search entre 2024-01-01 e 2024-01-31?
```

### Caminho esperado

```mermaid
sequenceDiagram
    participant U as Usuario
    participant I as invoke_analytics_graph
    participant B as build_analytics_graph
    participant R as router_node
    participant C as conversation_node
    participant T as execute_tools_node
    participant F as final_response_node

    U->>I: pergunta
    I->>B: constroi grafo
    I->>R: state com question
    R-->>C: next_step = conversation
    C->>C: injeta HumanMessage se necessario
    C->>C: chama conversation_llm
    C-->>T: AIMessage com tool_call
    T->>T: executa traffic_volume_analyzer
    T-->>F: ToolMessage com resultado JSON
    F->>F: chama synthesis_llm
    F-->>I: final_answer + tools_used
```

### Caminho quando faltam datas

Pergunta:

```text
Qual canal teve mais usuarios?
```

Fluxo:

```mermaid
sequenceDiagram
    participant U as Usuario
    participant I as invoke_analytics_graph
    participant R as router_node
    participant F as final_response_node

    U->>I: pergunta sem datas
    I->>R: state com question
    R-->>F: final_answer = MISSING_DATES_MESSAGE
    F-->>I: resposta de clarificacao
```

## 10. Resumo final por funcao

| Funcao | Papel |
|---|---|
| `_content_to_text` | Normaliza conteudo de mensagem para string |
| `_resolve_question` | Descobre a pergunta a partir do estado |
| `_extract_iso_dates` | Encontra datas no formato ISO por regex |
| `_get_last_ai_message` | Pega a ultima resposta do modelo |
| `_collect_tool_messages` | Filtra mensagens de tool |
| `_collect_tools_used` | Lista nomes de tools usadas sem duplicar |
| `_serialize_tool_result` | Transforma retorno da tool em JSON |
| `build_analytics_graph` | Monta e compila o `StateGraph` |
| `router_node` | Faz validacao inicial e decide se continua |
| `conversation_node` | Chama o LLM que pode gerar `tool_calls` |
| `execute_tools_node` | Executa as tools pedidas pela IA |
| `final_response_node` | Fecha o fluxo e monta a resposta final |
| `route_after_router` | Decide a aresta depois do router |
| `route_after_conversation` | Decide se vai para tools ou resposta final |
| `invoke_analytics_graph` | Fachada simples para executar o grafo |

## 11. Leitura em linguagem simples

Se eu resumisse o arquivo em uma frase:

> Ele recebe uma pergunta, verifica se da para prosseguir, deixa a IA decidir se precisa consultar dados, executa a consulta quando necessario e transforma o resultado em uma resposta de negocio.

Se eu resumisse em quatro frases:

1. Primeiro ele barra perguntas vazias ou sem datas.
2. Depois ele pergunta ao LLM se precisa chamar alguma tool.
3. Se precisar, executa a tool real e guarda o resultado no historico.
4. Por fim, usa outro LLM para transformar o resultado tecnico em resposta final legivel.

