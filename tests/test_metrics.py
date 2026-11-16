from datetime import date, timedelta

import duckdb
import pytest

from srag import metrics

AS_OF = date(2026, 11, 16)


def _row(days_ago: int, **overrides) -> dict:
    base = {"DT_SIN_PRI": AS_OF - timedelta(days=days_ago), "HOSPITAL": 1,
            "UTI": 2, "EVOLUCAO": 1, "VACINA_COV": 2}
    return base | overrides


@pytest.fixture
def con():
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE srag (DT_SIN_PRI DATE, HOSPITAL TINYINT, UTI TINYINT, "
        "EVOLUCAO TINYINT, VACINA_COV TINYINT)"
    )
    return connection


def _load(connection, rows: list[dict]) -> None:
    for r in rows:
        connection.execute(
            "INSERT INTO srag VALUES (?, ?, ?, ?, ?)",
            [r["DT_SIN_PRI"], r["HOSPITAL"], r["UTI"], r["EVOLUCAO"], r["VACINA_COV"]],
        )


def test_case_growth_adjusted_ignores_recent_days(con):
    # 2 casos na janela ajustada atual, 1 na anterior, 5 nos últimos 14 dias
    rows = [_row(20), _row(25), _row(50)] + [_row(3)] * 5
    _load(con, rows)
    result = metrics.case_growth(con, AS_OF)
    assert result["adjusted"]["current_cases"] == 2
    assert result["adjusted"]["previous_cases"] == 1
    assert result["adjusted"]["rate"] == 1.0
    assert result["raw"]["current_cases"] == 7


def test_mortality_excludes_other_causes_and_open_cases(con):
    _load(con, [_row(30, EVOLUCAO=2), _row(30, EVOLUCAO=1), _row(30, EVOLUCAO=3),
              _row(30, EVOLUCAO=9)])
    result = metrics.mortality(con, AS_OF)
    assert result["rate"] == 0.5
    assert result["denominator"] == 2
    assert result["open_share"] == 0.25


def test_icu_share_uses_hospitalised_with_known_icu(con):
    _load(con, [_row(30, UTI=1), _row(30, UTI=2), _row(30, UTI=9),
              _row(30, HOSPITAL=2, UTI=1)])
    result = metrics.icu_share(con, AS_OF)
    assert result["rate"] == 0.5
    assert result["denominator"] == 2


def test_vaccination_ignores_unknown_answers(con):
    _load(con, [_row(30, VACINA_COV=1), _row(30, VACINA_COV=2), _row(30, VACINA_COV=9)])
    result = metrics.vaccination(con, AS_OF)
    assert result["rate"] == 0.5
    assert result["valid_response_share"] == pytest.approx(0.6667)


def test_daily_series_has_30_days_including_zeros(con):
    _load(con, [_row(0)])
    series = metrics.daily_series(con, AS_OF)
    assert len(series) == 30
    assert series[-1]["cases"] == 1
    assert series[0]["cases"] == 0


def test_monthly_series_covers_12_months_back(con):
    _load(con, [_row(0), _row(340)])
    months = [m["month"] for m in metrics.monthly_series(con, AS_OF)]
    assert months[0] == "2025-12"
    assert months[-1] == "2026-11"


def test_rate_is_none_when_denominator_is_zero(con):
    result = metrics.mortality(con, AS_OF)
    assert result["rate"] is None
