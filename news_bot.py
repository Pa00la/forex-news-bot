"""Forex news alerts for a Telegram channel. Runs every ~5 min on GitHub Actions.

Sends a pre-alert about 1 hour before each high-impact release.
All times are shown in Dubai time. No trade recommendations.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
DUBAI = ZoneInfo("Asia/Dubai")
STATE_FILE = "state.json"

# Countries (currencies) to cover. Edit freely.
CURRENCIES = {"USD", "GBP", "EUR", "JPY", "CAD", "AUD", "CHF", "NZD", "CNY"}
IMPACTS = {"High"}
LEAD_MIN = 60      # send the pre-alert this many minutes before the release
WINDOW_MIN = 12    # tolerate late scheduler runs: send if 0 < minutes_left <= LEAD_MIN and not sent yet
                   # (late runs still send as long as the release hasn't happened)

COUNTRY_AR = {
    "USD": "أمريكا", "GBP": "بريطانيا", "EUR": "منطقة اليورو", "JPY": "اليابان",
    "CAD": "كندا", "AUD": "أستراليا", "CHF": "سويسرا", "NZD": "نيوزيلندا", "CNY": "الصين",
}
# Common event names. Anything not listed is sent with its English title.
TITLE_AR = {
    "Non-Farm Employment Change": "الوظائف الأمريكية غير الزراعية NFP",
    "Unemployment Rate": "نسبة البطالة",
    "Average Hourly Earnings m/m": "متوسط الأجور بالساعة",
    "CPI m/m": "مؤشر أسعار المستهلك الشهري",
    "CPI y/y": "مؤشر أسعار المستهلك السنوي",
    "Core CPI m/m": "مؤشر أسعار المستهلك الأساسي الشهري",
    "Core PCE Price Index m/m": "مؤشر نفقات الاستهلاك الشخصي الأساسي",
    "PPI m/m": "مؤشر أسعار المنتجين",
    "Retail Sales m/m": "مبيعات التجزئة",
    "Core Retail Sales m/m": "مبيعات التجزئة الأساسية",
    "Advance GDP q/q": "الناتج المحلي الإجمالي الأولي",
    "Prelim GDP q/q": "الناتج المحلي الإجمالي المبدئي",
    "Final GDP q/q": "الناتج المحلي الإجمالي النهائي",
    "GDP m/m": "الناتج المحلي الإجمالي الشهري",
    "FOMC Statement": "بيان الفيدرالي الأمريكي",
    "FOMC Press Conference": "مؤتمر رئيس الفيدرالي الصحفي",
    "Federal Funds Rate": "قرار الفائدة الأمريكي",
    "FOMC Meeting Minutes": "محضر اجتماع الفيدرالي",
    "Unemployment Claims": "طلبات إعانة البطالة الأسبوعية",
    "ISM Manufacturing PMI": "مؤشر ISM للتصنيع",
    "ISM Services PMI": "مؤشر ISM للخدمات",
    "ADP Non-Farm Employment Change": "الوظائف الأمريكية الخاصة ADP",
    "Official Bank Rate": "قرار الفائدة البريطاني",
    "Main Refinancing Rate": "قرار الفائدة الأوروبي",
    "BOJ Policy Rate": "قرار الفائدة الياباني",
    "BOC Rate Statement": "قرار الفائدة الكندي",
    "Cash Rate": "قرار الفائدة الأسترالي",
}

def fetch_events():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0 (news-bot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sent": []}

def save_state(state):
    state["sent"] = state["sent"][-400:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

def event_key(e):
    return f'{e.get("date")}|{e.get("country")}|{e.get("title")}'

def fmt_time_ar(dt):
    days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    h = dt.hour % 12 or 12
    suffix = "م" if dt.hour >= 12 else "ص"
    return f"{days[dt.weekday()]} {h}:{dt.minute:02d} {suffix}"

def build_message(e, when):
    title = TITLE_AR.get(e["title"], e["title"])
    country = COUNTRY_AR.get(e["country"], e["country"])
    lines = [f"تنبيه: بعد ساعة تقريبًا، {fmt_time_ar(when)} بتوقيت دبي",
             f"{country}: {title}"]
    fc, pv = (e.get("forecast") or "").strip(), (e.get("previous") or "").strip()
    if fc or pv:
        parts = []
        if fc: parts.append(f"التوقع: {fc}")
        if pv: parts.append(f"السابق: {pv}")
        lines.append(" | ".join(parts))
    lines.append("خبر عالي التأثير وممكن يحرك الدولار والذهب. للمعلومات فقط وليس توصية.")
    return "\n".join(lines)

def send(text):
    token, chat = os.environ["BOT_TOKEN"], os.environ["CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=30) as r:
        r.read()

def due_events(events, now):
    for e in events:
        if e.get("impact") not in IMPACTS or e.get("country") not in CURRENCIES:
            continue
        try:
            when = datetime.fromisoformat(e["date"]).astimezone(DUBAI)
        except Exception:
            continue
        left = (when - now).total_seconds() / 60
        if 0 < left <= LEAD_MIN:
            yield e, when

def main(dry_run=False):
    now = datetime.now(timezone.utc).astimezone(DUBAI)
    events = fetch_events()
    state = load_state()
    n = 0
    for e, when in due_events(events, now):
        k = event_key(e)
        if k in state["sent"]:
            continue
        msg = build_message(e, when)
        if dry_run:
            print(msg, "\n---")
        else:
            send(msg)
            state["sent"].append(k)
        n += 1
    if not dry_run:
        save_state(state)
    print(f"done, sent {n}")

if __name__ == "__main__":
    main(dry_run="--dry" in sys.argv)
