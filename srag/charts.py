"""Gráficos do relatório (Matplotlib), gerados a partir dos agregados."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from srag.metrics import LAG_DAYS

COLOR = "#2a6fdb"
LAG_COLOR = "#d98c1f"


def _style(ax, title: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=12)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def daily_chart(series: list[dict], out: Path) -> Path:
    days = [p["day"][5:] for p in series]
    cases = [p["cases"] for p in series]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(days, cases, color=COLOR, linewidth=2)
    ax.axvspan(len(days) - LAG_DAYS - 0.5, len(days) - 0.5, color=LAG_COLOR, alpha=0.15,
               label=f"últimos {LAG_DAYS} dias: possível subnotificação")
    ax.set_xticks(range(0, len(days), 3), days[::3], rotation=45, ha="right")
    _style(ax, "Casos diários de SRAG (últimos 30 dias, por início dos sintomas)", "casos")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def monthly_chart(series: list[dict], out: Path) -> Path:
    months = [p["month"] for p in series]
    cases = [p["cases"] for p in series]
    colors = [COLOR] * (len(cases) - 1) + [LAG_COLOR]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.bar(months, cases, color=colors)
    ax.set_xticks(range(len(months)), months, rotation=45, ha="right")
    _style(ax, "Casos mensais de SRAG (últimos 12 meses; mês corrente parcial em laranja)", "casos")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def generate_charts(metrics: dict, out_dir: Path) -> dict:
    """Grava os PNGs em out_dir e devolve só os nomes dos arquivos (sem caminho absoluto no log)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "daily": daily_chart(metrics["daily_cases"], out_dir / "casos_diarios_30d.png").name,
        "monthly": monthly_chart(metrics["monthly_cases"], out_dir / "casos_mensais_12m.png").name,
    }
