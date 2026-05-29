from app.analysis.schemas import PageSignals
from app.analysis.signals import heuristic_baseline, summarize_signals


def _page(**kw):
    base = dict(final_url="https://x.com/a", status_code=200, main_text="word " * 700)
    base.update(kw)
    return PageSignals(**base)


def test_blocking_ai_crawlers_tanks_score():
    blocked = heuristic_baseline(_page(blocks_ai_crawlers=True))
    open_ = heuristic_baseline(_page(blocks_ai_crawlers=False))
    assert blocked < open_


def test_structured_data_and_author_raise_score():
    poor = heuristic_baseline(_page(word_count=700))
    rich = heuristic_baseline(
        _page(word_count=700, has_jsonld=True, has_author=True, modified_date="2025-01-01")
    )
    assert rich > poor


def test_score_clamped_0_100():
    assert 0 <= heuristic_baseline(_page(blocks_ai_crawlers=True, js_dependent=True)) <= 100


def test_summary_mentions_key_factors():
    s = summarize_signals(_page(title="T", has_jsonld=True, schema_types=["Article"]))
    assert "JSON-LD" in s and "Article" in s and "T" in s
