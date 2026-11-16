"""Lightweight extractive summarization and keyword extraction.

No external LLMs or ML libraries are required: we use classic,
deterministic NLP (stopwords, TF scoring, sentence scoring) which works
offline. Good enough to turn a transcript into a useful summary,
keyword list and a simple mind map.
"""

from __future__ import annotations

import functools
import math
import re
import string
import time
from collections import Counter
from dataclasses import dataclass, field

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "for", "of",
    "to", "in", "on", "at", "by", "with", "from", "as", "into", "onto", "over",
    "under", "is", "are", "was", "were", "be", "been", "being", "am", "have",
    "has", "had", "do", "does", "did", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must", "i", "you", "he", "she", "it",
    "we", "they", "me", "him", "her", "us", "them", "my", "your", "his",
    "its", "our", "their", "that", "this", "these", "those", "what", "which",
    "who", "whom", "whose", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s",
    "t", "just", "don", "now", "like", "going", "okay", "yeah", "know",
    "right", "let", "get", "got", "one", "also", "well", "think", "say",
    "said", "thing", "things", "really", "actually", "way", "kind",
    "el", "la", "de", "que", "y", "en", "un", "una", "los", "las", "del",
    "con", "por", "para", "como", "más", "menos", "es", "son", "se", "lo",
    "le", "su", "al", "me", "te", "nos", "tan", "hay", "este", "esta",
    "estos", "estas", "ese", "esa", "esos", "esas", "mi", "tu", "pero",
    "und", "der", "die", "das", "ein", "eine", "ist", "sind", "mit", "auf",
    "für", "von", "ich", "du", "er", "sie", "es", "wir", "nicht", "zu", "den",
    "dem", "einem", "einer", "als", "auch", "bei", "dass", "eine", "kein",
    "le", "la", "les", "un", "une", "des", "est", "sont", "et", "ou", "dans",
    "pour", "avec", "sur", "ce", "cette", "ces", "pas", "que", "qui",
    # Portuguese
    "de", "do", "dos", "das", "em", "num", "numa", "nuns", "numas", "para",
    "pra", "pro", "com", "sem", "sob", "sobre", "entre", "até", "após",
    "antes", "durante", "contra", "segundo", "conforme", "mediante", "perante",
    "exceto", "salvo", "afora", "fora", "dentro", "através", "o", "os",
    "as", "ao", "aos", "à", "às", "pelo", "pelos", "pela", "pelas",
    "dum", "duma", "neste", "nesta", "nesse", "nessa", "nisso", "nele",
    "nela", "deles", "delas", "aqui", "aí", "ali", "lá", "cá", "onde",
    "quando", "quanto", "quantos", "qual", "quais", "quem", "cujo", "cuja",
    "e", "nem", "mas", "porém", "todavia", "contudo", "entretanto",
    "portanto", "logo", "pois", "porque", "porquanto", "embora", "apesar",
    "caso", "se", "senão", "ou", "ora", "quer", "já", "tão", "tanto",
    "muito", "pouco", "bastante", "demais", "mais", "menos", "todo",
    "toda", "todos", "todas", "algum", "alguma", "alguns", "algumas",
    "nenhum", "nenhuma", "outro", "outra", "outros", "outras", "mesmo",
    "mesma", "próprio", "tal", "tais", "cada", "qualquer", "quaisquer",
    "algo", "tudo", "nada", "alguém", "ninguém", "outrem", "si", "consigo",
    "eu", "tu", "você", "vocês", "nós", "eles", "elas", "mim", "ti",
    "lhe", "lhes", "nele", "nela", "dele", "dela", "meu", "minha",
    "teu", "tua", "nosso", "nossa", "vosso", "vossa", "desse", "dessa",
    "deste", "desta", "daquele", "daquela", "isto", "isso", "aquilo",
    "este", "esta", "esse", "essa", "aquele", "aquela", "foi", "são",
    "ser", "ter", "estar", "haver", "fazer", "dizer", "dar", "ver",
    "poder", "querer", "saber", "ficar", "ir", "vir", "há", "tem",
    "têm", "está", "estão", "estava", "eram", "foram", "será", "seria",
    "coisa", "coisas", "vez", "vezes", "ano", "anos", "dia", "dias",
    "gente", "pessoa", "pessoas", "tempo", "forma", "parte", "mundo",
    "vida", "casa", "trabalho", "governo", "país", "empresa", "grupo",
    "meio", "fim", "início", "lugar", "modo", "motivo", "jeito", "tipo",
    "né", "tá", "pra", "aí", "então", "ainda", "também", "sempre",
    "nunca", "jamais", "talvez", "apenas", "só", "somente", "inclusive",
    "até", "mesmo", "próprio", "cerca", "quase", "muita", "muitas",
    "pouca", "poucas", "vários", "várias", "ambos", "ambas", "tanto",
}

# Standard English function words and contractions missing above (NLTK list).
STOPWORDS |= {
    "myself", "ours", "ourselves", "yours", "yourself", "yourselves", "himself", "hers",
    "herself", "itself", "theirs", "themselves", "having", "doing", "because", "until",
    "while", "about", "against", "between", "through", "during", "before", "after",
    "above", "below", "down", "out", "off", "again", "further", "once", "here", "there",
    "you're", "you've", "you'll", "you'd", "she's", "it's", "that'll", "don't", "should've",
    "aren't", "couldn't", "didn't", "doesn't", "hadn't", "hasn't", "haven't", "isn't",
    "mightn't", "mustn't", "needn't", "shan't", "shouldn't", "wasn't", "weren't", "won't",
    "wouldn't", "can't", "i'm", "i've", "i'll", "i'd", "we're", "we've", "we'll", "they're",
    "they've", "they'll", "that's", "there's", "what's", "let's",
}

# Spanish function words (the README is trilingual; Portuguese overlap covers some).
STOPWORDS |= {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "al", "del", "y", "o",
    "pero", "sino", "que", "qué", "quien", "quién", "cual", "cuál", "cuando", "cuándo",
    "donde", "dónde", "como", "cómo", "porque", "por", "para", "con", "sin", "sobre",
    "entre", "hasta", "desde", "hacia", "según", "muy", "más", "menos", "también",
    "tampoco", "ya", "aún", "todavía", "siempre", "nunca", "aquí", "allí", "ahí", "así",
    "yo", "tú", "él", "ella", "ellos", "ellas", "nosotros", "nosotras", "vosotros",
    "usted", "ustedes", "me", "te", "se", "nos", "os", "le", "les", "mi", "mis", "tu",
    "tus", "su", "sus", "nuestro", "nuestra", "este", "esta", "estos", "estas", "ese",
    "esa", "esos", "esas", "esto", "eso", "aquel", "aquella", "uno", "otro", "otra",
    "otros", "otras", "todo", "toda", "todos", "todas", "nada", "algo", "alguien",
    "es", "son", "era", "eran", "fue", "fueron", "ser", "estar", "está", "están",
    "estaba", "hay", "había", "ha", "han", "he", "hemos", "tiene", "tienen", "tener",
    "hacer", "hace", "puede", "pueden", "bueno", "vale", "pues", "entonces", "sí", "mío",
}

# SMART stop list (571 words; Salton, SMART information retrieval system,
# Cornell), as redistributed in the MIT-licensed python-rake 1.5.0. It removes
# frequent content-light words ("first", "used", "however") that are not
# topics; adopting it raised keyword precision and topic purity on the dev
# split of benchmarks/ (see benchmarks/METHODOLOGY.md).
SMART_STOPWORDS = frozenset("""
a a's able about above according accordingly across actually after afterwards again against
ain't all allow allows almost alone along already also although always am among amongst an and
another any anybody anyhow anyone anything anyway anyways anywhere apart appear appreciate
appropriate are aren't around as aside ask asking associated at available away awfully b be
became because become becomes becoming been before beforehand behind being believe below beside
besides best better between beyond both brief but by c c'mon c's came can can't cannot cant
cause causes certain certainly changes clearly co com come comes concerning consequently
consider considering contain containing contains corresponding could couldn't course currently d
definitely described despite did didn't different do does doesn't doing don't done down
downwards during e each edu eg eight either else elsewhere enough entirely especially et etc
even ever every everybody everyone everything everywhere ex exactly example except f far few
fifth first five followed following follows for former formerly forth four from further
furthermore g get gets getting given gives go goes going gone got gotten greetings h had hadn't
happens hardly has hasn't have haven't having he he's hello help hence her here here's hereafter
hereby herein hereupon hers herself hi him himself his hither hopefully how howbeit however i
i'd i'll i'm i've ie if ignored immediate in inasmuch inc indeed indicate indicated indicates
inner insofar instead into inward is isn't it it'd it'll it's its itself j just k keep keeps
kept know known knows l last lately later latter latterly least less lest let let's like liked
likely little look looking looks ltd m mainly many may maybe me mean meanwhile merely might more
moreover most mostly much must my myself n name namely nd near nearly necessary need needs
neither never nevertheless new next nine no nobody non none noone nor normally not nothing novel
now nowhere o obviously of off often oh ok okay old on once one ones only onto or other others
otherwise ought our ours ourselves out outside over overall own p particular particularly per
perhaps placed please plus possible presumably probably provides q que quite qv r rather rd re
really reasonably regarding regardless regards relatively respectively right s said same saw say
saying says second secondly see seeing seem seemed seeming seems seen self selves sensible sent
serious seriously seven several shall she should shouldn't since six so some somebody somehow
someone something sometime sometimes somewhat somewhere soon sorry specified specify specifying
still sub such sup sure t t's take taken tell tends th than thank thanks thanx that that's thats
the their theirs them themselves then thence there there's thereafter thereby therefore therein
theres thereupon these they they'd they'll they're they've think third this thorough thoroughly
those though three through throughout thru thus to together too took toward towards tried tries
truly try trying twice two u un under unfortunately unless unlikely until unto up upon us use
used useful uses using usually uucp v value various very via viz vs w want wants was wasn't way
we we'd we'll we're we've welcome well went were weren't what what's whatever when whence
whenever where where's whereafter whereas whereby wherein whereupon wherever whether which while
whither who who's whoever whole whom whose why will willing wish with within without won't
wonder would wouldn't x y yes yet you you'd you'll you're you've your yours yourself yourselves
z zero
""".split())
STOPWORDS |= SMART_STOPWORDS

# Chat/voice-note interjections (en/pt/es) that carry no topic, so they never
# become keywords, mind-map branches or topic-tree nodes.
STOPWORDS |= {
    "lol", "lmao", "omg", "btw", "haha", "hahaha", "kkk", "kkkk", "rsrs",
    "jaja", "jajaja", "hmm", "hmmm", "uh", "um", "umm", "uhm", "yep", "nope", "wow",
}

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9À-ý']+", re.UNICODE)
_SENT_RE = re.compile(r"(?<=[.!?\u3002\uff61\n])\s+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.split(text) if p.strip()]
    out: list[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        # Chunk overlong buffers (weak/no punctuation, common in raw
        # Whisper output) into 30-word sentences.
        toks = buffer.split()
        while len(toks) > 30:
            out.append(" ".join(toks[:30]))
            toks = toks[30:]
        if toks:
            out.append(" ".join(toks))
        buffer = ""

    for part in parts:
        buffer = f"{buffer} {part}".strip()
        words = buffer.count(" ") + 1
        if buffer.endswith((".", "!", "?", "\u3002")) or words >= 30:
            flush()
    if buffer:
        flush()
    return out


def _clean(token: str) -> str:
    return token.strip(string.punctuation).lower()


def _is_content(term: str) -> bool:
    return len(term) > 2 and term not in STOPWORDS and not term.isdigit() and not term.endswith("'s")


@functools.lru_cache(maxsize=65536)
def _content_terms(text: str) -> tuple[str, ...]:
    return tuple(t for t in (_clean(tok) for tok in tokenize(text)) if _is_content(t))


def content_terms(text: str) -> list[str]:
    """Cleaned tokens that carry meaning (no stopwords, digits, short words, possessives).

    Cached per text: every analysis step looks at the same units.
    """
    return list(_content_terms(text))


def term_frequencies(text: str) -> Counter[str]:
    return Counter(content_terms(text))


def is_weakly_punctuated(text: str) -> bool:
    """True when the text has fewer than one sentence end per 30 words."""
    words = len(text.split())
    ends = len(re.findall(r"[.!?\u3002\uff61]", text))
    return words >= 60 and ends * 30 < words


def analysis_units(text: str, segments: list[dict] | None = None) -> list[str]:
    """The text units every analysis works on.

    Normally the sentences of ``text``. When the transcript is weakly
    punctuated (raw Whisper output often is), ``sentences`` can only cut
    30-word chunks that mix several utterances; Whisper's own segments are
    much better boundaries, so they are used instead when available.
    """
    if segments and is_weakly_punctuated(text):
        units = [" ".join(str(seg.get("text", "")).split()) for seg in segments]
        units = [u for u in units if u]
        if units:
            return units
    return sentences(text)


def term_specificity(units: list[str], window: int = 2, smoothing: float = 50.0,
                     min_mentions: int = 2) -> dict[str, float]:
    """How strongly each term predicts the words around it (lexical cohesion).

    A topic word ("lisbon") is surrounded by its topic for a while, so the
    words in the ``window`` units before and after it differ from the text as
    a whole; a generic word ("needs", a name, a weekday) shows up everywhere,
    so its surroundings look like the whole text. The score is the KL
    divergence (nats) between the two word distributions, with ``smoothing``
    pseudo-counts towards the global distribution so rare words are not
    over-rated. Terms mentioned in fewer than ``min_mentions`` units are left
    out (score 0 for callers).
    """
    bags = [set(content_terms(u)) for u in units]
    mentions = Counter(t for bag in bags for t in bag)
    around: dict[str, Counter[str]] = {}
    background: Counter[str] = Counter()
    for i, bag in enumerate(bags):
        if not bag:
            continue
        context: Counter[str] = Counter()
        for j in range(max(0, i - window), min(len(bags), i + window + 1)):
            if j != i:
                context.update(bags[j])
        background.update(context)
        for term in bag:
            if mentions[term] >= min_mentions:
                around.setdefault(term, Counter()).update(context)
    total = sum(background.values())
    scores: dict[str, float] = {}
    for term, ctx in around.items():
        n = sum(ctx.values())
        shrink = smoothing / (n + smoothing)
        kl, q_seen = 0.0, 0.0
        for word, count in ctx.items():
            q = background[word] / total
            p = (count + smoothing * q) / (n + smoothing)
            kl += p * math.log(p / q)
            q_seen += q
        # Every word never seen near `term` has p = shrink * q, so together they
        # add shrink * log(shrink) * (their share of the background): closed form,
        # keeping the cost proportional to the context, not to the vocabulary.
        if shrink > 0 and q_seen < 1.0:
            kl += shrink * math.log(shrink) * (1.0 - q_seen)
        scores[term] = kl
    return scores


@dataclass
class _Vocabulary:
    """Keyword candidates: words and two-word phrases with real counts."""
    counts: dict[str, int]        # chosen phrases + remaining words
    absorbed: dict[str, str]      # word -> chosen phrase that covers it
    dropped: set[str]             # words covered only by a skipped phrase fragment
    first: dict[str, int]         # first-mention position of every word/phrase
    length: int = 0               # total tokens (for relative positions)


def _vocabulary(units: list[str], min_phrase_count: int = 2) -> _Vocabulary:
    freqs = Counter(t for u in units for t in content_terms(u))
    pairs: Counter[str] = Counter()
    triples: Counter[str] = Counter()
    first: dict[str, int] = {}
    pos = 0
    for unit in units:
        toks = [_clean(t) for t in tokenize(unit)]
        for i, a in enumerate(toks):
            first.setdefault(a, pos + i)
            b = toks[i + 1] if i + 1 < len(toks) else None
            if b is None or a not in freqs or b not in freqs or a == b:
                continue
            pairs[f"{a} {b}"] += 1
            first.setdefault(f"{a} {b}", pos + i)
            if i + 2 < len(toks) and toks[i + 2] in freqs:
                triples[f"{a} {b} {toks[i + 2]}"] += 1
        pos += len(toks)

    recurring = {p: c for p, c in pairs.items() if c >= min_phrase_count}

    # A phrase "x y" only continues a chosen "a x" (via "a x y") or "y b" (via
    # "x y b"), so index chosen phrases by their last and first word.
    ends_with: dict[str, list[str]] = {}
    starts_with: dict[str, list[str]] = {}

    def extends(phrase: str, count: int) -> bool:
        x, y = phrase.split()
        return any(triples[f"{a.split()[0]} {x} {y}"] >= count / 2 for a in ends_with.get(x, ())) or \
               any(triples[f"{x} {y} {b.split()[1]}"] >= count / 2 for b in starts_with.get(y, ()))

    counts: dict[str, int] = {}
    for phrase, count in sorted(recurring.items(), key=lambda kv: (-kv[1], first[kv[0]])):
        if not extends(phrase, count):
            counts[phrase] = count
            a, b = phrase.split()
            ends_with.setdefault(b, []).append(phrase)
            starts_with.setdefault(a, []).append(phrase)
    chosen = dict(counts)
    by_word: dict[str, list[str]] = {}
    for phrase in recurring:
        for w in set(phrase.split()):
            by_word.setdefault(w, []).append(phrase)
    absorbed: dict[str, str] = {}
    dropped: set[str] = set()
    for word, count in freqs.items():
        covering = [p for p in by_word.get(word, ()) if recurring[p] >= 0.8 * count]
        if not covering:
            counts[word] = count
            continue
        kept = [p for p in covering if p in chosen]
        if kept:
            absorbed[word] = max(kept, key=lambda p: (chosen[p], -first[p]))
        else:
            dropped.add(word)
    return _Vocabulary(counts, absorbed, dropped, first, pos)


# Share of plain frequency in keyword ranking. Chosen on benchmarks/ as the
# largest value that keeps generic-word rejection at 100% on the synthetic
# group chat; it lifts the article-subject MRR on real Wikipedia articles from
# 0.44 to 0.75 (held-out half: 0.45 -> 0.73). See benchmarks/METHODOLOGY.md.
KEYWORD_FREQUENCY_SHARE = 0.12

# Terms first mentioned in the opening KEYWORD_INTRO_SHARE of the text get up
# to (1 + KEYWORD_INTRO_BOOST) x their score, fading linearly to 1 at the end
# of that zone: speakers usually introduce their subject early. On the dev
# split: article-subject MRR 0.78 -> 0.84, topical precision 0.856 -> 0.840.
KEYWORD_INTRO_SHARE = 0.05
KEYWORD_INTRO_BOOST = 1.0


def _weight(term: str, specificity: dict[str, float]) -> float:
    """Specificity of a word, or of a phrase's least specific word."""
    return min(specificity.get(w, 0.0) for w in term.split())


def extract_keywords(text: str, n: int = 15, min_phrase_count: int = 2,
                     units: list[str] | None = None,
                     specificity: dict[str, float] | None = None) -> list[tuple[str, int]]:
    """Top topical terms and two-word phrases with their real occurrence counts.

    A phrase is two *adjacent* content words inside one unit (never across a
    sentence break or a skipped stopword) that occur at least
    ``min_phrase_count`` times. Phrases that only extend an already chosen one
    ("scored twice" inside "striker scored twice") are skipped, and a single
    word is dropped when one recurring phrase accounts for >= 80% of its uses
    ("bank" when it is almost always "bank api").

    Ranking is by mentions x (0.12 + 0.88 x specificity / max specificity),
    boosted for terms first mentioned in the opening 5% (KEYWORD_INTRO_*).
    Specificity (``term_specificity``) sinks frequent but generic words
    ("needs", names, weekdays); the 0.12 frequency share keeps a recording's
    main subject, which is spread over the whole text and therefore not
    "specific", near the top (see KEYWORD_FREQUENCY_SHARE). The count shown
    is always the real number of mentions. Ties keep first-mention order.
    ``units``/``specificity`` can be passed to reuse a shared analysis.
    """
    units = sentences(text) if units is None else units
    specificity = term_specificity(units) if specificity is None else specificity
    vocab = _vocabulary(units, min_phrase_count)
    end = len(vocab.first)
    top = max(specificity.values(), default=0.0) or 1.0
    share = KEYWORD_FREQUENCY_SHARE
    length = max(1, vocab.length)

    def score(term: str, count: int) -> float:
        base = count * (share + (1 - share) * _weight(term, specificity) / top)
        where = vocab.first.get(term, length) / length
        return base * (1 + KEYWORD_INTRO_BOOST * max(0.0, 1 - where / KEYWORD_INTRO_SHARE))

    ranked = sorted(vocab.counts.items(), key=lambda kv: (
        -score(*kv), -kv[1], vocab.first.get(kv[0], end)))
    return ranked[:n]


def summarize(text: str, ratio: float = 0.25, max_sentences: int = 8,
              min_char_length: int = 20, units: list[str] | None = None) -> list[str]:
    """Extractive summary: pick the most informative, non-redundant sentences.

    Sentences shorter than ``min_char_length`` characters (e.g. "Okay.",
    "Right, so.") are never selected; pass ``0`` to disable the filter.
    They still count towards term frequencies, so topic weighting is
    unaffected. Returns ``[]`` if no sentence is long enough. ``units``
    replaces ``sentences(text)`` (see ``analysis_units``).
    """
    if min_char_length < 0:
        raise ValueError(f"min_char_length must be >= 0, got {min_char_length}")
    sents = sentences(text) if units is None else units
    candidates = [i for i, s in enumerate(sents) if len(s) >= min_char_length]
    if not candidates:
        return []
    # Length is based on all sentences (as before the filter); the filter only
    # changes which sentences are eligible, capped by how many there are.
    n = max(1, min(len(candidates), max(2, round(len(sents) * ratio)), max_sentences))

    freqs = term_frequencies(text)
    if not freqs:
        total = 1.0
    else:
        total = sum(freqs.values())

    weighted: list[tuple[float, int]] = []
    for i in candidates:
        s = sents[i]
        toks = [_clean(t) for t in tokenize(s)]
        score = sum(freqs.get(t, 0) for t in toks) / (total or 1)
        # Position bias: opening and closing sentences are often important.
        position_bias = 1.0
        if i < 2:
            position_bias = 1.5
        elif i >= len(sents) - 2:
            position_bias = 1.2
        # Penalize overly long sentences slightly.
        length_penalty = 1.0 if len(toks) < 60 else 0.8
        weighted.append((score * position_bias * length_penalty, i))

    chosen: list[int] = []
    pool = sorted(weighted, key=lambda x: x[0], reverse=True)
    for _, idx in pool:
        if idx in chosen:
            continue
        # Skip if too similar to something already chosen.
        if any(_overlap(sents[idx], sents[c]) > 0.7 for c in chosen):
            continue
        chosen.append(idx)
        if len(chosen) >= n:
            break
    chosen.sort()
    return [sents[i] for i in chosen]


# Alias matching the naming of ``extract_keywords``.
extract_summary = summarize


def _overlap(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb))


def stats(text: str) -> dict[str, int]:
    """Basic document statistics for reports."""
    words = len(tokenize(text))
    n_sentences = len(sentences(text))
    return {
        "words": words,
        "sentences": n_sentences,
        "reading_minutes": max(1, round(words / 200)) if words else 0,
    }


@dataclass
class Cluster:
    members: list[int] = field(default_factory=list)
    words: Counter[str] = field(default_factory=Counter)
    misc: bool = False  # the leftovers branch (single sentences)


def cluster_sentences(sents: list[str], threshold: float = 0.2,
                      min_char_length: int = 0,
                      weights: dict[str, float] | None = None,
                      horizon: int | None = 500) -> list[Cluster]:
    """Greedy single-pass topic clustering by cosine similarity (no ML deps).

    Each sentence joins the cluster whose word profile is most similar
    (cosine >= ``threshold``) or starts a new one. Cosine does not shrink as a
    cluster grows, so a long recording keeps one cluster per topic instead of
    splitting it into duplicates, and an inverted word index keeps the cost
    roughly linear. Sentences shorter than ``min_char_length`` or without
    content words (e.g. "lol ok.") are left out. ``weights`` (e.g.
    ``term_specificity``) scale each word, so topic words decide the grouping
    instead of frequent generic ones; words without a weight are ignored.

    A cluster that has not received a sentence for ``horizon`` units stops
    accepting new ones (a topic raised again much later starts a new
    cluster; ``group_mindmap`` puts both under the same topic). This keeps
    the number of live clusters, and so the cost, bounded: total time grows
    linearly. Texts shorter than ``horizon`` units are unaffected; ``None``
    disables it.
    """
    clusters: list[Cluster] = []
    norm2: list[float] = []  # squared norm of each cluster's word vector
    index: dict[str, set[int]] = {}  # word -> live clusters containing it
    last_used: list[int] = []
    for i, sent in enumerate(sents):
        if horizon and i and i % horizon == 0:  # retire idle clusters from the index
            idle = {ci for ci, last in enumerate(last_used) if i - last > horizon}
            if idle:
                for word in list(index):
                    index[word] -= idle
                    if not index[word]:
                        del index[word]
        if len(sent) < min_char_length:
            continue
        counts = Counter(content_terms(sent))
        if weights is None:
            vec = dict(counts)
        else:
            vec = {w: c * weights[w] for w, c in counts.items() if weights.get(w, 0.0) > 0}
        if not vec:
            continue
        vnorm = math.sqrt(sum(v * v for v in vec.values()))
        # Candidates come from the heaviest words only. A cluster sharing none
        # of them can reach at most |v_rest| / |v| (Cauchy-Schwarz); we stop
        # adding words once that bound is below the threshold, so skipping such
        # clusters never changes the outcome, while common words that sit in
        # hundreds of clusters are not scanned.
        rest2 = vnorm * vnorm
        candidates: set[int] = set()
        for word, v in sorted(vec.items(), key=lambda kv: -kv[1]):
            if rest2 < (threshold * vnorm) ** 2:
                break
            candidates.update(index.get(word, ()))
            rest2 -= v * v
        best, best_score = -1, 0.0
        for ci in sorted(candidates):
            words = clusters[ci].words
            dot = sum(v * words.get(w, 0.0) for w, v in vec.items())
            score = dot / (vnorm * math.sqrt(norm2[ci]))
            if score > best_score:
                best, best_score = ci, score
        if best < 0 or best_score < threshold:
            clusters.append(Cluster())
            norm2.append(0.0)
            last_used.append(i)
            best = len(clusters) - 1
        last_used[best] = i
        cluster = clusters[best]
        cluster.members.append(i)
        for word, v in vec.items():
            old = cluster.words[word]
            cluster.words[word] = old + v
            norm2[best] += (old + v) ** 2 - old ** 2
            index.setdefault(word, set()).add(best)
    return clusters


def cluster_label(cluster: Cluster, sents: list[str]) -> str:
    top = [w for w, _ in cluster.words.most_common(3) if w]
    label = " / ".join(top[:3])
    if not label:
        label = sents[cluster.members[0]][:40]
    return label[:60]


def build_mindmap(text: str, max_leaves: int = 5, min_char_length: int = 20,
                  units: list[str] | None = None,
                  specificity: dict[str, float] | None = None,
                  threshold: float = 0.3) -> list[Cluster]:
    """Cluster sentences (or ``units``) into sub-topics for the mind map.

    Words are weighted by ``term_specificity`` (cosine ``threshold`` 0.3 was
    chosen on benchmarks/: best worst-case purity across all corpora). Branches follow the order
    topics first come up; single sentences go to a final ``misc`` branch.
    Members index into ``units`` (default ``sentences(text)``).
    """
    sents = sentences(text) if units is None else units
    specificity = term_specificity(sents) if specificity is None else specificity
    clusters = cluster_sentences(sents, threshold=threshold, min_char_length=min_char_length,
                                 weights=specificity)
    # Keep only reasonably populated clusters; merge singletons into a Misc node.
    real = [c for c in clusters if len(c.members) > 1]
    misc = Cluster(misc=True)
    for c in clusters:
        if len(c.members) <= 1:
            misc.members.extend(c.members)
            misc.words.update(c.words)  # weights are positive; `+=` re-filtered every time
    if misc.members:
        real.append(misc)
    for c in real:
        # Cap leaves per branch.
        c.members = c.members[:max_leaves]
    return real


@dataclass
class TopicNode:
    term: str  # a word or a two-word phrase ("bank api")
    mentions: int  # number of units (sentences/segments) that mention ``term``
    children: list[TopicNode] = field(default_factory=list)
    times: list[float] = field(default_factory=list)  # segment starts (see attach_timestamps)


def topic_tree(text: str, max_topics: int = 16, max_children: int = 6, max_depth: int = 3,
               min_char_length: int = 20, min_mentions: int = 2,
               threshold: float = 0.7, units: list[str] | None = None,
               specificity: dict[str, float] | None = None, window: int = 1,
               keep: float = 0.5, resolution: float = 1.0, major_share: float = 0.05,
               max_vocab: int = 400, min_cooc: int = 3, merge_lift: float = 1.5,
               min_topic_units: int = 3) -> list[TopicNode]:
    """Hierarchy of the recording's topics as words and phrases.

    1. Vocabulary: keyword words/phrases (``extract_keywords`` rules) that are
       mentioned in >= ``min_mentions`` units and are *topical*: specificity
       >= ``keep`` x the 90th-percentile specificity (``keep=0`` keeps all);
       at most ``max_vocab`` of them (the strongest), which bounds the cost.
    2. Two terms co-occur when they appear within ``window`` units of each
       other (``window=0``: same unit).
    3. Topics: communities of the term graph weighted by positive PMI of
       co-occurrence (pairs seen together >= ``min_cooc`` times, so chance
       pairs of rare words do not link topics), found with Louvain modularity
       optimisation (Blondel et al. 2008; ``resolution`` 1 = standard
       modularity). The number of topics comes from the text, not from
       ``max_topics``.
    4. Significance: a topic must cover >= ``major_share`` of the units that
       mention a topical term (and >= ``min_topic_units``); smaller ones are
       fragments or generic words and are left out.
    4b. Sub-topics: communities whose nearby units overlap >= ``merge_lift``
       times more than chance (average linkage) belong to one subject; the
       largest names it and the others become its sub-topics (children).
    5. Inside a topic, the most characteristic term (mentions x specificity)
       is the root; a term goes under a more mentioned term of the same topic
       when >= ``threshold`` of its units have it nearby (subsumption,
       Sanderson & Croft 1999; the most specific such term wins); other terms
       are children of the root.

    Topics are ranked by how many units they cover; units shorter than
    ``min_char_length`` are ignored.
    """
    units = sentences(text) if units is None else units
    specificity = term_specificity(units) if specificity is None else specificity
    vocab = _vocabulary(units)

    bags: list[set[str]] = []
    for unit in units:
        bag: set[str] = set()
        if len(unit) >= min_char_length:
            for term in content_terms(unit):
                if term not in vocab.dropped:
                    bag.add(vocab.absorbed.get(term, term))
        bags.append(bag)

    mentions = Counter(t for bag in bags for t in bag)
    score = {t: _weight(t, specificity) for t in mentions}
    ranked_scores = sorted((v for v in score.values() if v > 0), reverse=True)
    ref = ranked_scores[len(ranked_scores) // 10] if ranked_scores else 0.0
    topical = [t for t, c in mentions.items()
               if c >= min_mentions and (keep <= 0 or (score[t] > 0 and score[t] >= keep * ref))]
    topical = set(sorted(topical, key=lambda t: (-mentions[t] * score.get(t, 0.0), t))[:max_vocab])

    df: Counter[str] = Counter()
    cooc: dict[str, Counter[str]] = {t: Counter() for t in topical}
    where: dict[str, list[int]] = {}
    for i, bag in enumerate(bags):
        here = bag & topical
        if not here:
            continue
        near = set().union(*bags[max(0, i - window): i + window + 1]) & topical
        for y in here:
            df[y] += 1
            where.setdefault(y, []).append(i)
            for x in near:
                if x != y:
                    cooc[y][x] += 1
    if not df:
        return []

    # 3. Topics = Louvain communities of the positive-PMI co-occurrence graph.
    total = sum(sum(c.values()) for c in cooc.values())
    row = {t: sum(c.values()) for t, c in cooc.items()}
    edges: dict[tuple[str, str], float] = {}
    for y, c in cooc.items():
        for x, n in c.items():
            if y < x and n >= min_cooc:
                pmi = math.log(n * total / (row[y] * row[x]))
                if pmi > 0:
                    edges[(y, x)] = pmi
    nodes = sorted(df, key=lambda t: (-df[t], t))
    communities = louvain(nodes, edges, resolution)

    # 4. Significance.
    topical_units = len({i for t in nodes for i in where[t]})
    floor = max(min_topic_units, major_share * topical_units)
    reach = [{i for t in com for i in where[t]} for com in communities]
    kept = [(r, com) for r, com in zip(reach, communities) if len(r) >= floor]

    # 4b. Sub-topics of one subject occur in the same stretch of text: merge
    # communities (average linkage) whose nearby units overlap >= merge_lift
    # times more than chance; merged communities become sub-topics.
    n_all = max(1, len(units))
    groups = [[j] for j in range(len(kept))]
    if merge_lift > 0 and len(kept) > 1:
        near_sets = [{k for i in r for k in range(i - window, i + window + 1)} for r, _ in kept]

        def lift_ab(a: int, b: int) -> float:
            rb = kept[b][0]
            hits = sum(1 for i in rb if i in near_sets[a])
            return (hits / len(rb)) / (len(near_sets[a]) / n_all) if near_sets[a] else 0.0

        pair = {(a, b): (lift_ab(a, b) + lift_ab(b, a)) / 2 for a in range(len(kept)) for b in range(a + 1, len(kept))}
        while len(groups) > 1:
            best, best_val = None, merge_lift
            for gi in range(len(groups)):
                for gj in range(gi + 1, len(groups)):
                    vals = [pair[(min(a, b), max(a, b))] for a in groups[gi] for b in groups[gj]]
                    val = sum(vals) / len(vals)
                    if val >= best_val:
                        best, best_val = (gi, gj), val
            if best is None:
                break
            gi, gj = best
            groups[gi] += groups.pop(gj)
    topics = []
    for g in groups:
        covered = set().union(*(kept[j][0] for j in g))
        coms = [kept[j][1] for j in sorted(g, key=lambda j: (-len(kept[j][0]), j))]
        topics.append((len(covered), coms))
    topics.sort(key=lambda rc: (-rc[0], min(min(c) for c in rc[1])))

    # 5. Hierarchy inside each topic; the label is ranked like a keyword, so a
    # subject spread over the whole text can still name its topic.
    top = max(score.values(), default=0.0) or 1.0
    share = KEYWORD_FREQUENCY_SHARE

    def characteristic(t: str) -> tuple:
        return (-df[t] * (share + (1 - share) * score.get(t, 0.0) / top), -df[t], t)

    def community_tree(com: list[str], depth: int) -> TopicNode:
        members = sorted(com, key=characteristic)
        return _subsumption_tree(members[0], members[1:], df, cooc, threshold,
                                 max_children, max_depth, depth)

    out: list[TopicNode] = []
    for _, coms in topics[:max_topics]:
        if len(coms) == 1:
            out.append(community_tree(coms[0], 1))
            continue
        # several communities: the main one names the topic, the others are sub-topics
        main = community_tree(coms[0], 1)
        subs = [community_tree(c, 2) for c in coms[1:]]
        main.children = (subs + main.children)[:max_children]
        out.append(main)
    return out


def louvain(nodes: list[str], edges: dict[tuple[str, str], float],
            resolution: float = 1.0) -> list[list[str]]:
    """Louvain community detection (Blondel et al. 2008), deterministic.

    Repeats local moving (each node joins the neighbouring community with the
    largest modularity gain, nodes visited in the given order, ties broken by
    community name) and aggregation until nothing moves. Isolated nodes stay
    alone. ``edges`` maps (a, b) with a < b to a positive weight.
    """
    adj: dict[str, dict[str, float]] = {n: {} for n in nodes}
    for (a, b), w in edges.items():
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w
    members: dict[str, list[str]] = {n: [n] for n in nodes}
    level = list(nodes)
    while True:
        m2 = sum(sum(v.values()) for v in adj.values())
        if m2 == 0:
            break
        deg = {n: sum(adj[n].values()) for n in level}
        comm = {n: n for n in level}
        tot = dict(deg)
        improved = moved = True
        improved = False
        while moved:
            moved = False
            for n in level:
                current = comm[n]
                tot[current] -= deg[n]
                links: dict[str, float] = {}
                for nb, w in adj[n].items():
                    if nb != n:
                        links[comm[nb]] = links.get(comm[nb], 0.0) + w
                best = current
                gain = links.get(current, 0.0) - resolution * tot[current] * deg[n] / m2
                for c in sorted(links):
                    g = links[c] - resolution * tot[c] * deg[n] / m2
                    if g > gain + 1e-12:
                        best, gain = c, g
                tot[best] += deg[n]
                if best != current:
                    comm[n] = best
                    moved = improved = True
        if not improved:
            break
        grouped: dict[str, list[str]] = {}
        for n in level:
            grouped.setdefault(comm[n], []).extend(members[n])
        new_adj: dict[str, dict[str, float]] = {c: {} for c in grouped}
        for n in level:
            for nb, w in adj[n].items():
                a, b = comm[n], comm[nb]
                new_adj[a][b] = new_adj[a].get(b, 0.0) + w
        adj, members, level = new_adj, grouped, list(grouped)
    return [sorted(m) for m in members.values()]


def _subsumption_tree(root: str, rest: list[str], df: Counter[str], cooc: dict[str, Counter[str]],
                      threshold: float, max_children: int, max_depth: int, depth: int = 1) -> TopicNode:
    """Tree of one topic: ``y`` goes under a more mentioned term ``x`` when
    >= ``threshold`` of y's units have ``x`` nearby (the most specific such
    ``x`` wins); terms without such a parent hang directly under ``root``."""
    order = sorted(rest, key=lambda t: (-df[t], t))
    rank = {t: i for i, t in enumerate(order)}
    parent: dict[str, str] = {}
    for y in order:
        subsumers = [x for x, c in cooc.get(y, {}).items()
                     if x in rank and rank[x] < rank[y] and c / df[y] >= threshold]
        parent[y] = max(subsumers, key=rank.__getitem__) if subsumers else root
    kids: dict[str, list[str]] = {t: [] for t in [root, *order]}
    for y in order:
        kids[parent[y]].append(y)
    size: dict[str, int] = {}
    for y in sorted(order, key=lambda t: -_depth(t, parent)):
        size[y] = 1 + sum(size[k] for k in kids[y])

    def build(term: str, d: int) -> TopicNode:
        below = sorted(kids[term], key=lambda k: (-size.get(k, 1), -df[k], k))
        below = below[:max_children] if d < max_depth else []
        return TopicNode(term, df[term], [build(k, d + 1) for k in below])

    return build(root, depth)


def _depth(term: str, parent: dict[str, str]) -> int:
    d = 0
    while term in parent:
        term = parent[term]
        d += 1
    return d


def attach_timestamps(nodes: list[TopicNode], segments: list[dict] | None) -> list[TopicNode]:
    """Fill ``node.times`` with the start of every segment mentioning the node's term.

    A phrase node counts when all of its words appear in the segment. Returns
    ``nodes`` (modified in place) for chaining.
    """
    where: dict[str, set[int]] = {}
    starts: list[float] = []
    for i, seg in enumerate(segments or []):
        starts.append(float(seg.get("start", 0.0)))
        for term in content_terms(str(seg.get("text", ""))):
            where.setdefault(term, set()).add(i)

    def visit(node: TopicNode) -> None:
        hits = set.intersection(*(where.get(w, set()) for w in node.term.split()))
        node.times = sorted(starts[i] for i in hits)
        for child in node.children:
            visit(child)

    for node in nodes:
        visit(node)
    return nodes


# --- mind map grouping ----------------------------------------------------------------------

@dataclass
class MindmapGroup:
    label: str
    clusters: list[Cluster]


def group_mindmap(clusters: list[Cluster], tree: list[TopicNode],
                  sents: list[str]) -> list[MindmapGroup]:
    """Group sub-topic clusters under the topic tree's top-level topics.

    A cluster joins the topic whose subtree words weigh most in it; clusters
    that match no topic (and the leftovers branch) stay top-level. Groups keep
    the order topics first come up; the leftovers branch stays last.
    """
    topic_words = [{w for node in _walk_topics([root]) for w in node.term.split()} for root in tree]
    by_topic: dict[int, list[Cluster]] = {}
    alone: list[Cluster] = []
    for cl in clusters:
        scores = [sum(cl.words.get(w, 0) for w in words) for words in topic_words]
        if cl.misc or not scores or max(scores) <= 0:
            alone.append(cl)
        else:
            by_topic.setdefault(scores.index(max(scores)), []).append(cl)

    groups: list[tuple[int, MindmapGroup]] = []
    for ti, cls in by_topic.items():
        root = tree[ti]
        label = " / ".join([root.term] + [c.term for c in root.children[:2]])
        groups.append((min(cl.members[0] for cl in cls), MindmapGroup(label[:60], cls)))
    for cl in alone:
        if not cl.misc and cl.members:
            groups.append((cl.members[0], MindmapGroup(cluster_label(cl, sents), [cl])))
    out = [g for _, g in sorted(groups, key=lambda x: x[0])]
    out += [MindmapGroup(cluster_label(cl, sents), [cl]) for cl in alone if cl.misc and cl.members]
    return out


def _walk_topics(nodes: list[TopicNode]):
    for node in nodes:
        yield node
        yield from _walk_topics(node.children)


# --- one-pass analysis ----------------------------------------------------------------------

@dataclass
class Analysis:
    units: list[str]
    specificity: dict[str, float]
    summary: list[str]
    keywords: list[tuple[str, int]]
    topics: list[TopicNode]
    clusters: list[Cluster]
    mindmap: list[MindmapGroup]
    unit_kind: str = "sentences"  # or "segments" (weakly punctuated transcript)
    # seconds per stage; not part of equality (timings differ run to run)
    timings: dict[str, float] = field(default_factory=dict, compare=False)


def analyze(text: str, segments: list[dict] | None = None, summary_n: int = 8,
            keywords_n: int = 15, min_char_length: int = 20, max_topics: int = 16) -> Analysis:
    """Everything the writers need, computed once and sharing one specificity table.

    ``Analysis.timings`` records how long each stage took (seconds).
    """
    timings: dict[str, float] = {}

    def timed(stage, fn, *args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        timings[stage] = time.perf_counter() - start
        return result

    units = timed("units", analysis_units, text, segments)
    spec = timed("specificity", term_specificity, units)
    summary = timed("summary", summarize, text, max_sentences=summary_n,
                    min_char_length=min_char_length, units=units)
    keywords = timed("keywords", extract_keywords, text, n=keywords_n, units=units, specificity=spec)
    topics = timed("topic tree", topic_tree, text, max_topics=max_topics,
                   min_char_length=min_char_length, units=units, specificity=spec)
    timed("timestamps", attach_timestamps, topics, segments)
    clusters = timed("mind map", build_mindmap, text, min_char_length=min_char_length,
                     units=units, specificity=spec)
    groups = timed("grouping", group_mindmap, clusters, topics, units)
    kind = "segments" if segments and is_weakly_punctuated(text) and units != sentences(text) else "sentences"
    return Analysis(units, spec, summary, keywords, topics, clusters, groups, kind, timings)
