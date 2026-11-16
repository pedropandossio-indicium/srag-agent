import json
from datetime import date

import duckdb
import pytest

from srag import agent as agent_module
from srag.audit import AuditLog
from srag.llm import ToolCall, Turn

NEWS = {"status": "ok", "items": [{"id": "n1", "title": "Alta de SRAG", "source": "Fonte",
                                   "published": "2026-11-10", "url": "https://example.com/a"}]}
GOOD_COMMENT = {"text": "Circulação em alta", "news_refs": ["n1"]}
RESOLVED_COMMENT = {"text": "Circulação em alta", "news_refs": ["https://example.com/a"]}


def _turn(text="", calls=()):
    return Turn(text=text, tool_calls=list(calls), stop_reason="stop", input_tokens=10, output_tokens=5)


def _text(comments):
    return json.dumps({"commentary": comments})


class FakeSession:
    model = "fake-model"

    def __init__(self, scripted):
        self.scripted = list(scripted)

    def send(self, _text):
        return self.scripted.pop(0)

    def send_tool_results(self, _results):
        return self.scripted.pop(0)


@pytest.fixture
def clean_parquet(tmp_path):
    path = tmp_path / "srag.parquet"
    duckdb.execute(
        f"COPY (SELECT DATE '2026-11-01' AS DT_SIN_PRI, 1 AS HOSPITAL, 2 AS UTI, "
        f"1 AS EVOLUCAO, 1 AS VACINA_COV) TO '{path}' (FORMAT PARQUET)")
    return path


def _make_agent(monkeypatch, tmp_path, clean_parquet, scripted):
    monkeypatch.setattr(agent_module, "make_session", lambda *_: FakeSession(scripted))
    monkeypatch.setattr(agent_module.news, "search_news", lambda q, run_id: NEWS)
    audit = AuditLog(tmp_path / "logs")
    return agent_module.ReportAgent(clean_parquet, tmp_path / "out", audit, date(2026, 11, 16)), audit


def _events(audit):
    return [json.loads(line)["event"] for line in audit.path.read_text().splitlines()]


def test_full_run_with_tool_calls_and_valid_commentary(monkeypatch, tmp_path, clean_parquet):
    calls = [ToolCall(f"t{i}", n, {}) for i, n in enumerate(agent_module.REQUIRED_TOOLS)]
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet,
                               [_turn(calls=calls), _turn(_text([GOOD_COMMENT]))])
    commentary, notes = agent.run()
    assert commentary == [RESOLVED_COMMENT] and notes == []
    assert agent.call_ids["get_metrics"] == "t0"
    assert "guardrail_block" not in _events(audit)


def test_missing_tools_are_forced_by_code_and_audited(monkeypatch, tmp_path, clean_parquet):
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [_turn(_text([]))])
    _, notes = agent.run()
    assert set(agent.call_ids) == set(agent_module.REQUIRED_TOOLS)
    assert _events(audit).count("forced_tool_call") == 3
    assert len(notes) == 3


def test_invented_numbers_are_discarded_and_audited(monkeypatch, tmp_path, clean_parquet):
    bad = _turn(_text([{"text": "Alta de 50%", "news_refs": ["n1"]}]))
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [bad, bad])
    commentary, notes = agent.run()
    assert commentary == []
    assert _events(audit).count("guardrail_block") == 2
    assert any("descartados" in n for n in notes)


def test_model_gets_one_repair_attempt_after_a_rejected_answer(monkeypatch, tmp_path, clean_parquet):
    bad = _turn(_text([{"text": "Alta de 50%", "news_refs": ["n1"]}]))
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [bad, _turn(_text([GOOD_COMMENT]))])
    commentary, _ = agent.run()
    assert commentary == [RESOLVED_COMMENT]
    assert _events(audit).count("guardrail_block") == 1


def test_unknown_tool_request_is_blocked(monkeypatch, tmp_path, clean_parquet):
    rogue = _turn(calls=[ToolCall("x", "run_sql", {})])
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [rogue, _turn(_text([]))])
    agent.run()
    assert "guardrail_block" in _events(audit)
