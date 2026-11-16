import io
import json

import pytest

from srag import llm

TOOLS = [{"name": "get_metrics", "description": "d", "input_schema": {"type": "object", "properties": {}}}]


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _reply(message, **extra):
    return FakeHTTPResponse(json.dumps({"message": message, "done_reason": "stop", **extra}).encode())


def test_ollama_session_parses_tool_calls_and_replays_results(monkeypatch):
    sent = []
    replies = [
        _reply({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_metrics", "arguments": {}}}]}, prompt_eval_count=7, eval_count=3),
        _reply({"role": "assistant", "content": "pronto"}),
    ]

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return replies.pop(0)

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    session = llm.OllamaSession("sistema", TOOLS, "qwen2.5:3b")

    turn = session.send("oi")
    assert [c.name for c in turn.tool_calls] == ["get_metrics"]
    assert (turn.input_tokens, turn.output_tokens) == (7, 3)

    final = session.send_tool_results([(turn.tool_calls[0], '{"ok": 1}')])
    assert final.text == "pronto" and not final.tool_calls
    assert sent[1]["messages"][-1] == {"role": "tool", "tool_name": "get_metrics", "content": '{"ok": 1}'}


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "foo")
    with pytest.raises(ValueError):
        llm.make_session("s", TOOLS)
