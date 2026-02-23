# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VAAX AI-News-Daily is a static site generator that collects AI/XR/government news daily, summarizes it with LLMs, and publishes to GitHub Pages (`docs/`). The site is deployed automatically via GitHub Actions twice daily (07:20 KST, 17:20 KST).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env

# Full run (all categories)
python main.py

# Test run with limited articles
python main.py --limit 3

# Collect government data separately (run before main.py in CI)
python scripts/collect_gov_data.py

# Admin dashboard
streamlit run admin/app.py

# Run tests (from project root)
python tests/test_style_constants.py
# or with pytest if installed:
pytest tests/
```

## Environment Variables

Required API keys in `.env`:
- `GROK_API_KEY` — Groq API key (connects to Groq cloud, not xAI Grok)
- `GEMINI_API_KEY` — Google Gemini key; supports multiple comma-separated keys for rotation
- `GOV_API_KEY` — Korea public data portal API key

Run control flags (default `true`; set to `false` to skip):
- `RUN_AI`, `RUN_XR`, `RUN_GOV`, `RUN_MEMBERS`

Other notable vars:
- `MAX_ARTICLES` — articles per category (default: 10)
- `AI_RANKING_STRATEGY` — `heuristic` (default), `llm`, or `hybrid`
- `ENABLE_NOTIFICATION` — must be explicitly `true` to send Telegram notifications (prevents accidental sends locally)
- `CONSOLIDATE_ARCHIVES` — default `true`; merges duplicate daily HTML files
- `SKIP_WORDCLOUD` — set `true` to skip wordcloud generation
- `LLM_REQUEST_DELAY` — min seconds between API calls (default: 2.0)
- `GEMINI_MODEL` — defaults to `gemini-2.0-flash`
- `GROK_MODEL` — defaults to `qwen/qwen3-32b`

## Architecture

### Data Flow

```
RSS Feeds / Gov API / Google News Search
         ↓
   src/fetchers/  (rss.py, gov.py, search.py)
         ↓
   main.py: process_category()
         ↓
   src/generators/llm.py: summarize_article()  ← OpenAI → Groq → Gemini (fallback chain)
         ↓
   src/generators/html.py: render_*()          ← Jinja2 templates in templates/
         ↓
   docs/  (committed to git → GitHub Pages)
```

### Key Modules

- **`main.py`** — orchestrates the entire pipeline: fetch → summarize → render → rebuild indexes → wordcloud → dashboard → briefing → notifications
- **`src/config.py`** — `CategoryConfig` and `MemberConfig` dataclasses; loads `config/categories.yaml` and `config/members.yaml`
- **`src/generators/llm.py`** — LLM summarization with rate limiting, retry/backoff, and 3-provider fallback (OpenAI → Grok → Gemini). Also contains heuristic/LLM article ranking and key message generation.
- **`src/generators/html.py`** — Jinja2 rendering; templates loaded from project root `templates/`
- **`src/utils/storage.py`** — `MemberStorage`: JSON persistence in `data/members/{id}.json`. Deduplicates by link AND title similarity (SequenceMatcher ≥90%).
- **`src/storage/gov_storage.py`** — `GovStorage`: similar JSON persistence for government announcements
- **`src/utils/wordcloud_generator.py`** — generates wordcloud from recent HTML archives

### Output Structure

All generated HTML goes into `docs/` (GitHub Pages source, committed to git):
- `docs/index.html` — main dashboard
- `docs/ai/daily/YYYY-MM-DD_HHMMSS.html` — AI news daily pages
- `docs/xr/daily/` — XR news daily pages
- `docs/gov/index.html` — government announcements archive
- `docs/members/` — member company news pages
- `docs/briefing.html` — daily briefing
- `docs/static/` — CSS/images (copied from `static/` on each run)

`data/` is **git-ignored** (local/CI ephemeral): member news JSON, gov JSON, SQLite usage DB.

### Deduplication Logic

Articles are deduplicated across two dimensions:
1. **Link-based**: exact URL match against past and today's articles
2. **Title similarity**: SequenceMatcher ratio ≥80% (80% for primary feeds, 95% for fallback YouTube/blog feeds)

### Article Selection Strategies

Controlled by `AI_RANKING_STRATEGY`:
- `heuristic` (default): keyword scoring on company names, AI model names, event/business keywords; negative penalty for tutorials/irrelevant local news
- `llm`: calls Grok/Gemini to select articles by prompt
- `hybrid`: LLM ordering, topped up with heuristic results if needed

### Fallback Feed Logic

When primary RSS sources yield fewer than 3 articles, YouTube/blog fallback feeds are queried with a 7-day time window (`fallback_feeds`, `fallback_time_hours` in `config/categories.yaml`). YouTube-sourced articles get a `🎬` prefix in titles.

### GitHub Actions CI

- **`daily-news.yml`**: main pipeline, runs twice daily; commits `docs/` and `data/` back to `main`
- **`send-notification.yml`**: Telegram notification workflow
- **`blogger-queue.yml`**: Blogger publishing queue

In CI, government data is collected first (`scripts/collect_gov_data.py`), then `main.py` runs.

## Configuration Files

- `config/categories.yaml` — RSS feeds, archive paths, keyword filters, and fallback feeds per category (ai, xr, gov)
- `config/members.yaml` — member company names and search keywords

## In-Development Modules

`src/parser/` (base, youtube, article) and `src/llm/summarizer.py` are newly added (untracked in git) and not yet integrated into the main pipeline.
