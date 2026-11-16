"""Guardrails do agente. Cada violação levanta GuardrailViolation (e é auditada)."""
import re

ALLOWED_TOOLS = frozenset({"get_metrics", "generate_charts", "search_news"})
MAX_ITERATIONS = 6
MAX_NEWS_TEXT = 200
MAX_COMMENTS = 5

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_FIGURES = re.compile(r"(?<![\w-])\d")  # número solto; "Covid-19" e "H1N1" não contam


class GuardrailViolation(Exception):
    pass


def check_tool_allowed(name: str) -> None:
    if name not in ALLOWED_TOOLS:
        raise GuardrailViolation(f"tool fora da allowlist: {name!r}")


def sanitize_news_text(text: str) -> str:
    """Notícia é dado não confiável: remove controles e limita o tamanho."""
    return _CONTROL_CHARS.sub(" ", text).strip()[:MAX_NEWS_TEXT]


def validate_commentary(comments: list[dict], news_ids: set[str]) -> list[dict]:
    """O LLM não escreve números e toda afirmação cita o id de uma notícia recebida da tool."""
    if len(comments) > MAX_COMMENTS:
        raise GuardrailViolation(f"mais de {MAX_COMMENTS} comentários")
    for comment in comments:
        text, refs = comment.get("text", ""), comment.get("news_refs", [])
        if _FIGURES.search(text):
            raise GuardrailViolation(f"comentário com números: {text!r}")
        if not refs or not set(refs) <= news_ids:
            raise GuardrailViolation(f"comentário sem referência válida: {text!r}")
    return comments
