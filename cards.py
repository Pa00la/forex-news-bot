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
    (("gold", "xau"), "الذهب", "Au", (230, 170, 40)),
    (("oil", "opec", "crude", "brent"), "النفط", "OIL", (90, 90, 100)),
    (("china", "xi ", "beijing", "tariff"), "الصين والتجارة", "CN", (210, 60, 40)),
    (("iran", "israel", "war", "ceasefire", "russia", "ukraine", "sanction"), "جيوسياسة", "!", (170, 60, 60)),
    (("cpi", "inflation", "nfp", "payroll", "gdp", "pce", "ppi", "retail", "jobless", "unemployment"), "بيانات اقتصادية", "#", (46, 160, 110)),
]

def pick_cat(english_title):
    t = (english_title or "").lower() + " "
    for keys, name, glyph, col in CATS:
        if any(k in t for k in keys):
            return name, glyph, col
    return "عاجل", "!", (200, 50, 50)

QUERIES = {
    "ترامب": ["white house building", "american flag", "washington dc capitol"],
    "الفيدرالي": ["federal reserve building", "us dollar bills", "wall street"],
    "المركزي الأوروبي": ["euro banknotes", "frankfurt skyline", "european union flags"],
    "بنك إنجلترا": ["london city skyline", "british pound money", "big ben"],
    "بنك اليابان": ["tokyo skyline", "japanese yen", "tokyo night"],
    "الذهب": ["gold bars", "gold coins", "gold bullion"],
    "النفط": ["oil refinery", "oil barrels", "oil pump sunset"],
    "الصين والتجارة": ["shipping containers port", "shanghai skyline", "cargo ship"],
    "جيوسياسة": ["city skyline night", "world map", "stormy sky"],
    "بيانات اقتصادية": ["stock market chart", "financial charts screen", "trading screen"],
    "عاجل": ["stock exchange trading floor", "financial district", "forex chart"],
}

def fetch_bg(cat, seed):
    """Optional royalty-free photo from Pexels (needs PEXELS_KEY). Never people photos of public figures:
    queries are places/objects only. Returns a PIL image or None."""
    key = os.environ.get("PEXELS_KEY", "").strip()
    if not key:
        return None
    import json, random, urllib.request, urllib.parse, zlib
    try:
        qs = QUERIES.get(cat) or QUERIES["عاجل"]
        rnd = random.Random(zlib.crc32(str(seed).encode()))
        q = rnd.choice(qs)
        url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "per_page": 30, "orientation": "square"})
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0"})
        res = json.loads(urllib.request.urlopen(req, timeout=20).read())
        photos = res.get("photos") or []
        if not photos:
            return None
        ph = rnd.choice(photos)
        data = urllib.request.urlopen(urllib.request.Request(ph["src"]["large"], headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = im.size; m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((W, W))
        return im
    except Exception as ex:
        print("pexels failed:", ex)
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

def card_news(headline_ar, english_title="", source=""):
    name, glyph, col = pick_cat(english_title)
    bg = fetch_bg(name, english_title or headline_ar)
    if bg is not None:
        shade = Image.new("RGB", (W, W), (8, 12, 22))
        img = Image.blend(bg, shade, 0.62)
    else:
        img = Image.new("RGB", (W, W), BG)
        if name in PERSON_CATS:
            img = draw_silhouette(img, col)
    d = ImageDraw.Draw(img)
    # faint giant glyph + diagonal accent
    if bg is None and name not in PERSON_CATS:
        d.text((W // 2 - 20, W // 2 + 40), glyph, font=font(560), fill=(20, 30, 50), anchor="mm")
    d.polygon([(0, 0), (W, 0), (W, 120), (0, 260)], fill=PANEL)
    d.rectangle([0, 0, 18, W], fill=col)
    d.rounded_rectangle([W - 330, 40, W - 40, 130], 20, fill=(200, 40, 40))
    text(d, (W - 185, 85), "عاجل", 56, WHITE, "mm")
    d.rounded_rectangle([40, 50, 40 + 40 + int(d.textlength(ar(name), font=font(40))), 125], 20, fill=col)
    text(d, (60, 87), name, 40, WHITE, "lm")
    size = 66 if len(headline_ar) < 110 else 54
    lines = wrap(d, headline_ar, size, W - 130)[:7]
    total = len(lines) * int(size * 1.45)
    y = (W - total) // 2 + 70
    for ln in lines:
        text(d, (W - 65, y), ln, size, WHITE, "ra")
        y += int(size * 1.45)
    d.rectangle([0, W - 110, W, W], fill=PANEL)
    d.text((40, W - 55), BRAND, font=font(36), fill=GOLD, anchor="lm")
    d.text((W - 40, W - 55), HANDLE, font=font(30), fill=GREY, anchor="rm")
    if source:
        text(d, (W - 65, W - 150), "المصدر: " + source, 28, GREY, "ra")
    return to_png(img)
