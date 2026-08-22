#!/usr/bin/env python3
"""tool3_deep_read.py - Tool 3 single-paper deep reading.

Resolves one paper (from a PMID, DOI, title, or a local PDF/text file),
prints its citation metadata, and fetches/reads its full text so the agent
can do a deep-reading report.

The printed REPORT_NAME line is the exact report filename the skill should
use: "<FirstAuthor et al.> - <Journal> - <Year>.md".

For paywalled papers this script prints PAYWALLED + EZPROXY_URL; the agent
then retrieves the body with the hku-browser MCP (Tool 2 path) and saves it
to cache/<pmid>_<source>.txt.

Usage:
  python tool3_deep_read.py <pmid>    # e.g. 27583450
  python tool3_deep_read.py 10.1371/journal.pgen.1006293
  python tool3_deep_read.py "DMRT1 is required for mouse spermatogonial stem cell maintenance"
  python tool3_deep_read.py --local "C:\\Users\\me\\Downloads\\paper.pdf"
"""

import argparse
import os
import re
import sys
import time

import tool2_full_text

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
INVALID_FS = r'[<>:"/\\|?*\x00-\x1f]'


def sanitize(s, fallback=""):
    s = re.sub(INVALID_FS, " ", s or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s or fallback


def clean(s):
    return tool2_full_text.clean(s)


def lookup_by_title(title):
    """Europe PMC title search; returns candidate records (best first)."""
    import requests
    r = requests.get(f"{EPMC}/search", params={
        "query": f'TITLE:"{title}"', "resultType": "core",
        "format": "json", "pageSize": 5,
    }, timeout=30)
    r.raise_for_status()
    return (r.json().get("resultList", {}).get("result") or [])


def detect_kind(identifier):
    if re.fullmatch(r"\d{6,9}", identifier.strip()):
        return "pmid"
    if re.match(r"10\.\S+", identifier.strip()):
        return "doi"
    return "title"


def first_author(meta):
    """Return (last_name, total_author_count) from an EPMC record."""
    authors = (meta.get("authorList") or {}).get("author") or []
    last = ""
    if authors:
        last = authors[0].get("lastName") or authors[0].get("fullName") or ""
    if not last:
        m = re.search(r"\b([A-Z][a-zA-Z\-]+)\s+\S", meta.get("authorString") or "")
        last = m.group(1) if m else ""
    return clean(last), len(authors)


def meta_year(meta):
    y = meta.get("pubYear") or ""
    if not y:
        y = str(meta.get("firstPublicationDate") or "")[:4]
    return clean(y)


def meta_journal(meta):
    return clean(meta.get("journalInfo", {}).get("journal", {}).get("title"))


def report_name(last, n_authors, journal, year):
    author = last if n_authors <= 1 else f"{last} et al."
    j = sanitize(journal, "UnknownJournal")
    y = sanitize(year, "UnknownYear")
    return f"{author} - {j} - {y}.md"


def print_meta(meta):
    last, n = first_author(meta)
    journal = meta_journal(meta)
    year = meta_year(meta)
    title = clean(meta.get("title"))
    pmid = meta.get("pmid") or ""
    doi = meta.get("doi") or ""
    pmcid = meta.get("pmcid") or ""
    print("TITLE:", title)
    print("AUTHORS:", clean(meta.get("authorString") or "") or f"{last} et al.")
    print("JOURNAL:", journal)
    print("YEAR:", year)
    print("PMID:", pmid, "| DOI:", doi, "| PMCID:", pmcid)
    print("REPORT_NAME:", report_name(last, n, journal, year))
    return pmid, doi, pmcid


def fetch_web(args):
    ident = args.identifier.strip()
    kind = detect_kind(ident)
    print(f"LOOKUP_KIND: {kind}")

    if kind == "pmid":
        meta = tool2_full_text.lookup_by_pmid(ident)
    elif kind == "doi":
        meta = tool2_full_text.lookup_by_doi(ident)
    else:
        candidates = lookup_by_title(ident)
        if not candidates:
            print("NOT_FOUND: no Europe PMC record for this identifier", file=sys.stderr)
            sys.exit(1)
        for i, c in enumerate(candidates, 1):
            print(f"CANDIDATE[{i}]: {clean(c.get('title'))} "
                  f"({meta_journal(c)} {meta_year(c)}) PMID:{c.get('pmid')} DOI:{c.get('doi')}")
        meta = candidates[0]

    if not meta:
        print("NOT_FOUND: no Europe PMC record for this identifier", file=sys.stderr)
        sys.exit(1)

    pmid, doi, pmcid = print_meta(meta)
    os.makedirs(args.outdir, exist_ok=True)

    xml = tool2_full_text.get_fulltext_xml(pmcid) if pmcid else None
    if xml:
        text = tool2_full_text.extract_text(xml)
        if len(text) >= 200:
            out_path = os.path.join(args.outdir, f"{pmid or doi.replace('/', '_')}.txt")
            with open(out_path, "w", encoding="utf-8-sig") as f:
                f.write(f"TITLE: {clean(meta.get('title'))}\n"
                        f"PMID: {pmid}\nDOI: {doi}\nPMCID: {pmcid}\n\n")
                f.write(text)
            print(f"OK: full text saved to {out_path}")
            print(f"WORDS: {len(text.split())}")
            return

    url = tool2_full_text.ezproxy_url(doi, pmid)
    print("PAYWALLED: no open-access full text available.")
    print(f"EZPROXY_URL: {url}")
    print("ACTION: open the EZPROXY_URL in the hku-browser MCP and extract the"
          " article body text to cache/<pmid>_<source>.txt")


def fetch_local(args):
    path = args.local
    if not os.path.isfile(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            print("ERROR: pypdf is required to read PDFs. Run: pip install pypdf",
                  file=sys.stderr)
            sys.exit(1)
        reader = PdfReader(path)
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()

    text = clean(text)
    if len(text) < 100:
        print("ERROR: could not extract enough text from this file "
              "(scanned PDFs are not supported).", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    base = sanitize(os.path.splitext(os.path.basename(path))[0], "local_paper")
    out_path = os.path.join(args.outdir, f"{base}.txt")
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(text)
    print(f"OK: local full text saved to {out_path}")
    print(f"WORDS: {len(text.split())}")
    print("REPORT_NAME: derive from the text below "
          "(first author et al. - journal - year).")
    print("\n--- HEAD (first 2500 chars, for citation identification) ---\n")
    print(text[:2500])


def main():
    t0 = time.perf_counter()
    ap = argparse.ArgumentParser()
    ap.add_argument("identifier", nargs="?", help="PMID, DOI, or paper title")
    ap.add_argument("--local", help="path to a local PDF/text file")
    ap.add_argument("--outdir", default="cache")
    args = ap.parse_args()

    if args.local:
        fetch_local(args)
    elif args.identifier:
        fetch_web(args)
    else:
        ap.error("provide an identifier or --local")
    print(f"ELAPSED: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
