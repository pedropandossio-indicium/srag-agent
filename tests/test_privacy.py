import duckdb
import pytest

from srag import ingest
from srag.audit import AuditLog

FORBIDDEN = {"DT_NASC", "NU_IDADE_N", "CO_MUN_NOT", "ID_MUNICIP", "SG_UF_NOT", "ID_UNIDADE",
             "CS_SEXO", "CS_RACA", "NOME_PROF"}
ALLOWED = {"DT_SIN_PRI", "HOSPITAL", "UTI", "EVOLUCAO", "VACINA_COV"}


def _columns(path) -> set[str]:
    return {r[0] for r in duckdb.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    """Base bruta sintética com identificáveis, colunas extras e uma data impossível."""
    data = tmp_path / "data"
    data.mkdir()
    duckdb.execute(
        f"COPY (SELECT * FROM (VALUES "
        f"(DATE '2026-05-01', '1', '1', '2', '1', DATE '1980-01-01', 'SP', 'F', '35'), "
        f"(DATE '5202-01-01', '2', NULL, '9', '2', DATE '1990-02-02', 'RJ', 'M', '41')) "
        f"AS t(DT_SIN_PRI, HOSPITAL, UTI, EVOLUCAO, VACINA_COV, DT_NASC, SG_UF_NOT, CS_SEXO, NU_IDADE_N)) "
        f"TO '{data / 'INFLUD99-01-01-2026.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(ingest, "RAW_GLOB", str(data / "INFLUD*.parquet"))
    monkeypatch.setattr(ingest, "CLEAN_PATH", data / "processed" / "srag.parquet")
    monkeypatch.setattr(ingest, "MANIFEST_PATH", data / "processed" / "manifest.json")
    return data


def test_ingest_keeps_only_allowed_columns(raw_dir):
    ingest.main()
    cols = _columns(ingest.CLEAN_PATH)
    assert cols == ALLOWED
    assert not cols & FORBIDDEN


def test_ingest_nulls_impossible_dates_and_maps_unknown_codes(raw_dir):
    ingest.main()
    rows = duckdb.execute(
        f"SELECT DT_SIN_PRI, UTI FROM read_parquet('{ingest.CLEAN_PATH}') ORDER BY HOSPITAL").fetchall()
    assert rows[0][0] is not None and rows[0][1] == 1
    assert rows[1] == (None, 9)  # ano 5202 vira nulo; UTI nula vira 9 (ignorado)


def test_audit_log_redacts_secrets(tmp_path):
    audit = AuditLog(tmp_path)
    audit.log("x", api_key="sk-abc", nested={"access_token": "t", "ok": 1}, input_tokens=42)
    content = audit.path.read_text()
    assert "sk-abc" not in content and '"ok": 1' in content
    assert '"input_tokens": 42' in content
