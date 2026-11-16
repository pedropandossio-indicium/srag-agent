"""Monta o relatório em Markdown. Todo número vem das tools, nunca do LLM."""
import json
from pathlib import Path

from srag.metrics import LAG_DAYS


def _pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.1%}".replace(".", ",")


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def build_report(*, run_id: str, model: str, metrics: dict, call_ids: dict, charts: dict,
                 news: dict, commentary: list[dict], notes: list[str], manifest: dict,
                 log_sha256: str) -> str:
    g, m = metrics["case_growth"], metrics["mortality"]
    u, v = metrics["icu_share"], metrics["vaccination"]
    adj, raw = g["adjusted"], g["raw"]
    src = call_ids["get_metrics"]

    lines = [
        f"# Relatório de SRAG — dados até {metrics['as_of']}",
        "",
        "## Métricas",
        "| Métrica | Valor | Detalhe | Janela | Origem (tool_call_id) |",
        "|---|---|---|---|---|",
        f"| Taxa de aumento de casos | {_pct(adj['rate'])} | {_n(adj['current_cases'])} vs {_n(adj['previous_cases'])} casos"
        f" (bruta, sem ajuste de atraso: {_pct(raw['rate'])}) | {adj['window']} | {src} |",
        f"| Taxa de mortalidade | {_pct(m['rate'])} | {_n(m['deaths'])} óbitos / {_n(m['denominator'])} com desfecho"
        f" ({_pct(m['open_share'])} dos casos em aberto) | {m['window']} | {src} |",
        f"| Internações com passagem por UTI | {_pct(u['rate'])} | {_n(u['icu'])} / {_n(u['denominator'])} | {u['window']} | {src} |",
        f"| Casos vacinados (COVID-19) | {_pct(v['rate'])} | {_n(v['vaccinated'])} / {_n(v['denominator'])}"
        f" ({_pct(v['valid_response_share'])} de respostas válidas) | {v['window']} | {src} |",
        "",
        "## Gráficos",
    ]
    for key in ("daily", "monthly"):
        lines.append(f"![{key}]({Path(charts[key]).name})" if key in charts else f"_Gráfico {key} indisponível._")
    lines += ["", "## Contexto das notícias"]
    if commentary:
        for c in commentary:
            lines.append(f"- {c['text']} ({'; '.join(f'[fonte]({u})' for u in c['news_refs'])})")
    else:
        lines.append("_Sem comentários: " + ("notícias indisponíveis na execução._" if news["status"] != "ok"
                                              else "nenhum comentário passou pelos guardrails._"))
    if news["items"]:
        lines += ["", "Notícias consultadas:"] + [
            f"- [{i['id'][1:]}] {i['published']} · {i['source']} · [{i['title']}]({i['url']})"
            for i in news["items"]
        ]
    lines += [
        "",
        "## Metodologia e limitações",
        f"- **Atraso de notificação:** as janelas ajustadas terminam {LAG_DAYS} dias antes da data de referência; "
        "os últimos dias estão subnotificados (área laranja no gráfico diário).",
        "- **Casos:** todos os registros, datados pelo início dos sintomas (DT_SIN_PRI).",
        "- **Mortalidade:** óbitos por SRAG sobre casos com desfecho cura ou óbito; óbito por outras causas e casos sem desfecho ficam fora.",
        "- **UTI:** a base não traz capacidade de leitos; o indicador é a proporção de internados que passaram por UTI, não ocupação.",
        "- **Vacinação:** só há casos de SRAG, não a população; há viés de seleção e não é cobertura vacinal.",
        "- **Privacidade:** o LLM recebeu somente agregados; data de nascimento, idade, município, UF e unidade foram descartados na ingestão.",
    ]
    lines += [f"- **Aviso:** {n}" for n in notes]
    lines += [
        "",
        "## Auditoria",
        f"- run_id: `{run_id}` · modelo: `{model}`",
        f"- dataset: {', '.join(manifest['sources'])} (ingerido em {manifest['ingested_at']}, "
        f"{manifest['rows']} linhas, sha256 `{manifest['clean_sha256'][:16]}…`)",
        f"- sha256 do log de auditoria: `{log_sha256}`",
        f"- chamadas de tool: `{json.dumps(call_ids)}`",
    ]
    return "\n".join(lines) + "\n"
