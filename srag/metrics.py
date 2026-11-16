"""Métricas e séries do relatório, calculadas com SQL fixo sobre a base limpa.

Convenções (documentadas também no relatório):
- "Caso" é qualquer registro, datado pelo início dos sintomas (DT_SIN_PRI).
- Atraso de notificação: as janelas comparadas terminam em hoje - LAG_DAYS.
  A taxa bruta (janelas terminando hoje) é reportada ao lado, por transparência.
- Código 9 = ignorado/nulo e fica fora dos denominadores.
"""
from datetime import date, timedelta
from pathlib import Path

import duckdb

LAG_DAYS = 14
WINDOW_DAYS = 30
MONTHS = 12
STABLE_BAND = 0.05  # variação de até 5% para cima ou para baixo conta como estável


def _scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> int:
    return con.execute(sql, params).fetchone()[0]


def _cases_between(con, start: date, end: date) -> int:
    return _scalar(
        con,
        "SELECT count(*) FROM srag WHERE DT_SIN_PRI BETWEEN ? AND ?",
        [start, end],
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _trend(rate: float | None) -> str:
    """Rótulo qualitativo calculado pelo código, para o LLM não ter de interpretar números."""
    if rate is None:
        return "indefinida"
    if rate > STABLE_BAND:
        return "alta"
    return "queda" if rate < -STABLE_BAND else "estável"


def case_growth(con, as_of: date) -> dict:
    """Casos dos últimos 30 dias contra os 30 anteriores, com e sem atraso."""

    def growth(end: date) -> dict:
        current_start = end - timedelta(days=WINDOW_DAYS - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=WINDOW_DAYS - 1)
        current = _cases_between(con, current_start, end)
        previous = _cases_between(con, previous_start, previous_end)
        rate = round(current / previous - 1, 4) if previous else None
        return {
            "current_cases": current,
            "previous_cases": previous,
            "rate": rate,
            "trend": _trend(rate),
            "window": f"{current_start} a {end}",
        }

    return {
        "adjusted": growth(as_of - timedelta(days=LAG_DAYS)),
        "raw": growth(as_of),
        "lag_days": LAG_DAYS,
    }


def mortality(con, as_of: date) -> dict:
    """Óbitos por SRAG (EVOLUCAO=2) sobre casos com desfecho cura ou óbito.

    Óbito por outras causas (3) fica fora; casos sem desfecho (9) são
    reportados à parte como "em aberto".
    """
    start = as_of - timedelta(days=365)
    row = con.execute(
        """
        SELECT count(*) FILTER (WHERE EVOLUCAO = 2),
               count(*) FILTER (WHERE EVOLUCAO IN (1, 2)),
               count(*) FILTER (WHERE EVOLUCAO = 9),
               count(*)
        FROM srag WHERE DT_SIN_PRI BETWEEN ? AND ?
        """,
        [start, as_of - timedelta(days=LAG_DAYS)],
    ).fetchone()
    deaths, resolved, open_cases, total = row
    return {
        "rate": _ratio(deaths, resolved),
        "deaths": deaths,
        "denominator": resolved,
        "open_share": _ratio(open_cases, total),
        "window": f"{start} a {as_of - timedelta(days=LAG_DAYS)}",
    }


def icu_share(con, as_of: date) -> dict:
    """Proporção das internações com passagem por UTI (não é ocupação de leitos)."""
    start = as_of - timedelta(days=365)
    row = con.execute(
        """
        SELECT count(*) FILTER (WHERE UTI = 1),
               count(*) FILTER (WHERE UTI IN (1, 2))
        FROM srag
        WHERE HOSPITAL = 1 AND DT_SIN_PRI BETWEEN ? AND ?
        """,
        [start, as_of - timedelta(days=LAG_DAYS)],
    ).fetchone()
    icu, valid = row
    return {
        "rate": _ratio(icu, valid),
        "icu": icu,
        "denominator": valid,
        "window": f"{start} a {as_of - timedelta(days=LAG_DAYS)}",
    }


def vaccination(con, as_of: date) -> dict:
    """Proporção dos casos de SRAG vacinados contra COVID-19 (viés de seleção)."""
    start = as_of - timedelta(days=365)
    row = con.execute(
        """
        SELECT count(*) FILTER (WHERE VACINA_COV = 1),
               count(*) FILTER (WHERE VACINA_COV IN (1, 2)),
               count(*)
        FROM srag WHERE DT_SIN_PRI BETWEEN ? AND ?
        """,
        [start, as_of - timedelta(days=LAG_DAYS)],
    ).fetchone()
    vaccinated, valid, total = row
    return {
        "rate": _ratio(vaccinated, valid),
        "vaccinated": vaccinated,
        "denominator": valid,
        "valid_response_share": _ratio(valid, total),
        "window": f"{start} a {as_of - timedelta(days=LAG_DAYS)}",
    }


def daily_series(con, as_of: date) -> list[dict]:
    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    rows = con.execute(
        """
        SELECT d::DATE AS day, count(s.DT_SIN_PRI) AS cases
        FROM generate_series(?::DATE, ?::DATE, INTERVAL 1 DAY) AS g(d)
        LEFT JOIN srag s ON s.DT_SIN_PRI = d::DATE
        GROUP BY 1 ORDER BY 1
        """,
        [start, as_of],
    ).fetchall()
    return [{"day": day.isoformat(), "cases": cases} for day, cases in rows]


def monthly_series(con, as_of: date) -> list[dict]:
    """12 meses de calendário: 11 completos mais o mês corrente, que é parcial."""
    first_month = date(as_of.year, as_of.month, 1)
    month = first_month.month - (MONTHS - 1)
    year = first_month.year + (month - 1) // 12
    start = date(year, (month - 1) % 12 + 1, 1)
    rows = con.execute(
        """
        SELECT strftime(date_trunc('month', DT_SIN_PRI), '%Y-%m') AS month,
               count(*) AS cases
        FROM srag WHERE DT_SIN_PRI BETWEEN ? AND ?
        GROUP BY 1 ORDER BY 1
        """,
        [start, as_of],
    ).fetchall()
    return [{"month": m, "cases": c} for m, c in rows]


def connect(clean_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW srag AS SELECT * FROM read_parquet('{clean_path}')")
    return con


def compute_all(con, as_of: date) -> dict:
    return {
        "as_of": as_of.isoformat(),
        "case_growth": case_growth(con, as_of),
        "mortality": mortality(con, as_of),
        "icu_share": icu_share(con, as_of),
        "vaccination": vaccination(con, as_of),
        "daily_cases": daily_series(con, as_of),
        "monthly_cases": monthly_series(con, as_of),
    }
