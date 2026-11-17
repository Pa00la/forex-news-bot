"""Image cards for the channel (Pillow). Free, runs inside GitHub Actions, no accounts needed."""
import io, os, subprocess, sys

BRAND = "Maged | Forex News"
HANDLE = "t.me/forex_news_M1"

try:
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # fresh runner: install once, then import
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pillow", "arabic-reshaper", "python-bidi"],
                   check=False)
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display

_RESHAPER = arabic_reshaper.ArabicReshaper(configuration={"use_unshaped_instead_of_isolated": True})

W = 1080
BG, PANEL, GOLD = (11, 18, 32), (20, 30, 50), (245, 185, 66)
WHITE, GREY = (240, 244, 250), (150, 164, 188)
GREEN, RED = (46, 204, 113), (231, 76, 60)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATHS = [
    os.path.join(HERE, "Tajawal-ExtraBold.ttf"),
    os.path.join(HERE, "Tajawal-Bold.ttf"),
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]

def font(size):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.BASIC)
    return ImageFont.load_default()

def ar(s):
    s = str(s)
    if any("؀" <= ch <= "ۿ" for ch in s):
        return get_display(_RESHAPER.reshape(s))
    return s

def text(d, xy, s, size, fill=WHITE, anchor="ra"):
    d.text(xy, ar(s), font=font(size), fill=fill, anchor=anchor)

def wrap(d, s, size, maxw):
    """Greedy wrap, then tighten the width so the last line is not a lonely word."""
    base_lines = _wrap(d, s, size, maxw)
    n = len(base_lines)
    if n < 2:
        return base_lines
    w = maxw
    while w > maxw * 0.55:
        w -= 20
        cand = _wrap(d, s, size, w)
        if len(cand) != n:
            break
        base_lines = cand
    return base_lines

def _wrap(d, s, size, maxw):
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(ar(t), font=font(size)) <= maxw:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def base(height, title, subtitle=""):
    img = Image.new("RGB", (W, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 110], fill=PANEL)
    d.rectangle([0, 108, W, 114], fill=GOLD)
    d.text((40, 55), BRAND, font=font(40), fill=GOLD, anchor="lm")
    text(d, (W - 40, 55), title, 46, WHITE, "rm")
    if subtitle:
        text(d, (W - 40, 150), subtitle, 30, GREY, "ra")
    d.text((W // 2, height - 38), HANDLE, font=font(30), fill=GREY, anchor="mm")
    return img, d

def to_png(img):
    b = io.BytesIO(); img.save(b, "PNG", optimize=True); return b.getvalue()

def card_strength(rows, subtitle):
    """rows: [(code, arabic name, pct)] sorted strongest first."""
    h = 230 + 105 * len(rows) + 90
    img, d = base(h, "قوة العملات الآن", subtitle)
    mid = 470
    mx = max(abs(v) for _, _, v in rows) or 1
    y = 215
    for code, name, v in rows:
        col = GREEN if v >= 0 else RED
        d.rounded_rectangle([40, y, W - 40, y + 90], 16, fill=PANEL)
        text(d, (W - 65, y + 45), name, 36, WHITE, "rm")
        ln = int(abs(v) / mx * 200) + 6
        x0, x1 = (mid, mid + ln) if v >= 0 else (mid - ln, mid)
        d.rounded_rectangle([x0, y + 28, x1, y + 62], 8, fill=col)
        d.text((70, y + 45), f"{v:+.2f}%", font=font(34), fill=col, anchor="lm")
        y += 105
    return to_png(img)

def card_table(title, subtitle, rows):
    """rows: [(label, value string, pct or None)]"""
    h = 230 + 105 * len(rows) + 90
    img, d = base(h, title, subtitle)
    y = 215
    for label, val, pct in rows:
        d.rounded_rectangle([40, y, W - 40, y + 90], 16, fill=PANEL)
        text(d, (W - 65, y + 45), label, 36, WHITE, "rm")
        d.text((W // 2 + 40, y + 45), val, font=font(34), fill=GREY, anchor="rm")
        if pct is not None:
            col = GREEN if pct >= 0 else RED
            d.text((70, y + 45), f"{pct:+.2f}%", font=font(36), fill=col, anchor="lm")
        y += 105
    return to_png(img)

def card_result(country, name, actual, forecast, previous, verdict):
    img, d = base(900, "نتيجة الخبر", f"{country} - {name}")
    boxes = [("الفعلي", actual, GOLD), ("المتوقع", forecast, WHITE), ("السابق", previous, GREY)]
    x = W - 40
    bw = (W - 80 - 40) // 3
    for lab, val, col in boxes:
        x0 = x - bw
        d.rounded_rectangle([x0, 260, x, 520], 20, fill=PANEL)
        text(d, ((x0 + x) // 2, 315), lab, 34, GREY, "mm")
        d.text(((x0 + x) // 2, 430), val or "-", font=font(72), fill=col, anchor="mm")
        x = x0 - 20
    text(d, (W // 2, 640), verdict, 52, GOLD, "mm")
    text(d, (W // 2, 740), "للمعلومات فقط وليست توصية", 28, GREY, "mm")
    return to_png(img)

def card_tip(title, body, kicker="فكرة اليوم"):
    img, d = base(900, kicker)
    text(d, (W - 60, 210), title, 70, GOLD, "ra")
    d.rectangle([W - 60 - 140, 310, W - 60, 316], fill=GOLD)
    lines = wrap(d, body, 48, W - 140)
    y = 380
    for ln in lines:
        text(d, (W - 60, y), ln, 48, WHITE, "ra")
        y += 82
    return to_png(img)


CATS = [
    (("trump", "white house", "biden"), "ترامب", "$", (200, 50, 50)),
    (("fed ", "powell", "fomc", "warsh", "federal reserve", "waller", "fed's"), "الفيدرالي", "%", (52, 120, 220)),
    (("ecb", "lagarde"), "المركزي الأوروبي", "€", (40, 90, 200)),
    (("bank of england", "boe", "bailey"), "بنك إنجلترا", "£", (140, 60, 170)),
    (("boj", "ueda", "yen"), "بنك اليابان", "¥", (200, 70, 90)),
    (("nvidia", "stocks", "stock market", "wall street", "s&p", "nasdaq", "dow jones", "tesla", "apple", "microsoft", "tech "), "الأسهم", "STK", (40, 150, 120)),
    (("gold", "xau"), "الذهب", "Au", (230, 170, 40)),
    (("oil", "opec", "crude", "brent"), "النفط", "OIL", (90, 90, 100)),
    (("china", "xi ", "beijing", "tariff"), "الصين والتجارة", "CN", (210, 60, 40)),
    (("iran", "israel", "war", "ceasefire", "russia", "ukraine", "sanction"), "جيوسياسة", "!", (170, 60, 60)),
    (("cpi", "inflation", "nfp", "payroll", "gdp", "pce", "ppi", "retail", "jobless", "unemployment"), "بيانات اقتصادية", "#", (46, 160, 110)),
]

def pick_cat(english_title):
    import re
    t = (english_title or "").lower() + " "
    for keys, name, glyph, col in CATS:
        for k in keys:
            if re.search(r"(?<![a-z])" + re.escape(k.strip()) + r"(?![a-z])", t):
                return name, glyph, col
    return "عاجل", "!", (200, 50, 50)

QUERIES = {
    "ترامب": ["white house building", "american flag", "washington dc capitol"],
    "الفيدرالي": ["federal reserve building", "us dollar bills", "wall street"],
    "المركزي الأوروبي": ["euro banknotes", "frankfurt skyline", "european union flags"],
    "بنك إنجلترا": ["london city skyline", "british pound money", "big ben"],
    "بنك اليابان": ["tokyo skyline", "japanese yen", "tokyo night"],
    "الذهب": ["gold bars", "gold coins", "gold bullion"],
    "النفط": ["oil refinery", "oil drilling rig", "oil pump sunset"],
    "الأسهم": ["stock exchange", "stock market chart", "financial charts"],
    "الصين والتجارة": ["shipping containers port", "shanghai skyline", "cargo ship"],
    "جيوسياسة": ["city skyline night", "world map", "stormy sky"],
    "بيانات اقتصادية": ["stock market chart", "financial charts screen", "trading screen"],
    "عاجل": ["stock exchange trading floor", "financial district", "forex chart"],
}

def _crop_sq(data):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size; m = min(w, h)
    return im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((W, W))

TOPICS = [  # (regex on the English headline, photo searches) - checked before the broad category
    (r"nvidia|chip|semiconductor|\bai\b|artificial intelligence", ["semiconductor chip", "computer processor close up", "data center servers"]),
    (r"tesla|electric vehicle|\bev\b", ["electric car charging", "electric car"]),
    (r"apple|iphone", ["smartphone close up", "technology gadgets"]),
    (r"housing|mortgage|real estate|home sales|homebuilder", ["houses neighborhood aerial", "real estate buildings"]),
    (r"shipping|port|container|supply chain|freight", ["cargo ship", "shipping containers port"]),
    (r"inflation|cpi|prices|grocery|consumer", ["supermarket shelves", "shopping cart supermarket"]),
    (r"jobs|payroll|unemployment|hiring|labor", ["office building windows", "city skyline day"]),
    (r"treasury|yield|bond", ["us treasury building", "government building columns"]),
    (r"bank|banks|lender", ["bank building columns", "bank building exterior"]),
    (r"dollar|dxy|greenback", ["us dollar banknotes", "dollar bills close up"]),
    (r"\beuro\b|eurozone", ["euro banknotes", "european union flags"]),
    (r"yen|japan", ["tokyo skyline", "japanese yen banknotes"]),
    (r"pound|sterling|britain|\buk\b", ["london skyline", "british pound banknotes"]),
    (r"tariff|trade war|china", ["shipping containers port", "cargo ship"]),
    (r"retail sales|retail", ["shopping mall interior", "shopping street"]),
]
_BAD_TAGS = {"woman", "man", "girl", "boy", "people", "person", "child", "children", "portrait", "model", "face", "horse",
             "rider", "couple", "baby", "wedding", "fashion", "selfie", "dog", "cat"}

def topic_queries(title, cat):
    import re
    t = (title or "").lower()
    if cat in ("الذهب", "النفط", "الفيدرالي", "المركزي الأوروبي", "بنك إنجلترا", "بنك اليابان", "ترامب"):
        return QUERIES[cat]  # strong categories keep their own scenes
    for rx, qs in TOPICS:
        if re.search(rx, t):
            return qs
    return QUERIES.get(cat) or QUERIES["عاجل"]

def _links_pexels(key, q):
    import json, urllib.request, urllib.parse
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "per_page": 30, "orientation": "square"})
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0"})
    ph = json.loads(urllib.request.urlopen(req, timeout=20).read()).get("photos") or []
    return [p_["src"]["large"] for p_ in ph if not (set((p_.get("alt") or "").lower().replace(",", " ").split()) & _BAD_TAGS)]

def _links_pixabay(key, q):
    import json, urllib.request, urllib.parse
    for extra in ({"editors_choice": "true", "category": "business"}, {"editors_choice": "true"}, {}):
        url = "https://pixabay.com/api/?" + urllib.parse.urlencode({"key": key, "q": q, "image_type": "photo", "per_page": 50,
                                                                    "safesearch": "true", "min_width": 1000, **extra})
        hits = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()).get("hits") or []
        hits = [h for h in hits if not ({t_.strip() for t_ in (h.get("tags") or "").lower().split(",")} & _BAD_TAGS)]
        if hits:
            return [h["largeImageURL"] for h in hits]
    return []

def _links_openverse(key, q):
    """No key needed. CC0 / public-domain photographs only, so no attribution is required."""
    import json, urllib.request, urllib.parse
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "license": "cc0,pdm", "category": "photograph", "size": "large", "page_size": 20})
    res = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()).get("results") or []
    return [r["url"] for r in res if r.get("url")]

def fetch_bg(cat, seed, title=""):
    """Optional royalty-free photo. Uses every library that has a key (PEXELS_KEY, PIXABAY_KEY), in a
    per-news random order, and falls back to the next one if a library fails. Places/objects only."""
    providers = []
    if os.environ.get("PEXELS_KEY", "").strip(): providers.append(("pexels", _links_pexels, os.environ["PEXELS_KEY"].strip()))
    if os.environ.get("PIXABAY_KEY", "").strip(): providers.append(("pixabay", _links_pixabay, os.environ["PIXABAY_KEY"].strip()))
    import random, urllib.request, zlib
    rnd = random.Random(zlib.crc32(str(seed).encode()))
    rnd.shuffle(providers)
    providers.append(("openverse", _links_openverse, ""))  # keyless last resort
    qs = topic_queries(title, cat)
    for name, fn, key in providers:
        try:
            links = fn(key, rnd.choice(qs))
            if not links:
                continue
            data = urllib.request.urlopen(urllib.request.Request(rnd.choice(links), headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
            return _crop_sq(data)
        except Exception as ex:
            print(f"{name} failed:", ex)
    return None

PERSON_CATS = ("ترامب", "الفيدرالي", "المركزي الأوروبي", "بنك إنجلترا", "بنك اليابان")

def draw_silhouette(img, col):
    """Generic anonymous suit silhouette (not a real person) shown on central-bank / politics news."""
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    cx, by = W // 2 + 250, W - 110
    o.ellipse([cx - 95, by - 520, cx + 95, by - 330], fill=col + (42,))
    o.polygon([(cx - 260, by), (cx - 215, by - 250), (cx - 60, by - 320), (cx + 60, by - 320),
               (cx + 215, by - 250), (cx + 260, by)], fill=col + (42,))
    o.polygon([(cx - 30, by - 320), (cx + 30, by - 320), (cx + 15, by - 200), (cx - 15, by - 200)], fill=(255, 255, 255, 60))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

def _ctext(d, cx, cy, s_, size, fill):
    """Center text on its real ink box (anchor 'mm' leaves big capital letters sitting too high)."""
    f = font(size)
    l, t, r, b = d.textbbox((0, 0), ar(s_), font=f, anchor="la")
    d.text((cx - (l + r) / 2, cy - (t + b) / 2), ar(s_), font=f, fill=fill, anchor="la")

def _footer(d, source, dark=True):
    d.rectangle([0, W - 110, W, W], fill=PANEL)
    d.text((40, W - 55), BRAND, font=font(36), fill=GOLD, anchor="lm")
    d.text((W - 40, W - 55), HANDLE, font=font(30), fill=GREY, anchor="rm")
    if source:
        text(d, (W - 65, W - 150), "المصدر: " + source, 28, GREY, "ra")

def _pill(d, xy, label, size, fill, fg=WHITE):
    w = int(d.textlength(ar(label), font=font(size))) + 60
    x, y = xy
    d.rounded_rectangle([x - w // 2, y - size, x + w // 2, y + size], 20, fill=fill)
    text(d, (x, y), label, size, fg, "mm")

def _fit(d, s, maxw, maxlines, sizes=(72, 64, 56, 48)):
    for size in sizes:
        lines = wrap(d, s, size, maxw)
        if len(lines) <= maxlines:
            return size, lines
    return sizes[-1], wrap(d, s, sizes[-1], maxw)[:maxlines]

def _lines(d, lines, size, x, y, anchor="ra", fill=WHITE):
    for ln in lines:
        text(d, (x, y), ln, size, fill, anchor)
        y += int(size * 1.45)
    return y

def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)

def _gradient_bottom(img, y0, strength=235):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    for y in range(y0, W):
        a = int(strength * (y - y0) / (W - y0))
        o.line([(0, y), (W, y)], fill=(5, 8, 16, a))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

N_LAYOUTS = 10

def card_news(headline_ar, english_title="", source="", layout=None):
    import zlib
    name, glyph, col = pick_cat(english_title)
    seed = zlib.crc32((english_title + headline_ar).encode())
    v = seed % N_LAYOUTS if layout is None else layout
    bgs = [(11, 18, 32), (14, 14, 28), (10, 24, 30), (22, 14, 20)]
    base_bg = bgs[(seed // 10) % len(bgs)]
    photo = fetch_bg(name, english_title or headline_ar, english_title)
    if photo is not None:
        img = Image.blend(photo, Image.new("RGB", (W, W), (8, 12, 22)), 0.6 if v not in (5,) else 0.4)
    else:
        img = Image.new("RGB", (W, W), base_bg)
        if name in PERSON_CATS:
            img = draw_silhouette(img, col)
    if v == 5:
        img = _gradient_bottom(img, 300)
    d = ImageDraw.Draw(img)
    big = photo is None and name not in PERSON_CATS

    if v == 0:      # classic: side bar + corner pills
        if big: _ctext(d, W // 2, W // 2, glyph, 560 if len(glyph) <= 2 else 420, _shade(base_bg, 1.8))
        d.polygon([(0, 0), (W, 0), (W, 120), (0, 260)], fill=PANEL)
        d.rectangle([0, 0, 18, W], fill=col)
        d.rounded_rectangle([W - 330, 40, W - 40, 130], 20, fill=(200, 40, 40))
        text(d, (W - 185, 85), "عاجل", 56, WHITE, "mm")
        d.rounded_rectangle([40, 50, 40 + 40 + int(d.textlength(ar(name), font=font(40))), 125], 20, fill=col)
        text(d, (60, 87), name, 40, WHITE, "lm")
        size, lines = _fit(d, headline_ar, W - 130, 7, (66, 58, 52))
        y = (W - len(lines) * int(size * 1.45)) // 2 + 70
        _lines(d, lines, size, W - 65, y)
    elif v == 1:    # centered with pill on top
        if big: _ctext(d, W // 2, W // 2, glyph, 620 if len(glyph) <= 2 else 440, _shade(base_bg, 1.6))
        _pill(d, (W // 2, 120), "عاجل", 54, (200, 40, 40))
        text(d, (W // 2, 235), name, 46, GOLD, "mm")
        d.rectangle([W // 2 - 90, 280, W // 2 + 90, 286], fill=col)
        size, lines = _fit(d, headline_ar, W - 150, 6, (68, 60, 52))
        y = 330 + (520 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W // 2, y, "ma")
    elif v == 2:    # split: color block top
        d.rectangle([0, 0, W, 400], fill=col)
        _ctext(d, W // 2, 205, glyph, 420 if len(glyph) <= 2 else 330, _shade(col, 0.82))
        text(d, (W - 60, 90), name, 84, WHITE, "rm")
        _pill(d, (170, 90), "عاجل", 40, (200, 40, 40))
        size, lines = _fit(d, headline_ar, W - 130, 5, (64, 56, 50))
        y = 440 + (400 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    elif v == 3:    # quote style
        text(d, (W - 60, 250), "”", 420, _shade(col, 0.9), "rd")
        _pill(d, (190, 90), "عاجل", 40, (200, 40, 40))
        size, lines = _fit(d, headline_ar, W - 150, 6, (62, 56, 50))
        y = 330
        y = _lines(d, lines, size, W - 75, y)
        d.rectangle([W - 75 - 200, y + 20, W - 75, y + 26], fill=col)
        text(d, (W - 75, y + 50), name, 44, GOLD, "ra")
    elif v == 4:    # diagonal band
        d.polygon([(0, 330), (W, 130), (W, 560), (0, 760)], fill=_shade(col, 0.55))
        d.polygon([(0, 330), (W, 130), (W, 150), (0, 350)], fill=col)
        _pill(d, (W - 190, 90), "عاجل", 44, (200, 40, 40))
        text(d, (60, 90), name, 46, GOLD, "lm")
        size, lines = _fit(d, headline_ar, W - 190, 5, (64, 56, 50))
        y = 330 + (360 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 90, y)
    elif v == 5:    # bottom-heavy with giant category word
        text(d, (W - 50, 60), name, 150, _shade(col, 1.0) if photo is not None else _shade(col, 0.5), "ra")
        _pill(d, (190, 330), "عاجل", 44, (200, 40, 40))
        size, lines = _fit(d, headline_ar, W - 130, 5, (62, 56, 50))
        h = len(lines) * int(size * 1.45)
        _lines(d, lines, size, W - 65, W - 200 - h)
    elif v == 6:    # frame
        d.rectangle([34, 34, W - 34, W - 34], outline=GOLD, width=4)
        d.rectangle([52, 52, W - 52, W - 52], outline=_shade(GOLD, 0.5), width=2)
        d.rectangle([W // 2 - 150, 14, W // 2 + 150, 74], fill=(200, 40, 40))
        text(d, (W // 2, 44), "عاجل", 44, WHITE, "mm")
        text(d, (W // 2, 170), name, 48, GOLD, "mm")
        size, lines = _fit(d, headline_ar, W - 220, 6, (64, 56, 50))
        y = 230 + (560 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W // 2, y, "ma")
    elif v == 7:    # ticker strip
        d.rectangle([0, 0, W, 90], fill=col)
        for k in range(6):
            text(d, (W - 90 - k * 190, 45), "عاجل", 38, WHITE, "mm")
            d.ellipse([W - 175 - k * 190 - 7, 38, W - 175 - k * 190 + 7, 52], fill=WHITE)
        size, lines = _fit(d, headline_ar, W - 130, 6, (66, 58, 52))
        y = 170 + (600 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
        _pill(d, (W - 190, 810), name, 40, col)
    elif v == 8:    # big circle badge
        d.ellipse([40, 40, 300, 300], fill=col)
        _ctext(d, 170, 170, glyph, 150 if len(glyph) <= 1 else (110 if len(glyph) == 2 else 78), WHITE)
        text(d, (W - 60, 120), "عاجل", 70, (230, 60, 60), "rm")
        text(d, (W - 60, 215), name, 48, GOLD, "rm")
        size, lines = _fit(d, headline_ar, W - 130, 6, (62, 56, 50))
        y = 360 + (440 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    else:           # minimal
        text(d, (W - 65, 130), name, 54, GOLD, "ra")
        d.rectangle([W - 65 - 120, 215, W - 65, 224], fill=col)
        text(d, (65, 135), "عاجل", 40, (230, 60, 60), "la")
        size, lines = _fit(d, headline_ar, W - 130, 6, (70, 62, 54))
        y = 290 + (500 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    _footer(d, source)
    return to_png(img)
