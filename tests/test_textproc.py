"""Tests for audio_brief.textproc (pure offline NLP, no Whisper needed)."""

from collections import Counter

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


# --- min_char_length filter -------------------------------------------------

FRAGMENTY = (
    "Okay. The quarterly budget review covers marketing spend. Right. "
    "Marketing spend grew because of the new budget campaign. Yes. "
    "The budget review ends with next quarter marketing goals."
)


def test_summarize_filters_short_fragments_by_default():
    summary = textproc.summarize(FRAGMENTY, max_sentences=10, ratio=1.0)
    assert summary  # long sentences survive
    assert all(len(s) >= 20 for s in summary)
    assert "Okay." not in summary and "Right." not in summary and "Yes." not in summary


def test_summarize_min_char_length_zero_disables_filter():
    sents = textproc.sentences(FRAGMENTY)
    summary = textproc.summarize(FRAGMENTY, max_sentences=10, ratio=1.0, min_char_length=0)
    assert summary == sents  # every sentence is eligible (and distinct)


def test_summarize_min_char_length_boundary_is_inclusive():
    text = "Exactly twenty chars. Short one. This sentence is clearly long enough to stay."
    assert len("Exactly twenty chars") == 20 and len("Exactly twenty chars.") == 21
    summary = textproc.summarize(text, max_sentences=10, ratio=1.0, min_char_length=21)
    assert "Exactly twenty chars." in summary
    assert "Short one." not in summary
    summary = textproc.summarize(text, max_sentences=10, ratio=1.0, min_char_length=22)
    assert "Exactly twenty chars." not in summary


def test_summarize_returns_empty_when_everything_is_too_short():
    assert textproc.summarize("Yes. No. Okay. Sure.") == []


def test_summarize_rejects_negative_min_char_length():
    import pytest

    with pytest.raises(ValueError):
        textproc.summarize(FRAGMENTY, min_char_length=-1)


def test_summarize_preserves_order_after_filtering():
    sents = textproc.sentences(FRAGMENTY)
    summary = textproc.summarize(FRAGMENTY, max_sentences=2)
    assert summary == sorted(summary, key=sents.index)


def test_extract_summary_is_summarize():
    assert textproc.extract_summary is textproc.summarize
    assert textproc.extract_summary(FRAGMENTY, min_char_length=40) == textproc.summarize(
        FRAGMENTY, min_char_length=40
    )


def test_summarize_filter_does_not_shrink_summary_length():
    # 3 long sentences among 7 total: ratio applies to all 7, so all 3 long ones fit.
    long_only = textproc.summarize(FRAGMENTY, ratio=0.5, max_sentences=3)
    unfiltered = textproc.summarize(FRAGMENTY, ratio=0.5, max_sentences=3, min_char_length=0)
    assert len(long_only) == len(unfiltered) == 3


# --- topic_tree ----------------------------------------------------------------

# alpha: 3 sentences, beta: 2 sentences (1 together with alpha) -> P(alpha|beta) = 0.5
ALPHA_BETA = (
    "Alpha handles incoming requests. Alpha and beta share configuration files. "
    "Alpha restarts automatically overnight. Beta crashed yesterday evening."
)


def test_topic_tree_empty_and_tiny_text():
    assert textproc.topic_tree("") == []
    assert textproc.topic_tree("Just one sentence about nothing special.") == []


# window=0 (same-sentence co-occurrence) and keep=0 (no specificity filter) isolate
# the subsumption rule itself; tiny texts have no usable cohesion statistics.
RULE = {"window": 0, "keep": 0, "min_cooc": 1, "merge_lift": 0, "major_share": 0, "min_topic_units": 1}


def test_subsumption_threshold():
    # beta: 2 units, 1 of them near alpha -> P(alpha | beta) = 0.5
    df = Counter({"alpha": 3, "beta": 2})
    cooc = {"alpha": Counter({"beta": 1}), "beta": Counter({"alpha": 1})}
    node = textproc._subsumption_tree("topic", ["alpha", "beta"], Counter({"topic": 9, **df}), cooc, 0.6, 6, 3)
    assert [c.term for c in node.children] == ["alpha", "beta"]  # both directly under the topic
    node = textproc._subsumption_tree("topic", ["alpha", "beta"], Counter({"topic": 9, **df}), cooc, 0.5, 6, 3)
    assert [(c.term, [g.term for g in c.children]) for c in node.children] == [("alpha", ["beta"])]


def test_subsumption_picks_most_specific_parent():
    # "release" always appears near both "project" (broad) and "deploy" (narrow)
    df = Counter({"topic": 9, "project": 6, "deploy": 4, "release": 2})
    cooc = {"deploy": Counter({"project": 4}), "release": Counter({"project": 2, "deploy": 2}),
            "project": Counter({"deploy": 4, "release": 2})}
    node = textproc._subsumption_tree("topic", ["project", "deploy", "release"], df, cooc, 0.7, 6, 4)
    (project,) = node.children
    (deploy,) = project.children
    assert (project.term, deploy.term, [c.term for c in deploy.children]) == ("project", "deploy", ["release"])


def test_louvain_finds_two_communities():
    a = ["a1", "a2", "a3", "a4"]
    b = ["b1", "b2", "b3", "b4"]
    edges = {(x, y): 1.0 for group in (a, b) for i, x in enumerate(group) for y in group[i + 1:]}
    edges[("a1", "b1")] = 0.1  # weak bridge
    assert sorted(textproc.louvain(a + b, edges)) == [a, b]
    assert textproc.louvain(a + b, edges) == textproc.louvain(a + b, edges)  # deterministic
    assert textproc.louvain(["x", "y"], {}) == [["x"], ["y"]]  # isolated nodes stay alone


def test_topic_count_follows_the_text_not_the_cap():
    from tests.conftest import CONVERSATION_TOPICS, make_conversation

    for names in (("trip", "rent", "gym"), tuple(CONVERSATION_TOPICS)):
        c = make_conversation(2000, topics={k: CONVERSATION_TOPICS[k] for k in names})
        roots = textproc.topic_tree(c.text, units=textproc.analysis_units(c.text, c.segments))
        assert len(roots) == len(names)


def test_small_communities_are_not_topics():
    from tests.conftest import make_conversation

    c = make_conversation(2000)
    units = textproc.analysis_units(c.text, c.segments)
    assert len(textproc.topic_tree(c.text, units=units, major_share=0.3)) < len(textproc.topic_tree(c.text, units=units))


def test_topic_tree_window_links_neighbouring_sentences():
    # One content word per sentence: alpha and beta never share a sentence,
    # but always follow each other.
    text = " ".join(["We have the alpha.", "Then we have the beta."] * 3)
    same = textproc.topic_tree(text, min_char_length=0, **RULE)
    assert [(r.term, r.children) for r in same] == [("alpha", []), ("beta", [])]
    (root,) = textproc.topic_tree(text, min_char_length=0, window=1, keep=0)
    assert (root.term, [c.term for c in root.children]) == ("alpha", ["beta"])


def test_topic_tree_uses_phrases_as_nodes():
    from tests.conftest import SAMPLE_MEETING

    terms = {n.term for r in textproc.topic_tree(SAMPLE_MEETING) for n in [r, *r.children]}
    assert {"bank api", "data pipeline", "customer feedback"} <= terms
    assert not {"bank", "api", "data", "pipeline"} & terms  # absorbed into the phrases


def test_topic_tree_filters_generic_words():
    from tests.conftest import make_conversation

    c = make_conversation(2000)
    units = textproc.analysis_units(c.text, c.segments)
    terms = {w for r in textproc.topic_tree(c.text, units=units) for w in r.term.split()}
    generic = {"needs", "really", "great", "ana", "bruno", "carla", "diego", "monday", "friday", "list"}
    assert not terms & generic
    assert len(textproc.topic_tree(c.text, units=units, keep=0)) > 0  # filter is what removes them


def test_topic_tree_ignores_short_fragments():
    text = "Budget talk. Budget talk. Budget talk. The quarterly budget review starts now."
    assert textproc.topic_tree(text, **RULE) == []  # only one sentence >= 20 chars mentions budget
    assert [r.term for r in textproc.topic_tree(text, min_char_length=0, **RULE)][0] == "budget"


def test_chat_interjections_are_stopwords():
    freqs = textproc.term_frequencies("lol haha omg kkkk rsrs jajaja hmm budget")
    assert list(freqs) == ["budget"]


# --- extract_keywords: phrases ----------------------------------------------------

def _kw(text, n=50):
    return dict(textproc.extract_keywords(text, n=n))


def test_keyword_phrases_never_cross_sentences():
    text = "The rollout ends. Budget starts later. The rollout ends. Budget starts later."
    kws = _kw(text)
    assert "ends budget" not in kws  # adjacent only across the "." boundary
    assert "rollout ends" in kws and "budget starts" in kws


def test_keyword_phrases_never_skip_stopwords():
    text = "We book the hotel today. Please book the hotel soon."
    assert "book hotel" not in _kw(text)


def test_keyword_phrases_need_to_recur():
    kws = _kw("The payment integration is blocked. Nothing else matters here.")
    assert not any(" " in k for k in kws)


def test_keyword_counts_are_real_occurrences():
    from tests.conftest import SAMPLE_MEETING

    kws = _kw(SAMPLE_MEETING)
    assert kws["bank api"] == SAMPLE_MEETING.lower().count("bank api") == 4  # not doubled
    assert kws["data pipeline"] == 4


def test_keyword_word_dropped_when_one_phrase_covers_it():
    from tests.conftest import SAMPLE_MEETING

    kws = _kw(SAMPLE_MEETING)
    assert "bank" not in kws and "api" not in kws  # always part of "bank api"
    assert "onboarding" in kws  # never part of a recurring phrase


def test_keyword_word_kept_when_spread_over_phrases():
    from tests.conftest import make_group_chat

    kws = _kw(make_group_chat(400))
    assert "match" in kws  # "football match", "last match", "match tickets": none dominates


def test_keyword_phrase_chains_collapse():
    text = "The striker scored twice today. Again the striker scored twice. Our striker scored twice."
    phrases = [k for k in _kw(text) if " " in k]
    assert phrases == ["striker scored"]  # not also "scored twice"


def test_keyword_distinct_phrases_sharing_a_word_are_kept():
    text = ("Customer feedback arrived early. Customer feedback looks positive. "
            "The feedback form broke. The feedback form needs fixing.")
    kws = _kw(text)
    assert kws["customer feedback"] == 2 and kws["feedback form"] == 2


def test_keyword_ties_keep_first_mention_order():
    kws = textproc.extract_keywords("Zebra runs. Apple falls. Mango grows.", n=3)
    assert [k for k, _ in kws] == ["zebra", "runs", "apple"]


def test_meeting_keywords_are_real_topics():
    from tests.conftest import SAMPLE_MEETING

    top = [k for k, _ in textproc.extract_keywords(SAMPLE_MEETING, n=7)]
    assert {"bank api", "data pipeline", "release date", "mobile app", "customer feedback"} <= set(top)


def test_sample_keywords_have_no_cross_sentence_pairs():
    from tests.conftest import SAMPLE_EN

    kws = _kw(SAMPLE_EN)
    assert "meetings extracts" not in kws and "maps tool" not in kws


# --- mind map clustering -------------------------------------------------------------

def _labels(text, **kw):
    sents = textproc.sentences(text)
    return [textproc.cluster_label(c, sents) for c in textproc.build_mindmap(text, **kw)]


def test_mindmap_has_no_duplicate_branches_for_long_chats():
    from tests.conftest import make_group_chat

    for n in (400, 2000, 10000):
        labels = _labels(make_group_chat(n))
        assert len(labels) == len(set(labels)), n


def test_mindmap_branch_count_does_not_grow_with_length():
    # Branches must track topics, not length (the old scorer went 63 -> 295 -> 730).
    from tests.conftest import make_group_chat

    counts = [len(textproc.cluster_sentences(textproc.sentences(make_group_chat(n)), min_char_length=20))
              for n in (400, 2000, 10000)]
    assert counts[0] == counts[1] == counts[2] <= 32  # 8 topics x 4 distinct messages


def test_mindmap_clusters_are_topic_pure():
    from tests.conftest import GROUP_CHAT_TOPICS, make_group_chat

    topic_of = {s.lower(): k for k, v in GROUP_CHAT_TOPICS.items() for s in v}
    sents = textproc.sentences(make_group_chat(2000))
    weights = textproc.term_specificity(sents)  # as build_mindmap does
    for cl in textproc.cluster_sentences(sents, threshold=0.3, min_char_length=20, weights=weights):
        topics = {topic_of.get(sents[i].rstrip(".").lower()) for i in cl.members}
        assert len(topics) == 1


def test_mindmap_groups_meeting_sentences_by_topic():
    from tests.conftest import SAMPLE_MEETING

    a = textproc.analyze(SAMPLE_MEETING)
    branches = {g.label: [a.units[i] for c in g.clusters for i in c.members] for g in a.mindmap}
    (feedback,) = [v for v in branches.values() if any("Customer feedback" in s for s in v)]
    assert sum("customer feedback" in s.lower() for s in feedback) == 3  # every one of them
    (bank,) = [v for k, v in branches.items() if k.startswith("bank api")]
    # The other two "bank API" sentences are also about the app / the data pipeline.
    assert len(bank) >= 2 and all("bank API" in s for s in bank)


def test_mindmap_groups_subtopics_under_topics():
    from tests.conftest import CONVERSATION_TOPICS, make_conversation

    c = make_conversation(2000)
    a = textproc.analyze(c.text, c.segments)
    assert len(a.clusters) > len(a.mindmap)  # sub-topics were grouped
    assert any(len(g.clusters) > 1 for g in a.mindmap)
    topical = [g for g in a.mindmap if not any(cl.misc for cl in g.clusters)]
    assert len(topical) <= len(CONVERSATION_TOPICS) + 2


def test_mindmap_drops_fragments_unless_disabled():
    text = "The quarterly budget review starts now. Budget talk. The budget review ends today."

    def members(**kw):
        sents = textproc.sentences(text)
        return {sents[i] for c in textproc.cluster_sentences(sents, **kw) for i in c.members}

    assert "Budget talk." not in members(min_char_length=20)
    assert "Budget talk." in members(min_char_length=0)
    assert "Budget talk." not in {s for c in textproc.build_mindmap(text) for s in
                                  [textproc.sentences(text)[i] for i in c.members]}


def test_content_terms_filter():
    assert textproc.content_terms("The 2 API's lol and Whisper's bank, Bank!") == ["bank", "bank"]


def test_keywords_keep_the_main_subject_of_a_single_topic_text():
    # The subject ("volcano") is spread over the whole text, so it is not
    # "specific" to any part of it; it must still be the top keyword.
    parts = [
        "The volcano erupted with lava flows. Lava flows covered the slopes of the volcano. "
        "Hot lava flows reached the valley below the volcano.",
        "Ash clouds rose above the volcano. The ash clouds drifted over towns near the volcano. "
        "Airports closed because ash clouds surrounded the volcano.",
        "Scientists monitored the volcano with seismometers. Seismometers near the volcano "
        "recorded tremors. The tremors under the volcano grew stronger.",
        "Villagers left homes near the volcano. Evacuation buses took villagers away from the volcano. "
        "Shelters far from the volcano housed the villagers.",
    ]
    text = " ".join(parts)
    assert "volcano" in [k for k, _ in textproc.extract_keywords(text, n=5)]


def test_keyword_frequency_share_is_what_keeps_the_subject(monkeypatch):
    # Ranking = mentions x (share + (1 - share) x specificity / max). A subject
    # spread evenly over the text has specificity 0, so it outranks a fully
    # specific sub-topic word once mentioned more than 1/share (~8x) as often.
    units = ["volcano"] * 30 + ["lava", "ash", "tremors"] * 3
    spec = {"volcano": 0.0, "lava": 1.0, "ash": 1.0, "tremors": 1.0}
    ranked = [k for k, _ in textproc.extract_keywords("", n=4, units=units, specificity=spec)]
    assert ranked[0] == "volcano"  # 30 x 0.12 = 3.6 > 3 x 1.0
    monkeypatch.setattr(textproc, "KEYWORD_FREQUENCY_SHARE", 0.0)
    ranked = [k for k, _ in textproc.extract_keywords("", n=4, units=units, specificity=spec)]
    assert ranked[-1] == "volcano"  # pure specificity: the subject drops to the bottom


# --- analysis transparency ------------------------------------------------------------

STAGES = ["units", "specificity", "summary", "keywords", "topic tree", "timestamps", "mind map", "grouping"]


def test_analyze_records_stage_timings():
    from tests.conftest import SAMPLE_MEETING

    a = textproc.analyze(SAMPLE_MEETING)
    assert list(a.timings) == STAGES
    assert all(t >= 0 for t in a.timings.values())
    assert a.unit_kind == "sentences"


def test_analyze_reports_segment_units_for_unpunctuated_text():
    from tests.conftest import make_conversation

    c = make_conversation(400, punct=False)
    assert textproc.analyze(c.text, c.segments).unit_kind == "segments"
    assert textproc.analyze(c.text).unit_kind == "sentences"  # no segments: falls back


def test_timings_do_not_affect_equality():
    from tests.conftest import SAMPLE_MEETING

    a, b = textproc.analyze(SAMPLE_MEETING), textproc.analyze(SAMPLE_MEETING)
    a.timings["units"] += 1.0
    assert a == b


# --- linear cost safeguards ------------------------------------------------------------

def test_horizon_changes_nothing_below_it():
    from tests.conftest import make_conversation

    c = make_conversation(400)
    units = textproc.analysis_units(c.text, c.segments)
    weights = textproc.term_specificity(units)
    assert len(units) < 500
    with_h = textproc.cluster_sentences(units, threshold=0.3, min_char_length=20, weights=weights, horizon=500)
    without = textproc.cluster_sentences(units, threshold=0.3, min_char_length=20, weights=weights, horizon=None)
    assert [c.members for c in with_h] == [c.members for c in without]


def test_horizon_starts_a_new_cluster_after_a_long_gap():
    topic = "The budget review covers marketing spend."
    other = [f"Unrelated sentence number {i} about gardening tomatoes." for i in range(12)]
    sents = [topic, topic] + other + [topic]
    clusters = textproc.cluster_sentences(sents, horizon=4)
    home = [c for c in clusters if 0 in c.members][0]
    assert len(sents) - 1 not in home.members  # idle for > 4 units: not joined any more
    clusters = textproc.cluster_sentences(sents, horizon=None)
    assert len(sents) - 1 in [c for c in clusters if 0 in c.members][0].members


def test_topic_tree_vocabulary_is_capped():
    from tests.conftest import make_conversation

    c = make_conversation(2000)
    units = textproc.analysis_units(c.text, c.segments)
    small = textproc.topic_tree(c.text, units=units, max_vocab=10, max_children=50, max_depth=5)

    def terms(nodes):
        return [n.term for n in nodes] + [t for n in nodes for t in terms(n.children)]

    assert len(terms(small)) <= 10
