#!/usr/bin/env python3
"""
Fetches the Mensa NF 304 menu page, extracts window.mensaData,
and writes a processed menu.json for the GitHub Pages site.

Set the MENSA_URL environment variable (or the Actions variable) to the
URL of the mensa page that embeds window.mensaData.
Example: https://www.stw.uni-heidelberg.de/essen-trinken/speiseplan/
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

# Official legend from the Studierendenwerk menu page (allergens, additives,
# meat labels). Used to explain codes in the UI.
CODE_LEGEND = {
    "1": "Farbstoff", "2": "Konservierungsstoff", "3": "Antioxidationsmittel",
    "4": "Geschmacksverstärker", "5": "geschwefelt", "6": "geschwärzt",
    "7": "gewachst", "8": "Süßungsmittel", "9": "Phosphat",
    "10": "Farbstoff (Aufmerksamkeit)", "11": "Phenylalaninquelle",
    "12": "Süßungsmittel (abführend)", "13": "Schweinefleisch",
    "14": "Geflügelfleisch", "15": "Rindfleisch", "16": "Wild",
    "21": "Coffein", "22": "Chinin", "23": "Taurin",
    "25": "kakaohaltige Fettglasur", "26": "Nitritpökelsalz", "62": "Alkohol",
    "GlWe": "Weizen", "GlGe": "Gerste", "GlHa": "Hafer", "GlRo": "Roggen",
    "GlDi": "Dinkel", "GlKa": "Kamut", "Kr": "Krebstiere", "Ei": "Ei",
    "Fi": "Fisch", "Er": "Erdnuss", "So": "Soja", "ML": "Milch",
    "NuMa": "Mandeln", "NuWa": "Walnüsse", "NuHa": "Haselnüsse",
    "NuKa": "Cashew", "NuPe": "Pekannüsse", "NuPa": "Paranüsse",
    "NuPi": "Pistazien", "NuMd": "Macadamia", "Se": "Sellerie", "Sn": "Senf",
    "Sa": "Sesam", "Sf": "Sulfite", "Lu": "Lupinen", "We": "Weichtiere",
    "vegan": "vegan",
}
_CANONICAL = {k.lower(): k for k in CODE_LEGEND}

# Codes that mean an animal product is in the dish.
NON_VEGAN_CODES = {"ML", "Ei", "Fi", "Kr", "We", "13", "14", "15", "16"}

# Words that give a dish away even when the codes don't (only used when the
# dish carries no explicit vegan label). Matched as word stems.
NON_VEGAN_WORDS = [
    "käse", "parmesan", "mozzarella", "feta",
    "gorgonzola", "sahne", "schmand", "quark", "joghurt", "butter", "honig",
    "fleisch", "hähnchen", "huhn", "pute", "schwein", "rind", "speck",
    "schinken", "fisch", "lachs", "garnele", "gelatine",
]


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


def extract_codes(*texts: str) -> list:
    """
    Collect codes from *every* parenthetical group. A dish can have several
    components on separate lines, each with its own code list, e.g.
    "Gnocchi mit Rahmkürbis (3,5,GlWe,ML)\nWeißkrautsalat (3,5,Sf)".
    Codes are normalised ("+ML", "Ml" → "ML"); unknown tokens are dropped.
    """
    seen = []
    for text in texts:
        for group in re.findall(r"\(([^)]*)\)", text or ""):
            for tok in re.split(r"[,;\s]+", group):
                tok = tok.strip().lstrip("+")
                code = _CANONICAL.get(tok.lower())
                if code and code not in seen:
                    seen.append(code)
    return seen


def classify_vegan(text: str, text_en: str, codes: list) -> tuple:
    """
    Returns (status, reasons).

    not_vegan – an animal-product code is present in ANY component
                (ML, Ei, Fi, Kr, We, 13–16). Wins over a "vegan" label,
                because a mislabelled side (dip, cheese topping) still counts.
    vegan     – "vegan" code, or the word vegan/vegane/veganer… in the text.
    not_vegan – no vegan label, but the text names an animal product
                (Käse, Sahne, Hähnchen, …).
    unclear   – everything else.
    """
    bad = [c for c in codes if c in NON_VEGAN_CODES]
    if bad:
        return "not_vegan", [CODE_LEGEND[c] for c in bad]

    if "vegan" in codes or re.search(r"\bvegan", f"{text} {text_en}", re.I):
        return "vegan", []

    lower = text.lower()
    words = [w for w in NON_VEGAN_WORDS if w in lower]
    if words:
        return "not_vegan", [f"„{w.capitalize()}“ laut Beschreibung" for w in words[:2]]

    return "unclear", []


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%d.%m.%Y")


def process_data(raw: dict) -> dict:
    mensa = raw.get(MENSA_NAME, {})
    days = []

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
            text_en = g.get("text_en", "")
            codes = extract_codes(g["text"], text_en)
            status, reasons = classify_vegan(g["text"], text_en, codes)
            dishes.append({
                "text": g["text"],
                "text_en": text_en,
                "price_studi": g.get("studi", ""),
                "allergens": ",".join(codes),
                "codes": [
                    {"code": c, "label": CODE_LEGEND[c]}
                    for c in codes if c != "vegan"
                ],
                "vegan_status": status,
                "reasons": reasons,
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

    # Last date covered by the scrape — closed days count too, otherwise an
    # all-closed week (placeholder data) would leave this null.
    last_date = max((parse_date(d["date"]) for d in days), default=None)
    next_fetch_date = last_date.strftime("%Y-%m-%d") if last_date else None

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

    closed = sum(1 for d in result["days"] if d["closed"])
    open_ = len(result["days"]) - closed
    print(
        f"Wrote {len(result['days'])} days → {OUTPUT_FILE}  "
        f"({open_} open, {closed} closed; last date: {result['next_fetch_date']})",
        file=sys.stderr,
    )
    if open_ == 0 and closed:
        print(
            "WARNING: every day is marked closed. This is normal during the "
            "semester break, but can also mean the menu has not been published "
            "yet — the daily re-run will pick it up once it is.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
