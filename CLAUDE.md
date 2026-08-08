# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A GitHub Pages site that answers "is the vegan option available today at Mensa NF 304, Ausgabe D (Heidelberg)?". It has two components:

1. **`scraper.py`** — fetches the mensa page (which embeds a `window.mensaData` JSON blob), classifies each dish as `vegan` / `not_vegan` / `unclear` using allergen codes, and writes `menu.json`.
2. **`index.html`** — a self-contained static page that fetches `menu.json` at runtime, groups days by ISO week, and renders a colour-coded card view. No build step.

## Running the scraper locally

```bash
MENSA_URL="<the stw.uni-heidelberg.de page URL>" python scraper.py
```

`MENSA_URL` must be set; the script exits with an error otherwise. The output is written to `menu.json` in the working directory.

## Vegan classification logic

`scraper.py:classify_vegan` applies in order:

1. **vegan** — the word "vegan" appears anywhere in the German text, English text, or allergen string.
2. **not_vegan** — allergen codes `ML` (milk), `Ei` (egg), `Fi` (fish), or `Kr` (crustaceans) are present.
3. **unclear** — everything else (plant-based but no explicit "vegan" label and no disqualifying allergens).

The day-level `vegan_status` is `vegan` if any dish is vegan, `not_vegan` if any dish is not vegan (and none is vegan), otherwise `unclear`.

## Automation

`.github/workflows/update-menu.yml` runs **daily** at 06:30 UTC and unconditionally re-scrapes, committing `menu.json` only when it actually changed.

Daily rather than weekly on purpose: the Studierendenwerk sometimes publishes a menu week late and serves `geschlossen: true` placeholders for every day in the meantime. Under the old weekly schedule one unlucky Monday snapshot froze "closed" onto the site for a full week. A daily re-run self-heals within 24h.

`next_fetch_date` in `menu.json` is informational only (the last date present in the scraped data); nothing reads it any more.

The `MENSA_URL` is stored as a GitHub Actions repository variable (not a secret), under Settings → Variables → Actions.

## Data flow

```
stw.uni-heidelberg.de page (window.mensaData)
  → scraper.py
    → menu.json  (committed by the workflow bot)
      → index.html (fetched client-side, rendered in browser)
```

`menu.json` is committed directly to the repo and served via GitHub Pages alongside `index.html`.
