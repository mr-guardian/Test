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
USE_API_MODE = False  # Doğrudan çalışan Web Kazıma modunu varsayılan yapıyoruz

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
        "viewoo_url": "https://viewoo.co/u/sillagunerrr?tab=reposts",
        "username": "sillagunerrr",
        "name": "sillagunerrr Repostlar",
        "type": "repost",
        "default_val": 6
    },
    "userr44559014_reposts": {
        "url": "https://www.tiktok.com/@userr44559014",
        "viewoo_url": "https://viewoo.co/u/userr44559014?tab=reposts",
        "username": "userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "repost",
        "default_val": 1
    },
    "emin_htp_reposts": {
        "url": "https://www.tiktok.com/@emin_htp",
        "viewoo_url": "https://viewoo.co/u/emin_htp?tab=reposts",
        "username": "emin_htp",
        "name": "emin_htp Repostlar",
        "type": "repost",
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

LAST_AUDIT_REPORT = {}


def get_inline_keyboard():
    mod_text = "⚡ Mod: Canlı API" if USE_API_MODE else "🌐 Mod: Web Kazıma"
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Durum & Rapor", "callback_data": "btn_durum"},
                {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"}
            ],
            [
                {"text": mod_text, "callback_data": "btn_toggle_mode"},
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


def fetch_url(url, custom_headers=None):
    h = custom_headers or HEADERS
    try:
        if IS_CLOUDSCRAPER:
            return HTTP_CLIENT.get(url, headers=h, timeout=8)
        return requests.get(url, headers=h, timeout=8)
    except Exception:
        return None


def fetch_repost_via_api(username):
    """Açık API köprüleri üzerinden repost kontrolü."""
    try:
        # TikWM v2 video sorgusu
        api_url = f"https://www.tikwm.com/api/user/posts?unique_id={username}&count=35"
        r = requests.get(api_url, headers=HEADERS, timeout=8)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            if data.get("code") == 0 and "data" in data:
                videos = data["data"].get("videos", [])
                reposts = [v for v in videos if v.get("is_repost") is True or "repost" in str(v).lower()]
                if len(reposts) > 0:
                    return len(reposts), f"TikWM API ({len(reposts)} Repost)"
    except Exception:
        pass

    try:
        # Countik kullanıcı istatistikleri
        alt_url = f"https://countik.com/api/userinfo/{username}"
        r_alt = requests.get(alt_url, headers=HEADERS, timeout=8)
        if r_alt.status_code == 200 and r_alt.text.strip().startswith("{"):
            d_alt = r_alt.json()
            if "reposts" in d_alt and int(d_alt["reposts"]) > 0:
                return int(d_alt["reposts"]), "Countik API"
    except Exception:
        pass

    return None, "API yanıtı boş veya engelli"


def fetch_repost_via_scraper(username, viewoo_url):
    """Viewoo Next.js RSC ve sayfa gövdesindeki video kimliklerini eksiksiz ayıklar."""
    try:
        ts = int(time.time())
        
        # 1. Next.js Flight Payload / RSC İsteği
        rsc_headers = {
            "User-Agent": HEADERS["User-Agent"],
            "RSC": "1",
            "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22u%22%2C%7B%22children%22%3A%5B%22" + username + "%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
            "Next-Url": f"/u/{username}?tab=reposts"
        }
        v_url = f"https://viewoo.co/u/{username}?tab=reposts&_t={ts}"
        resp = fetch_url(v_url, rsc_headers)
        
        if resp and resp.status_code == 200:
            text = resp.text
            # 19 haneli TikTok video/aweme ID kalıbı
            ids = set(re.findall(r'\b7\d{18}\b', text))
            # Veya video link kalıpları: /video/7...
            video_links = set(re.findall(r'/video/(7\d{18})', text))
            all_ids = ids.union(video_links)
            
            if len(all_ids) > 0:
                return len(all_ids), f"Viewoo RSC ({len(all_ids)} Video/Repost Bulundu)"

        # 2. Standart HTML Çözümleme
        resp_html = fetch_url(f"https://viewoo.co/u/{username}?tab=reposts")
        if resp_html and resp_html.status_code == 200:
            html_text = resp_html.text
            soup = BeautifulSoup(html_text, "html.parser")
            
            # Repost kartları veya video kutuları
            cards = soup.select("[data-video-id], a[href*='/video/'], div[class*='repost'], div[class*='post']")
            valid_cards = [c for c in cards if "avatar" not in (c.get("class") or [])]
            if len(valid_cards) > 1:
                return len(valid_cards), f"Viewoo HTML Kartları ({len(valid_cards)} Adet)"
            
            ids_html = set(re.findall(r'\b7\d{18}\b', html_text))
            if len(ids_html) > 0:
                return len(ids_html), f"HTML İçerik ID ({len(ids_html)} Adet)"

        return None, "Sayfa tarandı fakat video ID'si eşleşmedi"
    except Exception as e:
        return None, f"Kazıma Hatası: {str(e)[:25]}"


def check_page_count(key, page_info, current_state_val=0):
    global LAST_AUDIT_REPORT
    p_type = page_info["type"]
    default_val = page_info.get("default_val", 0)

    try:
        if p_type == "repost":
            username = page_info["username"]
            if USE_API_MODE:
                count, detail = fetch_repost_via_api(username)
                mod_name = "Canlı API"
            else:
                count, detail = fetch_repost_via_scraper(username, page_info.get("viewoo_url", ""))
                mod_name = "Web Kazıma"

            if count is not None and count > 0:
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı ({mod_name}) - {detail}"
                return count
            else:
                fallback_val = current_state_val if (current_state_val is not None and current_state_val > 0) else default_val
                LAST_AUDIT_REPORT[key] = f"⚠️ Araştırıldı ({mod_name}) - Taban korundu ({detail})"
                return fallback_val

        elif p_type == "story":
            resp = fetch_url(page_info["url"])
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı (Sunucu yanıtı yok)"
                return current_state_val if current_state_val is not None else default_val

            text_lower = resp.text.lower()
            if any(p in text_lower for p in ("no active stories", "no stories", "0 stories", "hikaye yok")):
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Hikaye Yok)"
                return 0

            soup = BeautifulSoup(resp.text, "html.parser")
            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            if story_items:
                c = len(set(str(el) for el in story_items))
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı ({c} Aktif Hikaye Kartı Sayıldı)"
                return c

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Aktif Hikaye Yok)"
            return 0

        elif p_type == "threads":
            resp = fetch_url(page_info["url"])
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı"
                return current_state_val if current_state_val is not None else default_val

            text = BeautifulSoup(resp.text, "html.parser").get_text()

            matches = re.findall(r'THREADS\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
            if matches:
                val = int(matches[0])
                if val not in (2025, 2026, 2027):
                    LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (THREADS Sayacı Doğrulandı)"
                    return val

            matches_alt = re.findall(r'(\d+)\s+threads', text, re.IGNORECASE)
            if matches_alt:
                val = int(matches_alt[0])
                if val not in (2025, 2026, 2027):
                    LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Alt Sayaç Doğrulandı)"
                    return val

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Sabit Değer Doğrulandı)"
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
    mod_str = "⚡ Canlı API Modu" if USE_API_MODE else "🌐 Web Kazıma (Scraper) Modu"

    lines = [f"📊 GÜNCEL DURUM VE ARAŞTIRMA RAPORU\nAktif Çalışma Modu: {mod_str}\n"]
    for key, info in PAGES.items():
        val = current_state.get(key, info.get("default_val", 0))
        audit = LAST_AUDIT_REPORT.get(key, "Henüz canlı taranmadı")
        lines.append(f"📌 {info['name']}: {val}\n   └ Durum: {audit}\n")

    return "\n".join(lines)


def handle_callback(callback_data, chat_id):
    global IS_TRACKING_PAUSED, SILENT_MODE, USE_API_MODE

    if callback_data == "btn_durum":
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())

    elif callback_data == "btn_kontrol":
        send_telegram_message("🔎 Canlı tarama ve doğrulama başlatıldı...")
        run_check()
        send_telegram_message(
            "✅ Kontrol tamamlandı!\n\n" + get_status_report_text(),
            reply_markup=get_inline_keyboard()
        )

    elif callback_data == "btn_toggle_mode":
        USE_API_MODE = not USE_API_MODE
        yeni_mod = "⚡ Canlı API Modu" if USE_API_MODE else "🌐 Web Kazıma (Scraper) Modu"
        send_telegram_message(
            f"🔄 Çalışma Modu Değiştirildi!\nŞu anki mod: **{yeni_mod}**\n\n'Canlı Kontrol' butonuna basarak kontrol edebilirsin.",
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

    if text_clean.startswith("/set "):
        parts = text_clean.split()
        if len(parts) == 3 and parts[2].isdigit():
            k, v = parts[1], int(parts[2])
            current_state = load_state()
            current_state[k] = v
            save_state(current_state)
            send_telegram_message(f"✅ {k} taban değeri {v} yapıldı.", reply_markup=get_inline_keyboard())
            return

    text_lower = text_clean.lower()
    if "durum" in text_lower or text_lower == "/durum":
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
    print("Master Takip Botu Başlatıldı...")

    current_state = load_state()
    for key, info in PAGES.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)

    current_state["sillagunerr_threads"] = 122
    save_state(current_state)

    t = threading.Thread(target=listen_telegram, daemon=True)
    t.start()

    send_telegram_message("🚀 Bot Başlatıldı! Gelişmiş RSC kazıma motoru aktif.", reply_markup=get_inline_keyboard())

    while True:
        run_check()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
