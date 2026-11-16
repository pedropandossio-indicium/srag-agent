"""Trilha de auditoria: um arquivo JSON Lines por execução (run_id).

Cada evento (chamada de tool, chamada ao LLM, bloqueio de guardrail, falha)
recebe timestamp. Só agregados e texto de notícias entram no log, nunca
microdados nem credenciais. O hash SHA-256 do log fechado vai no relatório.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
SECRET_HINTS = ("api_key", "apikey", "secret", "password", "authorization", "access_token")


def _redact(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if any(h in k.lower() for h in SECRET_HINTS) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class AuditLog:
    def __init__(self, log_dir: Path = LOG_DIR) -> None:
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"{self.run_id}.jsonl"

    def log(self, event: str, **data) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **_redact(data)}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()
