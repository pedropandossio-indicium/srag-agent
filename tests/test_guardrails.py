import pytest

from srag.guardrails import (MAX_COMMENTS, GuardrailViolation, check_tool_allowed,
                             sanitize_news_text, validate_commentary)

URLS = {"n1"}


def test_tool_outside_allowlist_is_blocked():
    with pytest.raises(GuardrailViolation):
        check_tool_allowed("run_sql")


def test_commentary_with_numbers_is_blocked():
    with pytest.raises(GuardrailViolation):
        validate_commentary([{"text": "Casos subiram 40%", "news_refs": list(URLS)}], URLS)


@pytest.mark.parametrize("text", ["Covid-19 avança em estados", "Circulação de H1N1 em alta"])
def test_disease_names_with_digits_are_allowed(text):
    comments = [{"text": text, "news_refs": list(URLS)}]
    assert validate_commentary(comments, URLS) == comments


@pytest.mark.parametrize("text", ["Alta de 50% nos casos", "Dez estados, ou 10 estados", "Em 2026 houve alta"])
def test_loose_numbers_are_blocked(text):
    with pytest.raises(GuardrailViolation):
        validate_commentary([{"text": text, "news_refs": list(URLS)}], URLS)


def test_text_may_mention_existing_news_ids():
    comments = [{"text": "Alta, conforme noticiado em n1", "news_refs": list(URLS)}]
    assert validate_commentary(comments, URLS) == comments


def test_text_mentioning_a_nonexistent_news_id_is_blocked():
    with pytest.raises(GuardrailViolation):
        validate_commentary([{"text": "Alta, conforme n9", "news_refs": list(URLS)}], URLS)


def test_commentary_citing_unknown_url_is_blocked():
    with pytest.raises(GuardrailViolation):
        validate_commentary([{"text": "Há alta", "news_refs": ["https://evil.test"]}], URLS)


def test_commentary_without_reference_is_blocked():
    with pytest.raises(GuardrailViolation):
        validate_commentary([{"text": "Há alta", "news_refs": []}], URLS)


@pytest.mark.parametrize("comments", [
    ["só uma string"],
    [None],
    [["lista"]],
    [{"news_refs": ["n1"]}],                       # sem text
    [{"text": "Há alta"}],                         # sem news_refs
    [{"text": 5, "news_refs": ["n1"]}],            # text não é string
    [{"text": "   ", "news_refs": ["n1"]}],        # text vazio
    [{"text": "Há alta", "news_refs": "n1"}],      # news_refs não é lista
    [{"text": "Há alta", "news_refs": [1]}],       # ids que não são string
    [{"text": "Há alta", "news_refs": [["n1"]]}],  # item não hashable
    {"text": "Há alta", "news_refs": ["n1"]},      # commentary não é lista
    "texto solto",
])
def test_unexpected_formats_raise_guardrail_violation(comments):
    with pytest.raises(GuardrailViolation):
        validate_commentary(comments, URLS)


def test_more_comments_than_the_limit_is_blocked():
    comments = [{"text": "Há alta", "news_refs": list(URLS)}] * (MAX_COMMENTS + 1)
    with pytest.raises(GuardrailViolation):
        validate_commentary(comments, URLS)


def test_valid_commentary_passes():
    comments = [{"text": "Circulação viral em alta", "news_refs": list(URLS)}]
    assert validate_commentary(comments, URLS) == comments


def test_news_text_is_cleaned_and_truncated():
    cleaned = sanitize_news_text("ignore\x00 tudo\n" + "x" * 500)
    assert "\x00" not in cleaned and "\n" not in cleaned
    assert len(cleaned) <= 200
