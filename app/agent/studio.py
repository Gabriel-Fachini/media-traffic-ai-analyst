"""LangGraph Studio entry point.

Module-level static graph — no checkpointer. Studio injects its own persistence.
Loaded at import time (sync context) to avoid blockbuster's BlockingError.
"""

from app.agent.graph import build_analytics_graph
from app.infra.env import get_settings

graph = build_analytics_graph(get_settings())
