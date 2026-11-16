"""Ponto de entrada: python -m srag.run"""
import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from srag.agent import ReportAgent
from srag.audit import AuditLog
from srag.ingest import CLEAN_PATH, MANIFEST_PATH
from srag.report import build_report

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def main() -> None:
    load_dotenv()
    key = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(os.getenv("LLM_PROVIDER", "ollama"))
    if key and not os.getenv(key):
        raise SystemExit(f"Defina {key} no .env (veja .env.example).")
    if not CLEAN_PATH.exists():
        raise SystemExit("Base limpa ausente. Rode: python -m srag.ingest")

    audit = AuditLog()
    out_dir = REPORTS_DIR / audit.run_id
    manifest = json.loads(MANIFEST_PATH.read_text())
    audit.log("run_start", as_of=date.today().isoformat(), manifest=manifest)

    agent = ReportAgent(CLEAN_PATH, out_dir, audit, date.today())
    commentary, notes = agent.run()
    audit.log("run_end", commentary_count=len(commentary), notes=notes)

    report = build_report(
        run_id=audit.run_id, model=agent.model, metrics=agent.results["get_metrics"],
        call_ids=agent.call_ids, charts=agent.results["generate_charts"],
        news=agent.results["search_news"], commentary=commentary, notes=notes,
        manifest=manifest, log_sha256=audit.sha256())
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"Relatório: {out_dir / 'report.md'}\nLog: {audit.path}")


if __name__ == "__main__":
    main()
