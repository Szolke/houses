# Ingatlan Portfólió

Statikus ingatlan-bemutató oldal — GitHub Pages / Cloudflare Pages kompatibilis.

## Struktúra

```
ingatlan-site/
├── index.html              # Főoldal (statikus)
├── data/
│   └── properties.json     # Ingatlanok adatai
├── images/
│   └── <slug>/             # Letöltött képek ingatlanonként
│       ├── img_01.jpeg
│       └── ...
├── ingatlan_add.py         # Skill: új ingatlan hozzáadása
└── README.md
```

## Új ingatlan hozzáadása

### Előfeltételek

```bash
pip install requests beautifulsoup4
```

### Futtatás

```bash
python ingatlan_add.py https://varos.hu/ingatlan/valami-haz-neve
```

A script:
1. Letölti az oldalt
2. Kinyeri az adatokat (cím, ár, méret, képek stb.)
3. Letölti az összes képet az `images/<slug>/` mappába
4. Hozzáadja az ingatlant a `data/properties.json` fájlhoz

### Utána

```bash
git add .
git commit -m "Új ingatlan: ..."
git push
```

Cloudflare Pages automatikusan újra deploy-olja.

## Manuális szerkesztés

A `data/properties.json` fájl szabadon szerkeszthető. Mezők:

| Mező | Típus | Leírás |
|---|---|---|
| `id` / `slug` | string | Egyedi azonosító (URL-ből) |
| `title` | string | Teljes cím |
| `shortTitle` | string | Kártyán megjelenő rövidített cím |
| `price` | string | Ár (szóközzel tagolt, pl. "129 000 000") |
| `currency` | string | Pénznem (Ft) |
| `location` | string | Helyszín |
| `size` | number | Alapterület m²-ben |
| `plotSize` | number | Telek m²-ben |
| `balconySize` | number | Erkély/terasz m²-ben |
| `bedrooms` | number | Hálószobák száma |
| `livingRooms` | number | Nappalík száma |
| `bathrooms` | number | Fürdőszobák száma |
| `builtYear` | number | Építés éve |
| `renovatedYear` | number/null | Felújítás éve |
| `condition` | string | Állapot |
| `heating` | string | Fűtés |
| `parking` | string | Parkolás |
| `orientation` | string | Tájolás |
| `energyRating` | string | Energetikai besorolás |
| `status` | string | "Eladó" / "Kiadó" |
| `sourceUrl` | string | Eredeti hirdetés URL |
| `description` | string | Leírás (sortörés: `\n`) |
| `extras` | string[] | Extrák listája |
| `rooms` | string[] | Helyiségek listája |
| `contact.name` | string | Értékesítő neve |
| `contact.title` | string | Pozíció |
| `contact.phone` | string | Telefonszám |
| `contact.company` | string | Iroda neve |
| `images` | string[] | Képek relatív útvonalai |

## Cloudflare Pages deploy

1. GitHub repóba push
2. Cloudflare Pages → New project → GitHub repo kiválasztása
3. Build command: *(üres)*
4. Output directory: `/` (root)
5. Deploy!

## Technikai megjegyzések

- Teljesen statikus: nincs szerver, nincs build lépés
- Képek lokálisan tárolva → nem függ külső oldal elérhetőségétől
- `data/properties.json` betöltése `fetch()`-el történik kliens oldalon
- Cloudflare Pages-en a `fetch('data/properties.json')` működik (CORS-mentes saját domain)
