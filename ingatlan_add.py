#!/usr/bin/env python3
"""
ingatlan_add.py — Új ingatlan hozzáadása a portfólióhoz
========================================================
Használat:
    python ingatlan_add.py <URL>

Példa:
    python ingatlan_add.py https://varos.hu/ingatlan/valami-haz

A script:
  1. Leszedi az oldalt
  2. Kinyeri az ingatlan adatait (cím, ár, képek, leírás stb.)
  3. Letölti a képeket az images/<slug>/ mappába
  4. Hozzáadja az ingatlant a data/properties.json fájlhoz
  5. NEM ír felül meglévő bejegyzést (slug alapján egyedi)

Követelmények:
    pip install requests beautifulsoup4
"""

import sys
import os
import re
import json
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Hiányzó csomagok. Futtasd: pip install requests beautifulsoup4")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "data" / "properties.json"
IMAGES_DIR = SCRIPT_DIR / "images"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def slug_from_url(url: str) -> str:
    """Kinyeri a slug-ot az URL-ből."""
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_price(text: str) -> str:
    """'129 000 000 Ft' -> '129 000 000'"""
    m = re.search(r"[\d\s]+(?=\s*Ft)", text)
    if m:
        return m.group().strip()
    digits = re.sub(r"\D", "", text)
    # Format with spaces
    if digits:
        return "{:,}".format(int(digits)).replace(",", " ")
    return ""


def parse_int(text: str) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


# ── Scrapers ─────────────────────────────────────────────────────────────────

def scrape_varos_hu(soup: BeautifulSoup, url: str, slug: str) -> dict:
    """varos.hu specifikus scraper."""

    # Cím
    h2 = soup.find("h2")
    title = clean_text(h2.text) if h2 else slug.replace("-", " ").title()

    # Ár
    price_raw = ""
    for el in soup.find_all(text=re.compile(r"\d[\d\s]*Ft")):
        price_raw = clean_text(el)
        break
    price = parse_price(price_raw)

    # Képek – a teljes méretű linkek (nem thumbnail _t)
    images = []
    for a in soup.find_all("a", href=re.compile(r"/storage/listings/.*\.jpeg$")):
        href = a["href"]
        if href not in images:
            images.append(href)
    # Fallback: img src
    if not images:
        for img in soup.find_all("img", src=re.compile(r"/storage/listings/")):
            src = img["src"]
            if "_t." not in src and src not in images:
                images.append(src)

    # Fix relative URLs
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    images = [
        (img if img.startswith("http") else base + img)
        for img in images
    ]

    # Adatok táblázatból
    data = {}
    rows = soup.find_all("tr") or []
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            key = clean_text(cells[0].text).lower()
            val = clean_text(cells[1].text)
            data[key] = val

    # Div-alapú adatok (varos.hu esetén)
    for pair in soup.select(".property-details li, .detail-row, .param-row"):
        spans = pair.find_all(["span", "strong", "b"])
        if len(spans) >= 2:
            key = clean_text(spans[0].text).lower()
            val = clean_text(spans[1].text)
            data[key] = val

    # Leírás
    desc_el = soup.find("p", class_=lambda c: c and "desc" in c) or \
              soup.find("div", class_=lambda c: c and "desc" in c)
    if not desc_el:
        # Hosszabb szövegblokk keresése
        candidates = [
            p for p in soup.find_all("p")
            if len(p.text.strip()) > 150
        ]
        desc_el = candidates[0] if candidates else None
    description = clean_text(desc_el.text) if desc_el else ""

    # Helyszín
    location = "Szeged"
    for breadcrumb in soup.select(".breadcrumb a, .location"):
        t = clean_text(breadcrumb.text)
        if t and t not in ("Főoldal", "Ingatlanok", ""):
            location = t

    # Kontakt
    contact = {}
    agent_name_el = soup.find("h2", class_=lambda c: c and "agent" in (c or "")) or \
                    soup.find("a", class_=lambda c: c and "munkatars" in urlparse(
                        (c or "")).path if hasattr(urlparse(c or ""), "path") else False)
    if not agent_name_el:
        for link in soup.find_all("a", href=re.compile(r"munkatars")):
            contact["name"] = clean_text(link.text)
            break
    phone_match = re.search(r"\+36[\s\d]{9,12}", soup.text)
    if phone_match:
        contact["phone"] = phone_match.group().strip()
    contact["company"] = "Városi Ingatlaniroda" if "varos.hu" in url else ""

    def get_data(*keys, default=None, as_int=False):
        for key in keys:
            for k, v in data.items():
                if key in k:
                    return parse_int(v) if as_int else v
        return default

    return {
        "id": slug,
        "slug": slug,
        "title": title,
        "shortTitle": title,
        "price": price,
        "currency": "Ft",
        "location": location,
        "size": get_data("méret", "alapter", default=0, as_int=True),
        "plotSize": get_data("telek", default=0, as_int=True),
        "balconySize": get_data("erkély", "terasz", default=0, as_int=True),
        "bedrooms": get_data("háló", default=0, as_int=True),
        "livingRooms": get_data("nappali", default=1, as_int=True),
        "bathrooms": get_data("fürdő", default=1, as_int=True),
        "floors": get_data("szint", "emelet", default=1, as_int=True),
        "type": get_data("típus", "jelleg", default="Családi ház"),
        "material": get_data("anyag", "építési", default=""),
        "builtYear": get_data("épít", "év", default=None, as_int=True),
        "renovatedYear": get_data("felúj", default=None, as_int=True),
        "condition": get_data("állapot", default=""),
        "heating": get_data("fűtés", default=""),
        "parking": get_data("parkolás", default=""),
        "orientation": get_data("tájolás", default=""),
        "energyRating": get_data("energia", "tanúsítvány", default=""),
        "status": "Eladó",
        "sourceUrl": url,
        "description": description,
        "extras": [],
        "rooms": [],
        "contact": contact,
        "images": [],  # filled after download
    }


def scrape_generic(soup: BeautifulSoup, url: str, slug: str) -> dict:
    """Általános scraper ismeretlen oldalakhoz."""
    title = clean_text(soup.title.text) if soup.title else slug
    # OG description
    desc_meta = soup.find("meta", property="og:description") or \
                soup.find("meta", attrs={"name": "description"})
    description = desc_meta["content"] if desc_meta and desc_meta.get("content") else ""

    # OG image
    og_img = soup.find("meta", property="og:image")
    images = [og_img["content"]] if og_img and og_img.get("content") else []

    price_m = re.search(r"[\d\s]{6,}(?:\s*Ft|HUF)", soup.text)
    price = parse_price(price_m.group()) if price_m else ""

    return {
        "id": slug,
        "slug": slug,
        "title": title,
        "shortTitle": title,
        "price": price,
        "currency": "Ft",
        "location": "",
        "size": 0,
        "plotSize": 0,
        "balconySize": 0,
        "bedrooms": 0,
        "livingRooms": 1,
        "bathrooms": 1,
        "floors": 1,
        "type": "Ingatlan",
        "material": "",
        "builtYear": None,
        "renovatedYear": None,
        "condition": "",
        "heating": "",
        "parking": "",
        "orientation": "",
        "energyRating": "",
        "status": "Eladó",
        "sourceUrl": url,
        "description": description,
        "extras": [],
        "rooms": [],
        "contact": {},
        "images": [],
    }


# ── Image download ────────────────────────────────────────────────────────────

def download_images(image_urls: list[str], slug: str) -> list[str]:
    """Letölti a képeket és visszaadja a relatív útvonalakat."""
    target_dir = IMAGES_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    local_paths = []
    for i, img_url in enumerate(image_urls, 1):
        ext = os.path.splitext(urlparse(img_url).path)[-1] or ".jpeg"
        filename = f"img_{i:02d}{ext}"
        filepath = target_dir / filename
        rel_path = f"images/{slug}/{filename}"

        if filepath.exists():
            print(f"  [kész] {filename}")
            local_paths.append(rel_path)
            continue

        try:
            req = urllib.request.Request(img_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(filepath, "wb") as f:
                    f.write(resp.read())
            print(f"  ✓ {filename} ({filepath.stat().st_size // 1024} KB)")
            local_paths.append(rel_path)
        except Exception as e:
            print(f"  ✗ Nem sikerült: {filename} — {e}")
            # Fallback: eredeti URL megtartása
            local_paths.append(img_url)

    return local_paths


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1].strip()
    slug = slug_from_url(url)

    print(f"\n🏠 Ingatlan feldolgozása: {slug}")
    print(f"   URL: {url}\n")

    # 1) Meglévő adatok betöltése
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            properties = json.load(f)
    else:
        properties = []

    # 2) Duplikáció ellenőrzés
    existing_slugs = [p["slug"] for p in properties]
    if slug in existing_slugs:
        print(f"⚠️  Ez az ingatlan már szerepel az adatbázisban: {slug}")
        ans = input("Felülírjuk? [i/N] ").strip().lower()
        if ans != "i":
            print("Kilépés.")
            sys.exit(0)
        properties = [p for p in properties if p["slug"] != slug]

    # 3) Oldal letöltése
    print("⬇️  Oldal letöltése...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except Exception as e:
        print(f"✗ Nem sikerült letölteni az oldalt: {e}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "html.parser")

    # 4) Adatok kinyerése
    print("🔍 Adatok kinyerése...")
    domain = urlparse(url).netloc
    if "varos.hu" in domain:
        prop = scrape_varos_hu(soup, url, slug)
    else:
        prop = scrape_generic(soup, url, slug)
        print(f"  ⚠️  Ismeretlen forrás ({domain}), általános scrappert használok.")
        print("      Kérlek ellenőrizd kézzel az adatokat a data/properties.json fájlban!")

    print(f"  Cím: {prop['title']}")
    print(f"  Ár:  {prop['price']} {prop['currency']}")
    print(f"  Képek száma: {len(prop.get('_raw_images', prop.get('images', [])))}")

    # 5) Képek letöltése
    raw_images = prop.pop("_raw_images", None) or prop.get("images", [])
    if raw_images:
        print(f"\n📸 {len(raw_images)} kép letöltése...")
        local_images = download_images(raw_images, slug)
        prop["images"] = local_images
    else:
        print("  ⚠️  Nem találtam képeket.")
        prop["images"] = []

    # 6) Mentés
    properties.append(prop)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(properties, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Kész! Az ingatlan hozzáadva: {DATA_FILE}")
    print(f"   Összesen {len(properties)} ingatlan az adatbázisban.\n")

    print("Következő lépés:")
    print("  git add .")
    print('  git commit -m "Új ingatlan: ' + prop["title"][:50] + '"')
    print("  git push")


if __name__ == "__main__":
    main()
