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
        "type": "tiktok_live_api",
        "default_val": 6
    },
    "userr44559014_reposts": {
        "username": "userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "tiktok_live_api",
        "default_val": 1
    },
    "emin_htp_reposts": {
        "username": "emin_htp",
        "name": "emin_htp Repostlar",
        "type": "tiktok_live_api",
        "default_val": 11
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads",
        "default_val": 0
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

def get_inline_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Durum", "callback_data": "btn_durum"},
                {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"}
            ],
            [
                {"text": "🔕 Sessiz Mod", "callback_data": "btn_sessiz"},
                {"text": "⏸ Durdur", "callback_data": "btn_durdur"},
                {"text": "▶️ Başlat", "callback_data": "btn_baslat"}
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

def get_live_repost_count(username):
    try:
        api_url = f"https://www.tikwm.com/api/user/posts?unique_id={username}&count=30"
        resp = requests.get(api_url, headers=HEADERS, timeout=8).json()
        
        if resp.get("code") == 0 and "data" in resp:
            videos = resp["data"].get("videos", [])
            reposts = [v for v in videos if v.get("is_repost") is True or "repost" in str(v).lower()]
            if len(reposts) > 0:
                return len(reposts)

        alt_api = f"https://countik.com/api/userinfo/{username}"
        r_alt = requests.get(alt_api, headers=HEADERS, timeout=8).json()
        if "reposts" in r_alt:
            return int(r_alt["reposts"])
            
    except Exception as e:
        print(f"[!] Canlı API hatası ({username}): {e}")
        
    return None

def check_page_count(page_info, current_state_val=0):
    p_type = page_info["type"]
    default_val = page_info.get("default_val", 0)

    try:
        if p_type == "tiktok_live_api":
            username = page_info["username"]
            count = get_live_repost_count(username)
            if count is not None and count > 0:
                return count
            return current_state_val if (current_state_val is not None and current_state_val > 0) else default_val

        elif p_type == "story":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                return current_state_val if current_state_val is not None else default_val

            text_lower = resp.text.lower()
            if any(p in text_lower for p in ("no active stories", "no stories", "0 stories", "hikaye yok")):
                return 0

            soup = BeautifulSoup(resp.text, "html.parser")
            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            if story_items:
                return len(set(str(el) for el in story_items))
            if "data-story" in text_lower or "<video" in text_lower:
                return 1
            return 0

        elif p_type == "threads":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                return current_state_val if current_state_val is not None else default_val

            text = BeautifulSoup(resp.text, "html.parser").get_text()

            matches = re.findall(r'THREADS\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
            if matches:
                val = int(matches[0])
                if val not in (2025, 2026, 2027):
                    return val

            matches_alt = re.findall(r'(\d+)\s+threads', text, re.IGNORECASE)
            if matches_alt:
                val = int(matches_alt[0])
                if val not in (2025, 2026, 2027):
                    return val

            if current_state_val in (2025, 2026, 2027):
                return default_val
            return current_state_val if current_state_val is not None else default_val

        return current_state_val if current_state_val is not None else default_val
    except Exception:
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
        count = check_page_count(info, current_state_val=old_val)

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

def handle_callback(callback_data, chat_id):
    global IS_TRACKING_PAUSED, SILENT_MODE

    if callback_data == "btn_durum":
        current_state = load_state()
        lines = ["📑 Takip Edilen Sayfalar Güncel Durumu:\n"]
        for key, info in PAGES.items():
            val = current_state.get(key, info.get("default_val", 0))
            lines.append(f"• {info['name']}: {val}")
        send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())

    elif callback_data == "btn_kontrol":
        send_telegram_message("🔎 Canlı kontrol başlatıldı...")
        run_check()
        send_telegram_message("✅ Canlı kontrol tamamlandı.", reply_markup=get_inline_keyboard())

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

    if text_clean.startswith("/set "):
        parts = text_clean.split()
        if len(parts) == 3 and parts[2].isdigit():
            k, v = parts[1], int(parts[2])
            current_state = load_state()
            current_state[k] = v
            save_state(current_state)
            send_telegram_message(f"✅ {k} taban değeri {v} olarak ayarlandı.", reply_markup=get_inline_keyboard())
            return

    text_lower = text_clean.lower()
    if "durum" in text_lower or text_lower == "/durum":
        current_state = load_state()
        lines = ["📑 Takip Edilen Sayfalar Güncel Durumu:\n"]
        for key, info in PAGES.items():
            val = current_state.get(key, info.get("default_val", 0))
            lines.append(f"• {info['name']}: {val}")
        send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())
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

                    # 1. Callback (Buton) Olayları
                    callback_query = item.get("callback_query")
                    if callback_query:
                        cb_data = callback_query.get("data")
                        cb_chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
                        cb_id = callback_query.get("id")

                        # Telegram'a tıklandığı anında onaylatılır (Yükleniyor çarkı takılmaz)
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

                    # 2. Normal Metin Mesajları
                    msg = item.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text and chat_id:
                        handle_message(text, chat_id)

        except Exception as e:
            time.sleep(2)

        time.sleep(0.3)

def main():
    print("Master Takip Botu Başlatıldı...")

    current_state = load_state()
    for key, info in PAGES.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)

    # 2026 kalıntısını sıfırla
    if current_state.get("sillagunerr_threads") in (2025, 2026, 2027):
        current_state["sillagunerr_threads"] = 0

    save_state(current_state)

    t = threading.Thread(target=listen_telegram, daemon=True)
    t.start()

    send_telegram_message("🚀 Bot Başlatıldı! Butonlar yenilendi ve aktif.", reply_markup=get_inline_keyboard())

    while True:
        run_check()
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
