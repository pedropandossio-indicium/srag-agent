"""Guardrails do agente. Cada violação levanta GuardrailViolation (e é auditada)."""
import re

ALLOWED_TOOLS = frozenset({"get_metrics", "generate_charts", "search_news"})
MAX_ITERATIONS = 6
MAX_NEWS_TEXT = 200
MAX_COMMENTS = 4

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_FIGURES = re.compile(r"(?<![\w-])\d")  # número solto; "Covid-19" e "H1N1" não contam
NEWS_ID = re.compile(r"\bn\d+\b")  # ids de notícia (n1, n2, ...) que o texto pode mencionar


class GuardrailViolation(Exception):
    pass


def check_tool_allowed(name: str) -> None:
    if name not in ALLOWED_TOOLS:
        raise GuardrailViolation(f"tool fora da allowlist: {name!r}")


def sanitize_news_text(text: str) -> str:
    """Notícia é dado não confiável: remove controles e limita o tamanho."""
    return _CONTROL_CHARS.sub(" ", text).strip()[:MAX_NEWS_TEXT]


def _read_comment(comment) -> tuple[str, list[str]]:
    """Garante {"text": str não vazia, "news_refs": lista de str}; a saída do LLM é não confiável."""
    valid = (
        isinstance(comment, dict)
        and isinstance(comment.get("text"), str) and comment["text"].strip()
        and isinstance(comment.get("news_refs"), list)
        and all(isinstance(ref, str) for ref in comment["news_refs"])
    )
    if not valid:
        raise GuardrailViolation(f"comentário fora do formato esperado: {comment!r}")
    return comment["text"], comment["news_refs"]


def validate_commentary(comments: list[dict], news_ids: set[str]) -> list[dict]:
    """O LLM não escreve números e toda afirmação cita o id de uma notícia recebida da tool."""
    if not isinstance(comments, list):
        raise GuardrailViolation(f"commentary deve ser uma lista, não {type(comments).__name__}")
    if len(comments) > MAX_COMMENTS:
        raise GuardrailViolation(f"mais de {MAX_COMMENTS} comentários")
    for comment in comments:
        text, refs = _read_comment(comment)
        if _FIGURES.search(text):
            raise GuardrailViolation(f"comentário com números: {text!r}")
        unknown = [ref for ref in NEWS_ID.findall(text) if ref not in news_ids]
        if unknown:
            raise GuardrailViolation(f"comentário menciona notícias inexistentes {unknown}: {text!r}")
        if not refs or not set(refs) <= news_ids:
            raise GuardrailViolation(f"comentário sem referência válida: {text!r}")
    return comments
