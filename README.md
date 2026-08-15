# Literature Reviewer

AI-powered biomedical literature search and review via [OpenCode](https://opencode.ai). Searches PubMed, fetches full-text through HKU EZproxy, and generates structured review reports.

## Setup

```bash
npm install
```

## Usage

Ask OpenCode to search literature on a topic. The `literature-review` skill handles the workflow:

- **Mode 1 (screening)**: `python scripts/search.py "query||synonyms" --limit 30`
- **Mode 2 (full-text)**: `python scripts/fulltext.py --pmid <id>`
- **RAG extraction**: `python scripts/snippets.py "<question>" cache/<file>.txt --top 5`
- **Mode 3 (single-paper deep reading)**: `python scripts/paper.py "<pmid|doi|title>"` or `python scripts/paper.py --local "<path>"`

Reports are saved to `reports/` in Markdown format. Deep-reading reports use the filename
`<First Author> et al. - <Journal> - <Year>.md` (e.g. `Zhang et al. - PLoS genetics - 2016.md`).

## Report location

- By default, reports are saved to `reports/` in this workspace.
- If you ask for reports to be written **elsewhere** (e.g. inside another project you are
  working on), they are saved to `<target-path>/paper_reports/`. The `paper_reports`
  subfolder is created automatically if it does not exist.

## Mode 3: Single-paper deep reading

Given a single paper (by PMID, DOI, title, or a local PDF/text file), the agent
fetches/reads its full text, deep-reads it, and writes a structured report that
answers any questions the user asked. After the report is generated you can keep
asking questions about the same paper; answers are appended to the report only
when you explicitly ask.

```bash
python scripts/paper.py "27583450"                                  # by PMID
python scripts/paper.py "10.1371/journal.pgen.1006293"              # by DOI
python scripts/paper.py "DMRT1 is required for mouse SSC maintenance" # by title
python scripts/paper.py --local "C:\Users\me\Downloads\paper.pdf"   # local PDF/text
```

Local PDFs require `pypdf`: `pip install pypdf`.

## Cache

The `cache/` folder holds **temporary files** generated while working: fetched full texts
(`<pmid>.txt`, `<pmid>_<source>.txt`) and intermediate search results. They are git-ignored
and safe to delete.

Why it exists: before fetching a paper, the agent checks `cache/` first and reuses an
existing full-text file if present. This **speeds up reading papers you have already
covered** by skipping the network fetch (and the HKU EZproxy round-trip for paywalled
articles).

Feel free to **clean `cache/` whenever you want** (e.g. `Remove-Item cache\*`) — nothing
important lives there. Files will be re-fetched on demand. Note that reports are kept
separately in `reports/` and are not affected by clearing the cache.
