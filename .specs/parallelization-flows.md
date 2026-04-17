# Fluxos Paralelizaveis do MVP

Este documento mostra apenas frentes que podem ser executadas em paralelo com worktrees e agentes. Etapas puramente seriais nao aparecem aqui.

## 1. Paralelismo inicial apos a base compartilhada

```mermaid
flowchart LR
    Base["Base compartilhada pronta
    - contratos centrais
    - layout de pastas
    - dependencias comuns"] --> SQL["Worktree A
    Dados e SQL
    - channel_performance_analyzer
    - export da tool
    - validacao manual da tool"]

    Base --> Graph["Worktree B
    LangGraph core
    - router
    - scope guard
    - insight synthesizer
    - bind_tools"]

    Base --> API["Worktree C
    Superficie da API
    - QueryRequest e QueryResponse
    - router FastAPI
    - tratamento de excecoes
    - stub do servico"]
```

Leitura: depois que a base compartilhada estiver mergeada, essas tres frentes podem avancar em paralelo com baixo acoplamento inicial.

## 2. Integracao das frentes independentes

```mermaid
flowchart TB
    SQL["Frente A finalizada
    Tool financeira + smoke manual"] --> Integracao["Branch de integracao
    conectar tool real ao fluxo do agente"]

    Graph["Frente B finalizada
    grafo + roteamento + sintese"] --> Integracao

    API["Frente C finalizada
    endpoint /query + contrato HTTP"] --> Integracao

    Integracao --> Validacao["Validacao fim a fim
    pergunta -> tool -> insight -> JSON"]
```

Leitura: A, B e C podem andar em paralelo, mas convergem na integracao final, onde o endpoint passa a chamar o grafo real com a nova tool conectada.

## 3. Paralelismo tardio apos o backbone estar estavel

```mermaid
flowchart LR
    Backbone["Backbone integrado e estavel
    - grafo chamando tools
    - endpoint /query funcional"] --> CLI["Worktree D
    CLI
    - script de pergunta
    - impressao amigavel
    - validacao manual no terminal"]

    Backbone --> Docs["Worktree E
    Documentacao e polish
    - README final
    - exemplos de uso
    - arquitetura ilustrada
    - checklist manual"]
```

Leitura: quando o contrato de resposta ja estiver estabilizado, CLI e documentacao podem ser tocados em paralelo sem disputar o nucleo do sistema.

## 4. Regra pratica de ownership por fluxo

```mermaid
flowchart TB
    SQLTeam["Fluxo SQL"] --> SQLFiles["Arquivos esperados
    app/tools/channel_performance_analyzer.py
    app/tools/__init__.py
    scripts de validacao manual"]

    GraphTeam["Fluxo LangGraph"] --> GraphFiles["Arquivos esperados
    app/graph/*
    app/prompts/*
    app/services/*"]

    APITeam["Fluxo API"] --> APIFiles["Arquivos esperados
    app/main.py
    app/routers/*
    app/schemas/api.py"]

    DocsTeam["Fluxo CLI e Docs"] --> DocsFiles["Arquivos esperados
    scripts/ask_analyst.py ou app/cli.py
    README.md"]
```

Leitura: esse recorte reduz conflito porque cada worktree tem ownership predominante sobre um conjunto pequeno de arquivos.
