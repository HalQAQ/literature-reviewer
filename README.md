# Literature Reviewer

AI-powered biomedical literature search and review via [OpenCode](https://opencode.ai). Searches PubMed, fetches full-text through HKU EZproxy, and generates structured review reports.

## Setup

```bash
npm install
```

## Usage

Ask OpenCode to search literature on a topic. The `literature-review` skill handles the workflow:

- **Tool 1 (screening)**: `python scripts/tool1_search.py "query||synonyms" --limit 30`
  By default only **research papers** are returned (reviews/systematic reviews/meta-analyses are
  excluded). Use `--reviews include` to include reviews, or `--reviews only` for review-only results.
- **Tool 2 (full-text)**: `python scripts/tool2_full_text.py --pmid <id>`
- **RAG extraction**: `python scripts/snippets.py "<question>" cache/<file>.txt --top 5`
- **Tool 3 (single-paper deep reading)**: `python scripts/tool3_deep_read.py "<pmid|doi|title>"` or `python scripts/tool3_deep_read.py --local "<path>"`

Reports are saved to `reports/` in Markdown format. Deep-reading reports use the filename
`<First Author> et al. - <Journal> - <Year>.md` (e.g. `Zhang et al. - PLoS genetics - 2016.md`).

## Standard workflow

The tool can be used through OpenCode or any AI-agent tool. All prompts to the user are in
English. Every new search/deep-read task follows this flow:

1. **Start** — two ways:
   - *Entry A*: you say something like "start using literature reviewer" or "start a literature
     search" (no specific request yet) → the agent shows a short usage guide and introduces the
     modes below. The agent **never runs scripts to self-verify** the pipeline.
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
python scripts/tool3_deep_read.py "27583450"                                   # by PMID
python scripts/tool3_deep_read.py "10.1371/journal.pgen.1006293"               # by DOI
python scripts/tool3_deep_read.py "DMRT1 is required for mouse SSC maintenance" # by title
python scripts/tool3_deep_read.py --local "C:\Users\me\Downloads\paper.pdf"     # local PDF/text
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

## EZproxy login

This tool uses **EZproxy** to access paywalled articles through your institution's library.
EZproxy login sessions expire over time, so you will need to **log in manually once per
session** — the agent navigates you to the login page, you type your credentials, and the
agent clicks submit. After that the session is persisted and you can browse paywalled
articles until it expires again.

Different institutions use different login methods (portal UID + PIN, SSO, 2FA, etc.).
The agent cannot operate your browser's native password manager or your SSO provider by
default, but you can work with the agent to customize a login flow that fits your own
institution.

## Browser channel: web-access (dedicated isolated profile)

For paywalled full-text retrieval the agent uses the bundled **web-access** skill
(`.opencode/skills/web-access`), which drives a **dedicated, isolated Chrome instance**
(`web-access-profile/`) via CDP. The skill was adapted for this project:

- **Privacy (hard requirement)**: the skill's browser discovery was patched so the agent can
  only ever connect to the dedicated profile — your everyday Chrome/Edge is **physically
  undiscoverable**. The agent never reads your browser history/bookmarks/passwords, and only
  operates in tabs it creates itself (closing them afterwards). `find-url` (bookmark/history
  search) is likewise restricted to the dedicated profile and effectively disabled.
- **Windows/PowerShell**: all `curl` calls use `curl.exe`; skill paths use relative
  `.opencode/skills/web-access`.
- **Site experience**: after each successful fetch, the agent may record verified patterns
  (lazy-loading behavior, PDF streams, login redirects) in
  `.opencode/skills/web-access/references/site-patterns/<domain>.md`, reused across sessions.

**One-time setup**:
1. Run `powershell -ExecutionPolicy Bypass -File scripts\start-web-access-profile.ps1`
   to start the isolated Chrome (remote debugging on port 9222).
2. In that window, log in to your library/EZproxy once. The session persists there.

**Keep the dedicated window open** while the agent needs browser access. If it is not
running, the agent will ask you to start it, then falls back to the `hku-browser` MCP
(`.hku-profile`) with manual login.

## Parallel full-text fetching

When Mode 2 needs full texts for **multiple paywalled articles**, the agent fetches them in
**parallel using sub-agents** (shared CDP proxy + per-tab isolation, no race conditions).
Each sub-agent loads the web-access skill, opens its own background tab, extracts the body,
saves it to `cache/<pmid>_<source>.txt`, and closes the tab. The main agent then aggregates
results and continues with RAG extraction and report writing. If the dedicated instance is
unavailable, fetching degrades to the serial `hku-browser` path.
