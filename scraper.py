#!/usr/bin/env python3
"""
Fetches the Mensa NF 304 menu page, extracts window.mensaData,
and writes a processed menu.json for the GitHub Pages site.

Set the MENSA_URL environment variable (or the Actions variable) to the
URL of the mensa page that embeds window.mensaData.
Example: https://www.stw-ma.de/Essen+_Trinken-p-7.html
"""
import json
import os
import re
import sys
from datetime import datetime

import requests

MENSA_URL = os.environ.get("MENSA_URL", "")
MENSA_NAME = "Mensa Im Neuenheimer Feld 304"
OUTPUT_FILE = "menu.json"

# Allergen codes that make a dish non-vegan
NON_VEGAN_ALLERGENS = {"ML", "Ei", "Fi", "Kr"}


def fetch_mensa_data(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; vegan-mensa-bot/1.0)"}
    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    html = resp.text

    idx = html.find("window.mensaData")
    if idx == -1:
        raise ValueError("window.mensaData not found on page — check MENSA_URL")

    brace_idx = html.index("{", idx)
    data, _ = json.JSONDecoder().raw_decode(html, brace_idx)
    return data


def extract_allergens(text: str) -> str:
    """Return the last parenthetical group in the dish text (the allergen list)."""
    cleaned = text.replace("\n", " ").strip()
    m = re.search(r"\(([^)]+)\)\s*$", cleaned)
    return m.group(1) if m else ""


def classify_vegan(text: str, text_en: str, allergens: str) -> str:
    """
    vegan     – text or text_en explicitly contains the word 'vegan'
    not_vegan – allergen codes include ML (milk), Ei (egg), Fi (fish), or Kr (crustaceans)
    unclear   – everything else
    """
    combined = f"{text} {text_en} {allergens}".lower()
    if "vegan" in combined:
        return "vegan"
    codes = set(re.split(r"[,\s]+", allergens))
    if codes & NON_VEGAN_ALLERGENS:
        return "not_vegan"
    return "unclear"


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%d.%m.%Y")


def process_data(raw: dict) -> dict:
    mensa = raw.get(MENSA_NAME, {})
    days = []
    last_date_obj = None

    for date_str, day_data in sorted(mensa.items(), key=lambda x: parse_date(x[0])):
        tag = day_data.get("tag", "")
        if tag in ("Samstag", "Sonntag"):
            continue

        if day_data.get("geschlossen"):
            days.append({
                "date": date_str,
                "weekday": tag,
                "closed": True,
                "dishes": [],
                "vegan_status": "closed",
            })
            continue

        ausgabe_d = next(
            (l for l in day_data.get("linien", []) if l.get("ausgabe") == "D"),
            None,
        )
        if ausgabe_d is None:
            continue

        dishes = []
        for g in ausgabe_d.get("gerichte", []):
            allergens = extract_allergens(g["text"])
            status = classify_vegan(g["text"], g.get("text_en", ""), allergens)
            dishes.append({
                "text": g["text"],
                "text_en": g.get("text_en", ""),
                "price_studi": g.get("studi", ""),
                "allergens": allergens,
                "vegan_status": status,
            })

        if any(d["vegan_status"] == "vegan" for d in dishes):
            day_status = "vegan"
        elif any(d["vegan_status"] == "not_vegan" for d in dishes):
            day_status = "not_vegan"
        else:
            day_status = "unclear"

        days.append({
            "date": date_str,
            "weekday": tag,
            "closed": False,
            "dishes": dishes,
            "vegan_status": day_status,
        })
        last_date_obj = parse_date(date_str)

    next_fetch_date = last_date_obj.strftime("%Y-%m-%d") if last_date_obj else None

    return {
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "next_fetch_date": next_fetch_date,
        "days": days,
    }


def main():
    if not MENSA_URL:
        print(
            "ERROR: Set the MENSA_URL environment variable to the mensa page URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Fetching {MENSA_URL} …", file=sys.stderr)
    raw = fetch_mensa_data(MENSA_URL)
    result = process_data(raw)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"Wrote {len(result['days'])} days → {OUTPUT_FILE}  "
        f"(next fetch: {result['next_fetch_date']})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
