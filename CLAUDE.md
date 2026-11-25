# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A GitHub Pages site that answers "is the vegan option available today at Mensa NF 304, Ausgabe D (Heidelberg)?". It has two components:

1. **`scraper.py`** — fetches the mensa page (which embeds a `window.mensaData` JSON blob), classifies each dish as `vegan` / `not_vegan` / `unclear` using allergen codes, writes `menu.json`, and merges the scraped days into the long-term archive `history.json`.
2. **`index.html`** — a self-contained static page with two tabs: *Speiseplan* (fetches `menu.json`, hero card for today + week cards) and *Statistik* (`#statistik`, lazily fetches `history.json`: overall vegan share, week-by-week grid, share per weekday). No build step.

## history.json

Archive of every Ausgabe-D day ever scraped (slim: date, weekday, closed, status, dish text, reasons). Each run overwrites the dates it scraped (so "closed" placeholders get fixed) and leaves older dates frozen. It was backfilled once from the git history of `menu.json` (back to 27.04.2026), re-classifying every snapshot with the current classifier. If the classifier changes again, the archive keeps the old verdicts unless it is backfilled again the same way.

## Running the scraper locally

```bash
MENSA_URL="<the stw.uni-heidelberg.de page URL>" python scraper.py
```

`MENSA_URL` must be set; the script exits with an error otherwise. The output is written to `menu.json` in the working directory.

## Vegan classification logic

Codes are collected from **every** parenthetical group in the German and English text (`scraper.py:extract_codes`), not just the last one: Ausgabe D dishes often have several components on separate lines, each with its own code list (e.g. `Gnocchi mit Rahmkürbis (3,5,GlWe,ML)\nWeißkrautsalat (3,5,Sf)`). Codes are normalised (`+ML`, `Ml` → `ML`) against `CODE_LEGEND`, which mirrors the official legend on the Studierendenwerk menu page.

`scraper.py:classify_vegan` applies in order:

1. **not_vegan** — any animal-product code: `ML` (milk), `Ei`, `Fi`, `Kr`, `We` (molluscs), `13`–`16` (pork, poultry, beef, game). Beats a "vegan" label.
2. **vegan** — `vegan` code, or the word vegan/vegane/veganer… in the text.
3. **not_vegan** — no vegan label, but the description names an animal product (`NON_VEGAN_WORDS`: Käse, Sahne, Hähnchen, …).
4. **unclear** — everything else.

Each dish in `menu.json` also carries `codes` (`[{code, label}]`) and `reasons` (why it is not vegan), which the page shows.

The day-level `vegan_status` is `vegan` if any dish is vegan, `not_vegan` if any dish is not vegan (and none is vegan), otherwise `unclear`.

## Automation

`.github/workflows/update-menu.yml` runs **daily** at 06:30 UTC and unconditionally re-scrapes, committing `menu.json` and `history.json` only when they actually changed.

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

## Privacy, fonts and analytics

- Fonts (Inter, Fraunces; SIL OFL) are self-hosted in `fonts/`. Do not reintroduce Google Fonts or other third-party CDNs: embedding them sends every visitor's IP to the third party.
- Page views are counted with GoatCounter (cookieless). It is configured by the `GC_CODE` constant near the top of the `<script>` in `index.html`; an empty string disables tracking entirely and hides the GoatCounter paragraph in the footer's privacy note. Opening the Statistik tab is sent as the event `tab-statistik`.
