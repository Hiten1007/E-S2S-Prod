# PE-Screener

Private Equity Decarbonization Intelligence Pipeline.

## Architecture

```
Scraper (PE-Screener-Scraper) → Raw JSON
          ↓
AI Pipeline (this repo) → signals.json (encrypted in repo)
          ↓
Dashboard (Vercel) → Live intelligence for your team
```

## Pipeline Layers

| Layer | Script | Function |
|---|---|---|
| 1 | `layer1_chunker.py` | Splits articles into ≤3000-word semantic chunks |
| 2 | `layer2_pass1.py` | LLM relevance filtering (llama-3.3-70b) |
| 3 | `layer3_pass2.py` | LLM signal extraction (gpt-oss-120b) |
| 4 | `layer4_dedup.py` | Deduplication against existing signals |
| 5 | `layer5_cross_ref.py` | Cross-reference enrichment |

## Deployment

Dashboard is deployed on Vercel. Data files are stored encrypted (`*.enc`) and decrypted at build time.

## Setup

1. Clone this repo
2. Set `DATA_KEY` as a Vercel environment variable
3. Connect to Vercel — auto-deploys on every push to `main`
