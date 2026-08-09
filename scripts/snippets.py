#!/usr/bin/env python3
"""snippets.py - On-demand RAG passage extraction.

Given a user question and a plain-text full text file, rank paragraphs by
relevance (BM25) and print the top-K passages with the context heading they
appeared under. This is the retrieval step: only the returned snippets are
injected into the model context, never the whole document.

Usage:
  python snippets.py "<question>" <fulltext.txt> [--top 8] [--output FILE]
"""

import argparse
import io
import math
import re
import sys


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def tokenize(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1]


def split_sections(text):
    """Split into (heading, paragraph) blocks. Paragraphs inherit the last
    seen heading so we can attribute snippets to sections."""
    blocks = []
    heading = "GENERAL"
    current = []
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            if current:
                blocks.append((heading, " ".join(current)))
                current = []
            heading = clean(line[3:])
        elif line.strip():
            current.append(clean(line))
    if current:
        blocks.append((heading, " ".join(current)))
    return blocks


def split_paragraphs(text):
    """Split into sentence groups; also break on embedded newlines so chunks
    stay focused and don't span figures/captions."""
    text = text.replace("\\n", "\n")
    chunks = []
    for part in text.split("\n"):
        part = clean(part)
        if not part:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", part):
            sent = sent.strip()
            if sent:
                chunks.append(sent)
    return chunks


def bm25_score(query_terms, doc_terms, k1=1.5, b=0.75):
    if not doc_terms or not query_terms:
        return 0.0
    dl = len(doc_terms)
    avgdl = dl  # per-chunk normalization; keep simple
    tf = {}
    for t in doc_terms:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for t in query_terms:
        if t in tf:
            idf = math.log(1 + 1.0 / 1.0)  # idf constant per single doc
            f = tf[t]
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("textfile")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--output", "-o", default=None,
                    help="Write output to file (UTF-8 with BOM) instead of stdout")
    args = ap.parse_args()

    query_terms = tokenize(args.question)
    if not query_terms:
        print("ERROR: empty query", file=sys.stderr)
        sys.exit(1)

    text = open(args.textfile, encoding="utf-8").read()
    scored = []
    for heading, block in split_sections(text):
        for chunk in split_paragraphs(block):
            terms = tokenize(chunk)
            if len(terms) < 5:
                continue
            s = bm25_score(query_terms, terms)
            if s > 0:
                scored.append((s, heading, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        print("NO_MATCH: no relevant passages found in the document.")
        return

    lines = []
    lines.append(f"# Top {min(args.top, len(scored))} passages relevant to: {args.question}\n")
    for i, (s, heading, chunk) in enumerate(scored[: args.top], 1):
        lines.append(f"[{i}] (score={s:.3f}, section={heading})")
        lines.append(chunk)
        lines.append("")

    out_text = "\n".join(lines)
    if args.output:
        with open(args.output, "w", encoding="utf-8-sig") as f:
            f.write(out_text)
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        print(out_text)


if __name__ == "__main__":
    main()
