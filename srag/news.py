"""Busca de notícias sobre SRAG no Google News (RSS, sem chave).

Retorna só título, fonte, data e link. O snapshot fica em cache/ para que a
auditoria saiba exatamente quais notícias embasaram o relatório.
"""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from srag.guardrails import sanitize_news_text

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
FEED_URL = "https://news.google.com/rss/search?{query}"
MAX_ITEMS = 8
MAX_AGE_DAYS = 30


def _feed_url(query: str) -> str:
    params = {"q": f"{query} when:{MAX_AGE_DAYS}d", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
    return FEED_URL.format(query=urllib.parse.urlencode(params))


def _parse(xml_bytes: bytes) -> list[dict]:
    items, seen = [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    for node in ET.fromstring(xml_bytes).iter("item"):
        title = sanitize_news_text(node.findtext("title", ""))
        published = parsedate_to_datetime(node.findtext("pubDate"))
        if title in seen or published < cutoff:
            continue
        seen.add(title)
        items.append({
            "id": f"n{len(items) + 1}",
            "title": title,
            "source": sanitize_news_text(node.findtext("source", "")),
            "published": published.date().isoformat(),
            "url": node.findtext("link", ""),
        })
    return items[:MAX_ITEMS]


def search_news(query: str, run_id: str, cache_dir: Path = CACHE_DIR) -> dict:
    """Nunca levanta: falha vira status 'error', e o relatório avisa em vez de inventar."""
    try:
        with urllib.request.urlopen(_feed_url(query), timeout=15) as response:
            items = _parse(response.read())
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__, "items": []}

    cache_dir.mkdir(exist_ok=True)
    snapshot = {"query": query, "fetched_at": datetime.now(timezone.utc).isoformat(), "items": items}
    (cache_dir / f"news_{run_id}.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return {"status": "ok" if items else "empty", "items": items}
