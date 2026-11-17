"""Forex / gold news bot for a Telegram channel (free, runs on GitHub Actions every ~5 min).

What it posts (Arabic, no emojis, no trade recommendations, Egypt + Saudi time):
  - Morning calendar of today's high-impact events
  - Pre-alert ~1 hour before each high-impact release, and a "released now" alert
  - Breaking news from free RSS feeds (headline translated to Arabic + source)
  - Gold and currency strength snapshots a few times a day
Manual run (workflow_dispatch) sends a test message and prints a diagnosis of every source.
"""
import json, time, os, re, sys, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

def C():
    import cards  # lazy: installs Pillow only when an image is needed
    return cards

DUBAI = ZoneInfo("Africa/Cairo")   # base zone = Egypt time
KSA = ZoneInfo("Asia/Riyadh")
import content
STATE_FILE = "state.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; news-bot/1.0)"}

# ---------------- settings you can edit ----------------
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CURRENCIES = {"USD", "GBP", "EUR", "JPY", "CAD", "AUD", "CHF", "NZD", "CNY"}
LEAD_STAGES = [60, 5, 1]      # pre-alerts: 1 hour, 5 minutes and 1 minute before each release
MORNING_HOUR = 8              # Dubai hour for the daily calendar post
SNAPSHOT_HOURS = [12, 17, 21] # Dubai hours for gold + currency strength posts (weekdays)
MAX_NEWS_PER_RUN = 3
MAX_NEWS_PER_DAY = 40
NEWS_MAX_AGE_MIN = 45

FEEDS = {  # name -> url (a failing feed is simply skipped)
    "investingLive": "https://investinglive.com/feed",
    "CNBC Economy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "CNBC Finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "WSJ Markets": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "US BLS": "https://www.bls.gov/feed/bls_latest.rss",
    "ECB": "https://www.ecb.europa.eu/rss/press.html",
    "Bank of England": "https://www.bankofengland.co.uk/rss/news",
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
}
KEYWORDS = ["gold", "xau", "fed ", "fomc", "powell", "trump", "nfp", "payroll", "cpi", "inflation", "pce", "ppi",
            "gdp", "unemployment", "jobs report", "jobless", "rate cut", "rate hike", "rate decision", "interest rate",
            "bank of england", "boe", "ecb", "boj", "lagarde", "bailey", "ueda", "treasury", "yield", "dollar", "dxy",
            "oil", "opec", "tariff", "sanction", "iran", "israel", "ceasefire", "retail sales", "pmi", "ism",
            "china", "safe haven", "central bank"]
SKIP = ["bitcoin", "crypto", "ethereum", "xrp", "dogecoin", "stock picks", "sponsored", "earnings call", "podcast"]
RESULT_WORDS = ["nfp", "payroll", "cpi", "ppi", "pce", "gdp", "retail sales", "unemployment rate", "jobless claims",
                "pmi", "ism", "rate decision", "holds rates", "cuts rates", "raises rates", "keeps rates"]

COUNTRY_AR = {"USD": "أمريكا", "GBP": "بريطانيا", "EUR": "منطقة اليورو", "JPY": "اليابان", "CAD": "كندا",
              "AUD": "أستراليا", "CHF": "سويسرا", "NZD": "نيوزيلندا", "CNY": "الصين"}
TITLE_AR = {
    "Non-Farm Employment Change": "الوظائف الأمريكية غير الزراعية NFP", "Unemployment Rate": "نسبة البطالة",
    "Average Hourly Earnings m/m": "متوسط الأجور بالساعة", "CPI m/m": "مؤشر أسعار المستهلك الشهري",
    "CPI y/y": "مؤشر أسعار المستهلك السنوي", "Core CPI m/m": "مؤشر أسعار المستهلك الأساسي الشهري",
    "Core PCE Price Index m/m": "مؤشر نفقات الاستهلاك الشخصي الأساسي", "PPI m/m": "مؤشر أسعار المنتجين",
    "Retail Sales m/m": "مبيعات التجزئة", "Core Retail Sales m/m": "مبيعات التجزئة الأساسية",
    "Advance GDP q/q": "الناتج المحلي الإجمالي الأولي", "Prelim GDP q/q": "الناتج المحلي الإجمالي المبدئي",
    "Final GDP q/q": "الناتج المحلي الإجمالي النهائي", "FOMC Statement": "بيان الفيدرالي الأمريكي",
    "FOMC Press Conference": "مؤتمر رئيس الفيدرالي الصحفي", "Federal Funds Rate": "قرار الفائدة الأمريكي",
    "FOMC Meeting Minutes": "محضر اجتماع الفيدرالي", "Unemployment Claims": "طلبات إعانة البطالة الأسبوعية",
    "ISM Manufacturing PMI": "مؤشر ISM للتصنيع", "ISM Services PMI": "مؤشر ISM للخدمات",
    "ADP Non-Farm Employment Change": "الوظائف الأمريكية الخاصة ADP", "Official Bank Rate": "قرار الفائدة البريطاني",
    "Main Refinancing Rate": "قرار الفائدة الأوروبي", "BOJ Policy Rate": "قرار الفائدة الياباني",
    "BOC Rate Statement": "قرار الفائدة الكندي", "Cash Rate": "قرار الفائدة الأسترالي",
}
DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
DISCLAIMER = "للمعلومات فقط وليس توصية. التداول ينطوي على مخاطر عالية."
LINE = "━━━━━━━━━━━━━━"
FOOTER = '📢 <a href="https://t.me/forex_news_M1">انضم للقناة: Maged | Forex News</a>'
LINK = FOOTER
TAGS = "#أخبار_الفوركس #الذهب #الدولار"
FOOTER = TAGS + "\n" + FOOTER

import zlib
def pick(pool, key):
    """Stable variety: same event always gets the same wording, different events get different ones."""
    return pool[zlib.crc32(str(key).encode()) % len(pool)]

PRE_POOL = {
    60: ["🔔 <b>خبر مهم بعد ساعة</b>", "⏳ <b>ساعة وينزل خبر مهم</b>", "📌 <b>بعد ساعة تقريبًا: خبر مهم</b>"],
    5: ["⏰ <b>بعد 5 دقايق</b>", "🔥 <b>5 دقايق ويصدر الخبر</b>", "⚡ <b>خبر مهم بعد 5 دقايق</b>"],
    1: ["🚨 <b>بعد دقيقة</b>", "⏱️ <b>دقيقة واحدة ويصدر الخبر</b>", "❗ <b>الخبر بعد دقيقة</b>"],
}
NOW_POOL = ["🚨 <b>صدر الآن</b>", "⚡ <b>نزل الخبر الآن</b>", "🔴 <b>صدر الآن</b>", "📣 <b>خبر صدر الآن</b>"]
NEWS_POOL = ["🚨 <b>عاجل</b>", "⚡ <b>عاجل</b>", "🔴 <b>خبر عاجل</b>"]
SRC_AR = {"investingLive": "إنفستنج لايف", "CNBC Economy": "سي إن بي سي", "CNBC Finance": "سي إن بي سي",
          "MarketWatch": "ماركت ووتش", "WSJ Markets": "وول ستريت جورنال", "Federal Reserve": "الفيدرالي الأمريكي",
          "US BLS": "مكتب إحصاءات العمل", "ECB": "المركزي الأوروبي", "Bank of England": "بنك إنجلترا", "BBC Business": "بي بي سي"}
FLAGS = {"USD": "🇺🇸", "GBP": "🇬🇧", "EUR": "🇪🇺", "JPY": "🇯🇵", "CAD": "🇨🇦", "AUD": "🇦🇺", "CHF": "🇨🇭", "NZD": "🇳🇿", "CNY": "🇨🇳"}
esc = html.escape

# ---------------- helpers ----------------
def http_get(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()

def now_dubai():
    return datetime.now(timezone.utc).astimezone(DUBAI)

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("sent", []); s.setdefault("titles", []); s.setdefault("daily", {}); s.setdefault("news_count", {})
    return s

def save_state(s):
    s["sent"] = s["sent"][-500:]; s["titles"] = s["titles"][-200:]
    s["daily"] = dict(list(sorted(s["daily"].items()))[-60:])
    s["news_count"] = dict(list(sorted(s["news_count"].items()))[-10:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)

LRI, PDI, RLM = "\u2066", "\u2069", "\u200f"
_LATIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9&%.,:'+\-/$ ]*[A-Za-z0-9%$]|[A-Za-z0-9]")

def fix_bidi(text):
    """Keep English/number runs in their natural order inside Arabic lines (tags and links untouched)."""
    parts = re.split(r"(<[^>]+>)", text)
    out = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
        else:
            out.append(_LATIN.sub(lambda m: LRI + m.group(0).rstrip() + PDI + (" " if m.group(0).endswith(" ") else ""), part))
    return "\n".join(RLM + ln if ln.strip() else ln for ln in "".join(out).split("\n"))

def _tg(method, fields, files=None):
    token = os.environ["BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        boundary = "----nb" + str(int(time.time() * 1000))
        body = b""
        for k, v in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fn, data) in files.items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                     f'Content-Type: image/png\r\n\r\n').encode() + data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

def send(text):
    _tg("sendMessage", {"chat_id": os.environ["CHAT_ID"], "text": fix_bidi(text), "parse_mode": "HTML",
                        "disable_web_page_preview": "true"})

def send_photo(png, caption=""):
    chat = os.environ["CHAT_ID"]
    if len(caption) <= 1000:
        _tg("sendPhoto", {"chat_id": chat, "caption": fix_bidi(caption), "parse_mode": "HTML"}, {"photo": ("card.png", png)})
    else:
        _tg("sendPhoto", {"chat_id": chat}, {"photo": ("card.png", png)})
        send(caption)

def send_poll(question, options):
    _tg("sendPoll", {"chat_id": os.environ["CHAT_ID"], "question": question[:290],
                     "options": json.dumps(options, ensure_ascii=False), "is_anonymous": "true"})

def _t12(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'م' if dt.hour >= 12 else 'ص'}"

def fmt_time(dt):
    return f"{_t12(dt.astimezone(DUBAI))} مصر | {_t12(dt.astimezone(KSA))} السعودية"

def _tr_google(text):
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ar&dt=t&q="
           + urllib.parse.quote(text))
    data = json.loads(http_get(url, 15))
    return "".join(part[0] for part in data[0] if part and part[0]).strip()

def _tr_google_mobile(text):
    raw = http_get("https://translate.google.com/m?sl=en&tl=ar&q=" + urllib.parse.quote(text), 15).decode("utf-8", "ignore")
    m = re.search(r'class="result-container">(.*?)</div>', raw, re.S)
    return html.unescape(m.group(1)).strip() if m else ""

def _tr_mymemory(text):
    data = json.loads(http_get("https://api.mymemory.translated.net/get?langpair=en|ar&q=" + urllib.parse.quote(text), 15))
    out = data["responseData"]["translatedText"]
    return "" if "MYMEMORY WARNING" in out.upper() else html.unescape(out).strip()

def translate_ar(text, verbose=False):
    for fn in (_tr_google, _tr_google_mobile, _tr_mymemory):
        try:
            out = fn(text)
            if out and out != text:
                return out
        except Exception as ex:
            if verbose: print(f"translate {fn.__name__} failed: {ex}")
    return None

# ---------------- calendar ----------------
def fetch_calendar():
    return json.loads(http_get(CAL_URL, 30))

PRIORITY = [("federal funds", 10), ("fomc", 9), ("non-farm", 9), ("rate statement", 8), ("monetary policy", 8),
            ("cpi", 8), ("interest rate", 8), ("official bank rate", 8), ("main refinancing", 8), ("gdp", 6),
            ("unemployment", 6), ("retail sales", 6), ("pce", 6), ("ppi", 5), ("pmi", 4), ("claims", 4)]

def ev_score(e):
    t = (e.get("title") or "").lower()
    sc = max([w for k, w in PRIORITY if k in t] or [1])
    return sc + (2 if e.get("country") == "USD" else 0)

def cal_events(events):
    seen = {(e.get("country"), e.get("date"), e.get("title")) for e in events}
    best = {}
    for e in events:
        if e.get("impact") != "High" or e.get("country") not in CURRENCIES:
            continue
        t = e.get("title") or ""
        if t.startswith("Core ") and (e.get("country"), e.get("date"), t[5:]) in seen:
            continue  # the plain version is enough
        cur = best.get(e.get("date"))
        if cur is None or ev_score(e) > ev_score(cur):
            best[e.get("date")] = e  # one event per release time: the most important one
    for e in best.values():
        try:
            yield e, datetime.fromisoformat(e["date"]).astimezone(DUBAI)
        except Exception:
            continue

def ev_key(e):
    return f'{e.get("date")}|{e.get("country")}|{e.get("title")}'

def ev_names(e):
    return COUNTRY_AR.get(e["country"], e["country"]), TITLE_AR.get(e["title"], e["title"])

def fc_line(e):
    fc, pv = (e.get("forecast") or "").strip(), (e.get("previous") or "").strip()
    parts = ([f"التوقع: {fc}"] if fc else []) + ([f"السابق: {pv}"] if pv else [])
    return " | ".join(parts)

STAGE_AR = {60: "بعد ساعة تقريبًا", 5: "بعد 5 دقايق", 1: "بعد دقيقة"}

def _fc_pv(e):
    fc, pv = (e.get("forecast") or "").strip(), (e.get("previous") or "").strip()
    bits = ([f"🎯 المتوقع <b>{esc(fc)}</b>"] if fc else []) + ([f"📊 السابق <b>{esc(pv)}</b>"] if pv else [])
    return "   ".join(bits)

def msg_prealert(e, when, stage=60):
    c, t = ev_names(e)
    flag = FLAGS.get(e["country"], "")
    lines = [pick(PRE_POOL[stage], ev_key(e) + str(stage)), f"{flag} {esc(t)}"]
    line = _fc_pv(e)
    if line: lines.append(line)
    lines.append(LINK)
    return "\n".join(lines)

def msg_now(e, when):
    c, t = ev_names(e)
    flag = FLAGS.get(e["country"], "")
    lines = [pick(NOW_POOL, ev_key(e)), f"{flag} {esc(t)}"]
    line = _fc_pv(e)
    if line: lines.append(line)
    lines.append(LINK)
    return "\n".join(lines)

def msg_morning(items, today):
    lines = [f"📅 <b>أهم أخبار اليوم</b>", f"🗓️ {DAYS_AR[today.weekday()]} {today.day}/{today.month} ", LINE]
    for e, when in items:
        c, t = ev_names(e)
        lines.append(f"🕒 <b>{fmt_time(when)}</b>  {FLAGS.get(e['country'], '')} {esc(c)}: {esc(t)}")
    lines += [LINE, "🔔 هنبعت تنبيه قبل كل خبر وبعده", f"ℹ️ {DISCLAIMER}", FOOTER]
    return "\n".join(lines)

def run_calendar(state, now, events, out):
    items = sorted(cal_events(events), key=lambda x: x[1])
    today = now.date().isoformat()
    todays = [(e, w) for e, w in items if w.date() == now.date()]
    mkey = f"morning:{today}"
    if todays and now.hour >= MORNING_HOUR and now.hour < MORNING_HOUR + 6 and mkey not in state["sent"]:
        out.append((mkey, msg_morning(todays, now)))
    for e, when in items:
        left = (when - now).total_seconds() / 60
        due = [st for st in LEAD_STAGES if left <= st]
        if left > 0 and due:
            stage = min(due)  # if a run is late, only send the stage that still makes sense
            key = f"pre{stage}:" + ev_key(e)
            if key not in state["sent"]:
                for bigger in LEAD_STAGES:
                    if bigger > stage:
                        state["sent"].append(f"pre{bigger}:" + ev_key(e))  # skip stages already passed
                out.append((key, msg_prealert(e, when, stage)))
        elif -8 <= left <= 0 and ("now:" + ev_key(e)) not in state["sent"]:
            out.append(("now:" + ev_key(e), msg_now(e, when)))


# ---------------- market reaction after a US release (measured, not predicted) ----------------
def intraday(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
    res = json.loads(http_get(url, 20))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    return [(t, c, h, l) for t, c, h, l in zip(res["timestamp"], q["close"], q["high"], q["low"])
            if c is not None and h is not None and l is not None]

def reaction(symbol, t0, minutes=5):
    """Move of the price in the N minutes after t0 (epoch seconds)."""
    bars = intraday(symbol)
    before = [b for b in bars if b[0] <= t0]
    after = [b for b in bars if t0 < b[0] <= t0 + minutes * 60]
    if not before or len(after) < max(2, minutes - 2):
        return None
    p0 = before[-1][1]
    p1 = after[-1][1]
    hi, lo = max(b[2] for b in after), min(b[3] for b in after)
    return {"p0": p0, "p1": p1, "move": p1 - p0, "pct": (p1 / p0 - 1) * 100, "range": hi - lo, "range_pct": (hi - lo) / p0 * 100}

def strength_word(range_pct):
    if range_pct < 0.10: return "هادئة"
    if range_pct < 0.25: return "متوسطة"
    if range_pct < 0.50: return "قوية"
    return "عنيفة"

def msg_reaction(e, gold, dxy):
    c, t = ev_names(e)
    arrow = "🟢 ▲" if gold["move"] >= 0 else "🔴 ▼"
    lines = [f"📊 <b>تفاعل السوق مع الخبر</b>", f"{FLAGS.get(e['country'], '')} {esc(t)}",
             f"🥇 الذهب: {arrow} <b>{abs(gold['move']):.1f}$</b> ({gold['pct']:+.2f}%) خلال 5 دقايق",
             f"⚡ مدى التذبذب: <b>{gold['range']:.1f}$</b> - حركة {strength_word(gold['range_pct'])}"]
    if dxy:
        lines.append(f"💵 مؤشر الدولار: {'🟢 ▲' if dxy['move'] >= 0 else '🔴 ▼'} {dxy['pct']:+.2f}%")
    lines += [LINK]
    return "\n".join(lines)

def run_reaction(state, now, events, out):
    for e, when in cal_events(events):
        if e.get("country") != "USD": continue
        after = (now - when).total_seconds() / 60
        key = "react:" + ev_key(e)
        if 5.5 <= after <= 25 and key not in state["sent"]:
            t0 = int(when.timestamp())
            try:
                gold = reaction("GC=F", t0)
            except Exception as ex:
                print("reaction gold failed:", ex); continue
            if not gold: continue
            try: dxy = reaction("DX-Y.NYB", t0)
            except Exception: dxy = None
            out.append((key, msg_reaction(e, gold, dxy)))

# ---------------- RSS news ----------------
NUM = r"[+\-]?\d[\d.,]*\s?[%KMB]?"

def _f(x):
    try: return float(re.sub(r"[^\d.\-]", "", x.replace(",", "")))
    except Exception: return None

def parse_result(title):
    m = re.search(rf"(?P<a>{NUM})\s+vs\.?\s+(?P<f>{NUM})\s+(?:expected|est\.?|forecast|consensus)", title, re.I)
    if not m: return None
    pm = re.search(rf"(?:prior|previous)[^\d+\-]*(?P<p>{NUM})", title, re.I)
    a, f = _f(m.group("a")), _f(m.group("f"))
    if a is None or f is None: return None
    verdict = "أعلى من المتوقع" if a > f else "أقل من المتوقع" if a < f else "مطابق للمتوقع"
    name = re.sub(r"\s+", " ", title[:m.start()]).strip(" :-,") or "بيانات اقتصادية"
    name = re.sub(r"[+\-]?\d[\d.,]*\s?[%KMB]?$", "", name).strip() or name
    return {"name": name, "actual": m.group("a").strip(), "forecast": m.group("f").strip(),
            "prev": pm.group("p").strip() if pm else "", "verdict": verdict}

def parse_feed(raw):
    root = ET.fromstring(raw)
    items = []
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        def g(tag):
            el = it.find(tag) if it.find(tag) is not None else it.find("{http://www.w3.org/2005/Atom}" + tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = html.unescape(re.sub(r"<[^>]+>", "", g("title"))).strip()
        pub = g("pubDate") or g("published") or g("updated")
        try:
            dt = parsedate_to_datetime(pub)
        except Exception:
            try: dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception: dt = None
        if dt and dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        if title: items.append((title, dt))
    return items

def norm(t):
    return set(w for w in re.findall(r"[a-z0-9$%.]+", t.lower()) if len(w) > 2)

def is_dup(title, seen):
    a = norm(title)
    for s in seen:
        b = set(s.split())
        if a and b and len(a & b) / max(1, len(a | b)) >= 0.6:
            return True
    return False

def relevant(title):
    tl = title.lower() + " "
    return any(k in tl for k in KEYWORDS) and not any(s in tl for s in SKIP)

def run_news(state, now, out):
    day = now.date().isoformat()
    count = state["news_count"].get(day, 0)
    found, used = [], 0
    for name, url in FEEDS.items():
        try:
            items = parse_feed(http_get(url))
        except Exception as ex:
            print(f"feed failed: {name}: {ex}"); continue
        for title, dt in items:
            if dt is None or (datetime.now(timezone.utc) - dt) > timedelta(minutes=NEWS_MAX_AGE_MIN): continue
            if relevant(title): found.append((dt, name, title))
    for dt, name, title in sorted(found):
        if used >= MAX_NEWS_PER_RUN or count + used >= MAX_NEWS_PER_DAY: break
        if is_dup(title, state["titles"]): continue
        tl = title.lower()
        is_result = any(w in tl for w in RESULT_WORDS) and re.search(r"\d", title)
        ar = translate_ar(title)
        if not ar:
            continue  # Arabic only
        ar = re.sub(r"^(?:investing\s?live|InvestingLive)\s*[:\-–]?\s*", "", ar, flags=re.I).strip()
        res = parse_result(title) if is_result else None
        src = name
        head = "📊 <b>نتيجة</b>" if is_result else pick(NEWS_POOL, title)
        text = f"{head}\n{esc(ar)}\n📰 {esc(src)}\n{LINK}"
        extra = None
        if res:
            label = translate_ar(res["name"]) or res["name"]
            extra = ("img", lambda r=res, l=label: C().card_result("", l, r["actual"], r["forecast"], r["prev"], r["verdict"]))
        if extra is None:
            extra = ("img", lambda a=ar, t=title, sr=src: C().card_news(a, t, sr))
        out.append((None, text, extra))
        state["titles"].append(" ".join(sorted(norm(title))))
        used += 1
    state["news_count"][day] = count + used

# ---------------- gold + currency strength (Yahoo Finance chart, no key) ----------------
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

def yahoo_change(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    res = json.loads(http_get(url, 20))["chart"]["result"][0]
    price = res["meta"]["regularMarketPrice"]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    prev = closes[-2] if len(closes) >= 2 else res["meta"]["chartPreviousClose"]
    return price, (price / prev - 1) * 100

def currency_strength(changes):
    score = {c: [] for c in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]}
    for pair, ch in changes.items():
        base, quote = pair[:3], pair[3:]
        score[base].append(ch); score[quote].append(-ch)
    return sorted(((c, sum(v) / len(v)) for c, v in score.items() if v), key=lambda x: -x[1])

SNAP_NAMES = {"USD": "الدولار الأمريكي", "EUR": "اليورو", "GBP": "الإسترليني", "JPY": "الين", "AUD": "الأسترالي",
              "CAD": "الكندي", "CHF": "الفرنك السويسري", "NZD": "النيوزيلندي"}

def msg_snapshot(gold, strength, now):
    lines = [f"📈 <b>لقطة السوق</b>", f"🕒 {fmt_time(now)}", LINE]
    if gold:
        price, ch = gold
        arrow = "🟢" if ch >= 0 else "🔴"
        lines.append(f"🥇 <b>الذهب</b>: {price:,.2f} دولار للأوقية")
        lines.append(f"{arrow} التغيّر عن إغلاق أمس: <b>{ch:+.2f}%</b>")
    if strength:
        names = {"USD": "الدولار الأمريكي", "EUR": "اليورو", "GBP": "الإسترليني", "JPY": "الين", "AUD": "الأسترالي",
                 "CAD": "الكندي", "CHF": "الفرنك السويسري", "NZD": "النيوزيلندي"}
        flags = {**FLAGS}
        lines += ["", "💱 <b>قوة العملات اليوم</b> (من الأقوى للأضعف)"]
        for i, (c, v) in enumerate(strength, 1):
            lines.append(f"{'🟢' if v >= 0 else '🔴'} {i}. {flags.get(c, '')} {names[c]}: <b>{v:+.2f}%</b>")
    lines += [LINE, f"ℹ️ {DISCLAIMER}", FOOTER]
    return "\n".join(lines)

def run_snapshot(state, now, out):
    if now.weekday() >= 5: return
    for h in SNAPSHOT_HOURS:
        key = f"snap:{now.date().isoformat()}:{h}"
        if now.hour >= h and now.hour < h + 3 and key not in state["sent"]:
            try:
                gold = yahoo_change("GC=F")
            except Exception as ex:
                print("gold failed:", ex); gold = None
            changes = {}
            for p in PAIRS:
                try: changes[p] = yahoo_change(p + "=X")[1]
                except Exception as ex: print("pair failed:", p, ex)
            strength = currency_strength(changes) if len(changes) >= 5 else None
            if gold or strength:
                extra = None
                if strength:
                    rows = [(c, SNAP_NAMES[c], v) for c, v in strength]
                    sub = f"{DAYS_AR[now.weekday()]} {now.day}/{now.month} - {fmt_time(now)}"
                    extra = ("img", lambda r=rows, sb=sub: C().card_strength(r, sb))
                out.append((key, msg_snapshot(gold, strength, now), extra))
            else:
                print("snapshot skipped: no data")
            return


# ---------------- market sessions ----------------
SESSIONS = [  # name, flag, timezone, local open time
    ("لندن", "🇬🇧", "Europe/London", (8, 0)),
    ("الأمريكي", "🇺🇸", "America/New_York", (9, 30)),
]
INDICES = [("^GSPC", "S&P 500"), ("^IXIC", "ناسداك"), ("^DJI", "داو جونز"), ("^VIX", "مؤشر الخوف")]

def session_open_dubai(tzname, hm, now):
    tz = ZoneInfo(tzname)
    local_now = now.astimezone(tz)
    if local_now.weekday() >= 5:
        return None
    return local_now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0).astimezone(DUBAI)

def msg_open_alert(name, flag, open_dubai):
    return "\n".join([f"🔔 <b>السوق {name} يفتح بعد 5 دقايق</b>", f"{flag} السيولة بتزيد والتذبذب بيرتفع", LINK])

def msg_indices(rows):
    up = sum(1 for _, _, ch in rows if ch >= 0 and _ != "^VIX")
    head = "🟢 <b>المؤشرات الأمريكية تفتتح على ارتفاع</b>" if up >= 2 else "🔴 <b>المؤشرات الأمريكية تفتتح على انخفاض</b>"
    lines = [head, LINE]
    for sym, nm, ch in rows:
        lines.append(f"{'🟢' if ch >= 0 else '🔴'} {nm}: <b>{ch:+.2f}%</b>")
    lines += [LINE, f"ℹ️ {DISCLAIMER}", FOOTER]
    return "\n".join(lines)

def run_sessions(state, now, out):
    today = now.date().isoformat()
    for name, flag, tzname, hm in SESSIONS:
        op = session_open_dubai(tzname, hm, now)
        if not op: continue
        left = (op - now).total_seconds() / 60
        key = f"open5:{name}:{today}"
        if 0 < left <= 5 and key not in state["sent"]:
            out.append((key, msg_open_alert(name, flag, op)))
        if name == "الأمريكي":
            after = -left
            ikey = f"usidx:{today}"
            if 2 <= after <= 25 and ikey not in state["sent"]:
                rows = []
                for sym, nm in INDICES:
                    try: rows.append((sym, nm, yahoo_change(sym)[1]))
                    except Exception as ex: print("index failed:", sym, ex)
                if len(rows) >= 3:
                    out.append((ikey, msg_indices(rows)))


# ---------------- closes, weekly, tips, polls ----------------
EU_CLOSE = [("^GDAXI", "داكس ألمانيا"), ("^FTSE", "فوتسي لندن"), ("^FCHI", "كاك فرنسا"), ("^STOXX50E", "يورو ستوكس 50")]
US_CLOSE = [("^GSPC", "S&P 500"), ("^IXIC", "ناسداك"), ("^DJI", "داو جونز"), ("GC=F", "الذهب"), ("DX-Y.NYB", "مؤشر الدولار DXY")]
WEEKLY = [("GC=F", "الذهب"), ("DX-Y.NYB", "مؤشر الدولار DXY"), ("^GSPC", "S&P 500"), ("EURUSD=X", "اليورو/دولار"),
          ("GBPUSD=X", "الإسترليني/دولار"), ("USDJPY=X", "دولار/ين")]

def yahoo_weekly(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=15d"
    res = json.loads(http_get(url, 20))["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = res["meta"]["regularMarketPrice"]
    return price, (price / closes[-6] - 1) * 100 if len(closes) >= 6 else None

def table_rows(symbols, fn):
    rows = []
    for sym, nm in symbols:
        try:
            price, ch = fn(sym)
            if ch is not None: rows.append((nm, f"{price:,.2f}", ch))
        except Exception as ex:
            print("table row failed:", sym, ex)
    return rows

def msg_close(title, rows, up_word, down_word, n_head=None):
    hr = rows[:n_head] if n_head else rows
    ups = sum(1 for _, _, c in hr if c >= 0)
    head = f"🟢 <b>{up_word}</b>" if ups * 2 >= len(hr) else f"🔴 <b>{down_word}</b>"
    lines = [head, LINE]
    for nm, val, ch in rows:
        lines.append(f"{'🟢' if ch >= 0 else '🔴'} {nm}: {val}  (<b>{ch:+.2f}%</b>)")
    lines += [LINE, f"ℹ️ {DISCLAIMER}", FOOTER]
    return "\n".join(lines)

def run_closes(state, now, out):
    today = now.date().isoformat()
    for tzname, hm, kind in [("Europe/London", (16, 30), "eu"), ("America/New_York", (16, 0), "us")]:
        tz = ZoneInfo(tzname)
        ln = now.astimezone(tz)
        if ln.weekday() >= 5: continue
        close = ln.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0).astimezone(DUBAI)
        after = (now - close).total_seconds() / 60
        key = f"close:{kind}:{today}"
        if 5 <= after <= 40 and key not in state["sent"]:
            symbols = EU_CLOSE if kind == "eu" else US_CLOSE
            rows = table_rows(symbols, yahoo_change)
            if len(rows) < 3: continue
            if kind == "eu":
                title, sub, up, down = "إغلاق الأسواق الأوروبية", "ملخص الجلسة", "الأسواق الأوروبية تغلق على ارتفاع", "الأسواق الأوروبية تغلق على انخفاض"
            else:
                title, sub, up, down = "إغلاق وول ستريت", "ملخص الجلسة الأمريكية", "وول ستريت تغلق على ارتفاع", "وول ستريت تغلق على انخفاض"
            sb = f"{DAYS_AR[now.weekday()]} {now.day}/{now.month}"
            out.append((key, msg_close(title, rows, up, down, 3 if kind == "us" else None),
                        ("img", lambda t=title, sbt=sb, r=rows: C().card_table(t, sbt, r))))

def run_weekly(state, now, out):
    today = now.date().isoformat()
    # Sunday night: next week's calendar
    key = f"week:{today}"
    if now.weekday() == 6 and 21 <= now.hour <= 23 and key not in state["sent"]:
        try:
            ev = json.loads(http_get(CAL_URL.replace("thisweek", "nextweek"), 30))
            items = sorted(cal_events(ev), key=lambda x: x[1])
        except Exception as ex:
            print("nextweek failed:", ex); items = []
        if items:
            lines = ["🗓️ <b>جدول أهم أخبار الأسبوع الجاي</b>", LINE]
            day = None
            for e, w in items:
                if w.date() != day:
                    day = w.date(); lines += ["", f"📌 <b>{DAYS_AR[w.weekday()]} {w.day}/{w.month}</b>"]
                c, t = ev_names(e)
                lines.append(f"🕒 {_t12(w)} {FLAGS.get(e['country'], '')} {esc(c)}: {esc(t)}")
            lines += ["", LINE, "🔔 هنبعت تنبيه قبل كل خبر بساعة وبـ 5 دقايق وبدقيقة", f"ℹ️ {DISCLAIMER}", FOOTER]
            txt = "\n".join(lines)
            if len(txt) < 4000: out.append((key, txt))
    # Friday night: weekly recap
    key = f"recap:{today}"
    if now.weekday() == 4 and 22 <= now.hour <= 23 and key not in state["sent"]:
        rows = table_rows(WEEKLY, yahoo_weekly)
        if len(rows) >= 4:
            sb = f"ملخص الأسبوع - حتى {now.day}/{now.month}"
            txt = msg_close("", rows, "أسبوع إيجابي لمعظم الأسواق", "أسبوع ضاغط على معظم الأسواق")
            txt = txt.replace("\n" + LINE + "\n", "\n" + LINE + "\n📆 التغير خلال الأسبوع:\n", 1)
            out.append((key, txt, ("img", lambda r=rows, sbt=sb: C().card_table("ملخص الأسبوع", sbt, r))))

def run_engagement(state, now, out):
    day_no = now.date().toordinal()
    today = now.date().isoformat()
    key = f"tip:{today}"
    if 10 <= now.hour <= 14 and key not in state["sent"]:
        title, body = content.TIPS[day_no % len(content.TIPS)]
        cap = f"💡 <b>{esc(title)}</b>\n{LINE}\n{esc(body)}\n{LINE}\n{FOOTER}"
        out.append((key, cap, ("img", lambda t=title, b=body: C().card_tip(t, b))))
    key = f"poll:{today}"
    if now.weekday() < 5 and 19 <= now.hour <= 22 and key not in state["sent"]:
        q, opts = content.POLLS[day_no % len(content.POLLS)]
        out.append((key, "", ("poll", q, opts)))

# ---------------- diagnosis (manual run only) ----------------
def diagnose():
    print("=== DIAGNOSIS ===")
    try:
        ev = fetch_calendar(); print(f"calendar OK: {len(ev)} events; fields: {sorted(ev[0].keys()) if ev else '-'}")
    except Exception as ex: print("calendar FAILED:", ex)
    for name, url in FEEDS.items():
        try:
            items = parse_feed(http_get(url)); print(f"feed OK: {name}: {len(items)} items; newest: {items[0][0][:80] if items else '-'}")
        except Exception as ex: print(f"feed FAILED: {name}: {ex}")
    print("translate test:", translate_ar("Gold rises as dollar slips", verbose=True))
    for s in ["GC=F", "EURUSD=X"]:
        try: print("yahoo OK:", s, yahoo_change(s))
        except Exception as ex: print("yahoo FAILED:", s, ex)

# ---------------- main ----------------
_CAL = {"t": 0.0, "data": []}

def calendar_cached():
    if time.time() - _CAL["t"] > 300:
        try:
            _CAL["data"] = fetch_calendar(); _CAL["t"] = time.time()
        except Exception as ex:
            print("calendar fetch failed (using cache):", ex); _CAL["t"] = time.time() - 240
    return _CAL["data"]

def deliver(state, out):
    sent = 0
    for item in out:
        key, text = item[0], item[1]
        extra = item[2] if len(item) > 2 else None
        try:
            if extra and extra[0] == "poll":
                send_poll(extra[1], extra[2])
            elif extra and extra[0] == "img":
                try:
                    send_photo(extra[1](), text)
                except Exception as ex:
                    print("image failed, sending text:", ex)
                    send(text)
            else:
                send(text)
            if key: state["sent"].append(key)
            sent += 1
        except Exception as ex:
            print("send failed:", ex)
    return sent

def run_once(state, with_news=True):
    now = now_dubai()
    out = []
    try: run_calendar(state, now, calendar_cached(), out)
    except Exception as ex: print("calendar error:", ex)
    try: run_reaction(state, now, calendar_cached(), out)
    except Exception as ex: print("reaction error:", ex)
    if with_news:
        try: run_news(state, now, out)
        except Exception as ex: print("news error:", ex)
    for fn in (run_snapshot, run_sessions, run_closes, run_weekly, run_engagement):
        try: fn(state, now, out)
        except Exception as ex: print(fn.__name__, "error:", ex)
    return deliver(state, out)

def git_save():
    if not os.environ.get("GITHUB_ACTIONS"): return
    import subprocess
    cmds = [["git", "config", "user.name", "news-bot"], ["git", "config", "user.email", "bot@users.noreply.github.com"],
            ["git", "add", "state.json"]]
    for c in cmds: subprocess.run(c, check=False)
    if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode != 0:
        subprocess.run(["git", "commit", "-m", "update state"], check=False)
        subprocess.run(["git", "pull", "--rebase", "-X", "theirs", "-q"], check=False)
        subprocess.run(["git", "push", "-q"], check=False)

def main():
    if os.environ.get("TEST_RUN") == "yes":
        send("✅ <b>اختبار</b>\nالقناة شغالة والبوت متصل.")
        try:
            t, b = content.TIPS[0]
            send_photo(C().card_tip(t, b), "🖼️ اختبار الصور")
        except Exception as ex:
            print("image test failed:", ex)
        try:
            key = "PEXELS" if os.environ.get("PEXELS_KEY") else ("PIXABAY" if os.environ.get("PIXABAY_KEY") else "none")
            print("photo key:", key)
            send_photo(C().card_news("الذهب يقفز مع تراجع الدولار وترقب قرار الفائدة", "gold rises", "Reuters"),
                       "🖼️ اختبار صورة خبر - مصدر الخلفية: " + key)
            send_photo(C().card_news("باول يلمّح لخفض الفائدة في ديسمبر", "Fed Powell", "Reuters"), "🖼️ اختبار صورة خبر (الفيدرالي)")
        except Exception as ex:
            print("news card test failed:", ex)
        diagnose()
        if os.environ.get("TEST_ONLY") == "yes":
            return
    loop_min = float(os.environ.get("LOOP_MINUTES") or 0)
    state = load_state()
    if not loop_min:
        n = run_once(state); save_state(state); print(f"done, sent {n}"); return
    end = time.time() + loop_min * 60
    last_git, i = time.time(), 0
    while time.time() < end:
        t0 = time.time()
        try:
            n = run_once(state, with_news=(i % 2 == 0))
            save_state(state)
            if n: print(f"sent {n}")
        except Exception as ex:
            print("iteration error:", ex)
        i += 1
        if time.time() - last_git > 900:
            git_save(); last_git = time.time()
        time.sleep(max(1, 30 - (time.time() - t0)))
    print("loop finished")

if __name__ == "__main__":
    main()
