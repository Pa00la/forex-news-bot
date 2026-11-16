"""Forex / gold news bot for a Telegram channel (free, runs on GitHub Actions every ~5 min).

What it posts (Arabic, no emojis, no trade recommendations, Dubai time):
  - Morning calendar of today's high-impact events
  - Pre-alert ~1 hour before each high-impact release, and a "released now" alert
  - Breaking news from free RSS feeds (headline translated to Arabic + source)
  - Gold and currency strength snapshots a few times a day
Manual run (workflow_dispatch) sends a test message and prints a diagnosis of every source.
"""
import json, os, re, sys, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

DUBAI = ZoneInfo("Asia/Dubai")
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
    "FXStreet": "https://www.fxstreet.com/rss/news",
    "investingLive": "https://investinglive.com/feed",
    "CNBC Economy": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "CNBC Finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
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

def send(text):
    token, chat = os.environ["BOT_TOKEN"], os.environ["CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=30) as r:
        r.read()

def fmt_time(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'م' if dt.hour >= 12 else 'ص'}"

def translate_ar(text):
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ar&dt=t&q="
               + urllib.parse.quote(text))
        data = json.loads(http_get(url, 15))
        out = "".join(part[0] for part in data[0] if part and part[0])
        return out.strip() or None
    except Exception:
        return None

# ---------------- calendar ----------------
def fetch_calendar():
    return json.loads(http_get(CAL_URL, 30))

def cal_events(events):
    for e in events:
        if e.get("impact") != "High" or e.get("country") not in CURRENCIES:
            continue
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

def msg_prealert(e, when, stage=60):
    c, t = ev_names(e)
    lines = [f"تنبيه: {STAGE_AR[stage]}، {DAYS_AR[when.weekday()]} {fmt_time(when)} بتوقيت دبي", f"{c}: {t}"]
    if fc_line(e): lines.append(fc_line(e))
    if stage == 60:
        lines.append("خبر عالي التأثير وممكن يحرك الدولار والذهب. " + DISCLAIMER)
    return "\n".join(lines)

def msg_now(e, when):
    c, t = ev_names(e)
    lines = [f"صدر الآن: {c} - {t}", f"الوقت: {fmt_time(when)} بتوقيت دبي"]
    if fc_line(e): lines.append(fc_line(e))
    lines.append("القراءة الفعلية بتوصل في الرسالة اللي بعدها.")
    return "\n".join(lines)

def msg_morning(items, today):
    lines = [f"أهم أخبار اليوم، {DAYS_AR[today.weekday()]} {today.day}/{today.month} (بتوقيت دبي):"]
    for e, when in items:
        c, t = ev_names(e)
        lines.append(f"{fmt_time(when)} - {c}: {t}")
    lines.append("هنبعت تنبيه قبل كل خبر وبعده. " + DISCLAIMER)
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

# ---------------- RSS news ----------------
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
        head = "نتيجة" if is_result else "عاجل"
        text = f"{head}: {ar}\n{title}\nالمصدر: {name}" if ar else f"{head}: {title}\nالمصدر: {name}"
        out.append((None, text))
        state["titles"].append(" ".join(sorted(norm(title))))
        used += 1
    state["news_count"][day] = count + used

# ---------------- gold + currency strength (Yahoo Finance chart, no key) ----------------
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

def yahoo_change(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    meta = json.loads(http_get(url, 20))["chart"]["result"][0]["meta"]
    price, prev = meta["regularMarketPrice"], meta["chartPreviousClose"]
    return price, (price / prev - 1) * 100

def currency_strength(changes):
    score = {c: [] for c in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]}
    for pair, ch in changes.items():
        base, quote = pair[:3], pair[3:]
        score[base].append(ch); score[quote].append(-ch)
    return sorted(((c, sum(v) / len(v)) for c, v in score.items() if v), key=lambda x: -x[1])

def msg_snapshot(gold, strength, now):
    lines = [f"لقطة السوق، {fmt_time(now)} بتوقيت دبي:"]
    if gold:
        price, ch = gold
        lines.append(f"الذهب: {price:,.2f} دولار للأوقية ({ch:+.2f}% عن إغلاق أمس)")
    if strength:
        lines.append("قوة العملات اليوم (من الأقوى للأضعف):")
        names = {"USD": "الدولار الأمريكي", "EUR": "اليورو", "GBP": "الإسترليني", "JPY": "الين", "AUD": "الأسترالي",
                 "CAD": "الكندي", "CHF": "الفرنك", "NZD": "النيوزيلندي"}
        lines.append(" > ".join(f"{names[c]} ({v:+.2f}%)" for c, v in strength))
    lines.append(DISCLAIMER)
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
                out.append((key, msg_snapshot(gold, strength, now)))
            else:
                print("snapshot skipped: no data")
            return

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
    print("translate test:", translate_ar("Gold rises as dollar slips"))
    for s in ["GC=F", "EURUSD=X"]:
        try: print("yahoo OK:", s, yahoo_change(s))
        except Exception as ex: print("yahoo FAILED:", s, ex)

# ---------------- main ----------------
def main():
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if manual:
        send("اختبار: القناة شغالة والبوت متصل.")
        diagnose()
    now = now_dubai()
    state = load_state()
    out = []
    try: run_calendar(state, now, fetch_calendar(), out)
    except Exception as ex: print("calendar error:", ex)
    run_news(state, now, out)
    run_snapshot(state, now, out)
    sent = 0
    for key, text in out:
        try:
            send(text)
            if key: state["sent"].append(key)
            sent += 1
        except Exception as ex:
            print("send failed:", ex)
    save_state(state)
    print(f"done, sent {sent}")

if __name__ == "__main__":
    main()
