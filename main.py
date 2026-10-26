import os
import re
import time
import json
import threading
import requests
from bs4 import BeautifulSoup

try:
    import cloudscraper
    HTTP_CLIENT = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    IS_CLOUDSCRAPER = True
except Exception:
    HTTP_CLIENT = requests.Session()
    IS_CLOUDSCRAPER = False

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
        "url": "https://www.tiktok.com/@sillagunerrr",
        "name": "sillagunerrr Repostlar",
        "type": "tiktok_direct",
        "username": "sillagunerrr",
        "default_val": 5
    },
    "userr44559014_reposts": {
        "url": "https://www.tiktok.com/@userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "tiktok_direct",
        "username": "userr44559014",
        "default_val": 1
    },
    "emin_htp_reposts": {
        "url": "https://www.tiktok.com/@emin_htp",
        "name": "emin_htp Repostlar",
        "type": "tiktok_direct",
        "username": "emin_htp",
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
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}


def get_inline_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Durum", "callback_data": "btn_durum"},
                {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"}
            ],
            [
                {"text": "🔗 Sayfalar", "callback_data": "btn_sayfalar"},
                {"text": "🔕 Sessiz Mod", "callback_data": "btn_sessiz"}
            ],
            [
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
        "text": text[:4000],
        "disable_notification": SILENT_MODE
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[!] Gönderim hatası: {e}")


def fetch_url(url, custom_headers=None):
    h = custom_headers or HEADERS
    try:
        if IS_CLOUDSCRAPER:
            return HTTP_CLIENT.get(url, headers=h, timeout=12)
        return requests.get(url, headers=h, timeout=12)
    except Exception:
        return None


def fetch_tiktok_direct_reposts(username):
    """TikTok profilinin gömülü JSON verisinden repost/video verilerini doğrudan çeker."""
    url = f"https://www.tiktok.com/@{username}"
    resp = fetch_url(url)
    if not resp or resp.status_code != 200:
        return None

    html = resp.text

    # 1. __UNIVERSAL_DATA_FOR_REHYDRATION__ ayrıştırma
    m_univ = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m_univ:
        try:
            data = json.loads(m_univ.group(1))
            default_scope = data.get("__DEFAULT_SCOPE__", {})
            user_detail = default_scope.get("webapp.user-detail", {})
            stats = user_detail.get("userInfo", {}).get("stats", {})
            
            # Doğrudan sayaç alanı varsa
            for k in ["repostCount", "repost_count", "diggCount", "videoCount"]:
                if k in stats:
                    val = stats[k]
                    if isinstance(val, int) and val > 0:
                        return val

            # Item modülü içindeki liste sayısı
            item_list = default_scope.get("webapp.video-detail", {}).get("itemList", [])
            if len(item_list) > 0:
                return len(item_list)
        except Exception:
            pass

    # 2. SIGI_STATE bloğu ayrıştırma
    m_sigi = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m_sigi:
        try:
            data = json.loads(m_sigi.group(1))
            item_module = data.get("ItemModule", {})
            if item_module:
                return len(item_module)
        except Exception:
            pass

    # 3. Sayfa içinde yer alan video ID'leri (19 haneli 7 ile başlayan kalıplar)
    ids = set(re.findall(r'"id"\s*:\s*"([7]\d{18})"', html))
    if ids:
        return len(ids)

    return None


def check_page_count(page_info, current_state_val=0):
    p_type = page_info["type"]
    default_val = page_info.get("default_val", 0)

    try:
        # Doğrudan TikTok Entegrasyonu
        if p_type == "tiktok_direct":
            username = page_info.get("username")
            count = fetch_tiktok_direct_reposts(username)
            if count is not None and count > 0:
                return count
            return current_state_val if current_state_val > 0 else default_val

        # Viewoo Hikaye Takibi
        elif p_type == "story":
            resp = fetch_url(page_info["url"])
            if not resp or resp.status_code != 200:
                return current_state_val if current_state_val > 0 else default_val

            html_text = resp.text
            soup = BeautifulSoup(html_text, "html.parser")
            text_lower = soup.get_text().lower()

            empty_phrases = ("user has no stories", "no stories", "no active stories", "hikaye yok", "0 stories")
            if any(p in text_lower for p in empty_phrases):
                return 0

            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            story_items = [el for el in story_items if "story-viewer" not in (el.get("href") or "").lower()]
            if story_items:
                return len(set(str(el) for el in story_items))

            if bool(soup.find_all("video")) or "data-story" in html_text.lower():
                return 1
            return 0

        # Threads Takibi
        elif p_type == "threads":
            resp = fetch_url(page_info["url"])
            if not resp or resp.status_code != 200:
                return current_state_val if current_state_val > 0 else default_val

            text = BeautifulSoup(resp.text, "html.parser").get_text()
            matches = re.findall(r'THREADS\s*(\d+)', text, re.IGNORECASE)
            if matches:
                return int(matches[0])
            matches_alt = re.findall(r'(\d+)\s*threads', text, re.IGNORECASE)
            if matches_alt:
                return int(matches_alt[0])

            numbers = [int(n) for n in re.findall(r'\b\d+\b', text) if len(n) <= 4]
            if numbers:
                return max(numbers)

        return current_state_val if current_state_val > 0 else default_val
    except Exception:
        return current_state_val if current_state_val > 0 else default_val


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
    global CHECK_INTERVAL_SECONDS, IS_TRACKING_PAUSED, SILENT_MODE

    if callback_data == "btn_durum":
        current_state = load_state()
        lines = ["📑 Takip Edilen Sayfalar:\n"]
        for key, info in PAGES.items():
            val = current_state.get(key, info.get("default_val", 0))
            lines.append(f"• {info['name']}: {val}")
        send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())

    elif callback_data == "btn_kontrol":
        send_telegram_message("🔎 Sayfalar taranıyor (TikTok doğrudan sorgulanıyor)...")
        run_check()
        send_telegram_message("✅ Canlı kontrol tamamlandı.", reply_markup=get_inline_keyboard())

    elif callback_data == "btn_sayfalar":
        links = ["🔗 Takip Edilen Sayfalar:"]
        for k, inf in PAGES.items():
            links.append(f"• {inf['name']}: {inf['url']}")
        send_telegram_message("\n".join(links), reply_markup=get_inline_keyboard())

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

    text_clean = text.strip().lower()

    if "durum" in text_clean or text_clean == "/durum":
        current_state = load_state()
        lines = ["📑 Takip Edilen Sayfalar:\n"]
        for key, info in PAGES.items():
            val = current_state.get(key, info.get("default_val", 0))
            lines.append(f"• {info['name']}: {val}")
        send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())
        return

    if text_clean in ["/start", "/yardim", "anasayfa"]:
        send_telegram_message("👋 Bot aktif! Yönetmek için aşağıdaki butonları kullanabilirsin:", reply_markup=get_inline_keyboard())


def listen_telegram():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
    except Exception:
        pass

    last_update_id = 0

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 20, "limit": 10},
                timeout=25
            ).json()

            if resp.get("ok"):
                for item in resp.get("result", []):
                    last_update_id = item["update_id"]

                    msg = item.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text and chat_id:
                        handle_message(text, chat_id)

                    callback_query = item.get("callback_query")
                    if callback_query:
                        cb_data = callback_query.get("data")
                        cb_chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
                        cb_id = callback_query.get("id")
                        try:
                            requests.post(
                                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                                json={"callback_query_id": cb_id},
                                timeout=5
                            )
                        except Exception:
                            pass

                        if cb_data and cb_chat_id == str(TELEGRAM_CHAT_ID):
                            handle_callback(cb_data, cb_chat_id)

        except Exception as e:
            print(f"[!] Dinleme hatası: {e}")
            time.sleep(3)

        time.sleep(0.5)


def main():
    print("TikTok Doğrudan Kaynaklı Master Takip Botu Başlatıldı...")

    current_state = load_state()
    for key, info in PAGES.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)
    save_state(current_state)

    t = threading.Thread(target=listen_telegram, daemon=True)
    t.start()

    send_telegram_message("🚀 Bot Başlatıldı! Kontrol paneli:", reply_markup=get_inline_keyboard())

    while True:
        run_check()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
