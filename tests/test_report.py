from datetime import date

import duckdb

from srag import metrics
from srag.report import build_report

NEWS = {"status": "ok", "items": [
    {"id": "n1", "title": "Alta de SRAG", "source": "Fonte A", "published": "2026-11-10", "url": "https://example.com/a"},
    {"id": "n2", "title": "Queda de SRAG", "source": "Fonte B", "published": "2026-11-11", "url": "https://example.com/b"},
]}
MANIFEST = {"sources": ["x.parquet"], "ingested_at": "2026-11-16", "rows": 1, "clean_sha256": "a" * 64}


def _metrics():
    con = duckdb.connect()
    con.execute("CREATE TABLE srag AS SELECT DATE '2026-11-01' AS DT_SIN_PRI, 1 AS HOSPITAL, 2 AS UTI, "
                "1 AS EVOLUCAO, 1 AS VACINA_COV")
    return metrics.compute_all(con, date(2026, 11, 16))


def _report(commentary):
    return build_report(
        run_id="r1", model="m", metrics=_metrics(), call_ids={"get_metrics": "call-1"},
        charts={"daily": "d.png", "monthly": "m.png"}, news=NEWS, commentary=commentary, notes=[],
        manifest=MANIFEST, log_sha256="b" * 64)


def test_news_list_is_numbered_to_match_the_references_in_the_comments():
    report = _report([{"text": "Alta regional, conforme [1] e [2].", "news_refs": ["https://example.com/a"]}])
    assert "conforme [1] e [2]" in report
    assert "- [1] 2026-11-10 · Fonte A" in report and "- [2] 2026-11-11 · Fonte B" in report


def test_report_has_no_absolute_paths_and_names_the_metrics_source():
    report = _report([])
    assert "/home/" not in report and "call-1" in report
