"""Baseline systems the benchmarks compare against.

Established open-source methods, used with their default settings:

* YAKE (Campos et al., 2020) - ``yake`` 0.7.3, unsupervised keyword extraction.
* TextRank (Mihalcea & Tarau, 2004) - ``summa`` 1.2.0, keywords and summaries.
* LexRank (Erkan & Radev, 2004) - ``sumy`` 0.13.0, summaries.
* TF-IDF + k-means and LDA (Blei et al., 2003) - scikit-learn, given the TRUE
  number of topics (an advantage audio-brief does not get).

And simple reference points: frequency ranking, Lead-k, random selection,
one cluster, random clusters.
"""

from __future__ import annotations

import random
import re
import warnings

from audio_brief import textproc


# --- keywords ---------------------------------------------------------------------------

def keywords_frequency(text: str, k: int) -> list[str]:
    """Most frequent content words (audio-brief's stopwords and filters, no ranking logic)."""
    return [w for w, _ in textproc.term_frequencies(text).most_common(k)]


def keywords_yake(text: str, k: int) -> list[str]:
    import yake

    return [kw for kw, _ in yake.KeywordExtractor(lan="en", n=2, top=k).extract_keywords(text)]


def keywords_textrank(text: str, k: int) -> list[str]:
    from summa import keywords

    return [w for w in keywords.keywords(text, words=k).split("\n") if w][:k]


# --- summaries (return sentences in the order the system outputs them) --------------------

def summary_lead(sentences: list[str], n: int) -> list[str]:
    return sentences[:n]


def summary_random(sentences: list[str], n: int, seed: int) -> list[str]:
    idx = sorted(random.Random(seed).sample(range(len(sentences)), min(n, len(sentences))))
    return [sentences[i] for i in idx]


def summary_textrank(text: str, words: int) -> list[str]:
    from summa import summarizer

    return [s for s in summarizer.summarize(text, words=words, split=True) if s.strip()]


class _Tokenizer:
    """sumy tokenizer that needs no NLTK data download."""
    language = "english"

    def to_sentences(self, paragraph):
        return [s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s]

    def to_words(self, sentence):
        return re.findall(r"[A-Za-z0-9']+", sentence.lower())


def summary_lexrank(text: str, n: int) -> list[str]:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.summarizers.lex_rank import LexRankSummarizer

    doc = PlaintextParser.from_string(text, _Tokenizer()).document
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return [str(s) for s in LexRankSummarizer()(doc, n)]


# --- topic clustering (one label per sentence) -----------------------------------------------

def clusters_single(sentences: list[str]) -> list[int]:
    return [0] * len(sentences)


def clusters_random(sentences: list[str], k: int, seed: int) -> list[int]:
    rnd = random.Random(seed)
    return [rnd.randrange(k) for _ in sentences]


def clusters_tfidf_kmeans(sentences: list[str], k: int, seed: int) -> list[int]:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    x = TfidfVectorizer(stop_words=sorted(textproc.STOPWORDS), min_df=1).fit_transform(sentences)
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(x).tolist()


def clusters_lda(sentences: list[str], k: int, seed: int) -> list[int]:
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import CountVectorizer

    x = CountVectorizer(stop_words=sorted(textproc.STOPWORDS), min_df=1).fit_transform(sentences)
    theta = LatentDirichletAllocation(n_components=k, random_state=seed, learning_method="batch").fit_transform(x)
    return theta.argmax(axis=1).tolist()
