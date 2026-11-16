import duckdb
import pytest

from srag.audit import AuditLog
from srag.ingest import CLEAN_PATH

FORBIDDEN = {"DT_NASC", "NU_IDADE_N", "CO_MUN_NOT", "ID_MUNICIP", "SG_UF_NOT", "ID_UNIDADE",
             "CS_SEXO", "CS_RACA", "NOME_PROF"}
ALLOWED = {"DT_NOTIFIC", "DT_SIN_PRI", "DT_INTERNA", "HOSPITAL", "UTI", "EVOLUCAO",
           "VACINA_COV", "VACINA", "CLASSI_FIN"}


@pytest.mark.skipif(not CLEAN_PATH.exists(), reason="base limpa ainda não gerada")
def test_clean_parquet_has_only_allowed_columns():
    cols = {r[0] for r in duckdb.execute(f"DESCRIBE SELECT * FROM read_parquet('{CLEAN_PATH}')").fetchall()}
    assert cols == ALLOWED
    assert not cols & FORBIDDEN


def test_audit_log_redacts_secrets(tmp_path):
    audit = AuditLog(tmp_path)
    audit.log("x", api_key="sk-abc", nested={"access_token": "t", "ok": 1}, input_tokens=42)
    content = audit.path.read_text()
    assert "sk-abc" not in content and '"ok": 1' in content
    assert '"input_tokens": 42' in content
