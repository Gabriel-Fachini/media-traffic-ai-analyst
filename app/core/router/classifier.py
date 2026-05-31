from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.infra.llm import build_analytics_llm
from app.core.router.decision import RouterDecision
from app.infra.config import Settings

_MAX_CONTEXT_MESSAGES = 6

_ROUTER_SYSTEM_PROMPT = """
Voce e o classificador de intencao de um agente de analytics de midia e growth.

## Contexto do dominio

O agente consulta o dataset `thelook_ecommerce` com tres tabelas:
- `users` — visitas e cadastros por canal (traffic_source)
- `orders` — pedidos por usuario
- `order_items` — itens e receita por pedido

Canais suportados (traffic_source normalizado): Search, Organic, Facebook, Instagram.
Qualquer outro canal, fonte, dimensao ou metrica esta fora de escopo.

## Intencoes validas

- `traffic_volume`: pergunta sobre numero de usuarios/visitas/trafego por canal ou
  periodo. Ex: "quantos usuarios vieram do Search em janeiro?".
- `channel_performance`: pergunta sobre pedidos, receita, ranking ou desempenho
  financeiro por canal. Ex: "qual canal gerou mais receita em marco?".
- `strategy_follow_up`: pergunta de continuidade estrategica sobre uma analise
  anterior do mesmo thread — sugestoes, acoes, proximos passos, otimizacao,
  diversificacao, plano.
- `diagnostic_follow_up`: pergunta de continuidade diagnostica sobre uma analise
  anterior — "por que isso aconteceu?", "o que pode explicar?", hipoteses causais.
- `ambiguous_analytics`: pergunta que menciona tanto volume quanto performance
  financeira sem indicar qual metrica quer. Precisa de clarificacao do usuario.
- `out_of_scope`: qualquer pergunta fora do dominio acima.

## Regras de clarificacao (needs_clarification=true)

- `missing_dates`: intent e valido (traffic_volume ou channel_performance) mas
  nenhuma data ou periodo foi fornecido na pergunta nem no contexto do thread.
- `invalid_dates`: datas foram mencionadas mas sao invalidas ou inconsistentes.
- `ambiguous_metric`: intent ambiguous_analytics — usar este motivo ao emitir
  clarificacao para perguntas ambiguas.

## Regras de recusa (intent=out_of_scope + refusal_reason)

- `empty_question`: pergunta vazia ou sem conteudo semantico.
- `out_of_scope`: topico fora do dominio de trafego/pedidos/receita por canal.
- `unsupported_dimension`: menciona dimensao inexistente no schema (ex: cidade,
  dispositivo, campanha, criativo).
- `unsupported_metric`: menciona metrica inexistente (ex: cliques, CTR, CPA,
  impressoes, conversao, ROAS).
- `unsupported_traffic_source`: menciona canal que nao existe nos dados
  (ex: TikTok, YouTube, Pinterest, Email, Display).

## Parametros normalizados

- `traffic_source`: so preencher se a pergunta mencionar exatamente um dos canais
  suportados. Valores aceitos: "Search", "Organic", "Facebook", "Instagram".
  Alias aceitos: google/adwords -> "Search", seo -> "Organic", fb -> "Facebook".
  Nulo se a pergunta for sobre todos os canais ou nao mencionar canal.
- `start_date` e `end_date`: extrair apenas se a pergunta trouxer data valida.
  Deixar nulos se ausentes — nao inferir datas.

## Contexto do thread

Quando houver mensagens anteriores no contexto, use-as para:
1. Identificar se a pergunta atual e um follow-up (strategy ou diagnostic).
2. Inferir datas de mensagens anteriores se a pergunta atual nao trouxer novas datas
   mas o contexto tiver um periodo claro — incluindo quando o usuario esta respondendo
   uma clarificacao anterior (ex: especificou so metrica ou canal sem data). Nesse
   caso, herdar o periodo do contexto e nao pedir clarificacao de datas.
3. Nao pedir clarificacao de datas em follow-ups de estrategia/diagnostico.

## Formato de resposta

Sempre preencher `response_message` em pt-BR quando:
- `needs_clarification=true` (mensagem educada pedindo o dado ausente)
- `refusal_reason` estiver preenchido (recusa educada e objetiva)
""".strip()


def build_router_thread_context(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Extract the last N non-system messages from a LangGraph thread for router context.

    SystemMessages are internal graph instructions and must not be forwarded to the
    router — the router has its own system prompt and mixing them corrupts the context.
    ToolMessages are preserved because they carry the most direct signal for follow-up
    detection: they tell the LLM "a tool was already executed in this thread."
    """
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    return non_system[-_MAX_CONTEXT_MESSAGES:]


def classify_question(
    question: str,
    thread_context: list[BaseMessage] | None = None,
    settings: Settings | None = None,
    *,
    _router_runnable: Any | None = None,
) -> RouterDecision:
    """Classify a user question into a RouterDecision using structured output.

    The LLM is constrained to return a valid RouterDecision (Pydantic) via
    with_structured_output — no string parsing required.

    Args:
        question: The current user question.
        thread_context: Recent messages from the conversation thread. Used so the
            LLM can detect follow-up intent without token lists.
        settings: Optional settings override (useful in tests).
        _router_runnable: Pre-built chain (post with_structured_output) injected
            by tests to avoid real LLM calls. Production code leaves this None.
    """
    if _router_runnable is not None:
        active_runnable: Any = _router_runnable
    else:
        base_llm = build_analytics_llm(settings)
        # with_structured_output wraps the LLM in a chain:
        #   LLM → output parser → RouterDecision instance
        # Under the hood: OpenAI/Anthropic use function/tool calling to force the
        # model to fill the schema fields as function arguments.
        active_runnable = base_llm.with_structured_output(RouterDecision)

    messages: list[BaseMessage] = [SystemMessage(content=_ROUTER_SYSTEM_PROMPT)]

    if thread_context:
        # Defensive cap: callers may pass raw state messages not pre-trimmed by
        # build_router_thread_context.
        recent = thread_context[-_MAX_CONTEXT_MESSAGES:]
        messages.extend(recent)

    messages.append(HumanMessage(content=question))

    result = active_runnable.invoke(messages)
    return result  # type: ignore[return-value]
