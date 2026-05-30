from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.graph.llm import build_analytics_llm
from app.schemas.router import RouterDecision
from app.utils.config import Settings

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
   mas o contexto tiver um periodo claro.
3. Nao pedir clarificacao de datas em follow-ups de estrategia/diagnostico.

## Formato de resposta

Sempre preencher `response_message` em pt-BR quando:
- `needs_clarification=true` (mensagem educada pedindo o dado ausente)
- `refusal_reason` estiver preenchido (recusa educada e objetiva)
""".strip()

_MAX_CONTEXT_MESSAGES = 6


def classify_question(
    question: str,
    thread_context: list[BaseMessage] | None = None,
    settings: Settings | None = None,
) -> RouterDecision:
    """Classify a user question into a RouterDecision using structured output.

    The LLM is constrained to return a valid RouterDecision (Pydantic) via
    with_structured_output — no string parsing required.

    Args:
        question: The current user question.
        thread_context: Recent messages from the conversation thread. Used so the
            LLM can detect follow-up intent without token lists.
        settings: Optional settings override (useful in tests).
    """
    base_llm = build_analytics_llm(settings)

    # with_structured_output wraps the LLM in a chain:
    #   LLM → output parser → RouterDecision instance
    # Under the hood: OpenAI/Anthropic use function/tool calling to force the
    # model to fill the schema fields as function arguments.
    router_llm = base_llm.with_structured_output(RouterDecision)

    messages: list[BaseMessage] = [SystemMessage(content=_ROUTER_SYSTEM_PROMPT)]

    if thread_context:
        # Trim to last N messages to keep prompt size bounded.
        recent = thread_context[-_MAX_CONTEXT_MESSAGES:]
        messages.extend(recent)

    messages.append(HumanMessage(content=question))

    result = router_llm.invoke(messages)
    return result  # type: ignore[return-value]
