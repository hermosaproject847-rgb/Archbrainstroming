"""The reference library: NBC, IS codes and the standard architecture texts.

The books in NBC/ come to roughly 290 MB — far too much to put in front of the
model on every read, and most of it is irrelevant to any one drawing. So the
library is INDEXED once, and then CONSULTED: when the software meets something
it has no rule for, it looks the topic up and passes only the handful of
passages that actually bear on it.

    python -m core.library build        index every PDF in NBC/  (once)
    python -m core.library ask "riser"  see what comes back

The index is plain JSONL — one record per page — so it can be inspected, and
searching is a scored keyword match. No embeddings, nothing to download, works
on a machine with no egress.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(ROOT, "NBC")
INDEX = os.path.join(ROOT, "work", "library.jsonl")

MIN_CHARS = 120          # pages with less text than this are covers/plates
SNIPPET = 700

STOP = set("""a an the and or of to in on for with by is are was were be been
this that these those it its as at from into than then so such not no if we you
your their there here which who whom what when where how all any both each few
more most other some only own same too very can will just shall may
""".split())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _terms(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", (s or "").lower())
            if len(w) > 2 and w not in STOP]


# ------------------------------------------------------------------ build
def build(verbose=True) -> int:
    """Index every PDF in NBC/. Slow once, then instant for ever after."""
    import pdfplumber

    if not os.path.isdir(BOOKS):
        raise SystemExit(f"No library folder at {BOOKS}")
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)

    pdfs = sorted(f for f in os.listdir(BOOKS) if f.lower().endswith(".pdf"))
    n = 0
    with open(INDEX, "w", encoding="utf-8") as out:
        for f in pdfs:
            path = os.path.join(BOOKS, f)
            if verbose:
                print(f"  {f} …", flush=True)
            try:
                with pdfplumber.open(path) as pdf:
                    for i, page in enumerate(pdf.pages, start=1):
                        try:
                            text = _norm(page.extract_text() or "")
                        except Exception:
                            continue
                        if len(text) < MIN_CHARS:
                            continue
                        out.write(json.dumps({
                            "book": f[:-4], "page": i, "text": text,
                        }, ensure_ascii=False) + "\n")
                        n += 1
            except Exception as e:
                print(f"    skipped: {e}")
    if verbose:
        print(f"indexed {n} pages from {len(pdfs)} books -> {INDEX}")
    return n


def ready() -> bool:
    return os.path.isfile(INDEX) and os.path.getsize(INDEX) > 0


def status() -> dict:
    books = sorted(f for f in os.listdir(BOOKS)) if os.path.isdir(BOOKS) else []
    pages = 0
    if ready():
        with open(INDEX, encoding="utf-8") as fh:
            pages = sum(1 for _ in fh)
    return {"books": [b for b in books if b.lower().endswith(".pdf")],
            "pages": pages, "ready": ready(), "index": INDEX}


# ----------------------------------------------------------------- search
_CACHE: list[dict] | None = None


def _load() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = []
        if ready():
            with open(INDEX, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    r["_t"] = Counter(_terms(r["text"]))
                    _CACHE.append(r)
    return _CACHE


def search(query: str, limit: int = 5, book: str = "") -> list[dict]:
    """Passages bearing on `query`, best first.

    Scoring favours pages that carry ALL the query's words and that read like
    a rule — a page quoting a dimension or a clause number is far more use than
    one merely mentioning the word.
    """
    want = _terms(query)
    if not want:
        return []
    rows = _load()
    scored = []
    for r in rows:
        if book and book.lower() not in r["book"].lower():
            continue
        tf = r["_t"]
        hits = sum(1 for w in want if tf.get(w))
        if not hits:
            continue
        score = hits * 10 + sum(min(tf.get(w, 0), 4) for w in want)
        if hits == len(want):
            score += 25                                  # every word present
        low = r["text"].lower()
        if re.search(r"\b(shall|minimum|maximum|not less than)\b", low):
            score += 8                                   # reads like a rule
        if re.search(r"\d{2,4}\s*mm|\bm2\b|sq\.?\s*m", low):
            score += 5                                   # carries a dimension
        # A code states the requirement; a textbook explains it. When both
        # match, the code is the one to quote.
        b = r["book"].lower()
        if "national-building-code" in b or "nbc" in b:
            score += 20
        elif "bye law" in b or "standard_" in b:
            score += 12
        scored.append((score, r))

    scored.sort(key=lambda s: -s[0])
    out = []
    for score, r in scored[:limit]:
        out.append({"book": r["book"], "page": r["page"], "score": score,
                    "text": _excerpt(r["text"], want)})
    return out


def _excerpt(text: str, want: list[str]) -> str:
    """The part of the page that actually answers the query."""
    low = text.lower()
    best, best_hits = 0, -1
    step = 120
    for start in range(0, max(1, len(text) - SNIPPET + 1), step):
        window = low[start:start + SNIPPET]
        hits = sum(window.count(w) for w in want)
        if hits > best_hits:
            best, best_hits = start, hits
    s = text[best:best + SNIPPET].strip()
    return ("… " if best else "") + s + (" …" if best + SNIPPET < len(text) else "")


def brief(query: str, limit: int = 4, book: str = "") -> str:
    """The same passages, formatted for putting in front of a model."""
    hits = search(query, limit, book)
    if not hits:
        return ""
    parts = [f"Reference passages for “{query}” "
             "(from the project's code library — quote the source when you "
             "rely on one):"]
    for h in hits:
        parts.append(f"\n[{h['book']}, p.{h['page']}]\n{h['text']}")
    return "\n".join(parts)


# ------------------------------------------------------------------- cli
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "build":
        build()
    elif cmd == "ask":
        q = " ".join(sys.argv[2:]) or "staircase riser tread"
        for h in search(q, 5):
            print(f"\n=== {h['book']} p.{h['page']}  (score {h['score']})")
            print(h["text"][:600])
    else:
        st = status()
        print(f"books  {len(st['books'])}")
        for b in st["books"]:
            print("  ", b)
        print(f"pages indexed: {st['pages']}   ready: {st['ready']}")
