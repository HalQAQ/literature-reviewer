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
- **RAG extraction**: `python scripts/snippets.py "<question>" outputs/<file>.txt --top 5`

Reports are saved to `reports/` in Markdown format.
