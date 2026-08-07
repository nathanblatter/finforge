"""Loop-mechanics tests for the financial agent (finforge-28).

These exercise run_agent()'s control flow with a fake Anthropic client and a
stubbed tool dispatch — no network, no DB. They prove the manual tool-use loop:
tool_use round -> dispatch -> tool_result fed back -> final text answer, plus the
MAX_TOOL_ROUNDS safety valve and the tool-schema contract.
"""

import services.agent.loop as loop
from services.agent.tools import tool_schemas


# ---------------------------------------------------------------------------
# Fakes matching the shape the loop consumes from the Anthropic SDK.
# ---------------------------------------------------------------------------

class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


class _ToolUse:
    type = "tool_use"

    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeMessages:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._script.pop(0)


class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


def _install(monkeypatch, script, dispatch=None):
    client = _FakeClient(script)
    monkeypatch.setattr(loop, "get_client", lambda: client)
    monkeypatch.setattr(loop, "tool_schemas", lambda: [{"name": "t", "description": "d",
                                                        "input_schema": {"type": "object"}}])
    if dispatch is not None:
        monkeypatch.setattr(loop, "dispatch", dispatch)
    return client


def test_single_shot_answer_no_tools(monkeypatch):
    _install(monkeypatch, [_Resp("end_turn", [_Text("Your net worth is $123.")])])
    out = loop.run_agent(db=None, username="Nathan", message="hi")
    assert out["reply"] == "Your net worth is $123."
    assert out["steps"] == []
    assert out["rounds"] == 0


def test_one_tool_round_then_answer(monkeypatch):
    script = [
        _Resp("tool_use", [_ToolUse("tu_1", "get_financial_overview", {})]),
        _Resp("end_turn", [_Text("Net worth is $500.")]),
    ]
    seen = {}
    def fake_dispatch(name, args, db):
        seen["name"] = name
        return '{"net_worth": 500}'
    client = _install(monkeypatch, script, dispatch=fake_dispatch)

    out = loop.run_agent(db=None, username="Nathan", message="how am I doing?")

    assert out["reply"] == "Net worth is $500."
    assert seen["name"] == "get_financial_overview"
    assert out["steps"] == [{"tool": "get_financial_overview", "input": {}}]
    assert out["rounds"] == 1
    # Second call must carry the assistant tool_use turn + the user tool_result turn.
    second_msgs = client.messages.calls[1]["messages"]
    assert second_msgs[-1]["role"] == "user"
    assert second_msgs[-1]["content"][0]["type"] == "tool_result"
    assert second_msgs[-1]["content"][0]["tool_use_id"] == "tu_1"


def test_history_is_prepended(monkeypatch):
    _install(monkeypatch, [_Resp("end_turn", [_Text("ok")])])
    client = loop.get_client  # not used; grab calls via closure below
    fake = _FakeClient([_Resp("end_turn", [_Text("ok")])])
    monkeypatch.setattr(loop, "get_client", lambda: fake)
    hist = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "reply"}]
    loop.run_agent(db=None, username="N", message="now", history=hist)
    msgs = fake.messages.calls[0]["messages"]
    assert msgs[0]["content"] == "prev"
    assert msgs[-1] == {"role": "user", "content": "now"}


def test_tool_round_budget_forces_final_answer(monkeypatch):
    # Always ask for a tool → loop must bail after MAX_TOOL_ROUNDS+1 and issue a
    # final tool-less request for the answer.
    tool_resp = _Resp("tool_use", [_ToolUse("tu", "get_financial_overview", {})])
    script = [tool_resp] * (loop.MAX_TOOL_ROUNDS + 1) + [_Resp("end_turn", [_Text("final")])]
    client = _install(monkeypatch, script, dispatch=lambda n, a, d: "{}")

    out = loop.run_agent(db=None, username="N", message="loop forever")

    assert out["reply"] == "final"
    assert out["rounds"] == loop.MAX_TOOL_ROUNDS + 1
    # The final rescue call must have NO tools attached.
    assert "tools" not in client.messages.calls[-1]


def test_uses_opus_and_adaptive_thinking(monkeypatch):
    client = _install(monkeypatch, [_Resp("end_turn", [_Text("x")])])
    loop.run_agent(db=None, username="N", message="q")
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "high"}
    # System prompt must be cache-friendly blocks with a breakpoint.
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_real_tool_schemas_are_well_formed():
    schemas = tool_schemas()
    assert len(schemas) >= 12
    names = {s["name"] for s in schemas}
    assert {"get_financial_overview", "search_transactions", "get_cashflow_runway",
            "get_fire_projection", "get_tax_summary"} <= names
    for s in schemas:
        assert set(s) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
        assert s["description"].strip()
