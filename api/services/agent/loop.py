"""The FinForge financial-agent loop (finforge-28, Phase 1).

A manual tool-use loop (not the SDK tool-runner) so we control streaming and, later,
confirmation gates on write tools. Opus 4.8 with adaptive thinking + effort drives it;
the model pulls data on demand via the read tools in `tools.py` instead of being handed
one fixed context blob, so it can answer questions the old single-shot chat couldn't.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from .client import AGENT_MAX_TOKENS, AGENT_MODEL, get_client
from .tools import dispatch, tool_schemas

logger = logging.getLogger("finforge.api.agent.loop")

# Hard stop on tool rounds so a confused model can't loop forever.
MAX_TOOL_ROUNDS = 8

_BEHAVIOR = """You are FinForge, a personal financial analyst agent with live, tool-based access \
to the user's real financial data — accounts, transactions, holdings, cash flow, taxes, \
dividends, retirement projections, portfolio risk, and spending anomalies.

How to work:
- Use tools to gather what you need before answering. Don't guess at numbers you can look up.
- Chain tools when a question needs it (e.g. "why did my runway drop?" → check runway, then \
search recent transactions, then explain). Prefer pulling real figures over hand-waving.
- Be specific and quantitative. Lead with the answer, then the supporting numbers.
- Keep it concise by default (a few sentences); expand into a breakdown when the user asks for \
one or the data clearly warrants it.
- You may give investment opinions and financial advice when asked.
- If a tool returns an error or empty data, say what's missing rather than inventing an answer.
- All data is read-only right now; you cannot change anything yet, so don't claim to have done so.
- Money is USD. Positive transaction amounts are spending/debits; negative are income/credits."""


def _system_blocks(username: str) -> list[dict]:
    """System prompt as cache-friendly blocks: stable behavior (cached with the tool
    list) first, small volatile seed (date/user) after the breakpoint."""
    return [
        {
            "type": "text",
            "text": _BEHAVIOR,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"Today is {date.today().isoformat()}. You are assisting {username}.",
        },
    ]


def run_agent(
    db: Session,
    username: str,
    message: str,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Run the agent loop for one user turn.

    Returns {"reply": str, "steps": [{"tool", "input"}...], "rounds": int}. `steps`
    is the tool trace (for logging now, and a transcript UI in Phase 2).
    """
    client = get_client()
    tools = tool_schemas()
    system = _system_blocks(username)

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": message})

    steps: list[dict] = []
    rounds = 0

    while rounds <= MAX_TOOL_ROUNDS:
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=AGENT_MAX_TOKENS,
            system=system,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            reply = "".join(b.text for b in response.content if b.type == "text").strip()
            return {"reply": reply, "steps": steps, "rounds": rounds}

        # Preserve the full assistant turn (thinking + tool_use blocks) verbatim.
        messages.append({"role": "assistant", "content": response.content})

        tool_results: list[dict] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            steps.append({"tool": block.name, "input": block.input})
            logger.info("[agent] tool=%s args=%s", block.name, block.input)
            result_json = dispatch(block.name, block.input, db)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_json,
            })

        messages.append({"role": "user", "content": tool_results})
        rounds += 1

    # Exhausted the tool-round budget — ask for a final answer with tools disabled.
    final = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=system,
        messages=messages + [{
            "role": "user",
            "content": "You've reached the tool-call limit. Answer now with what you have.",
        }],
    )
    reply = "".join(b.text for b in final.content if b.type == "text").strip()
    return {"reply": reply, "steps": steps, "rounds": rounds}
