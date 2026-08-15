#!/usr/bin/env python3
"""fulltext.py - Fetch full text for a PMID or DOI.

Priority:
  1. Open-access full text via Europe PMC (free, no subscription).
  2. If paywalled, print an HKU EZproxy URL for the agent to open with the
     hku-browser MCP (user already logged in).

Output: plain-text file saved to <outdir>/<pmid>.txt and prints its path,
plus a summary of sections. Does NOT download any PDFs.

Usage:
  python fulltext.py --pmid 24930130 [--outdir cache]
  python fulltext.py --doi 10.1038/nmeth.2999 [--outdir cache]
"""

import argparse
import os
import re
import sys
import urllib.parse

import requests
from lxml import etree

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def lookup_by_pmid(pmid):
    r = requests.get(f"{EPMC}/search", params={
        "query": f"EXT_ID:{pmid} AND SRC:MED", "resultType": "core",
        "format": "json", "pageSize": 1,
    }, timeout=30)
    r.raise_for_status()
    res = (r.json().get("resultList", {}).get("result") or [])
    return res[0] if res else None


def lookup_by_doi(doi):
    r = requests.get(f"{EPMC}/search", params={
        "query": f'DOI:"{doi}"', "resultType": "core",
        "format": "json", "pageSize": 1,
    }, timeout=30)
    r.raise_for_status()
    res = (r.json().get("resultList", {}).get("result") or [])
    return res[0] if res else None


def get_fulltext_xml(pmcid):
    r = requests.get(f"{EPMC}/{pmcid}/fullTextXML", timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def extract_text(xml_bytes):
    """Parse Europe PMC fullTextXML into plain text with section headings."""
    root = etree.fromstring(xml_bytes)

    def t(node):
        return clean(" ".join(node.itertext()))

    parts = []
    title_node = root.xpath("//article-title")
    if title_node:
        parts.append("TITLE: " + t(title_node[0]))
    for ab in root.xpath("//abstract"):
        txt = t(ab)
        if txt:
            parts.append("ABSTRACT: " + txt)

    in_body = False
    for node in root.xpath("//body/* | //body//*"):
        if not in_body and node.getparent().tag.endswith("body"):
            in_body = True
        tag = etree.QName(node).localname
        if tag == "title":
            txt = t(node)
            if txt:
                parts.append(f"\n## {txt}")
        elif tag == "p":
            txt = t(node)
            if txt:
                parts.append(txt)
    return "\n".join(parts)


def ezproxy_url(doi, pmid=None):
    """Return an HKU EZproxy URL the user can access."""
    if pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif doi:
        url = f"https://doi.org/{doi}"
    else:
        return None
    return f"https://eproxy.lib.hku.hk/login?url={urllib.parse.quote(url, safe='')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid")
    ap.add_argument("--doi")
    ap.add_argument("--outdir", default="cache")
    args = ap.parse_args()

    if not args.pmid and not args.doi:
        ap.error("need --pmid or --doi")

    meta = lookup_by_pmid(args.pmid) if args.pmid else lookup_by_doi(args.doi)
    if not meta:
        print("NOT_FOUND: no Europe PMC record for this identifier", file=sys.stderr)
        sys.exit(1)

    pmid = meta.get("pmid")
    pmcid = meta.get("pmcid", "")
    title = clean(meta.get("title", ""))
    has_ft = meta.get("isOpenAccess") == "Y" or bool(pmcid)

    os.makedirs(args.outdir, exist_ok=True)

    xml = get_fulltext_xml(pmcid) if pmcid else None
    if xml:
        text = extract_text(xml)
        if len(text) < 200:
            text = ""
        if text:
            out_path = os.path.join(args.outdir, f"{pmid or args.doi.replace('/', '_')}.txt")
            with open(out_path, "w", encoding="utf-8-sig") as f:
                f.write(f"TITLE: {title}\nPMID: {pmid}\nDOI: {meta.get('doi', '')}\nPMCID: {pmcid}\n\n")
                f.write(text)
            print(f"OK: open-access full text saved to {out_path}")
            print(f"WORDS: {len(text.split())}")
            print(f"PMID: {pmid} | DOI: {meta.get('doi', '')} | PMCID: {pmcid}")
            sys.exit(0)

    # Paywalled / no OA full text
    url = ezproxy_url(args.doi, pmid)
    print("PAYWALLED: no open-access full text available.")
    print(f"TITLE: {title}")
    print(f"PMID: {pmid} | DOI: {meta.get('doi', '')}")
    print(f"EZPROXY_URL: {url}")
    print("ACTION: open the EZPROXY_URL in the hku-browser MCP and extract the"
          " article body text from the page.")


if __name__ == "__main__":
    main()
