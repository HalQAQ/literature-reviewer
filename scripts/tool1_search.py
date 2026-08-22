#!/usr/bin/env python3
"""tool1_search.py - Tool 1 literature screening.

Queries PubMed, Europe PMC and Semantic Scholar, merges by PMID/DOI, and
prints a ranked, deduplicated list of articles (title/abstract/authors/
journal/year/PMID/DOI/citations/source links).

Multiple queries are supported: separate them with '||' (e.g. "DMRT1
spermatogenesis||DMRT1 germline commitment"). Results from all queries are
merged and deduplicated. By default at least 10 results are targeted.

By default reviews/systematic reviews/meta-analyses are EXCLUDED (research
papers only). Use --reviews to change:
  --reviews exclude  research papers only (default)
  --reviews include  include reviews as well
  --reviews only     only reviews/systematic reviews/meta-analyses

Usage:
  python tool1_search.py "<query>" [--limit N] [--reviews exclude|include|only] [--json] [--output FILE]
  python tool1_search.py "A||B||C" --limit 30 --output results.txt
"""

import argparse
import html
import io
import json
import re
import sys
import time
import urllib.parse

import requests


def clean_text(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_HEADERS = {"User-Agent": "opencode-literature-review/0.1"}
DEFAULT_LIMIT = 30

# Secondary literature types excluded by default (--reviews exclude).
SECONDARY_TYPES = {"review", "systematic review", "meta-analysis"}
REVIEW_PUBMED = {
    "exclude": "NOT (review[pt] OR systematicreview[pt] OR meta-analysis[pt])",
    "only": "(review[pt] OR systematicreview[pt] OR meta-analysis[pt])",
}
REVIEW_EPMC = {
    "exclude": 'NOT (PUB_TYPE:"Review" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis")',
    "only": '(PUB_TYPE:"Review" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis")',
}


def _is_secondary(types):
    """types: lowercased publication type strings -> True if a review-type."""
    return any(any(s in t for s in ("review", "meta-analysis", "metaanalysis")) for t in types)


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def fetch(url, params=None, headers=None, timeout=30, retries=5):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.exceptions.HTTPError(r.status_code)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def search_pubmed(query, limit, reviews="exclude"):
    """PubMed E-utilities: esearch -> esummary (with abstract via efetch)."""
    term = query
    if reviews in REVIEW_PUBMED:
        term = f"{query} AND {REVIEW_PUBMED[reviews]}"
    ids = fetch(BASE + "/esearch.fcgi", {
        "db": "pubmed", "term": term, "retmax": limit,
        "retmode": "json", "sort": "relevance",
    }).json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    time.sleep(0.7)
    joined = ",".join(ids)
    summ = fetch(BASE + "/esummary.fcgi", {
        "db": "pubmed", "id": joined, "retmode": "json",
    }).json().get("result", {})
    time.sleep(0.7)
    abstr = fetch(BASE + "/efetch.fcgi", {
        "db": "pubmed", "id": joined, "rettype": "abstract", "retmode": "text",
    }).text
    chunks = re.split(r"\n(?=\d+\.\s)", abstr)
    abstract_map = {}
    for c in chunks:
        m = re.match(r"^(\d+)\.\s", c)
        if m:
            body = re.sub(r"^\d+\.\s", "", c, count=1).strip()
            lines = [l for l in body.splitlines() if l.strip()]
            abstract_map[m.group(1)] = "\n".join(lines)
    out = []
    for pid in ids:
        it = summ.get(pid, {})
        if not it.get("title"):
            continue
        authors = it.get("authors", [])
        out.append({
            "source": "PubMed",
            "title": clean_text(it.get("title", "")),
            "abstract": clean_text(abstract_map.get(pid, "")),
            "authors": [a.get("name") for a in authors] if isinstance(authors, list) else [],
            "journal": it.get("fulljournalname", "") or it.get("source", ""),
            "year": str(it.get("pubdate", ""))[:4],
            "pmid": pid,
            "doi": (it.get("articleids") or [{}])[0].get("value", "") if it.get("articleids") and it["articleids"][0].get("idtype") == "doi" else _doi_from_ids(it.get("articleids")),
            "citations": _pubmed_citations(pid),
        })
    return out


def _doi_from_ids(ids):
    if not ids:
        return ""
    for x in ids:
        if x.get("idtype") == "doi":
            return x.get("value", "")
    return ""


def _pubmed_citations(pmid):
    try:
        data = fetch(BASE + "/elink.fcgi", {
            "dbfrom": "pubmed", "db": "pmc", "id": pmid,
            "linkname": "pubmed_pmc_refs", "retmode": "json",
        }).json()
        return len(data.get("linksets", [{}])[0].get("linksetdbs", [{}])[0].get("links", [])) if data.get("linksets") else 0
    except Exception:
        return 0


def search_epmc(query, limit, reviews="exclude"):
    """Europe PMC REST search with abstracts."""
    q = query
    if reviews in REVIEW_EPMC:
        q = f"{query} AND {REVIEW_EPMC[reviews]}"
    data = fetch(EPMC + "/search", {
        "query": q, "resultType": "core", "pageSize": limit, "format": "json",
    }).json()
    out = []
    for it in data.get("resultList", {}).get("result", []):
        ptypes = it.get("pubTypeList", {})
        pt_entry = ptypes.get("pubType") or [] if isinstance(ptypes, dict) else ptypes or []
        if isinstance(pt_entry, dict):
            pt_entry = [pt_entry]
        elif isinstance(pt_entry, str):
            pt_entry = [pt_entry]
        pt = []
        for p in pt_entry:
            if isinstance(p, dict):
                pt.append(str(p.get("type", "")).lower())
            else:
                pt.append(str(p).lower())
        if reviews == "exclude" and _is_secondary(pt):
            continue
        if reviews == "only" and not _is_secondary(pt):
            continue
        out.append({
            "source": "EuropePMC",
            "title": clean_text(it.get("title", "")),
            "abstract": clean_text(it.get("abstractText", "")),
            "authors": [a.get("fullName", "") for a in it.get("authorList", {}).get("author", [])] if it.get("authorList") else [],
            "journal": it.get("journalInfo", {}).get("journal", {}).get("title", ""),
            "year": str(it.get("pubYear", "")),
            "pmid": str(it.get("pmid", "")),
            "doi": it.get("doi", ""),
            "citations": it.get("citedByCount", 0),
        })
    return out


def search_s2(query, limit, reviews="exclude"):
    """Semantic Scholar search (fields: title, abstract, authors, journal,
    year, externalIds, citationCount, publicationTypes)."""
    params = {
        "query": query, "limit": min(limit, 100),
        "fields": "title,abstract,authors,journal,year,externalIds,citationCount,publicationTypes",
    }
    try:
        data = fetch(S2, params, headers=S2_HEADERS, timeout=30).json()
    except Exception:
        return []
    out = []
    for it in data.get("data", []):
        pt = [str(t).lower() for t in (it.get("publicationTypes") or [])]
        if reviews == "exclude" and _is_secondary(pt):
            continue
        if reviews == "only" and not _is_secondary(pt):
            continue
        ex = it.get("externalIds") or {}
        out.append({
            "source": "SemanticScholar",
            "title": clean_text(it.get("title", "")),
            "abstract": clean_text(it.get("abstract")),
            "authors": [a.get("name") for a in it.get("authors", []) if a.get("name")],
            "journal": (it.get("journal") or {}).get("name", ""),
            "year": str(it.get("year", "")),
            "pmid": str(ex.get("PubMed", "")),
            "doi": ex.get("DOI", ""),
            "citations": it.get("citationCount", 0),
        })
    return out


def merge(results):
    """Merge by PMID then DOI, prefer entries with abstracts/citations."""
    by_key = {}
    order = []
    for rec in results:
        key = None
        if rec.get("pmid") and rec.get("pmid") != "0":
            key = "pmid:" + rec["pmid"]
        elif rec.get("doi"):
            key = "doi:" + rec["doi"].lower()
        if key is None:
            key = "title:" + norm_title(rec.get("title"))
        if key not in by_key:
            by_key[key] = rec
            order.append(key)
        else:
            old = by_key[key]
            for f in ("abstract", "citations", "doi"):
                if not old.get(f) and rec.get(f):
                    old[f] = rec[f]
            if old["source"] != rec["source"]:
                old["source"] = old["source"] + "+" + rec["source"]
    merged = [by_key[k] for k in order]
    for rec in merged:
        rec["rank_score"] = round(_score(rec), 3)
    merged.sort(key=lambda r: r["rank_score"], reverse=True)
    return merged


def _score(rec):
    # Citations dominate (proxy for impact/credibility), abstract completeness
    # adds a small tie-breaker. No position penalty: relevance to the query
    # is the caller's job via query selection; here we surface the most
    # trusted papers.
    abstract = rec.get("abstract") or ""
    return rec.get("citations", 0) + len(abstract) / 2000.0


def main():
    t0 = time.perf_counter()
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--reviews", choices=["exclude", "include", "only"],
                    default="exclude",
                    help="Publication-type filter: exclude reviews (default, "
                         "research papers only), include reviews, or only reviews")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--output", "-o", default=None,
                    help="Write output to file (UTF-8 with BOM) instead of stdout")
    args = ap.parse_args()

    queries = [q.strip() for q in args.query.split("||") if q.strip()]
    if not queries:
        ap.error("empty query")

    per_query = max(args.limit // len(queries), 15)
    results = []
    for q in queries:
        for fn in (search_pubmed, search_epmc, search_s2):
            try:
                results.extend(fn(q, per_query, args.reviews))
                time.sleep(0.5)
            except Exception as e:
                print(f"[warn] {fn.__name__} failed for {q!r}: {e}", file=sys.stderr)

    merged = merge(results)
    elapsed = time.perf_counter() - t0

    if args.json:
        out_text = json.dumps(merged, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8-sig") as f:
                f.write(out_text)
        else:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            print(out_text)
        print(f"ELAPSED: {elapsed:.1f}s")
        return

    lines = []
    lines.append(f"# Found {len(merged)} unique articles for: {args.query}")
    lines.append(f"REVIEW_FILTER: {args.reviews}\n")
    for i, rec in enumerate(merged, 1):
        lines.append(f"[{i}] {rec['title']}")
        lines.append(f"    Journal: {rec.get('journal') or 'N/A'} ({rec.get('year') or 'N/A'})")
        lines.append(f"    PMID: {rec.get('pmid') or 'N/A'} | DOI: {rec.get('doi') or 'N/A'} | Citations: {rec.get('citations', 0)} | Rank: {rec.get('rank_score')}")
        if rec.get("authors"):
            lines.append(f"    Authors: {', '.join(rec['authors'][:6])}{' et al.' if len(rec['authors']) > 6 else ''}")
        ab = rec.get("abstract") or ""
        if ab:
            lines.append(f"    Abstract: {ab[:300]}{'...' if len(ab) > 300 else ''}")
        lines.append("")

    out_text = "\n".join(lines)
    if args.output:
        with open(args.output, "w", encoding="utf-8-sig") as f:
            f.write(out_text)
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        print(out_text)
    print(f"ELAPSED: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
