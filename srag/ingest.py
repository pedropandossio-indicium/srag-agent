"""Ingestão: lê os Parquets brutos e grava uma base mínima e anonimizada.

Minimização de dados: só entram as colunas que as métricas usam. Data de
nascimento, idade, município, UF e unidade de saúde são descartados aqui, antes
de qualquer outra etapa. Códigos ignorados (9 ou nulo) viram 9; datas fora de
faixa (ex.: ano 5202) viram nulo.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW_GLOB = str(ROOT / "data" / "INFLUD*.parquet")
CLEAN_PATH = ROOT / "data" / "processed" / "srag.parquet"
MANIFEST_PATH = ROOT / "data" / "processed" / "manifest.json"

DATE_COLUMNS = ("DT_NOTIFIC", "DT_SIN_PRI", "DT_INTERNA")
CODE_COLUMNS = ("HOSPITAL", "UTI", "EVOLUCAO", "VACINA_COV", "VACINA")
MIN_DATE = "2019-01-01"


def build_query() -> str:
    dates = ", ".join(
        f"CASE WHEN {c} BETWEEN DATE '{MIN_DATE}' AND DATE '{date.today()}' "
        f"THEN CAST({c} AS DATE) END AS {c}"
        for c in DATE_COLUMNS
    )
    codes = ", ".join(
        f"COALESCE(TRY_CAST({c} AS TINYINT), 9) AS {c}" for c in CODE_COLUMNS
    )
    classi = "COALESCE(TRY_CAST(CLASSI_FIN AS TINYINT), 9) AS CLASSI_FIN"
    return f"SELECT {dates}, {codes}, {classi} FROM read_parquet('{RAW_GLOB}')"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    raw_files = sorted(Path(RAW_GLOB).parent.glob("INFLUD*.parquet"))
    if not raw_files:
        raise SystemExit("Nenhum INFLUD*.parquet em data/. Rode scripts/download_data.py.")

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"COPY ({build_query()}) TO '{CLEAN_PATH}' (FORMAT PARQUET)")
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{CLEAN_PATH}')").fetchone()[0]

    manifest = {
        "ingested_at": date.today().isoformat(),
        "sources": [f.name for f in raw_files],
        "rows": rows,
        "clean_sha256": sha256(CLEAN_PATH),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
