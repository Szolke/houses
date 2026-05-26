"""
Teszt: posztolom.com oldal JS-renderelés után
Futtasd: python teszt_posztolom.py
"""
import re, json
from playwright.sync_api import sync_playwright

URL = "https://ingatlan.posztolom.com/ujszeged-marostoi-varosreszeben-kinalunk-eladasra-egy-eldugott-739-m2-es-telken-131-m2-es-1990-ben-epult-szigetelt-gyonyoru-intim-kerttel-rendelkezo-nappali-plusz-4-haloszobas-jo-allapotu-felujitott-dupla-komfortos-csaladi-hazat/104487"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    print("Oldal betöltése...")
    page.goto(URL, wait_until="networkidle", timeout=30000)
    
    html = page.content()
    
    # Képek keresése
    images = page.query_selector_all("img")
    print(f"\nTalált <img> tagek: {len(images)}")
    for img in images[:5]:
        src = img.get_attribute("src") or img.get_attribute("data-src") or ""
        if src and len(src) > 10:
            print(f"  {src[:100]}")
    
    # Ár keresése
    price_els = page.query_selector_all("*")
    for el in price_els:
        try:
            text = el.inner_text()
            if re.search(r"\d[\d\s]{5,}\s*Ft", text) and len(text) < 30:
                print(f"\nÁr találat: '{text.strip()}'")
                break
        except:
            pass
    
    # Cím
    h1 = page.query_selector("h1")
    if h1:
        print(f"\nH1: {h1.inner_text()[:100]}")
    
    browser.close()
    print("\nHTML méret:", len(html), "karakter")
    
    # Képek URL-ek regex-szel a HTML-ből
    img_urls = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp)', html)
    img_urls = list(set(img_urls))
    print(f"\nKép URL-ek a HTML-ben: {len(img_urls)}")
    for u in img_urls[:5]:
        print(f"  {u[:100]}")