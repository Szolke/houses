#!/usr/bin/env python3
"""
ingatlan_add.py — Új ingatlan hozzáadása a portfólióhoz
========================================================
Használat:
    python ingatlan_add.py <URL>

Példa:
    python ingatlan_add.py https://varos.hu/ingatlan/valami-haz

Követelmények:
    pip install requests beautifulsoup4
"""

import sys
import os
import re
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Hiányzó csomagok. Futtasd: pip install requests beautifulsoup4")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DATA_FILE  = SCRIPT_DIR / "data" / "properties.json"
IMAGES_DIR = SCRIPT_DIR / "images"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]

def clean_text(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def parse_price(text: str) -> str:
    """'129 000 000 Ft' -> '129 000 000'"""
    cleaned = re.sub(r"[^\d\s]", " ", text)
    m = re.search(r"\d[\d\s]{4,}\d", cleaned)
    return m.group().strip() if m else ""

def parse_int(text) -> int | None:
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None

def make_soup(html: str) -> "BeautifulSoup":
    try:
        import lxml  # noqa
        return BeautifulSoup(html, "lxml")
    except ImportError:
        return BeautifulSoup(html, "html.parser")

# ── varos.hu scraper ─────────────────────────────────────────────────────────

def scrape_varos_hu(html: str, url: str, slug: str) -> dict:
    soup = make_soup(html)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    # ── Cím ──
    h2 = soup.find("h2")
    title = clean_text(h2.get_text()) if h2 else slug.replace("-", " ").title()

    # ── Ár ──
    price = ""
    for el in soup.find_all(string=re.compile(r"\d[\d\s]*Ft")):
        price = parse_price(clean_text(el))
        if price:
            break

    # ── Képek ──
    # varos.hu a galériát JS-sel rendereli, de a nyers HTML-ben benne vannak
    # a thumbnail <img src="..._t.jpeg"> és <a href="..._t.jpeg"> tagek.
    # A full-res URL: _t.jpeg -> .jpeg (csak a _t suffixet kell eltávolítani)
    images = []
    seen   = set()

    def add_image(src: str):
        if not src or "/storage/listings/" not in src:
            return
        # thumbnail -> full-res
        full_src = re.sub(r"_t(\.\w+)$", r"\1", src)
        full_url = full_src if full_src.startswith("http") else base + full_src
        if full_url not in seen:
            seen.add(full_url)
            images.append(full_url)

    # <a href>
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "/storage/listings/" in href and href.lower().endswith((".jpeg", ".jpg", ".png", ".webp")):
            add_image(href)

    # <img src> és data-src
    for tag in soup.find_all("img"):
        add_image(tag.get("src", ""))
        add_image(tag.get("data-src", ""))
        add_image(tag.get("data-lazy-src", ""))

    # Ha HTML-ben regex-szel keresünk (pl. JS inline string-ek)
    # varos.hu inline JS-be is beleírja a képek listáját
    raw_html_matches = re.findall(
        r'["\'](/storage/listings/[^"\']+\.(?:jpeg|jpg|png|webp))["\']',
        html
    )
    for src in raw_html_matches:
        add_image(src)

    print(f"  [debug] Kép URL-ek találva: {len(images)}")

    # ── Adatok (dt/dd, tr/td, definition list) ──
    data = {}
    # <tr><td>Kulcs</td><td>Érték</td></tr>
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            k = clean_text(cells[0].get_text()).lower()
            v = clean_text(cells[1].get_text())
            if k and v:
                data[k] = v
    # <dt>/<dd> párok
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            k = clean_text(dt.get_text()).lower()
            v = clean_text(dd.get_text())
            if k and v:
                data[k] = v

    # ── Leírás ──
    description = ""
    # Leghosszabb <p> blokkok összefűzése
    paras = [p for p in soup.find_all("p") if len(p.get_text(strip=True)) > 80]
    if paras:
        description = "\n\n".join(clean_text(p.get_text()) for p in paras[:6])

    # ── Helyszín ──
    location = "Szeged"
    for a in soup.select("a[href*='/terulet/']"):
        t = clean_text(a.get_text())
        if t:
            location = t  # utolsó = legszűkebb régió

    # ── Kontakt ──
    contact = {"company": "Városi Ingatlaniroda"}
    for a in soup.find_all("a", href=re.compile(r"munkatars")):
        name = clean_text(a.get_text())
        if name and len(name) > 3:
            contact["name"] = name
            break
    phone_m = re.search(r"\+36[\s\d()\-]{8,15}", soup.get_text())
    if phone_m:
        contact["phone"] = clean_text(phone_m.group())

    # ── Segédfüggvény az adatok kiolvasásához ──
    def get(default=None, as_int=False, *keys):
        for key in keys:
            for k, v in data.items():
                if key in k:
                    return parse_int(v) if as_int else v
        return default

    def geti(*keys, default=0):
        return get(default, True, *keys)

    def gets(*keys, default=""):
        return get(default, False, *keys)

    return {
        "id":            slug,
        "slug":          slug,
        "title":         title,
        "shortTitle":    title,
        "price":         price,
        "currency":      "Ft",
        "location":      location,
        "size":          geti("méret", "alapter"),
        "plotSize":      geti("telek"),
        "balconySize":   geti("erkély", "terasz", "erkely"),
        "bedrooms":      geti("háló", "hálószoba"),
        "livingRooms":   geti("nappali") or 1,
        "bathrooms":     geti("fürdő") or 1,
        "floors":        geti("szint", "emelet") or 1,
        "type":          gets("típus", "jelleg") or "Családi ház",
        "material":      gets("anyag", "építési"),
        "builtYear":     geti("épít") or None,
        "renovatedYear": geti("felúj") or None,
        "condition":     gets("állapot"),
        "heating":       gets("fűtés"),
        "parking":       gets("parkolás"),
        "orientation":   gets("tájolás"),
        "energyRating":  gets("energia", "tanúsítvány"),
        "status":        "Eladó",
        "sourceUrl":     url,
        "description":   description,
        "extras":        [],
        "rooms":         [],
        "contact":       contact,
        "images":        [],         # download lépésben töltjük fel
        "_raw_images":   images,     # temp
    }

# ── Általános scraper ────────────────────────────────────────────────────────

def scrape_generic(html: str, url: str, slug: str) -> dict:
    soup = make_soup(html)
    title = clean_text(soup.title.get_text()) if soup.title else slug

    desc_meta = (soup.find("meta", property="og:description") or
                 soup.find("meta", attrs={"name": "description"}))
    description = desc_meta.get("content", "") if desc_meta else ""

    og_img = soup.find("meta", property="og:image")
    images = [og_img["content"]] if og_img and og_img.get("content") else []

    price_m = re.search(r"[\d\s]{6,}(?:\s*Ft|HUF)", soup.get_text())
    price = parse_price(price_m.group()) if price_m else ""

    return {
        "id": slug, "slug": slug, "title": title, "shortTitle": title,
        "price": price, "currency": "Ft", "location": "", "size": 0,
        "plotSize": 0, "balconySize": 0, "bedrooms": 0, "livingRooms": 1,
        "bathrooms": 1, "floors": 1, "type": "Ingatlan", "material": "",
        "builtYear": None, "renovatedYear": None, "condition": "",
        "heating": "", "parking": "", "orientation": "", "energyRating": "",
        "status": "Eladó", "sourceUrl": url, "description": description,
        "extras": [], "rooms": [], "contact": {},
        "images": [], "_raw_images": images,
    }

# ── Képletöltő ───────────────────────────────────────────────────────────────

def download_images(image_urls: list, slug: str) -> list:
    target_dir = IMAGES_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    local_paths = []
    for i, img_url in enumerate(image_urls, 1):
        ext = os.path.splitext(urlparse(img_url).path)[-1] or ".jpeg"
        filename  = f"img_{i:02d}{ext}"
        filepath  = target_dir / filename
        rel_path  = f"images/{slug}/{filename}"

        if filepath.exists() and filepath.stat().st_size > 1000:
            print(f"  [kész] {filename}")
            local_paths.append(rel_path)
            continue

        try:
            req = urllib.request.Request(img_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            kb = len(data) // 1024
            print(f"  ✓ {filename}  ({kb} KB)")
            local_paths.append(rel_path)
        except Exception as e:
            print(f"  ✗ {filename}  — {e}")
            local_paths.append(img_url)   # fallback: eredeti URL

    return local_paths

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url  = sys.argv[1].strip()
    slug = slug_from_url(url)

    print(f"\n🏠 Ingatlan feldolgozása: {slug}")
    print(f"   URL: {url}\n")

    # Meglévő adatok
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    properties = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []

    # Duplikáció ellenőrzés
    if slug in [p["slug"] for p in properties]:
        print(f"⚠️  Már szerepel az adatbázisban: {slug}")
        if input("Felülírjuk? [i/N] ").strip().lower() != "i":
            sys.exit(0)
        properties = [p for p in properties if p["slug"] != slug]

    # Oldal letöltése
    print("⬇️  Oldal letöltése...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text
    except Exception as e:
        print(f"✗ Letöltési hiba: {e}")
        sys.exit(1)

    # Scraping
    print("🔍 Adatok kinyerése...")
    domain = urlparse(url).netloc
    if "varos.hu" in domain:
        prop = scrape_varos_hu(html, url, slug)
    else:
        prop = scrape_generic(html, url, slug)
        print(f"  ⚠️  Ismeretlen forrás ({domain}) — ellenőrizd kézzel a properties.json-t!")

    print(f"  Cím:   {prop['title']}")
    print(f"  Ár:    {prop['price']} {prop['currency']}")
    print(f"  Képek: {len(prop.get('_raw_images', []))} db")

    # Képek letöltése
    raw = prop.pop("_raw_images", [])
    if raw:
        print(f"\n📸 {len(raw)} kép letöltése...")
        prop["images"] = download_images(raw, slug)
    else:
        print("  ⚠️  Nem találtam képeket — ellenőrizd manuálisan.")
        prop["images"] = []

    # Mentés
    properties.append(prop)
    DATA_FILE.write_text(json.dumps(properties, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Kész!  ({len(properties)} ingatlan az adatbázisban)")
    print(f"\nKövetkező lépés:")
    print(f"  git add .")
    print(f'  git commit -m "Új ingatlan: {prop["title"][:50]}"')
    print(f"  git push\n")


if __name__ == "__main__":
    main()
