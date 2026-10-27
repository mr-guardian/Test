import os
import re
import time
import json
import threading
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
TELEGRAM_CHAT_ID = "6009524525"

CHECK_INTERVAL_SECONDS = 900
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"

PAGES = {
    "sillagunerrr_story": {
        "url": "https://viewoo.co/u/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "story",
        "default_val": 0
    },
    "sillagunerrr_reposts": {
        "username": "sillagunerrr",
        "name": "sillagunerrr Repostlar",
        "type": "viewoo_reposts",
        "default_val": 6
    },
    "userr44559014_reposts": {
        "username": "userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "viewoo_reposts",
        "default_val": 1
    },
    "emin_htp_reposts": {
        "username": "emin_htp",
        "name": "emin_htp Repostlar",
        "type": "viewoo_reposts",
        "default_val": 11
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads",
        "default_val": 122
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://viewoo.co/"
}

LAST_AUDIT_REPORT = {}


def get_inline_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Durum & Rapor", "callback_data": "btn_durum"},
                {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"}
            ],
            [
                {"text": "🔕 Sessiz Mod", "callback_data": "btn_sessiz"}
            ],
            [
                {"text": "⏸ Takibi Durdur", "callback_data": "btn_durdur"},
                {"text": "▶️ Takibi Başlat", "callback_data": "btn_baslat"}
            ]
        ]
    }


def send_telegram_message(text, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": str(text)[:4000],
        "disable_notification": SILENT_MODE
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print(f"[!] Gönderim hatası: {e}")


def fetch_viewoo_reposts(username):
    """Viewoo API üzerinden kesin repost sayısını alır."""
    ts = int(time.time())
    url = f"https://viewoo.co/api/reposts?username={username}&_={ts}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()

            # Liste formatı
            if isinstance(data, list):
                return len(data), f"API Listesi ({len(data)} Repost)"

            # Sözlük / Nesne formatı
            if isinstance(data, dict):
                for k in ["items", "reposts", "data", "videos", "posts"]:
                    if k in data and isinstance(data[k], list):
                        return len(data[k]), f"API ({k}: {len(data[k])} Repost)"
                if "count" in data and isinstance(data["count"], int):
                    return data["count"], f"API Sayacı ({data['count']})"

            # Ham JSON içinde 19 haneli video ID'leri
            ids = set(re.findall(r'\b7\d{18}\b', json.dumps(data)))
            if len(ids) > 0:
                return len(ids), f"API Video ID ({len(ids)} Repost)"

        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, f"Hata: {str(e)[:25]}"


def check_page_count(key, page_info, current_state_val=0):
    global LAST_AUDIT_REPORT
    p_type = page_info["type"]
    default_val = page_info.get("default_val", 0)

    try:
        # 1. Viewoo Repost Takibi
        if p_type == "viewoo_reposts":
            count, detail = fetch_viewoo_reposts(page_info["username"])
            if count is not None:
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı - {detail}"
                return count
            else:
                fallback = current_state_val if current_state_val is not None else default_val
                LAST_AUDIT_REPORT[key] = f"⚠️ Araştırıldı - {detail} (Taban Korundu)"
                return fallback

        # 2. Viewoo Hikaye Takibi
        elif p_type == "story":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı (Sunucu yanıt vermedi)"
                return current_state_val if current_state_val is not None else default_val

            text_lower = resp.text.lower()
            if any(p in text_lower for p in ("no active stories", "no stories", "0 stories", "hikaye yok")):
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Hikaye Yok)"
                return 0

            soup = BeautifulSoup(resp.text, "html.parser")
            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            if story_items:
                c = len(set(str(el) for el in story_items))
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı ({c} Aktif Hikaye)"
                return c

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Hikaye Yok)"
            return 0

        # 3. Threadlook Threads Takibi
        elif p_type == "threads":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı"
                return current_state_val if current_state_val is not None else default_val

            text = BeautifulSoup(resp.text, "html.parser").get_text()

            # "THREADS 122" veya "122 threads" kalıbı (2025/2026 yılları filtrelenir)
            m = re.findall(r'THREADS\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
            if m and int(m[0]) not in (2025, 2026, 2027):
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (THREADS Sayacı Doğrulandı)"
                return int(m[0])

            m_alt = re.findall(r'(\d+)\s+threads', text, re.IGNORECASE)
            if m_alt and int(m_alt[0]) not in (2025, 2026, 2027):
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Alt Sayaç Doğrulandı)"
                return int(m_alt[0])

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Sabit Değer Korundu)"
            return current_state_val if current_state_val is not None else default_val

        return current_state_val if current_state_val is not None else default_val
    except Exception as e:
        LAST_AUDIT_REPORT[key] = f"❌ Hata: {str(e)[:25]}"
        return current_state_val if current_state_val is not None else default_val


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_check():
    global IS_TRACKING_PAUSED
    if IS_TRACKING_PAUSED:
        return

    current_state = load_state()
    changes = []

    for key, info in PAGES.items():
        old_val = current_state.get(key, -1)
        count = check_page_count(key, info, current_state_val=old_val)

        if old_val == -1:
            current_state[key] = count
            continue

        if count != old_val:
            fark = count - old_val
            changes.append(f"• {info['name']}: {old_val} ➔ {count} ({fark:+d})")
            current_state[key] = count

    save_state(current_state)

    if changes:
        msg = "🔔 İçerik Değişikliği Algılandı!\n\n" + "\n".join(changes)
        send_telegram_message(msg, reply_markup=get_inline_keyboard())


def get_status_report_text():
    current_state = load_state()
    lines = ["📊 GÜNCEL DURUM VE ARAŞTIRMA RAPORU\n"]
    for key, info in PAGES.items():
        val = current_state.get(key, info.get("default_val", 0))
        audit = LAST_AUDIT_REPORT.get(key, "Henüz canlı taranmadı")
        lines.append(f"📌 {info['name']}: {val}\n   └ Durum: {audit}\n")
    return "\n".join(lines)


def handle_callback(callback_data, chat_id):
    global IS_TRACKING_PAUSED, SILENT_MODE

    if callback_data == "btn_durum":
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())

    elif callback_data == "btn_kontrol":
        send_telegram_message("🔎 Canlı tarama yapılıyor...")
        run_check()
        send_telegram_message(
            "✅ Kontrol tamamlandı!\n\n" + get_status_report_text(),
            reply_markup=get_inline_keyboard()
        )

    elif callback_data == "btn_durdur":
        IS_TRACKING_PAUSED = True
        send_telegram_message("⏸ Otomatik takip duraklatıldı.", reply_markup=get_inline_keyboard())

    elif callback_data == "btn_baslat":
        IS_TRACKING_PAUSED = False
        send_telegram_message("▶️ Otomatik takip başlatıldı!", reply_markup=get_inline_keyboard())

    elif callback_data == "btn_sessiz":
        SILENT_MODE = not SILENT_MODE
        durum = "AÇIK (Sessiz)" if SILENT_MODE else "KAPALI (Sesli)"
        send_telegram_message(f"🔕 Sessiz mod: {durum}", reply_markup=get_inline_keyboard())


def handle_message(text, chat_id):
    if str(chat_id) != str(TELEGRAM_CHAT_ID):
        return

    text_clean = text.strip()

    # /set komutu ile istenirse manuel değer atama
    if text_clean.startswith("/set "):
        parts = text_clean.split()
        if len(parts) == 3 and parts[2].isdigit():
            k, v = parts[1], int(parts[2])
            current_state = load_state()
            current_state[k] = v
            save_state(current_state)
            send_telegram_message(f"✅ {k} taban değeri {v} yapıldı.", reply_markup=get_inline_keyboard())
            return

    if "durum" in text_clean.lower() or text_clean == "/durum":
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())
        return

    if text_clean in ["/start", "/yardim", "anasayfa"]:
        send_telegram_message("👋 Bot aktif! Kontrol paneli hazır:", reply_markup=get_inline_keyboard())


def listen_telegram():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass

    last_update_id = 0

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 15, "limit": 10},
                timeout=20
            ).json()

            if resp.get("ok"):
                for item in resp.get("result", []):
                    last_update_id = item["update_id"]

                    callback_query = item.get("callback_query")
                    if callback_query:
                        cb_data = callback_query.get("data")
                        cb_chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
                        cb_id = callback_query.get("id")

                        try:
                            requests.post(
                                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                                json={"callback_query_id": cb_id},
                                timeout=4
                            )
                        except Exception:
                            pass

                        if cb_data and cb_chat_id == str(TELEGRAM_CHAT_ID):
                            handle_callback(cb_data, cb_chat_id)
                        continue

                    msg = item.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text and chat_id:
                        handle_message(text, chat_id)

        except Exception as e:
            time.sleep(2)

        time.sleep(0.3)


def main():
    print("Sadeleştirilmiş Takip Botu Başlatıldı...")

    current_state = load_state()
    for key, info in PAGES.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)

    save_state(current_state)

    t = threading.Thread(target=listen_telegram, daemon=True)
    t.start()

    send_telegram_message("🚀 Bot Başlatıldı! Temiz ve optimize edilmiş sürüm devrede.", reply_markup=get_inline_keyboard())

    while True:
        run_check()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
