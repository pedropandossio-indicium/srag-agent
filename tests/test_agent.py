import json
from datetime import date

import duckdb
import pytest

from srag import agent as agent_module
from srag.audit import AuditLog
from srag.guardrails import MAX_ITERATIONS
from srag.llm import ToolCall, Turn

NEWS = {"status": "ok", "items": [{"id": "n1", "title": "Alta de SRAG", "source": "Fonte",
                                   "published": "2026-11-10", "url": "https://example.com/a"}]}
GOOD_COMMENT = {"text": "Circulação em alta", "news_refs": ["n1"]}
OTHER_COMMENT = {"text": "Notícias divergem dos dados", "news_refs": ["n1"]}
RESOLVED_COMMENT = {"text": "Circulação em alta", "news_refs": ["https://example.com/a"]}
BAD_NUMBERS = {"text": "Alta de 50%", "news_refs": ["n1"]}


def _turn(text="", calls=()):
    return Turn(text=text, tool_calls=list(calls), stop_reason="stop", input_tokens=10, output_tokens=5)


def _text(comments):
    return json.dumps({"commentary": comments})


def _all_tool_calls():
    return _turn(calls=[ToolCall(f"t{i}", n, {}) for i, n in enumerate(agent_module.REQUIRED_TOOLS)])


class FakeSession:
    model = "fake-model"

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.sent = []  # textos enviados ao modelo como mensagem de usuário

    def send(self, text):
        self.sent.append(text)
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
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet,
                               [_all_tool_calls(), _turn(_text([GOOD_COMMENT]))])
    commentary, notes = agent.run()
    assert commentary == [RESOLVED_COMMENT] and notes == []
    assert agent.call_ids["get_metrics"] == "t0"
    events = _events(audit)
    assert "guardrail_block" not in events and "context_sent_to_model" not in events
    assert all("/" not in name for name in agent.results["generate_charts"].values())


def test_missing_tools_are_forced_by_code_and_audited(monkeypatch, tmp_path, clean_parquet):
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [_turn(_text([])), _turn(_text([]))])
    _, notes = agent.run()
    assert set(agent.call_ids) == set(agent_module.REQUIRED_TOOLS)
    assert _events(audit).count("forced_tool_call") == 3
    assert len(notes) == 3


def test_model_is_briefed_with_metrics_and_news_before_commenting(monkeypatch, tmp_path, clean_parquet):
    """Comentário escrito às cegas (citando n1 sem ter visto as notícias) é descartado."""
    blind, informed = _turn(_text([GOOD_COMMENT])), _turn(_text([OTHER_COMMENT]))
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [blind, informed])
    commentary, _ = agent.run()
    briefing = agent.session.sent[1]
    assert "<metricas>" in briefing and "<noticias_nao_confiaveis>" in briefing
    assert "case_growth" in briefing and "daily_cases" not in briefing  # só o resumo das métricas
    assert "context_sent_to_model" in _events(audit)
    assert commentary == [{"text": OTHER_COMMENT["text"], "news_refs": ["https://example.com/a"]}]


def test_only_what_the_model_has_not_seen_is_sent(monkeypatch, tmp_path, clean_parquet):
    """O modelo chamou só get_metrics: o código entrega as notícias, não repete as métricas."""
    seen_metrics = _turn(calls=[ToolCall("t0", "get_metrics", {})])
    agent, _ = _make_agent(monkeypatch, tmp_path, clean_parquet,
                           [seen_metrics, _turn(_text([])), _turn(_text([GOOD_COMMENT]))])
    commentary, _ = agent.run()
    briefing = agent.session.sent[1]
    assert "<noticias_nao_confiaveis>" in briefing and "<metricas>" not in briefing
    assert commentary == [RESOLVED_COMMENT]


def test_invented_numbers_are_discarded_and_audited(monkeypatch, tmp_path, clean_parquet):
    bad = _turn(_text([BAD_NUMBERS]))
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [_all_tool_calls(), bad, bad])
    commentary, notes = agent.run()
    assert commentary == []
    assert _events(audit).count("guardrail_block") == 2
    assert any("descartados" in n for n in notes)


def test_model_gets_one_repair_attempt_after_a_rejected_answer(monkeypatch, tmp_path, clean_parquet):
    scripted = [_all_tool_calls(), _turn(_text([BAD_NUMBERS])), _turn(_text([GOOD_COMMENT]))]
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, scripted)
    commentary, _ = agent.run()
    assert commentary == [RESOLVED_COMMENT]
    assert _events(audit).count("guardrail_block") == 1


@pytest.mark.parametrize("answer", [
    '{"commentary": ["só texto"]}',
    '{"commentary": {"text": "x", "news_refs": ["n1"]}}',
    '["lista", "solta"]',
    '{"outro": []}',
    "sem json nenhum",
])
def test_unexpected_formats_do_not_crash_the_run(monkeypatch, tmp_path, clean_parquet, answer):
    bad = _turn(answer)
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [_all_tool_calls(), bad, bad])
    commentary, notes = agent.run()
    assert commentary == []
    assert any("descartados" in n for n in notes)
    assert _events(audit).count("guardrail_block") == 2


def test_ids_mentioned_in_the_text_become_numbered_references(monkeypatch, tmp_path, clean_parquet):
    cited = {"text": "Alta regional, conforme n1.", "news_refs": ["n1"]}
    agent, _ = _make_agent(monkeypatch, tmp_path, clean_parquet, [_all_tool_calls(), _turn(_text([cited]))])
    commentary, _ = agent.run()
    assert commentary == [{"text": "Alta regional, conforme [1].", "news_refs": ["https://example.com/a"]}]


def test_extra_comments_are_cut_to_the_limit_and_audited(monkeypatch, tmp_path, clean_parquet):
    many = _turn(_text([GOOD_COMMENT] * (agent_module.MAX_COMMENTS + 3)))
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [_all_tool_calls(), many])
    commentary, _ = agent.run()
    assert len(commentary) == agent_module.MAX_COMMENTS
    assert "comments_truncated" in _events(audit) and "guardrail_block" not in _events(audit)


def test_unknown_tool_request_is_blocked(monkeypatch, tmp_path, clean_parquet):
    rogue = _turn(calls=[ToolCall("x", "run_sql", {})])
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet,
                               [rogue, _turn(_text([])), _turn(_text([]))])
    agent.run()
    assert "guardrail_block" in _events(audit)


def test_iteration_limit_with_pending_tool_calls_asks_nothing_more(monkeypatch, tmp_path, clean_parquet):
    """Com tool_use pendente a API rejeitaria qualquer texto: encerra sem briefing nem correção."""
    looping = _turn(calls=[ToolCall("t", "get_metrics", {})])
    agent, audit = _make_agent(monkeypatch, tmp_path, clean_parquet, [looping] * (MAX_ITERATIONS + 1))
    commentary, notes = agent.run()
    assert commentary == []
    assert len(agent.session.sent) == 1  # só a mensagem inicial
    assert any("limite" in n for n in notes)
    assert "guardrail_block" in _events(audit)
