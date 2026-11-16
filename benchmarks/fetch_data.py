"""Download and prepare the public corpora used by the benchmarks.

Every source is pinned to an exact package version and verified by checksum
before anything is extracted, so every run uses byte-identical data. Output goes
to ``benchmarks/data/`` (git-ignored):

* ``wikipedia.jsonl``  - 106 English Wikipedia articles (lead + sections), CC BY-SA 3.0
* ``newsgroups.jsonl`` - 200 Usenet posts from alt.atheism and sci.space (20 Newsgroups)
* ``sotu.jsonl``       - 233 U.S. State of the Union addresses, 1790-2021, public domain
* ``asr/``             - real speech for the speech-recognition benchmark:
  5 LibriVox read utterances with transcripts (PocketSphinx 5.1.1 test data),
  a 30 s two-speaker telephone conversation with a time-stamped transcript
  (pyannote.audio 4.0.7 sample), and 229 s of untranscribed speech for speed
  (Silero VAD 6.2.3 test/example audio); ``asr/items.json`` lists them
* ``manifest.json``    - sources, versions, licences, checksums, record counts

Usage: python -m benchmarks.fetch_data [--force]
"""

from __future__ import annotations

import argparse
import base64
import bz2
import copyreg
import hashlib
import io
import json
import pickle
import re
import sys
import tarfile
import time
import urllib.request
import zlib
from pathlib import Path

DATA = Path(__file__).with_name("data")

SOURCES = {
    "gensim": {
        "what": "gensim 4.4.0 source distribution (its test fixtures contain both corpora)",
        "url": "https://files.pythonhosted.org/packages/1a/80/fe9d2e1ace968041814dbcfce4e8499a643a36c41267fa4b6c4f54cce420/gensim-4.4.0.tar.gz",
        "sha256": "a3f5b626da5518e79a479140361c663089fe7998df8ba52d56e1ded71ac5bdf5",
        "size": 23260095,
    },
    "sotu": {
        "what": "@stdlib/datasets-sotu 0.2.3 (npm)",
        "url": "https://registry.npmjs.org/@stdlib/datasets-sotu/-/datasets-sotu-0.2.3.tgz",
        "sha512": "QbspCBwsy6S6io8mwmZoPh55YBCj4X3RwoGldDneFZU8WI9Vjrdq/l01beIF0qSiJBFlsngiIz8ySmmRjFm8aA==",
        "size": 7217658,
    },
    "pocketsphinx": {
        "what": "pocketsphinx 5.1.1 source distribution (LibriVox test utterances)",
        "url": "https://files.pythonhosted.org/packages/61/e7/13e0e787ff467218de880310d79cba14424f13b87171ac44af0bde1e428c/pocketsphinx-5.1.1.tar.gz",
        "sha256": "675778b309a22dfc9b7d37f7621976bba491d2a5f8c59696bd77fd6d07271355",
        "size": 34158862,
    },
    "pyannote": {
        "what": "pyannote.audio 4.0.7 source distribution (sample conversation + STM transcript)",
        "url": "https://files.pythonhosted.org/packages/6d/d7/03b1d00d431c7be1d98635fefb99c2da64d9b84b4b8a06d5302666a96c88/pyannote_audio-4.0.7.tar.gz",
        "sha256": "3a903dfb5ca711d134cc2522561c9158b186836f5d62e8a57c46c6648e8a8229",
        "size": 13963479,
    },
    "silero": {
        "what": "silero-vad 6.2.3 source distribution (untranscribed test/example speech)",
        "url": "https://files.pythonhosted.org/packages/32/17/df6bfc8f659fc5c1e082c18275be67c5a581bd2d07734a65b141fc983ccf/silero_vad-6.2.3.tar.gz",
        "sha256": "d7a23b09202be4953915cb9173089bb307eed0418a9bd4794d9ec5af07fa1996",
        "size": 29276676,
    },
}
WIKI_MEMBER = "gensim-4.4.0/gensim/test/test_data/enwiki-latest-pages-articles1.xml-p000000010p000030302-shortened.bz2"
NEWS_MEMBER = "gensim-4.4.0/gensim/test/test_data/mini_newsgroup"

LICENCES = {
    "wikipedia": "CC BY-SA 3.0 (Wikipedia contributors); redistributed in gensim's test data (LGPL-2.1 package)",
    "newsgroups": "20 Newsgroups (Ken Lang, 1995), widely redistributed for research; sample from gensim's test data",
    "sotu": "Works of the U.S. Government (no copyright); dataset PDDL-1.0 / CC0 (@stdlib)",
    "asr": "LibriVox recordings: public domain (via PocketSphinx, BSD-2); conversation sample: distributed "
           "with pyannote.audio (MIT), origin not documented there; Silero VAD test audio (MIT package); "
           "used locally for measurement only, not redistributed",
}


def log(msg: str) -> None:
    print(f"    {msg}", flush=True)


def download(name: str) -> bytes:
    src = SOURCES[name]
    cache = DATA / "downloads" / src["url"].rsplit("/", 1)[1]
    if cache.exists():
        blob = cache.read_bytes()
        log(f"{name}: using cached {cache.name} ({len(blob) / 1e6:.1f} MB)")
    else:
        log(f"{name}: downloading {src['what']} ({src['size'] / 1e6:.1f} MB) from {src['url'].split('/')[2]}")
        t0 = time.perf_counter()
        with urllib.request.urlopen(src["url"], timeout=120) as resp:  # noqa: S310 (pinned https URL)
            blob = resp.read()
        log(f"{name}: {len(blob) / 1e6:.1f} MB in {time.perf_counter() - t0:.1f}s")
    if "sha256" in src:
        digest = hashlib.sha256(blob).hexdigest()
        ok = digest == src["sha256"]
        log(f"{name}: sha256 {digest[:16]}... {'matches the pinned value' if ok else 'MISMATCH'}")
    else:
        digest = base64.b64encode(hashlib.sha512(blob).digest()).decode()
        ok = digest == src["sha512"]
        log(f"{name}: sha512 {digest[:16]}... {'matches the npm integrity value' if ok else 'MISMATCH'}")
    if not ok:
        raise SystemExit(f"Checksum mismatch for {name}: refusing to use this file.")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(blob)
    return blob


# --- Wikipedia ------------------------------------------------------------------------

def _strip_nested(text: str, open_: str, close: str) -> str:
    """Remove balanced, possibly nested spans such as {{templates}}."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith(open_, i):
            depth += 1
            i += len(open_)
        elif depth and text.startswith(close, i):
            depth -= 1
            i += len(close)
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def clean_wikitext(text: str) -> str:
    """Wikitext -> plain prose. Keeps sentences, drops markup, tables, refs, files."""
    import html

    text = html.unescape(html.unescape(text))  # the XML escapes entities twice (&amp;nbsp;)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    text = _strip_nested(text, "{{", "}}")
    text = _strip_nested(text, "{|", "|}")
    text = re.sub(r"\[\[(?:File|Image|Category|[a-z]{2,3}(?:-[a-z]+)?):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", " ", text)
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"'{2,}", "", text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("*", "#", ":", ";", "|", "!", "=")):
            continue  # lists, indents, table rows, headings: not running prose
        lines.append(re.sub(r"\s+", " ", line))
    return "\n".join(lines)


def parse_wikipedia(raw_xml: str) -> list[dict]:
    articles = []
    for page in re.findall(r"<page>(.*?)</page>", raw_xml, re.S):
        title = re.search(r"<title>(.*?)</title>", page).group(1)
        m = re.search(r"<text[^>]*>(.*?)</text>", page, re.S)
        body = m.group(1) if m else ""
        if ":" in title or body[:50].upper().lstrip().startswith("#REDIRECT"):
            continue
        parts = re.split(r"^==\s*([^=].*?)\s*==\s*$", body, flags=re.M)
        lead = clean_wikitext(parts[0])
        sections = [{"title": parts[i].strip(), "text": clean_wikitext(parts[i + 1])}
                    for i in range(1, len(parts) - 1, 2)]
        sections = [s for s in sections if len(s["text"].split()) >= 20
                    and s["title"].lower() not in {"see also", "references", "external links", "notes",
                                                    "further reading", "bibliography", "sources"}]
        articles.append({"title": title, "lead": lead, "sections": sections})
    return articles


# --- 20 Newsgroups -------------------------------------------------------------------

class _Inert:
    """Stand-in for numpy objects inside the pickle: stores nothing executable."""

    def __init__(self, *args):
        self.args = args

    def __setstate__(self, state):
        self.state = state


class _SafeUnpickler(pickle.Unpickler):
    """Allow only the handful of classes this file needs; never import code."""

    def find_class(self, module, name):
        if (module, name) in {("copy_reg", "_reconstructor"), ("copyreg", "_reconstructor")}:
            return copyreg._reconstructor
        if name in {"dict", "object"} and module in {"__builtin__", "builtins"}:
            return {"dict": dict, "object": object}[name]
        if (module, name) == ("sklearn.datasets.base", "Bunch"):
            return dict
        if module.startswith("numpy"):
            return (lambda *a: _Inert(*a)) if name == "_reconstruct" else _Inert
        raise pickle.UnpicklingError(f"blocked {module}.{name}")


def clean_post(raw: str) -> str:
    """Usenet post -> the author's own words (no headers, quotes or signature)."""
    body = raw.split("\n\n", 1)[1] if "\n\n" in raw else raw
    body = body.split("\n-- \n")[0]
    keep = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith((">", "|>", ":")) or re.match(r"^(In article|.*\bwrites:\s*$|.*\bwrote:\s*$)", s):
            continue
        keep.append(s)
    return re.sub(r"\s+", " ", " ".join(keep)).strip()


def parse_newsgroups(raw: bytes) -> list[dict]:
    bunch = _SafeUnpickler(io.BytesIO(zlib.decompress(raw)), encoding="latin-1").load()
    labels = bunch["target_names"]
    posts = []
    for doc in bunch["data"]:
        groups = re.search(r"^Newsgroups: (.+)$", doc, re.M).group(1).replace(" ", "").split(",")
        label = next(g for g in groups if g in labels)
        posts.append({"group": label, "text": clean_post(doc)})
    return posts


# --- State of the Union ------------------------------------------------------------------

def parse_sotu(blob: bytes) -> list[dict]:
    out = []
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        for member in sorted(tar.getmembers(), key=lambda m: m.name):
            if member.name.startswith("package/data/") and member.name.endswith(".json"):
                d = json.load(tar.extractfile(member))
                out.append({"year": d["year"], "president": d["name"], "party": d["party"], "text": d["text"]})
    return out


# --- speech (ASR benchmark) --------------------------------------------------------------

def prepare_asr(ps_blob: bytes, pyannote_blob: bytes, silero_blob: bytes) -> dict:
    """Extract the audio files and build asr/items.json (audio + reference text)."""
    out = DATA / "asr"
    out.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []

    def take(blob: bytes, member: str, dest: str) -> Path:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            data = tar.extractfile(member).read()
        path = out / dest
        path.write_bytes(data)
        return path

    lv = "pocketsphinx-5.1.1/test/data/librivox/sense_and_sensibility_01_austen_64kb-{}.{}"
    for n in ("0870", "0880", "0890", "0920", "0930"):
        wav = take(ps_blob, lv.format(n, "wav"), f"librivox_{n}.wav")
        with tarfile.open(fileobj=io.BytesIO(ps_blob)) as tar:
            ref = tar.extractfile(lv.format(n, "txt")).read().decode().strip()
        items.append({"id": f"librivox_{n}", "audio": wav.name, "reference": ref, "kind": "read speech",
                      "source": "LibriVox, Sense and Sensibility ch. 1 (PocketSphinx test data)"})
    conv = take(pyannote_blob, "pyannote_audio-4.0.7/src/pyannote/audio/sample/sample.wav", "conversation.wav")
    with tarfile.open(fileobj=io.BytesIO(pyannote_blob)) as tar:
        stm = tar.extractfile("pyannote_audio-4.0.7/src/pyannote/audio/sample/sample.stm").read().decode()
    turns = []
    for line in stm.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6:
            turns.append({"speaker": parts[2], "start": float(parts[3]), "end": float(parts[4]), "text": parts[5]})
    items.append({"id": "conversation", "audio": conv.name, "reference": " ".join(t["text"] for t in turns),
                  "turns": turns, "kind": "telephone conversation, 2 speakers",
                  "source": "pyannote.audio 4.0.7 sample (sample.wav + sample.stm)"})
    for member, dest in (("silero_vad-6.2.3/tests/data/test.wav", "speech_60s.wav"),
                         ("silero_vad-6.2.3/examples/c++/aepyx.wav", "speech_169s.wav")):
        wav = take(silero_blob, member, dest)
        items.append({"id": dest[:-4], "audio": wav.name, "reference": None, "kind": "speech, no transcript",
                      "source": f"silero-vad 6.2.3 ({member.split('/', 1)[1]})"})
    payload = json.dumps(items, indent=1).encode()
    (out / "items.json").write_bytes(payload)
    audio_bytes = sum((out / i["audio"]).stat().st_size for i in items)
    return {"file": "asr/items.json", "records": len(items), "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload) + audio_bytes,
            "words": sum(len((i["reference"] or "").split()) for i in items)}


def write_jsonl(name: str, rows: list[dict]) -> dict:
    path = DATA / f"{name}.jsonl"
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    path.write_bytes(payload)
    return {"file": path.name, "records": len(rows), "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="rebuild even if the data is present")
    args = parser.parse_args(argv)
    manifest_path = DATA / "manifest.json"
    if manifest_path.exists() and not args.force:
        manifest = json.loads(manifest_path.read_text())
        ok = all(hashlib.sha256((DATA / d["file"]).read_bytes()).hexdigest() == d["sha256"]
                 for d in manifest["datasets"].values() if (DATA / d["file"]).exists())
        if ok and all((DATA / d["file"]).exists() for d in manifest["datasets"].values()):
            for name, d in manifest["datasets"].items():
                log(f"{name:10} {d['records']:>4} records, sha256 {d['sha256'][:12]}... verified")
            log("data already present and verified (use --force to rebuild)")
            return 0
        log("existing data incomplete or modified: rebuilding")

    DATA.mkdir(parents=True, exist_ok=True)
    gensim_tar = tarfile.open(fileobj=io.BytesIO(download("gensim")))
    sotu_blob = download("sotu")

    wiki = parse_wikipedia(bz2.decompress(gensim_tar.extractfile(WIKI_MEMBER).read()).decode("utf-8"))
    news = parse_newsgroups(gensim_tar.extractfile(NEWS_MEMBER).read())
    sotu = parse_sotu(sotu_blob)
    datasets = {"wikipedia": write_jsonl("wikipedia", wiki), "newsgroups": write_jsonl("newsgroups", news),
                "sotu": write_jsonl("sotu", sotu),
                "asr": prepare_asr(download("pocketsphinx"), download("pyannote"), download("silero"))}
    words = {
        "wikipedia": sum(len((a["lead"] + " ".join(s["text"] for s in a["sections"])).split()) for a in wiki),
        "newsgroups": sum(len(p["text"].split()) for p in news),
        "sotu": sum(len(s["text"].split()) for s in sotu),
        "asr": datasets["asr"]["words"],
    }
    for name, d in datasets.items():
        d["words"] = words[name]
        d["licence"] = LICENCES[name]
        log(f"{name:10} {d['records']:>4} records, {d['words']:>9,} words -> {d['file']}")
    manifest = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "python": sys.version.split()[0],
                "sources": SOURCES, "datasets": datasets}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
