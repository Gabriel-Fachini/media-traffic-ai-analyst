# Media Traffic AI Analyst — Agents Blueprint

> **Fonte única:** o blueprint completo de agentes (objetivo, arquitetura do
> StateGraph, contratos de dados, política de segurança, pipeline de validação e
> harness) vive em [`CLAUDE.md`](CLAUDE.md).
>
> Este arquivo existe para ferramentas que procuram `AGENTS.md` por convenção.
> Para evitar drift entre cópias, o conteúdo não é duplicado aqui — leia
> `CLAUDE.md`. O roadmap de evolução está em [`PLANO_EVOLUCAO.md`](PLANO_EVOLUCAO.md)
> e a visão de produto/portfólio no [`README.md`](README.md).

## Resumo de 30 segundos

Agente conversacional de analytics (Mídia e Growth) sobre o dataset público
`bigquery-public-data.thelook_ecommerce`. Projeto de portfólio focado em
engenharia de agentes LLM.

- **Orquestração:** LangGraph `StateGraph`, 3 nodes `preprocess → agent → tool_executor`, roteamento via `Command(goto=...)`.
- **Router:** LLM com `with_structured_output(RouterDecision)` (`app/graph/llm_router.py`); datas normalizadas de forma determinística (`app/graph/date_normalizer.py`).
- **Tools:** `traffic_volume_analyzer` e `channel_performance_analyzer`, SQL sempre parametrizada.
- **Superfície:** API FastAPI (`/health`, `/query`) + CLI `analyst-chat`.
- **Confiança:** `poetry run verify` (ruff + compileall + pyright), `poetry run pytest`, eval do router (`-m eval`), smoke tests `live` opt-in.

Detalhes e invariantes completas: **[`CLAUDE.md`](CLAUDE.md)**.
