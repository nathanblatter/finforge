"""Central Anthropic client + model constants for FinForge.

Phase 0 of the agentic-chat harness (finforge-28). Historically every caller
instantiated `anthropic.Anthropic(...)` inline and hard-coded the model string
in five places. New agent code goes through here; the legacy call sites can be
migrated to `get_client()` / these constants incrementally.
"""

from __future__ import annotations

import anthropic

from config import settings

# The reasoning model that drives the financial agent loop. Opus 4.8 supports
# adaptive thinking + the effort parameter + tool use, which the agent relies on.
AGENT_MODEL = "claude-opus-4-8"

# Cheaper model for high-volume, non-agentic batch text (digests, narration).
# Kept as a constant so the fleet has one place to change it.
BATCH_MODEL = "claude-sonnet-4-6"

# Default output ceiling for a single agent turn. Non-streaming stays well under
# the SDK's HTTP-timeout guard; bump + switch to streaming in the Phase 2 SSE work.
AGENT_MAX_TOKENS = 8000


def get_client() -> anthropic.Anthropic:
    """Return a configured Anthropic client, or raise if the key is unset."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)
