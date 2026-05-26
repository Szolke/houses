"""
Teszt 2: ingatlan.com galéria képek kinyerése
"""
import re, json
from playwright.sync_api import sync_playwright

URL = "https://ingatlan.com/35387948"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )

    # Hálózati kérések figyelése - képek URL-jei
    image_requests = []
    page.on("request", lambda req: image_requests.append(req.url)
            if any(req.url.endswith(x) for x in ['.jpg','.jpeg','.png','.webp'])
            and 'ip.ingatlancdn.com' in req.url else None)

    page.goto(URL, wait_until="networkidle", timeout=30000)

    # Próbáljuk megnyitni a galériát - első képre kattintás
    try:
        first_img = page.query_selector("img[src*='ip.ingatlancdn.com']")
        if first_img:
            first_img.click()
            page.wait_for_timeout(2000)
            print("Galériára kattintottam")
    except Exception as e:
        print(f"Kattintás sikertelen: {e}")

    # Várjuk meg hogy több kép töltődjön be
    page.wait_for_timeout(3000)

    html = page.content()

    # ip.ingatlancdn.com képek a teljes HTML-ből
    ip_imgs = re.findall(r'https://ip\.ingatlancdn\.com/[^\s"\'<>]+', html)
    ip_imgs = list(set(ip_imgs))
    print(f"\n=== ip.ingatlancdn.com képek a HTML-ben: {len(ip_imgs)} ===")
    for u in ip_imgs:
        print(f"  {u[:120]}")

    # Hálózaton átmenő képkérések
    print(f"\n=== Hálózati kép-kérések: {len(image_requests)} ===")
    for u in image_requests:
        print(f"  {u[:120]}")

    # JSON-LD adatok (strukturált adatok)
    scripts = page.query_selector_all("script[type='application/ld+json']")
    print(f"\n=== JSON-LD scriptek: {len(scripts)} ===")
    for s in scripts:
        try:
            data = json.loads(s.inner_text())
            print(json.dumps(data, ensure_ascii=False, indent=2)[:500])
        except:
            pass

    # __NEXT_DATA__ vagy hasonló state
    next_data = page.query_selector("script#__NEXT_DATA__")
    if next_data:
        print("\n=== __NEXT_DATA__ találtam! ===")
        try:
            data = json.loads(next_data.inner_text())
            # Képek keresése
            text = json.dumps(data)
            imgs = re.findall(r'ip\.ingatlancdn\.com/[^"\'\\s]+', text)
            print(f"Képek a NEXT_DATA-ban: {len(set(imgs))}")
            for u in list(set(imgs))[:10]:
                print(f"  https://{u}")
        except Exception as e:
            print(f"Hiba: {e}")

    # H1
    h1s = page.query_selector_all("h1")
    for h in h1s:
        t = h.inner_text().strip()
        if t:
            print(f"\nH1: {t}")

    browser.close()