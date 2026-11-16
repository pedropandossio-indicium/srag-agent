"""Gera docs/arquitetura.pdf (diagrama conceitual). Uso: python docs/make_diagram.py"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "arquitetura.pdf"
BLUE, GREEN, ORANGE, GRAY = "#dbe7fb", "#dff2e1", "#fbe9cf", "#eeeeee"


def box(ax, x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc=color, ec="#444"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)


def arrow(ax, start, end, label="", style="-|>", side=False):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=12, color="#444"))
    if label and side:  # rótulo ao lado, para não cobrir as pontas da seta
        ax.text(start[0] + 0.12, (start[1] + end[1]) / 2, label, ha="left", va="center", fontsize=7)
    elif label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.15, label, ha="center", fontsize=7)


fig, ax = plt.subplots(figsize=(13, 7.5))
ax.set_xlim(0, 13)
ax.set_ylim(0, 7.5)
ax.axis("off")
ax.set_title("Agente de relatórios SRAG: arquitetura conceitual", fontsize=13, loc="left")

# Fronteira de confiança: microdados ficam à esquerda; só agregados cruzam.
ax.add_patch(FancyBboxPatch((0.1, 3.1), 3.9, 4.0, boxstyle="round,pad=0.02", fc="none", ec="#b03030", ls="--"))
ax.text(0.25, 6.85, "Zona dos microdados (nunca vai ao LLM)", fontsize=8, color="#b03030")

box(ax, 0.3, 5.6, 3.5, 0.9, "Portal de Dados Abertos do SUS\nINFLUD25/26.parquet", GRAY)
box(ax, 0.3, 4.2, 3.5, 0.9, "Ingestão (ingest.py)\nminimiza colunas, valida datas,\ndescarta identificáveis", BLUE)
box(ax, 0.3, 3.3, 3.5, 0.6, "Banco de dados: srag.parquet\n(consultado via DuckDB)", GRAY)
arrow(ax, (2.05, 5.6), (2.05, 5.1))
arrow(ax, (2.05, 4.2), (2.05, 3.9))

box(ax, 4.6, 3.3, 3.0, 3.2, "Tools (SQL fixo, DuckDB)\n\nget_metrics\ngenerate_charts\nsearch_news\n\nsó devolvem agregados", GREEN)
arrow(ax, (3.8, 3.6), (4.6, 4.2), "agregados")

box(ax, 8.4, 4.6, 4.3, 1.6, "Agente principal / Orquestrador (agent.py)\nloop de tool use; só vê agregados\nlimite de iterações; reparo de saída;\ncódigo chama tools que o LLM esquecer", BLUE)
box(ax, 8.4, 6.8, 4.3, 0.6, "LLM (llm.py): Ollama local qwen2.5:3b\n(opcional: Gemini ou Claude)", ORANGE)
arrow(ax, (10.55, 6.15), (10.55, 6.72), "prompts e respostas\n(só agregados)", style="<|-|>", side=True)
arrow(ax, (7.6, 5.0), (8.4, 5.4), "tool calls", style="<|-|>")

box(ax, 8.4, 3.3, 4.3, 0.9, "Guardrails (guardrails.py)\nallowlist · sem números no texto do LLM\ncitações validadas · notícia = dado", GREEN)
arrow(ax, (10.55, 4.6), (10.55, 4.2))

box(ax, 4.6, 1.2, 3.0, 1.2, "Fonte de notícias:\nGoogle News RSS\n(snapshot em cache/)", GRAY)
arrow(ax, (6.1, 3.3), (6.1, 2.4), "busca", style="<|-|>")

box(ax, 8.4, 1.2, 4.3, 1.5, "Relatório (report.py, template)\n4 métricas · 2 gráficos · comentários\nmetodologia · tabela métrica → tool_call_id", BLUE)
arrow(ax, (10.55, 3.3), (10.55, 2.7))

box(ax, 0.3, 0.3, 12.4, 0.6, "Auditoria (audit.py): log JSONL por run_id (tools, turnos do LLM, falhas, bloqueios, hash do dataset) · sha256 do log no relatório", ORANGE)
for x in (2.05, 6.1, 10.55):
    arrow(ax, (x, 1.2 if x != 2.05 else 3.3), (x, 0.9), style="-|>")

fig.savefig(OUT)
print(OUT)
