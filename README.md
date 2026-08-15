# Literature Reviewer

AI-powered biomedical literature search and review via [OpenCode](https://opencode.ai). Searches PubMed, fetches full-text through HKU EZproxy, and generates structured review reports.

## Setup

```bash
npm install
```

## Usage

Ask OpenCode to search literature on a topic. The `literature-review` skill handles the workflow:

- **Mode 1 (screening)**: `python scripts/mode1_search.py "query||synonyms" --limit 30`
- **Mode 2 (full-text)**: `python scripts/mode2_full_text.py --pmid <id>`
- **RAG extraction**: `python scripts/snippets.py "<question>" cache/<file>.txt --top 5`
- **Mode 3 (single-paper deep reading)**: `python scripts/mode3_deep_read.py "<pmid|doi|title>"` or `python scripts/mode3_deep_read.py --local "<path>"`

Reports are saved to `reports/` in Markdown format. Deep-reading reports use the filename
`<First Author> et al. - <Journal> - <Year>.md` (e.g. `Zhang et al. - PLoS genetics - 2016.md`).

## Standard workflow

The tool can be used through OpenCode or any AI-agent tool. All prompts to the user are in
English. Every new search/deep-read task follows this flow:

1. **Start** — two ways:
   - *Entry A*: you say something like "start using literature reviewer" or "start a literature
     search" (no specific request yet) → the agent introduces the modes below.
   - *Entry B*: you directly give keywords plus an explicit request, e.g. "search articles about
     the BMP pathway" or "deep read PMID 27583450" → step 2 is skipped.
2. **Choose a mode** (only for Entry A): 1) Title + Abstract Quick Search — describe the search
   direction; 2) Full-Text Detailed Report — describe the search direction; 3) Single-Paper Deep
   Reading — provide the article's DOI/PMID/title or the local file path.
3. **Confirm the plan** — the agent restates what it will do (e.g. "Shall I run a quick search
   using keywords 'XX', 'YY'?") and waits for your final confirmation; you may amend details.
4. **Report location** — the agent asks where to save the report: default `<workspace>\reports\`,
   or a custom target path (report is then saved to `<target>\paper_reports\`).
5. **Execute** — the search/deep-reading is performed and the report is generated and saved.
6. **Completion summary** — the agent reports (in English): number of articles found, how many
   were deemed useful after screening, how many references the report cites, search duration
   (the scripts print `ELAPSED: N.Ns`), and the full path where the report was saved.

Follow-up questions about an already-generated report do not restart this flow.

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
python scripts/mode3_deep_read.py "27583450"                                   # by PMID
python scripts/mode3_deep_read.py "10.1371/journal.pgen.1006293"               # by DOI
python scripts/mode3_deep_read.py "DMRT1 is required for mouse SSC maintenance" # by title
python scripts/mode3_deep_read.py --local "C:\Users\me\Downloads\paper.pdf"     # local PDF/text
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
