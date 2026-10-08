"""Lightweight extractive summarization and keyword extraction.

No external LLMs or ML libraries are required: we use classic,
deterministic NLP (stopwords, TF scoring, sentence scoring) which works
offline. Good enough to turn a transcript into a useful summary,
keyword list and a simple mind map.
"""

from __future__ import annotations

import re
import string
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


def term_frequencies(text: str) -> Counter[str]:
    freqs: Counter[str] = Counter()
    for tok in tokenize(text):
        tok = _clean(tok)
        if len(tok) > 2 and tok not in STOPWORDS and not tok.isdigit() and not tok.endswith("'s"):
            freqs[tok] += 1
    return freqs


def extract_keywords(text: str, n: int = 15) -> list[tuple[str, int]]:
    freqs = term_frequencies(text)
    # Score bigrams too (they capture real concepts better than single words).
    toks = [t for t in tokenize(text) if _clean(t) not in STOPWORDS and len(_clean(t)) > 2]
    bigrams = Counter(
        f"{_clean(a)} {_clean(b)}"
        for a, b in zip(toks, toks[1:])
        if _clean(a) in freqs or _clean(b) in freqs
    )
    scored: Counter[str] = Counter()
    for word, count in freqs.items():
        scored[word] += count
    for bg, count in bigrams.items():
        scored[bg] += count * 2
    return scored.most_common(n)


def summarize(text: str, ratio: float = 0.25, max_sentences: int = 8) -> list[str]:
    """Extractive summary: pick the most informative, non-redundant sentences."""
    sents = sentences(text)
    n = max(1, min(len(sents), max(2, round(len(sents) * ratio)), max_sentences))
    if not sents:
        return []

    freqs = term_frequencies(text)
    if not freqs:
        total = 1.0
    else:
        total = sum(freqs.values())

    weighted: list[tuple[float, int]] = []
    for i, s in enumerate(sents):
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


def cluster_sentences(sents: list[str]) -> list[Cluster]:
    """Greedy topic clustering by vocabulary overlap (no ML deps)."""
    if not sents:
        return []
    target = max(2, min(6, round(len(sents) ** 0.5)))
    vectors = [Counter(_clean(t) for t in tokenize(s) if _clean(t) not in STOPWORDS) for s in sents]
    clusters: list[Cluster] = []
    for i, vec in enumerate(vectors):
        if not clusters:
            clusters.append(Cluster(members=[i], words=vec))
            continue
        best, best_score = -1, 0.0
        for ci, cl in enumerate(clusters):
            if not cl.words or not vec:
                score = 0.0
            else:
                inter = sum((cl.words & vec).values())
                score = inter / (sum(cl.words.values()) + sum(vec.values()) or 1)
            if score > best_score:
                best, best_score = ci, score
        if best >= 0 and (best_score > 0.15 or len(clusters) < target or len(clusters[best].members) == 1):
            clusters[best].members.append(i)
            clusters[best].words = clusters[best].words + vec
        else:
            clusters.append(Cluster(members=[i], words=vec))
    return clusters


def cluster_label(cluster: Cluster, sents: list[str]) -> str:
    top = [w for w, _ in cluster.words.most_common(3) if w]
    label = " / ".join(top[:3])
    if not label:
        label = sents[cluster.members[0]][:40]
    return label[:60]


def build_mindmap(text: str, max_leaves: int = 5) -> list[Cluster]:
    """Cluster sentences into a small hierarchy for the mind map."""
    sents = sentences(text)
    clusters = cluster_sentences(sents)
    # Keep only reasonably populated clusters; merge singletons into a Misc node.
    real = [c for c in clusters if len(c.members) > 1]
    misc = Cluster()
    for c in clusters:
        if len(c.members) <= 1:
            misc.members.extend(c.members)
            misc.words += c.words
    if misc.members:
        real.append(misc)
    for c in real:
        # Cap leaves per branch.
        c.members = c.members[:max_leaves]
    return real