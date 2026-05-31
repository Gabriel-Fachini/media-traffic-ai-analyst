"""Backward-compat shim — real implementation moved to app/agent/prompts.py."""

from app.agent.prompts import (
    FINAL_RESPONSE_SYSTEM_PROMPT,
    build_conversation_system_prompt,
)

__all__ = ["FINAL_RESPONSE_SYSTEM_PROMPT", "build_conversation_system_prompt"]
