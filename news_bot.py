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
MORNING_HOUR = 10             # Egypt hour (fixed daily time) for the daily calendar post
SNAPSHOT_HOURS = [12, 17, 21] # Dubai hours for gold + currency strength posts (weekdays)
MAX_NEWS_PER_RUN = 2
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
    "CNBC Politics": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000113",
    "BBC US & Canada": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "NPR Politics": "https://feeds.npr.org/1014/rss.xml",
}
KEYWORDS = ["gold", "xau", "fed ", "fomc", "powell", "trump", "nfp", "payroll", "cpi", "inflation", "pce", "ppi",
            "gdp", "unemployment", "jobs report", "jobless", "rate cut", "rate hike", "rate decision", "interest rate",
            "bank of england", "boe", "ecb", "boj", "lagarde", "bailey", "ueda", "treasury", "yield", "dollar", "dxy",
            "oil", "opec", "tariff", "sanction", "iran", "israel", "ceasefire", "retail sales", "pmi", "ism",
            "china", "safe haven", "central bank",
            "election", "midterm", "senate", "congress", "ballot", "democrat", "republican", "white house", "treasury secretary",
            "bessent", "warsh", "waller", "shutdown", "debt ceiling", "supreme court", "zelensky", "putin", "xi jinping", "netanyahu"]
SKIP = ["should i ", "moneyist", "my husband", "my wife", "my mother", "my father", "my parents", "my daughter", "my son", "bitcoin", "crypto", "ethereum", "xrp", "dogecoin", "stock picks", "sponsored", "earnings call", "podcast",
        "singapore", "sgd", "malaysia", "ringgit", "thai ", "baht", "indonesia", "rupiah", "philippine", "taiwan", "korean won", "south korea", "vietnam", "rupee", "turkish lira", "south african rand", "brazilian real", "mexican peso", "hong kong dollar"]
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
FOOTER = "📚 لمتابعة أخبار الذهب والدولار والعملات لحظة بلحظة، انضم للقناة من الرابط:\n\nt.me/forex_news_M1"
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
NEWS_POOL_NORMAL = ["📰 <b>خبر جديد</b>", "🗞️ <b>من السوق</b>", "📌 <b>تحديث</b>"]
URGENT_MIN_SCORE = 2  # "عاجل" only for really important news, so it keeps its weight
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
    s["day_news"] = dict(list(sorted(s.get("day_news", {}).items()))[-5:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)

LRI, PDI, RLM = "\u2066", "\u2069", "\u200f"
_LATIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9&%.,:'+\-/_$ ]*[A-Za-z0-9%$]|[A-Za-z0-9]")

def fix_bidi(text):
    """Keep English/number runs in their natural order inside Arabic lines (tags and links untouched)."""
    parts = re.split(r"(<[^>]+>|&#?\w+;|[0-9#*]\ufe0f?\u20e3)", text)
    out = []
    for part in parts:
        if (part.startswith("<") and part.endswith(">")) or re.fullmatch(r"&#?\w+;|[0-9#*]\ufe0f?\u20e3", part):
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
    return unesc(m.group(1)).strip() if m else ""

def _tr_mymemory(text):
    data = json.loads(http_get("https://api.mymemory.translated.net/get?langpair=en|ar&q=" + urllib.parse.quote(text), 15))
    out = data["responseData"]["translatedText"]
    return "" if "MYMEMORY WARNING" in out.upper() else unesc(out).strip()

NAMES_AR = [(r"\bXi Jinping\b|\bXi\b", "شي جين بينغ"), (r"\bPutin\b", "بوتين"), (r"(?i:\bTrump(?:\'s)?\b)", "ترامب"),
            (r"\bBiden\b", "بايدن"), (r"\bPowell\b", "باول"), (r"\bLagarde\b", "لاغارد"), (r"\bBailey\b", "بايلي"),
            (r"\bUeda\b", "أويدا"), (r"\bWarsh\b", "وورش"), (r"\bZelensky\b", "زيلينسكي"), (r"\bNetanyahu\b", "نتنياهو"),
            (r"\bBessent\b", "بيسنت"), (r"\bWaller\b", "والر"), (r"\bMusk\b", "ماسك"), (r"\bModi\b", "مودي")]

NAMES_AR += [(r"\bJensen Huang\b", "جنسن هوانغ"), (r"\bTim Scott\b", "تيم سكوت"), (r"\bHoward Lutnick\b", "هوارد لوتنيك"),
             (r"\bJanet Yellen\b", "جانيت يلين"), (r"\bMike Johnson\b", "مايك جونسون"), (r"\bChuck Schumer\b", "تشاك شومر"),
             (r"\bJohn Thune\b", "جون ثون"), (r"\bKevin Hassett\b", "كيفن هاسيت"), (r"\bJamieson Greer\b", "جيميسون غير"),
             (r"\bSam Altman\b", "سام ألتمان"), (r"\bTim Cook\b", "تيم كوك"), (r"\bJamie Dimon\b", "جيمي ديمون"),
             (r"\bFed Chair(?:man)?\b", "رئيس الفيدرالي"), (r"\bTreasury Secretary\b", "وزير الخزانة"),
             (r"\bSenate Banking Committee\b", "لجنة الشؤون المصرفية في مجلس الشيوخ"),
             (r"\bSenate Finance Committee\b", "لجنة المالية في مجلس الشيوخ"),
             (r"\bHouse Financial Services Committee\b", "لجنة الخدمات المالية في مجلس النواب"),
             (r"\bSenate Majority Leader\b", "زعيم الأغلبية في مجلس الشيوخ"), (r"\bHouse Speaker\b|\bSpeaker of the House\b", "رئيس مجلس النواب")]

NAMES_AR += [(r"\bLutnick\b", "لوتنيك"), (r"\bHakeem Jeffries\b|\bJeffries\b", "حكيم جيفريز"), (r"\bSchumer\b", "شومر"),
             (r"\bThune\b", "ثون"), (r"\bHassett\b", "هاسيت"), (r"\bGreer\b", "غير")]

def fix_names(text):
    low = text.lower()
    for rx, ar_ in NAMES_AR:
        text = re.sub(rx, ar_, text, flags=re.I)
    if "committee" in low or "لجنة" in text:
        text = re.sub(r"\bChair(?:man|woman|person)?\b", "رئيس اللجنة", text)      # committee chair, not a president
        text = re.sub(r"\b(?:agreed to |will |to )?appear before\b", "الإدلاء بشهادته أمام", text)
    text = re.sub(r"\btestif(?:y|ies|ied|ying)\b", "الإدلاء بشهادته", text)
    return text

# unclear terms: replace a clumsy translation, or add a short explanation in brackets (first use only)
GLOSS = [("المثول أمام", "الإدلاء بشهادته أمام"),
         ("سقف الدين", "سقف الدين (الحد الأقصى لاقتراض الحكومة)"),
         ("التيسير الكمي", "التيسير الكمي (شراء البنك المركزي للسندات لضخ السيولة)"),
         ("التشديد الكمي", "التشديد الكمي (تقليص البنك المركزي لمشترياته من السندات)"),
         ("الركود التضخمي", "الركود التضخمي (تضخم مرتفع مع ضعف النمو)"),
         ("منحنى العائد", "منحنى العائد (الفرق بين عوائد السندات قصيرة وطويلة الأجل)"),
         ("الإغلاق الحكومي", "الإغلاق الحكومي (توقف الجهات الحكومية بسبب عدم إقرار الميزانية)"),
         ("الميزانية العمومية", "الميزانية العمومية (حجم أصول البنك المركزي)"),
         ("الدولار الأمريكي مؤشر", "مؤشر الدولار"),
         ("تجنب المخاطر", "تجنب المخاطر (ميل المستثمرين للأصول الآمنة)"),
         ("شهية المخاطرة", "شهية المخاطرة (ميل المستثمرين للأصول الأعلى مخاطرة)")]

_VARIANTS = {"ترامب": ("ترمب", "ترامپ", "ترومب", "ترمبو", "ترامبل"), "بوتين": ("بوتن", "بوتان"), "شي جين بينغ": ("شي جينبينغ", "شي جينبينج", "شي جين بينج"),
             "جنسن هوانغ": ("جينسن هوانغ", "جنسن هوانج", "جنسن هوانغ")}

def polish_names(out, src):
    """Plain-translation outputs: normalise the usual spellings of names that the source contains."""
    for good, bad in _VARIANTS.items():
        for b in bad:
            if b != good: out = out.replace(b, good)
    return out

PEOPLE_GLOSS = [("لوتنيك", "لوتنيك (وزير التجارة الأمريكي)"), ("بيسنت", "بيسنت (وزير الخزانة الأمريكي)"),
                ("جيفريز", "جيفريز (زعيم الديمقراطيين في مجلس النواب)"), ("شومر", "شومر (زعيم الديمقراطيين في مجلس الشيوخ)"),
                ("ثون", "ثون (زعيم الأغلبية الجمهورية في مجلس الشيوخ)"), ("مايك جونسون", "مايك جونسون (رئيس مجلس النواب)"),
                ("جنسن هوانغ", "جنسن هوانغ (رئيس شركة إنفيديا)"), ("جيمي ديمون", "جيمي ديمون (رئيس بنك جيه بي مورغان)"),
                ("سام ألتمان", "سام ألتمان (رئيس شركة OpenAI)"), ("تيم كوك", "تيم كوك (رئيس شركة أبل)"),
                ("إيلون ماسك", "إيلون ماسك (مالك تسلا وإكس)")]
GLOSS += [("مضيق هرمز", "مضيق هرمز (ممر شحن النفط الرئيسي في الخليج)"), ("أوبك", "أوبك (منظمة الدول المصدرة للنفط)"),
          ("التعريفات الجمركية", "التعريفات الجمركية (ضرائب على الواردات)")]

def polish_ar(t):
    for a, b in PEOPLE_GLOSS:
        if b and re.search(rf"(?<![\u0600-\u06FF]){re.escape(a)}(?![\u0600-\u06FF])", t) and (a + " (") not in t and b not in t:
            t = re.sub(rf"(?<![\u0600-\u06FF]){re.escape(a)}(?![\u0600-\u06FF])", b, t, count=1)
    t = re.sub(r"(?<![\u0600-\u06FF])(?:برم|برمب|ترمب)(?![\u0600-\u06FF])", "ترامب", t)   # common mangling of "Trump"
    for a, b in GLOSS:
        if a in t and (b not in t) and (a + " (") not in t:
            t = t.replace(a, b, 1)
    return t

def _missing_names(src, out):
    """Arabic names that must appear in the translation (because the English source has them) but do not."""
    return [ar_ for rx, ar_ in NAMES_AR if re.search(rx, src) and ar_ not in out and len(ar_) <= 14 and "لجنة" not in ar_ and "رئيس" not in ar_ and "وزير" not in ar_ and "زعيم" not in ar_]

def tr_score(title, out):
    """How trustworthy a translation looks (0 = fine, negative = problems). Used to pick the best of several candidates."""
    sc = 0
    en_words = re.findall(r"[A-Za-z0-9%$.\-']+", title)
    ar_words = re.findall(r"[\u0600-\u06FF]+", out or "")
    if len(en_words) < 6: sc -= 3            # too thin to be a useful headline
    if len(ar_words) < 4 or len(out or "") < 20: sc -= 3
    elif len(ar_words) < 0.4 * len(en_words): sc -= 2
    sc -= 2 * len(_missing_names(title, out or ""))
    a = re.sub(r"\D", "", _digits(out or ""))
    for n in re.findall(r"\d[\d.,]*", title):
        d_ = re.sub(r"\D", "", n)
        if len(d_) >= 2 and d_ not in a: sc -= 1   # a number got lost
    return sc

def translate_best(text, verbose=False):
    """Try every translator on both versions of the headline (names fixed first / plain English) and keep the best-scoring one."""
    fixed = fix_names(text)
    best, best_sc = None, -99
    for attempt in (fixed, text):
        for fn in (_tr_google, _tr_google_mobile, _tr_mymemory):
            try:
                out = fn(attempt)
                if not out or out == attempt: continue
                if attempt is text: out = polish_names(out, text)
                out = polish_ar(out)
                sc = tr_score(text, out)
                if sc > best_sc: best, best_sc = out, sc
                if sc >= 0: return best, best_sc
            except Exception as ex:
                if verbose: print(f"translate {fn.__name__} failed: {ex}")
    return best, best_sc

def translate_ar(text, verbose=False):
    return translate_best(text, verbose)[0]

# ---------------- "who is this?" lines from Wikipedia (automatic, always current) ----------------
_ROLES = {}   # english name -> arabic one-liner ("" = not a notable person); persisted in state.json
_ROLE_OK = re.compile(r"politician|businessman|businesswoman|executive|official|governor|minister|president|chair|ceo|senator|banker|economist|secretary|diplomat|judge|leader|speaker|entrepreneur|investor|prime minister|representative|congress", re.I)
_NAME_RX = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z\-]+){1,2})\b")
_NOT_NAMES = {"White House", "Wall Street", "Federal Reserve", "Supreme Court", "New York", "United States", "Middle East", "Hong Kong",
              "South Korea", "North Korea", "New Zealand", "Saudi Arabia", "Bank Of", "Fed Chair", "Treasury Secretary", "Senate Banking"}

def wiki_role(name):
    """Short Arabic description of a person from Wikipedia, or '' when unknown / not a notable political or business figure."""
    if name in _ROLES: return _ROLES[name]
    out = ""
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(name.replace(" ", "_")) + "?redirect=true"
        j = json.loads(http_get(url, 10))
        desc = re.sub(r"\s*\((?:born|b\.)[^)]*\)", "", j.get("description") or "").strip()
        title_ok = all(w.lower() in (j.get("title") or "").lower() for w in name.split())
        if j.get("type") == "standard" and title_ok and desc and _ROLE_OK.search(desc):
            ar_ = translate_ar(desc)
            if ar_: out = ar_
    except Exception as ex:
        print("wiki_role failed:", name, ex)
        return ""   # do not cache network failures
    _ROLES[name] = out
    return out

def who_lines(title, limit=2):
    """'👤 name: role' lines for people named in an English headline (people the built-in glossary already explains are skipped)."""
    lines, seen = [], set()
    for m in _NAME_RX.finditer(title or ""):
        nm = m.group(1)
        if nm in seen or nm in _NOT_NAMES or any(re.search(rx, nm, re.I) and ar_ in {a for a, b in PEOPLE_GLOSS if b} for rx, ar_ in NAMES_AR): continue
        seen.add(nm)
        role = wiki_role(nm)
        if role:
            lines.append(f"👤 {esc(translate_ar(nm) or nm)}: {esc(role)}")
        if len(lines) >= limit: break
    return lines

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

MEDIUM_PER_DAY = 12
MEDIUM_ALERTS = False  # medium events have no actual value in the calendar feed; results are posted from the news feed instead

def medium_events(events, high_dates):
    """Medium-impact releases of the main currencies: lighter alerts (5 min before + released now),
    only when no high-impact event shares the time, capped per day by importance."""
    by_day, seen = {}, set()
    for e in events:
        if e.get("impact") != "Medium" or e.get("country") not in CURRENCIES or e.get("country") == "CNY": continue
        d = e.get("date")
        if d in high_dates or d in seen: continue
        seen.add(d)
        by_day.setdefault((d or "")[:10], []).append(e)
    for day, lst in by_day.items():
        for e in sorted(lst, key=ev_score, reverse=True)[:MEDIUM_PER_DAY]:
            try:
                yield e, datetime.fromisoformat(e["date"]).astimezone(DUBAI)
            except Exception:
                continue

def ev_key(e):
    return f'{e.get("date")}|{e.get("country")}|{e.get("title")}'

_ABBR = [("non-farm", "NFP"), ("nonfarm", "NFP"), ("core pce", "PCE"), ("pce", "PCE"), ("core cpi", "CPI"), ("cpi", "CPI"), ("core ppi", "PPI"), ("ppi", "PPI"),
         ("unemployment rate", "UR"), ("adp", "ADP"), ("jolts", "JOLTS"), ("fomc", "FOMC"), ("gdp", "GDP"),
         ("ism", "ISM"), ("pmi", "PMI"), ("retail sales", "Retail Sales"), ("crude oil inventories", "EIA"), ("average hourly earnings", "AHE"),
         ("employment change", "NFP"), ("trade balance", "TB"), ("rate decision", "Rates"), ("cash rate", "RBA"), ("official bank rate", "BoE")]

def ev_abbr(e):
    t = (e.get("title") or "").lower()
    for k, ab in _ABBR:
        if k in t:
            return ab
    return ""

def ev_names(e):
    t = TITLE_AR.get(e["title"], e["title"])
    ab = ev_abbr(e)
    if ab and ab.lower() not in t.lower():
        t = f"{t} ({ab})"
    return COUNTRY_AR.get(e["country"], e["country"]), t

def fc_line(e):
    fc, pv = (e.get("forecast") or "").strip(), (e.get("previous") or "").strip()
    parts = ([f"التوقع: {fc}"] if fc else []) + ([f"السابق: {pv}"] if pv else [])
    return " | ".join(parts)

TITLE_AR.update({
    "Business Inventories m/m": "مخزون الشركات", "Existing Home Sales": "مبيعات المنازل القائمة",
    "Pending Home Sales m/m": "مبيعات المنازل المعلقة", "New Home Sales": "مبيعات المنازل الجديدة",
    "Housing Starts": "بدء بناء المنازل", "Building Permits": "تصاريح البناء",
    "Durable Goods Orders m/m": "طلبيات السلع المعمرة", "Core Durable Goods Orders m/m": "طلبيات السلع المعمرة الأساسية",
    "Trade Balance": "الميزان التجاري", "Crude Oil Inventories": "مخزونات النفط الخام",
    "CB Consumer Confidence": "ثقة المستهلك (كونفرنس بورد)", "Prelim UoM Consumer Sentiment": "ثقة المستهلك (ميشيجان)",
    "Empire State Manufacturing Index": "مؤشر إمباير ستيت للتصنيع", "Philly Fed Manufacturing Index": "مؤشر فيلادلفيا للتصنيع",
    "Richmond Manufacturing Index": "مؤشر ريتشموند للتصنيع", "Industrial Production m/m": "الإنتاج الصناعي",
    "Capacity Utilization Rate": "معدل استخدام الطاقة الإنتاجية", "Fed Chair Powell Speaks": "تصريحات رئيس الفيدرالي باول",
    "Natural Gas Storage": "مخزونات الغاز الطبيعي", "Treasury Currency Report": "تقرير العملات الأمريكي",
})

STAGE_AR = {60: "بعد ساعة تقريبًا", 5: "بعد 5 دقايق", 1: "بعد دقيقة"}

def _fc_pv(e):
    fc, pv = (e.get("forecast") or "").strip(), (e.get("previous") or "").strip()
    bits = ([f"🎯 المتوقع <b>{esc(fc)}</b>"] if fc else []) + ([f"📊 السابق <b>{esc(pv)}</b>"] if pv else [])
    return "   ".join(bits)

def impact_tag(e):
    return "🔴 <b>تأثير عالي</b>" if e.get("impact") == "High" else "🟡 <b>تأثير متوسط</b>"


def explain_lines(e):
    """Plain, conditional explanation shown in the 1-hour pre-alert (not a prediction)."""
    t = (e.get("title") or "").lower()
    cur = e.get("country")
    if "minutes" in t and "fomc" in t:
        return ["📝 محضر اجتماع الفيدرالي بيكشف نقاش اللجنة عن الفائدة والتضخم.",
                "🔺 نبرة أكثر تشددًا: ضغط على الذهب والأسهم ودعم للدولار",
                "▫️ دون مفاجآت: تأثير محدود",
                "🔻 نبرة أكثر تيسيرًا: دعم للذهب والأسهم وضغط على الدولار"]
    if any(k in t for k in ("interest rate", "federal funds", "rate statement", "official bank rate", "main refinancing", "monetary policy")):
        return ["🏛️ قرار الفائدة من أهم الأحداث على العملة والذهب.",
                f"🔺 قرار أو نبرة أكثر تشددًا: دعم للعملة ({cur}) وضغط على الذهب",
                "▫️ مطابق للتوقعات: تأثير محدود",
                f"🔻 قرار أو نبرة أكثر تيسيرًا: ضغط على العملة ({cur}) ودعم للذهب"]
    if cur == "USD" and any(k in t for k in ("unemployment", "jobless", "claims")):
        return ["🔺 بطالة أعلى من المتوقع: ضغط على الدولار ودعم للذهب",
                "🔻 بطالة أقل من المتوقع: دعم للدولار وضغط على الذهب"]
    if cur == "USD" and any(k in t for k in ("cpi", "ppi", "pce", "non-farm", "retail sales", "gdp", "pmi", "payroll")):
        return ["🔺 رقم أعلى من المتوقع: دعم للدولار وغالبًا ضغط على الذهب",
                "🔻 رقم أقل من المتوقع: ضغط على الدولار وغالبًا دعم للذهب"]
    if cur != "USD" and cur in CUR_AR and any(k in t for k in ("unemployment", "jobless", "employment", "cpi", "retail sales", "gdp", "pmi", "wage", "inflation")):
        inv = _inverse(t)
        up, dn = ("🔺 رقم أعلى من المتوقع", "🔻 رقم أقل من المتوقع")
        good, bad = (dn, up) if inv else (up, dn)
        return [f"{good}: دعم {lam(CUR_AR[cur])} وضغط خفيف على الدولار الأمريكي ودعم خفيف للذهب",
                f"{bad}: ضغط على {CUR_AR[cur]} ودعم خفيف للدولار الأمريكي وضغط خفيف على الذهب",
                "ℹ️ تأثير الحدث الأساسي على عملته، وعلى الذهب والدولار غير مباشر وأضعف"]
    return []

CUR_AR = {"USD": "الدولار الأمريكي", "AUD": "الدولار الأسترالي", "NZD": "الدولار النيوزيلندي", "CAD": "الدولار الكندي",
          "GBP": "الجنيه الإسترليني", "EUR": "اليورو", "JPY": "الين الياباني", "CHF": "الفرنك السويسري"}
_CUR_WORDS = [("australia", "AUD"), ("aussie", "AUD"), ("new zealand", "NZD"), ("kiwi", "NZD"), ("canada", "CAD"), ("canadian", "CAD"),
              ("uk ", "GBP"), ("u.k.", "GBP"), ("britain", "GBP"), ("british", "GBP"), ("eurozone", "EUR"), ("euro zone", "EUR"),
              ("germany", "EUR"), ("german", "EUR"), ("france", "EUR"), ("japan", "JPY"), ("swiss", "CHF"), ("switzerland", "CHF"),
              ("us ", "USD"), ("u.s.", "USD"), ("united states", "USD"), ("american", "USD"), ("fed ", "USD"), ("nonfarm", "USD"), ("payroll", "USD")]

def lam(n):
    return "لل" + n[2:] if n.startswith("ال") else "ل" + n

def _inverse(t):
    """True when a HIGHER number is bad for the currency (unemployment, jobless claims)."""
    t = (t or "").lower()
    return any(k in t for k in ("unemployment", "jobless", "claims", "layoff"))

def result_cur(title):
    t = " " + (title or "").lower() + " "
    for k, c in _CUR_WORDS:
        if k in t: return c
    return None

def impact_lines(title, verdict, cur=None):
    """What a released number means for the currency, the dollar and gold (rule-based, not a prediction)."""
    cur = cur or result_cur(title)
    if verdict == "مطابق للمتوقع":
        return ["▫️ مطابق للتوقعات، فالتأثير المباشر محدود"]
    higher = verdict == "أعلى من المتوقع"
    cur_up = higher != _inverse(title)
    if cur == "USD":
        return ["📈 إيجابي للدولار الأمريكي 🇺🇸" if cur_up else "📉 سلبي للدولار الأمريكي 🇺🇸",
                "📉 سلبي للذهب 🟡" if cur_up else "📈 إيجابي للذهب 🟡"]
    if cur in CUR_AR:
        return [f"{'📈 إيجابي' if cur_up else '📉 سلبي'} {lam(CUR_AR[cur])}",
                f"🇺🇸 الدولار: {'ضغط خفيف' if cur_up else 'دعم خفيف'} | 🟡 الذهب: {'دعم خفيف' if cur_up else 'ضغط خفيف'} (تأثير غير مباشر)"]
    return []

EVENT_POSTERS = [(r"fomc meeting minutes", "FOMC", "MEETING MINUTES"), (r"cpi", "CPI", "CONSUMER PRICE INDEX"),
                 (r"non-farm|nfp", "NFP", "NON-FARM PAYROLLS"), (r"federal funds|fomc|rate statement", "FED", "INTEREST RATE DECISION"),
                 (r"ppi", "PPI", "PRODUCER PRICE INDEX"), (r"pce", "PCE", "PCE PRICE INDEX"), (r"gdp", "GDP", "GROSS DOMESTIC PRODUCT"),
                 (r"retail sales", "RETAIL", "RETAIL SALES"), (r"unemployment|jobless", "JOBS", "UNEMPLOYMENT DATA"),
                 (r"official bank rate", "BOE", "BANK RATE DECISION"), (r"main refinancing", "ECB", "INTEREST RATE DECISION"),
                 (r"boj", "BOJ", "POLICY RATE DECISION")]
EVENT_HINT = {"USD": "American flag USA", "GBP": "Britain London flag", "EUR": "European Union flags", "JPY": "Japan Tokyo yen"}

def event_poster(e, when):
    """Image args for the 1-hour pre-alert of a big release, or None."""
    t = (e.get("title") or "").lower()
    for rx, abbr, eng in EVENT_POSTERS:
        if re.search(rx, t):
            c, name_ar = ev_names(e)
            name_ar = re.sub(r"\s*\([A-Za-z]+\)$", "", name_ar)  # the acronym is already huge on the poster
            cur = e.get("country")
            who = "الدولار والأسواق" if cur == "USD" else "العملة والأسواق"
            chips = ["ترقب عالي من الأسواق", f"الموعد {_t12(when.astimezone(DUBAI))} مصر", f"تأثير مباشر على {who}"]
            return ("img", lambda a=abbr, g=eng, n=name_ar, h=EVENT_HINT.get(cur, "world map finance"), ch=chips: C().card_event(a, g, n, h, ch))
    return None

def msg_prealert(e, when, stage=60):
    c, t = ev_names(e)
    flag = FLAGS.get(e["country"], "")
    if e.get("impact") == "High":
        head = pick(PRE_POOL[stage], ev_key(e) + str(stage))
    else:
        head = "⏳ <b>بعد 5 دقايق خبر متوسط التأثير</b>"
    lines = [head, f"{flag} {esc(t)}", impact_tag(e)]
    line = _fc_pv(e)
    if line: lines.append(line)
    if stage in (60, 5) and e.get("impact") == "High":
        ex = explain_lines(e)
        if ex: lines += ["", *ex, f"ℹ️ {DISCLAIMER}"]
    lines.append(LINK)
    return "\n".join(lines)

def msg_now(e, when):
    c, t = ev_names(e)
    flag = FLAGS.get(e["country"], "")
    head = pick(NOW_POOL, ev_key(e)) if e.get("impact") == "High" else "📌 <b>صدر الآن خبر متوسط التأثير</b>"
    lines = [head, f"{flag} {esc(t)}", impact_tag(e)]
    line = _fc_pv(e)
    if line: lines.append(line)
    if e.get("impact") == "High":
        lines.append("⏳ الرقم الفعلي وتأثيره على الذهب والدولار هيتنشر أول ما يتأكد")
    lines.append(LINK)
    return "\n".join(lines)

def msg_morning(items, today, rest=None):
    lines = [f"📅 <b>أهم أخبار اليوم</b>", f"🗓️ {DAYS_AR[today.weekday()]} {today.day}/{today.month}", "", LINE, ""]
    if items:
        for e, when in items:
            c, t = ev_names(e)
            lines += [f"🕒 <b>{fmt_time(when)}</b>", f"{FLAGS.get(e['country'], '')} {esc(t)}"]
    else:
        lines.append("✅ مفيش أخبار قوية النهارده")
    if rest:
        lines += ["", LINE, "", "🗓️ <b>باقي الأسبوع</b>"]
        day = None
        for e, w in rest:
            if w.date() != day:
                day = w.date(); lines += ["", f"📌 <b>{DAYS_AR[w.weekday()]} {w.day}/{w.month}</b>"]
            c, t = ev_names(e)
            lines.append(f"🕒 {_t12(w)}  {FLAGS.get(e['country'], '')} {esc(t)}")
    lines += ["", LINE, "", f"ℹ️ {DISCLAIMER}", FOOTER]
    return "\n".join(lines)

def run_calendar(state, now, events, out):
    items = sorted(cal_events(events), key=lambda x: x[1])
    today = now.date().isoformat()
    todays = [(e, w) for e, w in items if w.date() == now.date()]
    mkey = f"morning:{today}"
    if now.weekday() < 5 and MORNING_HOUR <= now.hour < MORNING_HOUR + 6 and mkey not in state["sent"]:
        rest = [(e, w) for e, w in items if w.date() > now.date()]
        txt = msg_morning(todays, now, rest)
        while len(txt) >= 3900 and rest:
            rest = rest[:-1]; txt = msg_morning(todays, now, rest)
        out.append((mkey, txt))
    mediums = list(medium_events(events, {e.get("date") for e, _ in items})) if MEDIUM_ALERTS else []
    for stages, group in ((LEAD_STAGES, items), ([5], mediums)):
        for e, when in group:
            left = (when - now).total_seconds() / 60
            due = [st for st in stages if left <= st]
            if left > 0 and due:
                stage = min(due)  # if a run is late, only send the stage that still makes sense
                key = f"pre{stage}:" + ev_key(e)
                if key not in state["sent"]:
                    for bigger in stages:
                        if bigger > stage:
                            state["sent"].append(f"pre{bigger}:" + ev_key(e))  # skip stages already passed
                    poster = event_poster(e, when) if (stage == 60 and e.get("impact") == "High") else None
                    out.append((key, msg_prealert(e, when, stage), poster) if poster else (key, msg_prealert(e, when, stage)))
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


# ---------------- end-of-day top 3 and fast gold move ----------------
def run_top3(state, now, out):
    if now.weekday() >= 5 or now.hour < 22: return
    day = now.date().isoformat()
    key = f"top3:{day}"
    if key in state["sent"]: return
    items = state.get("day_news", {}).get(day, [])
    if len(items) < 2: return
    top = sorted(items, key=lambda x: -x["score"])[:3]
    nums = ["1️⃣", "2️⃣", "3️⃣"]
    lines = ["🗞️ <b>أهم أخبار اليوم</b>", LINE]
    for i, it in enumerate(top):
        lines.append(f"{nums[i]} {esc(it['ar'])}")
    lines += [LINE, f"ℹ️ {DISCLAIMER}", FOOTER]
    out.append((key, "\n".join(lines)))


# ---------------- price cards, record levels ----------------
ASSET_CARDS = [("GC=F", "الذهب", "XAUUSD"), ("CL=F", "النفط الأمريكي (WTI)", "USOIL")]
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

def asset_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
    res = json.loads(http_get(url, 20))["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = res["meta"]["regularMarketPrice"]
    prev = res["meta"].get("chartPreviousClose") or closes[0]
    return price, price - prev, (price / prev - 1) * 100, closes

def record_context_from(rows, price, now_ts):
    """rows: [(epoch, close)] older -> newer (without today). Notable only if the level was last seen 200+ days ago."""
    at_or_below = [t for t, c in rows if c <= price]
    at_or_above = [t for t, c in rows if c >= price]
    if not at_or_below or now_ts - max(at_or_below) > 200 * 86400:   # price is a long-term LOW
        if not at_or_below: return "📉 أدنى مستوى في أكثر من سنتين"
        d = datetime.fromtimestamp(max(at_or_below), timezone.utc)
        return f"📉 أدنى مستوى منذ {AR_MONTHS[d.month - 1]} {d.year}"
    if not at_or_above or now_ts - max(at_or_above) > 200 * 86400:   # long-term HIGH
        if not at_or_above: return "📈 أعلى مستوى في أكثر من سنتين"
        d = datetime.fromtimestamp(max(at_or_above), timezone.utc)
        return f"📈 أعلى مستوى منذ {AR_MONTHS[d.month - 1]} {d.year}"
    return ""

def record_context(symbol, price):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2y"
        res = json.loads(http_get(url, 20))["chart"]["result"][0]
        rows = [(t, c) for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None][:-1]
        if len(rows) < 60: return ""
        return record_context_from(rows, price, time.time())
    except Exception as ex:
        print("record_context failed:", ex)
    return ""

def run_assets(state, now, out):
    """Gold and US oil (WTI) price cards once a day at 17:00."""
    if now.weekday() >= 5 or not (17 <= now.hour < 20): return
    for sym, nm, code in ASSET_CARDS:
        key = f"asset:{sym}:{now.date().isoformat()}"
        if key in state["sent"]: continue
        try:
            price, chg, pct, series = asset_data(sym)
        except Exception as ex:
            print("asset failed:", sym, ex); continue
        sub = f"{DAYS_AR[now.weekday()]} {now.day}/{now.month} - {fmt_time(now)}"
        lines = [f"{'🥇' if sym == 'GC=F' else '🛢️'} <b>{nm}</b> ({code})", f"{'🟢' if chg >= 0 else '🔴'} السعر: <b>{price:,.2f}</b> ({pct:+.2f}%)"]
        rc = record_context(sym, price) if sym == "GC=F" else ""
        if rc: lines.append(rc)
        lines += [LINE, f"ℹ️ {DISCLAIMER}", LINK]
        out.append((key, "\n".join(lines), ("img", lambda n=nm, c=code, p=price, ch=chg, pc=pct, sr=series, sb=sub: C().card_asset(n, c, p, ch, pc, sr, sb))))

GOLD_MOVE_PCT = 0.30
_gold_last = [0.0]

def run_goldmove(state, now, out):
    if now.weekday() >= 5: return
    if time.time() - _gold_last[0] < 120: return
    _gold_last[0] = time.time()
    try:
        bars = intraday("GC=F")
    except Exception as ex:
        print("goldmove failed:", ex); return
    if len(bars) < 20: return
    t_last, p_last = bars[-1][0], bars[-1][1]
    if time.time() - t_last > 600: return  # stale / market closed
    past = [b for b in bars if b[0] <= t_last - 900]
    if not past: return
    p0 = past[-1][1]
    pct = (p_last / p0 - 1) * 100
    if abs(pct) < GOLD_MOVE_PCT: return
    direction = "up" if pct > 0 else "down"
    bucket = int(time.time() // 1800)
    key = f"goldmove:{bucket}:{direction}"
    if key in state["sent"]: return
    arrow = "🟢 ▲" if pct > 0 else "🔴 ▼"
    verb = "يقفز" if pct > 0 else "يهبط"
    msg = "\n".join([f"⚡ <b>الذهب {verb} بسرعة</b>",
                     f"{arrow} <b>{abs(p_last - p0):.1f}$</b> ({pct:+.2f}%) خلال 15 دقيقة",
                     f"🥇 السعر الآن: <b>{p_last:,.2f}</b>"] + ([rc] if (rc := record_context("GC=F", p_last)) else []) + [LINE, f"ℹ️ {DISCLAIMER}", LINK])
    sub = f"{DAYS_AR[now.weekday()]} {now.day}/{now.month} - {fmt_time(now)}"
    def _gcard(sb=sub):
        price, chg, pc, sr = asset_data("GC=F")
        return C().card_asset("الذهب", "XAUUSD", price, chg, pc, sr, sb)
    out.append((key, msg, ("img", _gcard)))

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

_MATCH_STOP = {"us", "u", "s", "the", "of", "in", "rate", "data", "index", "change", "total", "m", "q", "y", "mom", "yoy", "qoq", "initial", "final", "flash", "prelim", "preliminary", "and", "a"}

def _tok(t):
    return {w for w in re.findall(r"[a-z]+", (t or "").lower()) if w not in _MATCH_STOP and len(w) > 1}

def match_event(name, now):
    """Find the calendar release (last 6 hours) that a result headline belongs to, to get its previous value and proper name."""
    nt = _tok(name)
    if not nt: return None
    best, bs = None, 0
    try:
        for e in calendar_cached():
            if e.get("impact") not in ("High", "Medium"): continue
            try: dt = datetime.fromisoformat(e["date"]).astimezone(DUBAI)
            except Exception: continue
            if not (0 <= (now - dt).total_seconds() / 60 <= 360): continue
            sc = len(nt & _tok(e.get("title")))
            cur = result_cur(name)
            if cur and cur == e.get("country"): sc += 1
            if sc > bs: best, bs = e, sc
    except Exception as ex:
        print("match_event failed:", ex)
    return best if bs >= 2 else None

def unesc(t):
    for _ in range(3):
        n = html.unescape(t)
        if n == t: break
        t = n
    return t

def parse_feed(raw):
    root = ET.fromstring(raw)
    items = []
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        def g(tag):
            el = it.find(tag) if it.find(tag) is not None else it.find("{http://www.w3.org/2005/Atom}" + tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = unesc(re.sub(r"<[^>]+>", "", g("title"))).strip()
        pub = g("pubDate") or g("published") or g("updated")
        try:
            dt = parsedate_to_datetime(pub)
        except Exception:
            try: dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception: dt = None
        if dt and dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        if title: items.append((title, dt))
    return items

_DUP_STOP = set("""the and for with from that this have has had are was were will would could should about after before over under into than
says said say new more most also amid as at by of on in to is it its be been not but out up down""".split())

_SYN = {"crude": "oil", "drops": "fall", "drop": "fall", "falls": "fall", "slides": "fall", "slumps": "fall", "declines": "fall",
        "tumbles": "fall", "retreats": "fall", "slips": "fall", "dips": "fall", "climbs": "rise", "jumps": "rise", "surges": "rise",
        "rises": "rise", "gains": "rise", "rallies": "rise", "advances": "rise", "november": "nov", "december": "dec",
        "october": "oct", "stronger": "strong", "strength": "strong", "greenback": "dollar", "usd": "dollar", "ahead": "await",
        "awaits": "await", "expectations": "expect", "expected": "expect", "expects": "expect", "bets": "expect", "hike": "raise", "hikes": "raise"}

def _stem(w):
    w = _SYN.get(w, w)
    if w.endswith("ies") and len(w) > 5: w = w[:-3] + "y"
    for suf in ("ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w

def norm(t):
    toks = (w.strip(".") for w in re.findall(r"[a-z0-9$%.]+", t.lower()))
    return set(_stem(w) for w in toks if len(w) > 2 and w not in _DUP_STOP)

def _same_story(a, b):
    """Same event reported with different wording by different outlets."""
    if not a or not b: return False
    inter = a & b
    if not inter: return False
    jac = len(inter) / len(a | b)
    ovl = len(inter) / min(len(a), len(b))
    nums = {w for w in inter if any(ch.isdigit() for ch in w)}
    if jac >= 0.45: return True
    if ovl >= 0.6 and len(inter) >= 4: return True
    if nums and len(inter) >= 3 and ovl >= 0.4: return True   # same figure + same topic words
    if len(inter) >= 3 and ovl >= 0.4: return True              # 3+ shared topic words covering 40% of the shorter title
    return False

def is_dup(title, seen):
    a = norm(title)
    return any(_same_story(a, set(s.split())) for s in seen)

def ar_tokens(t):
    return {w for w in re.findall(r"[\u0600-\u06FFa-zA-Z0-9%.]+", t or "") if len(w) > 3}

def is_dup_ar(ar, day_items):
    a = ar_tokens(ar)
    return any(_same_story(a, ar_tokens(it.get("ar"))) for it in day_items)

_NOT_NEWS_START = re.compile(r"^\s*(opinion|analysis|commentary|editorial|review|column|essay|explainer|op-ed|podcast|watch|live blog|live updates|"
                             r"why |how |what |what's |who |when |where |should |could |would |is |are |does |do |did |can |will |here's |here are |"
                             r"the case for|the case against|\d+ (things|ways|reasons|tips|stocks))", re.I)

def is_not_news(title):
    """Opinion pieces, explainers and questions: the channel wants facts that were actually said or happened."""
    t = (title or "").strip()
    return "?" in t or bool(_NOT_NEWS_START.match(t)) or bool(re.search(r"\|\s*(opinion|analysis)\b|\b(opinion|analysis)\s*[|:]", t, re.I))

def relevant(title):
    tl = title.lower() + " "
    if any(s in tl for s in SKIP) or is_not_news(title): return False
    return any(k in tl for k in KEYWORDS) or bool(parse_result(title))  # any data release with actual vs expected

NORMAL_PER_DAY = 12   # non-urgent news per day at most: the channel favours strong news over volume

IMPORTANT_WORDS = ["dollar", "yield", "treasury", "iran", "israel", "sanction", "china", "putin", "zelensky", "pmi", "retail sales",
                   "unemployment", "bessent", "warsh", "lagarde", "bailey", "ueda", "shutdown", "debt ceiling", "senate", "election",
                   "fed ", "powell", "trump", "cpi", "nfp", "payroll", "rate cut", "rate hike", "interest rate", "inflation",
                   "gold", "tariff", "opec", "oil", "ecb", "boj", "bank of england", "war", "ceasefire", "recession", "gdp", "jobs"]

ELECTION_WORDS = ["election", "midterm", "senate", "congress"]  # focus topic: counts double, so it earns the red "عاجل" label

def _digits(t):
    return (t or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))

def quality_ok(title, ar):
    """Drop headlines too thin to be useful, and translations that came out broken (too short, lost the numbers)."""
    en_words = re.findall(r"[A-Za-z0-9%$.\-']+", title)
    if len(en_words) < 6: return False
    ar_words = [w for w in re.findall(r"[\u0600-\u06FF]+", ar or "")]
    if len(ar_words) < 4 or len(ar or "") < 20: return False
    if len(ar_words) < 0.4 * len(en_words): return False
    nums = [n for n in re.findall(r"\d[\d.,]*", title) if len(re.sub(r"\D", "", n)) >= 2]
    a = _digits(ar)
    return all(re.sub(r"\D", "", n) in re.sub(r"\D", "", a) for n in nums)

def news_score(title):
    tl = title.lower() + " "
    return sum(1 for w in IMPORTANT_WORDS if w in tl) + 2 * sum(1 for w in ELECTION_WORDS if w in tl)

FAST_FEEDS = ("investingLive", "US BLS", "Federal Reserve")

def hot_window(now):
    """True from 1 minute before to 15 minutes after a high-impact release: the actual number is expected."""
    try:
        for e, when in cal_events(calendar_cached()):
            m = (now - when).total_seconds() / 60
            if -1 <= m <= 15: return True
    except Exception:
        pass
    return False

def run_news(state, now, out, fast=False):
    _ROLES.update(state.get("roles", {}))
    state["roles"] = _ROLES
    day = now.date().isoformat()
    count = state["news_count"].get(day, 0)
    found, used = [], 0
    for name, url in FEEDS.items():
        if fast and name not in FAST_FEEDS: continue
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
        ar, tsc = translate_best(title)
        if not ar:
            continue  # Arabic only
        ar = re.sub(r"^(?:investing\s?live|InvestingLive)\s*[:\-–]?\s*", "", ar, flags=re.I).strip()
        if is_dup_ar(ar, state.get("day_news", {}).get(day, [])):
            state["titles"].append(" ".join(sorted(norm(title))))  # remember it so it is not translated again
            continue
        res = parse_result(title) if is_result else None
        src = name
        sc_ = news_score(title)
        if not res and (sc_ < 1 or tsc < -1):   # one lost number is tolerated; anything worse is skipped
            print("skipped (weak/broken):", title[:70], "->", ar[:40])
            state["titles"].append(" ".join(sorted(norm(title))))
            continue
        if not res and sc_ < URGENT_MIN_SCORE and sum(1 for x in state.get("day_news", {}).get(day, []) if x.get("score", 0) < URGENT_MIN_SCORE) >= NORMAL_PER_DAY:
            continue   # enough ordinary news today
        urgent = sc_ >= URGENT_MIN_SCORE
        head = "📊 <b>نتيجة</b>" if is_result else pick(NEWS_POOL if urgent else NEWS_POOL_NORMAL, title)
        text = f"{head}\n{esc(ar)}\n📰 {esc(src)}"
        if not is_result:
            wl = who_lines(title)
            if wl: text += "\n" + "\n".join(wl)
        extra = None
        ev = match_event(res["name"], now) if res else None
        if res and ev:
            if not res["prev"] and (ev.get("previous") or "").strip(): res["prev"] = ev["previous"].strip()
            res["_flag"] = FLAGS.get(ev["country"], ""); res["_ar"] = ev_names(ev)[1]
        if res:
            fl = impact_lines(title, res["verdict"], ev.get("country") if ev else None)
            if fl:
                text = f"{head}\n{esc(ar)}\n🎯 الفعلي <b>{esc(res['actual'])}</b> مقابل المتوقع <b>{esc(res['forecast'])}</b>" + (f" والسابق <b>{esc(res['prev'])}</b>" if res["prev"] else "") + f" ({res['verdict']})\n" + "\n".join(fl) + f"\nℹ️ {DISCLAIMER}\n📰 {esc(src)}"
        if res:
            label = res.get("_ar") or translate_ar(res["name"]) or res["name"]
            extra = ("img", lambda r=res, l=label: C().card_result("", l, r["actual"], r["forecast"], r["prev"], r["verdict"]))
        if extra is None:
            extra = ("img", lambda a=ar, t=title, sr=src, u=urgent: C().card_news(a, t, sr, urgent=u))
        out.append((None, text, extra))
        state.setdefault("day_news", {}).setdefault(day, []).append({"ar": ar, "score": news_score(title)})
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
    ("سيدني", "🇦🇺", "Australia/Sydney", (10, 0)),
    ("طوكيو", "🇯🇵", "Asia/Tokyo", (9, 0)),
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

def msg_open_alert(name, flag, open_dubai, left=5):
    if left > 1.2:
        head = f"🔔 <b>السوق {name} يفتح بعد {int(round(left))} دقايق</b>"
    elif left > 0:
        head = f"🔔 <b>السوق {name} يفتح بعد دقيقة</b>"
    else:
        head = f"🔔 <b>السوق {name} فتح الآن</b>"
    return "\n".join([head, f"{flag} السيولة بتزيد والتذبذب بيرتفع", LINK])

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
        if -3 < left <= 6 and key not in state["sent"]:
            hint = {"سيدني": "Australia Sydney", "طوكيو": "Japan Tokyo yen", "لندن": "Britain London pound", "الأمريكي": "Wall Street stocks"}[name]
            sub = {"سيدني": "بداية يوم التداول في آسيا والمحيط الهادئ", "طوكيو": "الين والأسهم اليابانية في الواجهة",
                   "لندن": "السيولة بتزيد والتذبذب بيرتفع مع بداية الجلسة الأوروبية",
                   "الأمريكي": "أقوى سيولة في اليوم مع افتتاح وول ستريت"}[name]
            nm_full = "سوق " + name if name != "الأمريكي" else "السوق الأمريكي"
            out.append((key, msg_open_alert(name, flag, op, left), ("img", lambda a=nm_full, b=sub, h=hint: C().card_poster(a, b, h))))
        if name == "الأمريكي":
            after = -left
            ikey = f"usidx:{today}"
            if 2 <= after <= 25 and ikey not in state["sent"]:
                rows, trows = [], []
                for sym, nm in INDICES:
                    try:
                        pr, chg = yahoo_change(sym)
                        rows.append((sym, nm, chg)); trows.append((nm, f"{pr:,.2f}", chg))
                    except Exception as ex: print("index failed:", sym, ex)
                if len(rows) >= 3:
                    sub = f"{DAYS_AR[now.weekday()]} {now.day}/{now.month} - {fmt_time(now)}"
                    out.append((ikey, msg_indices(rows), ("img", lambda r=trows, sb=sub: C().card_table("المؤشرات الأمريكية", sb, r))))


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
            lines = ["🗓️ <b>جدول أهم أخبار الأسبوع الجاي</b>", "", LINE]
            day = None
            for e, w in items:
                if w.date() != day:
                    day = w.date(); lines += ["", f"📌 <b>{DAYS_AR[w.weekday()]} {w.day}/{w.month}</b>"]
                c, t = ev_names(e)
                lines.append(f"🕒 {_t12(w)}  {FLAGS.get(e['country'], '')} {esc(t)}")
            lines += ["", LINE, "", f"ℹ️ {DISCLAIMER}", FOOTER]
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

def run_friday(state, now, out):
    key = f"friday:{now.date().isoformat()}"
    if now.weekday() == 4 and 8 <= now.hour < 12 and key not in state["sent"]:
        cap = "🕌 <b>جمعة مباركة</b>\nنتمنى لكم يوم مبارك وأسواق هادية ومربحة بإذن الله.\n" + LINK
        out.append((key, cap, ("img", lambda: C().card_greeting("جمعة مباركة", "من فريق Forex News", "mosque minarets sky"))))

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
        if "t.me/forex_news_M1" not in text and not (len(item) > 2 and item[2] and item[2][0] == "poll"):
            text = text + "\n\n" + LINK   # every message carries the channel link
        extra = item[2] if len(item) > 2 else None
        try:
            if extra and extra[0] == "poll":
                send_poll(extra[1], extra[2])
            elif extra and extra[0] == "img":
                try:
                    send_photo(extra[1](), text)
                except Exception as ex:
                    print("image failed, sending text:", ex)
                    send(text if "t.me/forex_news_M1" in text else text + "\n\n" + LINK)
            else:
                send(text)
            if key: state["sent"].append(key)
            sent += 1
        except Exception as ex:
            print("send failed:", ex)
    return sent

def run_once(state, with_news=True, fast=False):
    now = now_dubai()
    out = []
    try: run_calendar(state, now, calendar_cached(), out)
    except Exception as ex: print("calendar error:", ex)
    try: run_reaction(state, now, calendar_cached(), out)
    except Exception as ex: print("reaction error:", ex)
    if with_news:
        try: run_news(state, now, out, fast=fast)
        except Exception as ex: print("news error:", ex)
    for fn in (run_snapshot, run_assets, run_friday, run_sessions, run_closes, run_weekly, run_engagement, run_top3, run_goldmove):
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
        hot = False
        try:
            hot = hot_window(now_dubai())
            n = run_once(state, with_news=(hot or i % 2 == 0), fast=hot)
            save_state(state)
            if n: print(f"sent {n}")
        except Exception as ex:
            print("iteration error:", ex)
        i += 1
        if time.time() - last_git > 900:
            git_save(); last_git = time.time()
        time.sleep(max(1, (10 if hot else 30) - (time.time() - t0)))
    print("loop finished")

if __name__ == "__main__":
    main()
