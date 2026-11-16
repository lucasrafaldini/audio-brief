"""Large multi-topic recordings (e.g. a group chat) become a tree of references.

Two synthetic chats with known topics (benchmarks/datasets.py):

* ``make_conversation``: realistic. Topic nouns change while generic words
  ("needs", "really"), names and weekdays are shared by every topic. These
  tests hold the pipeline to strict standards here.
* ``make_group_chat``: 32 fixed messages repeated verbatim. Some words bridge
  two topics ("landlord wants" / "client wants"), which is a known weak spot,
  so the thresholds there are lower and documented.
"""

import re

import pytest

from audio_brief import textproc, writers
from benchmarks import metrics
from tests.conftest import (
    CHAT_FILLER,
    CONVERSATION_TOPICS,
    GROUP_CHAT_TOPICS,
    make_conversation,
    make_group_chat,
)

CONV = metrics.distinctive_from_nouns(CONVERSATION_TOPICS)
VERBATIM = metrics.distinctive_from_sentences(GROUP_CHAT_TOPICS)


def _walk(nodes, depth=1):
    for node in nodes:
        yield node, depth
        yield from _walk(node.children, depth + 1)


def _terms(nodes):
    return [n.term for n, _ in _walk(nodes)]


def _analysis(n, seed=7, punct=True):
    c = make_conversation(n, seed=seed, punct=punct)
    return c, textproc.analyze(c.text, c.segments)


def _mindmap_quality(a, distinctive):
    branches = [[a.units[i] for c in g.clusters for i in c.members] for g in a.mindmap]
    return metrics.mindmap_quality(branches, [g.label for g in a.mindmap], distinctive)


def _topics_section(content):
    return content.split("## Topics\n\n", 1)[1].split("\n\n", 1)[0].splitlines()


# --- realistic conversation: strict ---------------------------------------------------

@pytest.mark.parametrize("seed", [1, 7, 42, 123])
@pytest.mark.parametrize("n_msgs", [2000, 8000])
def test_conversation_topics_become_clean_branches(seed, n_msgs):
    _, a = _analysis(n_msgs, seed)
    q = metrics.topic_tree_quality(a.topics, CONV)
    assert q["coverage"] == 1.0  # every topic has its own branch
    assert q["purity"] >= 0.9  # branches do not mix topics
    assert q["generic_roots"] <= 0.1  # "needs", names, weekdays are not topics
    assert q["fragmentation"] <= 1.5  # about one branch per topic


@pytest.mark.parametrize("seed", [1, 7, 42, 123])
def test_conversation_mindmap_groups_by_topic(seed):
    _, a = _analysis(2000, seed)
    mm = _mindmap_quality(a, CONV)
    assert mm["coverage"] == 1.0 and mm["purity"] >= 0.9
    assert mm["duplicate_labels"] == 0
    assert mm["branches"] <= len(CONVERSATION_TOPICS) + 4  # sub-topics are grouped


@pytest.mark.parametrize("seed", [1, 7, 42, 123])
def test_unpunctuated_conversation_uses_segments(seed):
    c, a = _analysis(2000, seed, punct=False)
    assert a.units == [" ".join(s["text"].split()) for s in c.segments]
    q = metrics.topic_tree_quality(a.topics, CONV)
    assert q["coverage"] == 1.0 and q["purity"] >= 0.9
    assert _mindmap_quality(a, CONV)["purity"] >= 0.85


def test_unpunctuated_without_segments_falls_back_to_chunks():
    c = make_conversation(2000, punct=False)
    assert textproc.analysis_units(c.text) == textproc.sentences(c.text)
    q = metrics.topic_tree_quality(textproc.topic_tree(c.text), CONV)
    assert q["coverage"] >= 0.75  # weaker: 30-word chunks mix messages


def test_tree_grows_with_the_number_of_topics():
    three = {k: CONVERSATION_TOPICS[k] for k in ("trip", "birthday", "rent")}
    small = make_conversation(2000, topics=three)
    large = make_conversation(2000)
    small_tree = textproc.analyze(small.text, small.segments).topics
    large_tree = textproc.analyze(large.text, large.segments).topics
    assert len(large_tree) > len(small_tree) >= 3
    assert len(_terms(large_tree)) > 1.5 * len(_terms(small_tree))


def test_no_duplicate_nodes_and_no_filler():
    _, a = _analysis(8000)
    terms = _terms(a.topics)
    assert len(terms) == len(set(terms))
    words = {w for t in terms for w in t.split()}
    assert not words & {"lol", "haha", "omg", "ana", "bruno", "monday", "friday", "needs", "really"}


def test_tree_respects_limits():
    _, a = _analysis(2000)
    tree = textproc.topic_tree("", units=a.units, specificity=a.specificity,
                               max_topics=3, max_children=2, max_depth=2)
    assert len(tree) == 3
    assert all(len(n.children) <= 2 for n, _ in _walk(tree))
    assert max(depth for _, depth in _walk(tree)) <= 2


def test_analysis_is_deterministic():
    c = make_conversation(2000)
    assert textproc.analyze(c.text, c.segments) == textproc.analyze(c.text, c.segments)


# --- timestamps -------------------------------------------------------------------------

def test_topic_timestamps_point_at_segments_that_mention_the_topic():
    c, a = _analysis(2000)
    starts = {s["start"]: set(textproc.content_terms(s["text"])) for s in c.segments}
    for node, _ in _walk(a.topics):
        assert node.times, node.term
        assert node.times == sorted(node.times)
        for t in node.times:
            assert set(node.term.split()) <= starts[t]
        # every segment that mentions the term is listed
        assert len(node.times) == sum(1 for terms in starts.values() if set(node.term.split()) <= terms)


def test_obsidian_topics_show_timestamps(tmp_path):
    c = make_conversation(400)
    writers.write_all(c.text, c.segments, {"source": "chat.wav"}, tmp_path)
    lines = _topics_section((tmp_path / "obsidian.md").read_text(encoding="utf-8"))
    stamp = re.compile(r"\(\d+\)( · \d\d:\d\d:\d\d){1,3}( …)?$")
    assert lines and all(stamp.search(line) for line in lines)


def test_obsidian_topics_without_segments_have_no_timestamps(tmp_path):
    c = make_conversation(400)
    path = writers.write_obsidian_note(tmp_path, c.text, [], [])
    assert all(line.endswith(")") for line in _topics_section(path.read_text(encoding="utf-8")))


# --- Obsidian vault -----------------------------------------------------------------------

def test_obsidian_note_renders_chat_as_nested_wikilinks(tmp_path):
    c = make_conversation(2000)
    path = writers.write_obsidian_note(tmp_path, c.text, [], [], segments=c.segments)
    lines = _topics_section(path.read_text(encoding="utf-8"))

    item = re.compile(r"^(?P<indent>(?:  )*)- \[\[(?P<term>[^\[\]|#^]+)\]\] \(\d+\)( · [\d:]+)*( …)?$")
    prev_level = -1
    for line in lines:
        m = item.match(line)
        assert m, f"not a wiki-link list item: {line!r}"
        level = len(m["indent"]) // 2
        assert level <= prev_level + 1  # children nest exactly one level deeper
        prev_level = level

    linked = {w for line in lines for w in item.match(line)["term"].split()}
    top_level = sum(1 for line in lines if not line.startswith(" "))
    assert len(CONVERSATION_TOPICS) <= top_level <= len(CONVERSATION_TOPICS) + 4
    for name, words in CONV.items():
        assert linked & words, f"topic {name!r} has no wiki-link in the tree"


def test_shared_topics_link_separate_recordings_in_the_vault(tmp_path):
    """Two chat recordings registered in one vault share links for shared topics."""
    t = CONVERSATION_TOPICS
    day1 = make_conversation(600, seed=1, topics={k: t[k] for k in ("trip", "rent", "gym")})
    day2 = make_conversation(600, seed=2, topics={k: t[k] for k in ("trip", "movies", "football")})
    links = {}
    for name, chat in (("day1", day1), ("day2", day2)):
        writers.write_all(chat.text, chat.segments, {"source": f"{name}.wav"}, tmp_path / name)
        content = (tmp_path / name / "obsidian.md").read_text(encoding="utf-8")
        found = re.findall(r"\[\[([^\]]+)\]\]", "\n".join(_topics_section(content)))
        links[name] = {w for term in found for w in term.split()}

    shared = links["day1"] & links["day2"]
    assert len(shared & CONV["trip"]) >= 3  # same notes => Obsidian backlinks
    assert not links["day1"] & (CONV["movies"] | CONV["football"])
    assert not links["day2"] & (CONV["rent"] | CONV["gym"])


def test_write_all_registers_large_chat_tree(tmp_path):
    c = make_conversation(2000)
    writers.write_all(c.text, c.segments, {"source": "chat.wav"}, tmp_path)
    content = (tmp_path / "obsidian.md").read_text(encoding="utf-8")
    assert len(_topics_section(content)) >= 40
    mindmap = (tmp_path / "mindmap.md").read_text(encoding="utf-8")
    assert mindmap.count("\n#### ") > 0  # topic > sub-topic > sentence


# --- verbatim chat: known weaker case -------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 7, 42, 123])
def test_verbatim_chat_topics_are_found(seed):
    tree = textproc.topic_tree(make_group_chat(2000, seed=seed))
    q = metrics.topic_tree_quality(tree, VERBATIM)
    assert q["coverage"] == 1.0
    # Words shared by two topics ("wants", "friday") can pull them into one
    # branch, so purity is lower here than on the realistic conversation.
    assert q["purity"] >= 0.4
    assert q["generic_roots"] == 0.0


def test_verbatim_chat_filler_never_becomes_a_node():
    terms = _terms(textproc.topic_tree(make_group_chat(10000, punct=False)))
    interjections = {w for msg in CHAT_FILLER for w in msg.split()} & {"lol", "haha", "omg"}
    assert interjections == {"lol", "haha", "omg"}  # the chat really contains them
    assert not interjections & {w for t in terms for w in t.split()}
