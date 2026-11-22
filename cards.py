"""Image cards for the channel (Pillow). Free, runs inside GitHub Actions, no accounts needed."""
import io, os, subprocess, sys

BRAND = "Forex News"
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
    img, d = base(900, "نتيجة الخبر", " - ".join(x for x in (country, name) if x and x.strip(" .…")) or "بيانات اقتصادية")
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
    (("election", "elections", "midterm", "midterms", "senate", "congress", "ballot", "voters", "democrats", "republicans", "speaker"), "الانتخابات", "VOTE", (60, 90, 200)),
    (("trump", "white house", "biden"), "ترامب", "$", (200, 50, 50)),
    (("fed ", "powell", "fomc", "warsh", "federal reserve", "waller", "fed's"), "الفيدرالي", "%", (52, 120, 220)),
    (("ecb", "lagarde"), "المركزي الأوروبي", "€", (40, 90, 200)),
    (("bank of england", "boe", "bailey"), "بنك إنجلترا", "£", (140, 60, 170)),
    (("boj", "ueda", "yen"), "بنك اليابان", "¥", (200, 70, 90)),
    (("nvidia", "stocks", "stock market", "wall street", "s&p", "nasdaq", "dow jones", "tesla", "apple", "microsoft", "tech "), "الأسهم", "STK", (40, 150, 120)),
    (("gold", "xau"), "الذهب", "XAU", (230, 170, 40)),
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
    "الانتخابات": ["us capitol building", "voting ballot box", "american flag"],
    "ترامب": ["white house building", "american flag", "washington dc capitol"],
    "الفيدرالي": ["federal reserve building", "us dollar bills", "wall street"],
    "المركزي الأوروبي": ["euro banknotes", "frankfurt skyline", "european union flags"],
    "بنك إنجلترا": ["london city skyline", "british pound money", "big ben"],
    "بنك اليابان": ["tokyo skyline", "japanese yen", "tokyo night"],
    "الذهب": ["gold bars", "gold coins", "gold bullion"],
    "النفط": ["oil refinery", "oil drilling rig", "oil pump sunset"],
    "الأسهم": ["stock exchange traders", "stock market chart", "financial charts"],
    "الصين والتجارة": ["shipping containers port", "shanghai skyline", "cargo ship"],
    "جيوسياسة": ["city skyline night", "world map", "stormy sky"],
    "بيانات اقتصادية": ["stock market chart", "financial charts screen", "economist analyzing charts"],
    "عاجل": ["stock exchange trading floor", "traders screens", "financial district"],
}

def _crop_sq(data):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size; m = min(w, h)
    return im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((W, W))

TOPICS = [  # (regex on the English headline, photo searches) - checked before the broad category
    (r"supreme court", ["us supreme court building", "supreme court washington"]),
    (r"wall street|stock market|stocks|nasdaq|s&p|dow jones", ["wall street new york stock exchange", "new york stock exchange building", "stock market trading floor"]),
    (r"federal reserve building|fed headquarters", ["federal reserve building washington", "marriner eccles building"]),
    (r"election|midterm|senate|congress|ballot|voters|democrat|republican|speaker", ["us capitol building", "voting ballot box", "american flag"]),
    (r"australia|sydney|aussie", ["sydney skyline", "sydney harbour"]),
    (r"summit|meeting|talks|visit|xi\b|putin|biden|president", ["flags diplomacy meeting room", "us china flags", "world leaders flags"]),
    (r"oil|crude|opec|brent|inventor", ["oil refinery", "oil storage tanks", "oil drilling rig"]),
    (r"singapore|asia|asian", ["asian city skyline", "singapore skyline"]),
    (r"war|ceasefire|iran|israel|ukraine|russia", ["world map conflict", "flags diplomacy", "city skyline night"]),
    (r"nvidia|chip|semiconductor|\bai\b|artificial intelligence", ["semiconductor chip", "computer processor close up", "data center servers"]),
    (r"tesla|electric vehicle|\bev\b", ["electric car charging", "electric car"]),
    (r"apple|iphone", ["smartphone close up", "technology gadgets"]),
    (r"housing|mortgage|real estate|home sales|homebuilder", ["houses neighborhood aerial", "house for sale sign", "real estate buildings"]),
    (r"shipping|port|container|supply chain|freight", ["cargo ship", "shipping containers port"]),
    (r"inflation|cpi|prices|grocery|consumer", ["supermarket shopping", "grocery prices", "shopping cart supermarket"]),
    (r"jobs|payroll|unemployment|hiring|labor", ["job interview office", "office workers", "factory workers"]),
    (r"treasury|yield|bond", ["us treasury building", "government building columns"]),
    (r"bank|banks|lender", ["bank building columns", "bank building exterior"]),
    (r"dollar|dxy|greenback", ["us dollar banknotes", "dollar bills close up"]),
    (r"\beuro\b|eurozone", ["euro banknotes", "european union flags"]),
    (r"yen|japan", ["tokyo skyline", "japanese yen banknotes"]),
    (r"pound|sterling|britain|\buk\b", ["london skyline", "british pound banknotes"]),
    (r"tariff|trade war|china", ["shipping containers port", "cargo ship"]),
    (r"retail sales|retail", ["shoppers in store", "supermarket shopping", "shopping bags store"]),
]
_BAD_TAGS = {"horse", "horses", "dog", "cat", "animal", "bird", "baby", "wedding", "bride", "groom", "fashion", "selfie",
             "model", "portrait", "couple", "kid", "kids", "child", "children", "elderly", "senior", "lady", "girl", "boy",
             "yoga", "beach", "bikini", "pet", "flower", "flowers", "food", "dessert"}

def _is_bad(txt):
    import re
    return bool(set(re.findall(r"[a-z]+", (txt or "").lower())) & _BAD_TAGS)

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
    return [(p_["src"]["large"], p_.get("alt") or "") for p_ in ph if not _is_bad(p_.get("alt"))]

def _links_pixabay(key, q):
    import json, urllib.request, urllib.parse
    for extra in ({"editors_choice": "true", "category": "business"}, {"editors_choice": "true"}, {}):
        url = "https://pixabay.com/api/?" + urllib.parse.urlencode({"key": key, "q": q, "image_type": "photo", "per_page": 50,
                                                                    "safesearch": "true", "min_width": 1000, **extra})
        hits = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()).get("hits") or []
        hits = [h for h in hits if not _is_bad(h.get("tags"))]
        if hits:
            return [(h["largeImageURL"], h.get("tags") or "") for h in hits]
    return []

def _links_openverse(key, q):
    """No key needed. CC0 / public-domain photographs only, so no attribution is required."""
    import json, urllib.request, urllib.parse
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "license": "cc0,pdm", "category": "photograph", "size": "large", "page_size": 20})
    res = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()).get("results") or []
    out = []
    for r in res:
        txt = (r.get("title") or "") + " " + " ".join((t.get("name") or "") for t in (r.get("tags") or []))
        if r.get("url") and not _is_bad(txt):
            out.append((r["url"], txt))
    return out

_STOP = set("""the a an and or of to in on for with from by at as is are was were be been it its this that these those after before over under
amid into than then but not new says say said will would could should may might more most less least up down out off about
us u s per vs year years month week day today stocks stock market markets news report reports data expected expect
expects rise rises fall falls higher lower""".split())
_VISUAL = {"inventories": "warehouse inventory", "inventory": "warehouse inventory", "surplus": "oil storage tanks",
           "crude": "oil refinery", "treasury": "treasury building", "yields": "bonds", "jobless": "unemployment office",
           "claims": "unemployment office", "payrolls": "workers", "payroll": "workers", "hiring": "job interview",
           "mortgage": "houses", "housing": "houses", "rates": "interest rates bank", "rate": "interest rate bank",
           "tariffs": "shipping containers", "tariff": "shipping containers", "sanctions": "flags", "summit": "flags diplomacy",
           "meeting": "flags diplomacy", "talks": "flags diplomacy", "ceasefire": "flags diplomacy", "inflation": "supermarket prices",
           "prices": "price tags", "retail": "shopping store", "consumer": "shopping store", "manufacturing": "factory production",
           "factory": "factory production", "pmi": "factory production", "growth": "economy growth chart", "recession": "economy downturn",
           "bank": "bank building", "banks": "bank building", "chip": "semiconductor", "chips": "semiconductor", "dollar": "dollar banknotes"}

def keyword_query(title):
    import re
    words = [w for w in re.findall(r"[a-z]+", (title or "").lower()) if len(w) > 3 and w not in _STOP]
    seen, out = set(), []
    for w in words:
        v = _VISUAL.get(w, w)
        if v not in seen:
            seen.add(v); out.append(v)
    return " ".join(out[:3])

def _words(txt):
    import re
    return {w[:6] for w in re.findall(r"[a-z]+", (txt or "").lower()) if len(w) > 3 and w not in _STOP}

def _scene_file(key, title):
    import re, zlib
    try:
        cand = sorted(f for f in os.listdir(PEOPLE_DIR) if re.fullmatch(rf"{key}\d*\.(jpg|jpeg|png|webp)", f.lower()))
        if cand:
            im = Image.open(os.path.join(PEOPLE_DIR, cand[zlib.crc32((title or "").encode()) % len(cand)])).convert("RGB")
            w, h = im.size; m = min(w, h)
            return im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((W, W))
    except Exception as ex:
        print("scene failed:", ex)
    return None

def _local_scene(title):
    """Owner-provided scene photos in the 'people' folder (e.g. whitehouse.jpg, whitehouse2.jpg)."""
    import re, zlib
    t = (title or "").lower()
    for key, rx in (("whitehouse", r"white house"),):
        if re.search(rx, t):
            try:
                cand = sorted(f for f in os.listdir(PEOPLE_DIR) if re.fullmatch(rf"{key}\d*\.(jpg|jpeg|png|webp)", f.lower()))
                if cand:
                    im = Image.open(os.path.join(PEOPLE_DIR, cand[zlib.crc32(t.encode()) % len(cand)])).convert("RGB")
                    w, h = im.size; m = min(w, h)
                    return im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((W, W))
            except Exception as ex:
                print("local scene failed:", ex)
    return None

def fetch_bg(cat, seed, title=""):
    """Royalty-free photo that matches the headline. For every library with a key we search several queries
    (topic scenes + keywords taken from the headline), then rank the results by how many words of their
    description/tags match the headline, and pick one of the best matches."""
    loc = _local_scene(title)
    if loc is not None:
        return loc
    strict = cat == "الانتخابات"   # politics: only a stock photo that clearly shows the Capitol / a government building
    providers = []
    if os.environ.get("PEXELS_KEY", "").strip(): providers.append(("pexels", _links_pexels, os.environ["PEXELS_KEY"].strip()))
    if os.environ.get("PIXABAY_KEY", "").strip(): providers.append(("pixabay", _links_pixabay, os.environ["PIXABAY_KEY"].strip()))
    import random, urllib.request, zlib
    rnd = random.Random(zlib.crc32(str(seed).encode()))
    rnd.shuffle(providers)
    providers.append(("openverse", _links_openverse, ""))  # keyless last resort
    topic_qs = topic_queries(title, cat)
    kq = keyword_query(title)
    queries = [(q, 2) for q in topic_qs[:2]] + ([(kq, 1)] if kq else [])
    want = _words(title) | _words(" ".join(topic_qs))
    for name, fn, key in providers:
        pool = []
        for q, bonus in queries:
            try:
                for url, txt in fn(key, q):
                    pool.append((len(_words(txt) & want) + bonus, rnd.random(), url))
            except Exception as ex:
                print(f"{name} failed ({q}):", ex)
        if not pool:
            continue
        pool.sort(reverse=True)
        if strict: pool = [p for p in pool if p[0] >= 5]
        if not pool: continue
        top = pool[:4]
        rnd.shuffle(top)
        for sc, _, url in top:
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
                print(f"photo: {name} score={sc} q={queries[0][0]}")
                return _crop_sq(data)
            except Exception as ex:
                print(f"{name} download failed:", ex)
    if strict:
        return _scene_file("whitehouse", title)
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
    """Brand + link sit directly on the picture over a soft dark fade (no separate strip)."""
    img = d._image
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    y0 = W - 230
    for y in range(y0, W):
        o.line([(0, y), (W, y)], fill=(4, 7, 14, int(215 * (y - y0) / 230)))
    img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"))
    d.text((45, W - 52), BRAND, font=font(40), fill=GOLD, anchor="lm")
    d.text((W - 45, W - 52), HANDLE, font=font(32), fill=WHITE, anchor="rm")
    d.line([(45, W - 100), (W - 45, W - 100)], fill=(255, 255, 255, 60), width=2)
    if source:
        text(d, (W - 45, W - 125), "المصدر: " + source, 28, (200, 205, 215), "ra")

def _pill(d, xy, label, size, fill, fg=WHITE):
    if not label: return
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

N_LAYOUTS = 11

def card_news(headline_ar, english_title="", source="", layout=None, urgent=True):
    import zlib
    name, glyph, col = pick_cat(english_title)
    LBL, PILL, PILLT = ("عاجل", (200, 40, 40), (230, 60, 60)) if urgent else ("", (45, 70, 110), (120, 160, 215))
    seed = zlib.crc32((english_title + headline_ar).encode())
    v = seed % N_LAYOUTS if layout is None else layout
    bgs = [(11, 18, 32), (14, 14, 28), (10, 24, 30), (22, 14, 20)]
    base_bg = bgs[(seed // 10) % len(bgs)]
    ppl = _people_imgs(english_title)
    if ppl:
        return _card_people(ppl, headline_ar, name, source, urgent)
    photo = fetch_bg(name, english_title or headline_ar, english_title)
    if v == 10 and photo is not None:
        return _card_photo_top(photo, headline_ar, name, source, urgent, col)
    if v == 10:
        v = 3
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
        if LBL:
            d.rounded_rectangle([W - 330, 40, W - 40, 130], 20, fill=PILL)
            text(d, (W - 185, 85), LBL, 56, WHITE, "mm")
        d.rounded_rectangle([40, 50, 40 + 40 + int(d.textlength(ar(name), font=font(40))), 125], 20, fill=col)
        text(d, (60, 87), name, 40, WHITE, "lm")
        size, lines = _fit(d, headline_ar, W - 130, 7, (66, 58, 52))
        y = (W - len(lines) * int(size * 1.45)) // 2 + 70
        _lines(d, lines, size, W - 65, y)
    elif v == 1:    # centered with pill on top
        if big: _ctext(d, W // 2, W // 2, glyph, 620 if len(glyph) <= 2 else 440, _shade(base_bg, 1.6))
        _pill(d, (W // 2, 120), LBL, 54, PILL)
        text(d, (W // 2, 235), name, 46, GOLD, "mm")
        d.rectangle([W // 2 - 90, 280, W // 2 + 90, 286], fill=col)
        size, lines = _fit(d, headline_ar, W - 150, 6, (68, 60, 52))
        y = 330 + (520 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W // 2, y, "ma")
    elif v == 2:    # split: color block top
        d.rectangle([0, 0, W, 400], fill=col)
        _ctext(d, W // 2, 205, glyph, 420 if len(glyph) <= 2 else 330, _shade(col, 0.82))
        _ns = 84
        while _ns > 44 and d.textlength(ar(name), font=font(_ns)) > W - 330: _ns -= 4
        text(d, (W - 60, 90), name, _ns, WHITE, "rm")
        _pill(d, (170, 90), LBL, 40, PILL)
        size, lines = _fit(d, headline_ar, W - 130, 5, (64, 56, 50))
        y = 440 + (400 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    elif v == 3:    # quote style
        text(d, (W - 60, 250), "”", 420, _shade(col, 0.9), "rd")
        _pill(d, (190, 90), LBL, 40, PILL)
        size, lines = _fit(d, headline_ar, W - 150, 6, (62, 56, 50))
        y = 330
        y = _lines(d, lines, size, W - 75, y)
        d.rectangle([W - 75 - 200, y + 20, W - 75, y + 26], fill=col)
        text(d, (W - 75, y + 50), name, 44, GOLD, "ra")
    elif v == 4:    # diagonal band
        d.polygon([(0, 330), (W, 130), (W, 560), (0, 760)], fill=_shade(col, 0.55))
        d.polygon([(0, 330), (W, 130), (W, 150), (0, 350)], fill=col)
        _pill(d, (W - 190, 90), LBL, 44, PILL)
        text(d, (60, 90), name, 46, GOLD, "lm")
        size, lines = _fit(d, headline_ar, W - 190, 5, (64, 56, 50))
        y = 330 + (360 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 90, y)
    elif v == 5:    # bottom-heavy with giant category word
        _ns = 150
        while _ns > 60 and d.textlength(ar(name), font=font(_ns)) > W - 100: _ns -= 6
        text(d, (W - 50, 60), name, _ns, _shade(col, 1.0) if photo is not None else _shade(col, 0.5), "ra")
        _pill(d, (190, 330), LBL, 44, PILL)
        size, lines = _fit(d, headline_ar, W - 130, 5, (62, 56, 50))
        h = len(lines) * int(size * 1.45)
        _lines(d, lines, size, W - 65, W - 200 - h)
    elif v == 6:    # frame
        d.rectangle([34, 34, W - 34, W - 34], outline=GOLD, width=4)
        d.rectangle([52, 52, W - 52, W - 52], outline=_shade(GOLD, 0.5), width=2)
        if LBL:
            d.rectangle([W // 2 - 150, 14, W // 2 + 150, 74], fill=PILL)
            text(d, (W // 2, 44), LBL, 44, WHITE, "mm")
        text(d, (W // 2, 170), name, 48, GOLD, "mm")
        size, lines = _fit(d, headline_ar, W - 220, 6, (64, 56, 50))
        y = 230 + (560 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W // 2, y, "ma")
    elif v == 7:    # ticker strip
        d.rectangle([0, 0, W, 90], fill=col)
        for k in range(6):
            text(d, (W - 90 - k * 190, 45), LBL, 38, WHITE, "mm")
            d.ellipse([W - 175 - k * 190 - 7, 38, W - 175 - k * 190 + 7, 52], fill=WHITE)
        size, lines = _fit(d, headline_ar, W - 130, 6, (66, 58, 52))
        y = 170 + (600 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
        _pill(d, (W - 190, 810), name, 40, col)
    elif v == 8:    # big circle badge
        d.ellipse([40, 40, 300, 300], fill=col)
        _ctext(d, 170, 170, glyph, 150 if len(glyph) <= 1 else (110 if len(glyph) == 2 else 78), WHITE)
        text(d, (W - 60, 120), LBL, 70, PILLT, "rm")
        text(d, (W - 60, 215), name, 48, GOLD, "rm")
        size, lines = _fit(d, headline_ar, W - 130, 6, (62, 56, 50))
        y = 360 + (440 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    else:           # minimal
        text(d, (W - 65, 130), name, 54, GOLD, "ra")
        d.rectangle([W - 65 - 120, 215, W - 65, 224], fill=col)
        text(d, (65, 135), LBL, 40, PILLT, "la")
        size, lines = _fit(d, headline_ar, W - 130, 6, (70, 62, 54))
        y = 290 + (500 - len(lines) * int(size * 1.45)) // 2
        _lines(d, lines, size, W - 65, y)
    _footer(d, source)
    return to_png(img)


# ---------------- people photos (only files the owner puts in the "people" folder) ----------------
PEOPLE_DIR = os.environ.get("PEOPLE_DIR", os.path.join(HERE, "people"))
PEOPLE = [("trump", r"\btrump\b"), ("xi", r"\bxi\b|xi jinping"), ("putin", r"\bputin\b"), ("powell", r"\bpowell\b"),
          ("bessent", r"\bbessent\b"), ("lagarde", r"\blagarde\b"), ("bailey", r"\bbailey\b"), ("ueda", r"\bueda\b"),
          ("biden", r"\bbiden\b"), ("warsh", r"\bwarsh\b"), ("waller", r"\bwaller\b"), ("zelensky", r"\bzelensky\b"),
          ("netanyahu", r"\bnetanyahu\b"), ("musk", r"\bmusk\b")]

_FOCUS = None
def _focus_of(fname):
    """Face position [cx, cy, face_height] (fractions) from people/focus.json, if the face was found."""
    global _FOCUS
    if _FOCUS is None:
        try:
            import json
            _FOCUS = {}
            for p in (os.path.join(PEOPLE_DIR, "focus.json"), os.path.join(HERE, "focus.json")):
                if os.path.exists(p):
                    _FOCUS = json.load(open(p)); break
        except Exception:
            _FOCUS = {}
    f = _FOCUS.get(fname)
    return f if f and f[2] >= 0.15 and 0.1 <= f[1] <= 0.6 else None

def _people_imgs(title):
    """One photo per person from the 'people' folder. Several files per person are allowed for variety:
    trump.jpg, trump2.jpg, trump_3.png ... one of them is picked per news item.
    Any new person works with no code change: name the file after the person, e.g. jensen_huang.jpg or jensen_huang2.jpg."""
    import re, zlib
    t = (title or "").lower()
    out = []
    try: files = os.listdir(PEOPLE_DIR)
    except Exception: return out
    keys = [(k, rx) for k, rx in PEOPLE]
    known = {k for k, _ in PEOPLE}
    for f in files:   # people found in the folder automatically
        m = re.fullmatch(r"([a-z][a-z_\-]*?)[_\-]?\d*\.(?:jpg|jpeg|png|webp)", f.lower())
        if m and m.group(1) not in known and not m.group(1).startswith("whitehouse"):
            k = m.group(1); known.add(k)
            keys.append((k, r"\b" + r"[\s_\-]+".join(re.escape(p) for p in re.split(r"[_\-]", k) if p) + r"\b"))
    hits = [(k, rx) for k, rx in keys if re.search(rx, t)][:3]
    n = max(1, len(hits)); pw, ph = W // n, 640
    for key, rx in hits:
        cand = sorted(f for f in files if re.fullmatch(rf"{re.escape(key)}[_\-]?\d*\.(jpg|jpeg|png|webp)", f.lower()))
        if not cand: continue
        cand = [f for f in cand if _focus_of(f)] or cand   # prefer photos where a clear face was found
        pick = cand[zlib.crc32((t + key).encode()) % len(cand)]
        try:
            im = Image.open(os.path.join(PEOPLE_DIR, pick)).convert("RGB")
            im.focus = _focus_of(pick)
            out.append(im)
        except Exception as ex: print("people image failed:", pick, ex)
    return out[:3]

def _crop_to(im, w, h, top_bias=0.25):
    from PIL import ImageFilter
    fc = getattr(im, "focus", None)
    s = max(w / im.width, h / im.height)          # "cover" scale
    if not fc:
        im2 = im.resize((max(w, int(im.width * s)), max(h, int(im.height * s))))
        x = (im2.width - w) // 2; y = int((im2.height - h) * top_bias)
        return im2.crop((x, y, x + w, y + h))
    cx, cy, fh = fc
    # keep the face fairly small and clear: zoom in a bit if tiny, zoom OUT if huge (blurred sides fill the gap)
    st = max(h / im.height, min(s * 1.25, 0.34 * h / (fh * im.height)))
    im2 = im.resize((max(1, int(im.width * st)), max(h, int(im.height * st))))
    y = min(max(int(cy * im2.height - 0.40 * h), 0), im2.height - h)
    if im2.width >= w:
        x = min(max(int(cx * im2.width - w / 2), 0), im2.width - w)
        return im2.crop((x, y, x + w, y + h))
    bg = im.resize((max(w, int(im.width * s)), max(h, int(im.height * s)))).filter(ImageFilter.GaussianBlur(28))
    bx = (bg.width - w) // 2; by = (bg.height - h) // 2
    bg = Image.blend(bg.crop((bx, by, bx + w, by + h)), Image.new("RGB", (w, h), (8, 12, 22)), 0.35)
    bg.paste(im2.crop((0, y, im2.width, y + h)), ((w - im2.width) // 2, 0))
    return bg

def _label(urgent):
    return ("عاجل", (200, 40, 40)) if urgent else ("", (45, 70, 110))

def _card_people(imgs, headline_ar, name, source, urgent):
    img = Image.new("RGB", (W, W), (8, 12, 22))
    n = len(imgs); pw = W // n; ph = 640
    for i, im in enumerate(imgs):
        img.paste(_crop_to(im, pw, ph), (i * pw, 0))
    d = ImageDraw.Draw(img)
    for i in range(1, n):
        d.rectangle([i * pw - 3, 0, i * pw + 3, ph], fill=(8, 12, 22))
    lab, lc = _label(urgent)
    d.rectangle([0, ph, W, W], fill=(245, 246, 249))
    if lab:
        d.rectangle([W - 215, ph, W, W - 110], fill=lc)
        text(d, (W - 108, ph + (W - 110 - ph) // 2), lab, 76, WHITE, "mm")
    right = W - 250 if lab else W - 60
    size, lines = _fit(d, headline_ar, right - 40, 4, (56, 50, 44, 40))
    h = len(lines) * int(size * 1.4)
    _lines(d, lines, size, right, ph + (W - 110 - ph - h) // 2 + 6, "ra", (18, 22, 36))
    d.rectangle([0, W - 110, W, W], fill=(245, 246, 249))
    d.line([(45, W - 108), (W - 45, W - 108)], fill=(205, 210, 222), width=2)
    d.text((45, W - 52), BRAND, font=font(40), fill=(176, 120, 10), anchor="lm")
    d.text((W - 45, W - 52), HANDLE, font=font(32), fill=(40, 48, 70), anchor="rm")
    if source:
        text(d, (W - 250, W - 135), "المصدر: " + source, 26, (90, 98, 120), "ra")
    return to_png(img)

def _card_photo_top(photo, headline_ar, name, source, urgent, col):
    img = Image.new("RGB", (W, W), (245, 246, 249))
    img.paste(photo.resize((W, W)).crop((0, 80, W, 80 + 640)) if photo.height >= W else _crop_to(photo, W, 640), (0, 0))
    d = ImageDraw.Draw(img)
    lab, lc = _label(urgent)
    ph = 640
    d.rounded_rectangle([30, 30, 30 + 44 + int(d.textlength(ar(name), font=font(38))), 104], 18, fill=col)
    text(d, (52, 67), name, 38, WHITE, "lm")
    if lab:
        d.rectangle([W - 215, ph + 30, W - 40 + 40, W - 110], fill=lc)
        text(d, (W - 108, ph + 30 + (W - 110 - ph - 30) // 2), lab, 76, WHITE, "mm")
    right = W - 250 if lab else W - 60
    size, lines = _fit(d, headline_ar, right - 40, 4, (56, 50, 44, 40))
    h = len(lines) * int(size * 1.4)
    _lines(d, lines, size, right, ph + 30 + (W - 110 - ph - 30 - h) // 2 + 6, "ra", (18, 22, 36))
    d.rectangle([0, W - 110, W, W], fill=(245, 246, 249))
    d.line([(45, W - 108), (W - 45, W - 108)], fill=(205, 210, 222), width=2)
    d.text((45, W - 52), BRAND, font=font(40), fill=(176, 120, 10), anchor="lm")
    d.text((W - 45, W - 52), HANDLE, font=font(32), fill=(40, 48, 70), anchor="rm")
    if source:
        text(d, (W - 250, W - 135), "المصدر: " + source, 26, (90, 98, 120), "ra")
    return to_png(img)


# ---------------- price card (gold / oil ...) and opening poster ----------------
def card_asset(name_ar, code, price, change, pct, series, subtitle=""):
    img, d = base(W, name_ar, subtitle)
    col = GREEN if change >= 0 else RED
    d.text((W - 60, 245), code, font=font(46), fill=GREY, anchor="rm")
    d.text((60, 330), f"{price:,.2f}", font=font(150), fill=WHITE, anchor="lm")
    tri = [(60, 495), (110, 495), (85, 445)] if change >= 0 else [(60, 445), (110, 445), (85, 495)]
    d.polygon(tri, fill=col)
    d.text((135, 470), f"{abs(change):,.2f}   ({pct:+.2f}%)", font=font(58), fill=col, anchor="lm")
    d.rounded_rectangle([40, 560, W - 40, W - 120], 24, fill=PANEL)
    pts = [v for v in series if v is not None]
    if len(pts) > 160:
        step = len(pts) / 160
        pts = [pts[int(i * step)] for i in range(160)] + [pts[-1]]
    if len(pts) >= 2:
        x0, x1, y0, y1 = 80, W - 80, 610, W - 170
        lo, hi = min(pts), max(pts); rng = (hi - lo) or 1
        xy = [(x0 + (x1 - x0) * i / (len(pts) - 1), y1 - (y1 - y0) * (v - lo) / rng) for i, v in enumerate(pts)]
        base_y = y1 - (y1 - y0) * (pts[0] - lo) / rng
        for x in range(x0, x1, 22):
            d.line([(x, base_y), (x + 10, base_y)], fill=(90, 100, 125), width=2)
        d.line(xy, fill=col, width=6, joint="curve")
        d.ellipse([xy[-1][0] - 10, xy[-1][1] - 10, xy[-1][0] + 10, xy[-1][1] + 10], fill=col)
        d.text((x1, y0 - 22), f"{hi:,.2f}", font=font(28), fill=GREY, anchor="rm")
        d.text((x1, y1 + 30), f"{lo:,.2f}", font=font(28), fill=GREY, anchor="rm")
        text(d, (x0, W - 165), "حركة اليوم", 28, GREY, "la")
    return to_png(img)

def card_poster(session_name, sub, english_hint, chips=("الذهب", "الدولار", "الأسهم")):
    photo = fetch_bg("عاجل", session_name, english_hint)
    if photo is not None:
        img = Image.blend(photo, Image.new("RGB", (W, W), (6, 10, 22)), 0.58)
    else:
        img = Image.new("RGB", (W, W), (11, 18, 32))
    img = _gradient_bottom(img, 420, 215)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([W // 2 - 210, 90, W // 2 + 210, 170], 24, fill=(200, 40, 40))
    text(d, (W // 2, 130), "افتتاح السوق", 50, WHITE, "mm")
    size = 130
    while size > 60 and d.textlength(ar(session_name), font=font(size)) > W - 120: size -= 6
    text(d, (W // 2, 400), session_name, size, WHITE, "mm")
    d.rectangle([W // 2 - 110, 490, W // 2 + 110, 498], fill=GOLD)
    for k, ln in enumerate(wrap(d, sub, 46, W - 200)[:3]):
        text(d, (W // 2, 560 + k * 70), ln, 46, (225, 230, 240), "mm")
    for i, ch in enumerate(chips):
        x = int(W // 2 + ((len(chips) - 1) / 2 - i) * 280)
        d.rounded_rectangle([x - 125, 790, x + 125, 870], 40, fill=(245, 185, 66))
        text(d, (x, 830), ch, 40, (20, 24, 36), "mm")
    _footer(d, "")
    return to_png(img)


def _poster_bg(hint, seed, dark=0.6):
    photo = fetch_bg("عاجل", seed, hint)
    if photo is not None:
        img = Image.blend(photo, Image.new("RGB", (W, W), (6, 10, 22)), dark)
    else:
        img = Image.new("RGB", (W, W), (11, 18, 32))
    return _gradient_bottom(img, 380, 215)

def _chip_row(d, items, y=800):
    n = len(items); gap = 20; bw = (W - 80 - gap * (n - 1)) // n
    x = W - 40
    for it in items:
        x0 = x - bw
        d.rounded_rectangle([x0, y, x, y + 130], 24, fill=(14, 20, 36), outline=(70, 80, 105), width=2)
        for k, ln in enumerate(wrap(d, it, 30, bw - 30)[:2]):
            text(d, ((x0 + x) // 2, y + 45 + k * 42), ln, 30, WHITE, "mm")
        x = x0 - gap

def card_event(abbr, english, arabic, hint, chips):
    """Poster for a big scheduled release (CPI, NFP, FOMC ...): giant acronym over a flag/skyline photo."""
    img = _poster_bg(hint, abbr + english)
    d = ImageDraw.Draw(img)
    size = 330
    while size > 110 and d.textlength(abbr, font=font(size)) > W - 100: size -= 10
    d.text((W // 2, 300), abbr, font=font(size), fill=(238, 240, 246), anchor="mm")
    d.rounded_rectangle([60, 470, W - 60, 560], 14, fill=(190, 30, 36))
    fs = 46
    while fs > 24 and d.textlength(english, font=font(fs)) > W - 160: fs -= 2
    d.text((W // 2, 515), english, font=font(fs), fill=WHITE, anchor="mm")
    size2 = 70
    while size2 > 40 and d.textlength(ar(arabic), font=font(size2)) > W - 120: size2 -= 4
    text(d, (W // 2, 640), arabic, size2, WHITE, "mm")
    text(d, (W // 2, 725), "الأهم في هذا الأسبوع" if False else "حدث مهم للأسواق", 38, GOLD, "mm")
    _chip_row(d, chips, 800)
    _footer(d, "")
    return to_png(img)

def card_greeting(title, sub, hint):
    img = _poster_bg(hint, title, 0.38)
    d = ImageDraw.Draw(img)
    size = 190
    while size > 80 and d.textlength(ar(title), font=font(size)) > W - 100: size -= 8
    d.text((W // 2 + 3, 303), ar(title), font=font(size), fill=(0, 0, 0), anchor="mm")
    text(d, (W // 2, 300), title, size, (230, 255, 190), "mm")
    d.rectangle([W // 2 - 120, 430, W // 2 + 120, 438], fill=GOLD)
    for k, ln in enumerate(wrap(d, sub, 46, W - 200)[:2]):
        text(d, (W // 2, 500 + k * 70), ln, 46, WHITE, "mm")
    _footer(d, "")
    return to_png(img)
