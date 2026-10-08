"""Tests for audio_brief.textproc (pure offline NLP, no Whisper needed)."""

from audio_brief import textproc


def test_sentences_splits_on_punctuation():
    sents = textproc.sentences("First sentence here. Second sentence here. Third one here too.")
    assert len(sents) == 3


def test_sentences_flushes_long_unpunctuated_text():
    text = " ".join(f"word{i}" for i in range(60))
    sents = textproc.sentences(text)
    assert len(sents) >= 2  # 30-word safety flush


def test_portuguese_stopwords_filtered():
    freqs = textproc.term_frequencies("o de e para com uma reunião importante sobre projeto")
    assert "o" not in freqs
    assert "de" not in freqs
    assert "reunião" in freqs
    assert "projeto" in freqs


def test_extract_keywords_returns_counts():
    from tests.conftest import SAMPLE_EN

    kws = textproc.extract_keywords(SAMPLE_EN, n=5)
    assert len(kws) == 5
    assert all(count >= 1 for _, count in kws)


def test_summarize_picks_subset_in_order():
    from tests.conftest import SAMPLE_EN

    sents = textproc.sentences(SAMPLE_EN)
    summary = textproc.summarize(SAMPLE_EN, max_sentences=3)
    assert 1 <= len(summary) <= 3
    # Order preserved (extractive summary reads naturally).
    assert summary == sorted(summary, key=sents.index)


def test_summarize_empty_text():
    assert textproc.summarize("") == []
    assert textproc.extract_keywords("") == []


def test_stats():
    from tests.conftest import SAMPLE_EN

    st = textproc.stats(SAMPLE_EN)
    assert st["words"] > 20
    assert st["sentences"] >= 5
    assert st["reading_minutes"] >= 1


def test_build_mindmap_caps_leaves():
    from tests.conftest import SAMPLE_EN

    clusters = textproc.build_mindmap(SAMPLE_EN)
    assert clusters
    assert all(len(c.members) <= 5 for c in clusters)
