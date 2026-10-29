import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return  # Log kirliliği yapmasın

def run_fake_server():
    server = HTTPServer(('0.0.0.0', 8080), HealthCheckHandler)
    server.serve_forever()

# Arka planda 8080 portunu dinleyecek thread başlat:
threading.Thread(target=run_fake_server, daemon=True).start()

import os
import re
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
TELEGRAM_CHAT_ID = "6009524525"

CHECK_INTERVAL_SECONDS = 900
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"
PAGES_FILE = "tracker_pages.json"

DEFAULT_PAGES = {
    "sillagunerrr_story": {
        "url": "https://viewoo.co/u/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "story",
        "default_val": 0
    },
    "sillagunerrr_reposts": {
        "username": "sillagunerrr",
        "view_url": "https://viewoo.co/u/sillagunerrr?tab=reposts",
        "name": "sillagunerrr Repostlar",
        "type": "viewoo_reposts",
        "default_val": 6
    },
    "userr44559014_reposts": {
        "username": "userr44559014",
        "view_url": "https://viewoo.co/u/userr44559014?tab=reposts",
        "name": "userr44559014 Repostlar",
        "type": "viewoo_reposts",
        "default_val": 1
    },
    "emin_htp_reposts": {
        "username": "emin_htp",
        "view_url": "https://viewoo.co/u/emin_htp?tab=reposts",
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


# --- FLY.IO İÇİN SAHTE WEB SUNUCUSU ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot Aktif ve Calisiyor!")

    def log_message(self, format, *args):
        pass  # Terminali gereksiz loglarla doldurmasin


def start_health_server():
    """Fly.io'nun kapanmaması ve 8080 portunu onaylaması için web sunucusu."""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()


def load_json(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_val


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_pages():
    pages = load_json(PAGES_FILE, None)
    if not pages:
        save_json(PAGES_FILE, DEFAULT_PAGES)
        return DEFAULT_PAGES
    return pages


def get_inline_keyboard():
    dk = CHECK_INTERVAL_SECONDS // 60
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Durum & Rapor", "callback_data": "btn_durum"},
                {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"}
            ],
            [
                {"text": f"⏱ Aralık: {dk} dk", "callback_data": "btn_aralik"},
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


def send_telegram_photo(photo_url, caption=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not photo_url:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": str(caption)[:1024],
        "disable_notification": SILENT_MODE
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[!] Fotoğraf gönderilemedi: {e}")


def fetch_viewoo_reposts(username):
    ts = int(time.time())
    url = f"https://viewoo.co/api/reposts?username={username}&_={ts}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            items_list = []
            if isinstance(data, list):
                items_list = data
            elif isinstance(data, dict):
                for k in ["items", "reposts", "data", "videos", "posts"]:
                    if k in data and isinstance(data[k], list):
                        items_list = data[k]
                        break

            if items_list:
                return len(items_list), f"API Listesi ({len(items_list)} Repost)"

            if isinstance(data, dict) and "count" in data and isinstance(data["count"], int):
                return data["count"], f"API Sayacı ({data['count']})"

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
        if p_type == "viewoo_reposts":
            count, detail = fetch_viewoo_reposts(page_info["username"])
            if count is not None:
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı - {detail}"
                return count, None, None
            else:
                fallback = current_state_val if current_state_val is not None else default_val
                LAST_AUDIT_REPORT[key] = f"⚠️ Araştırıldı - {detail} (Taban Korundu)"
                return fallback, None, None

        elif p_type == "story":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı (Sunucu yanıt vermedi)"
                return (current_state_val if current_state_val is not None else default_val), None, None

            text_lower = resp.text.lower()
            if any(p in text_lower for p in ("no active stories", "no stories", "0 stories", "hikaye yok")):
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Hikaye Yok)"
                return 0, None, None

            soup = BeautifulSoup(resp.text, "html.parser")
            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            
            story_img = None
            if story_items:
                first_img = story_items[0].select_one("img")
                if first_img and first_img.get("src"):
                    story_img = first_img["src"]
                elif story_items[0].get("data-cover"):
                    story_img = story_items[0]["data-cover"]

                c = len(set(str(el) for el in story_items))
                LAST_AUDIT_REPORT[key] = f"✅ Araştırıldı ({c} Aktif Hikaye)"
                return c, story_img, None

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Hikaye Yok)"
            return 0, None, None

        elif p_type == "threads":
            resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
            if not resp or resp.status_code != 200:
                LAST_AUDIT_REPORT[key] = "❌ Araştırılamadı"
                return (current_state_val if current_state_val is not None else default_val), None, None

            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            latest_post_text = None
            post_selectors = [
                ".thread-content", ".post-content", "[data-press-container]",
                "div[class*='postText']", "div[class*='content']", "article"
            ]
            for sel in post_selectors:
                elements = soup.select(sel)
                for el in elements:
                    cleaned = el.get_text().strip()
                    if cleaned and len(cleaned) > 5 and not any(k in cleaned.lower() for k in ["threads", "followers", "following", "takipçi"]):
                        latest_post_text = cleaned
                        break
                if latest_post_text:
                    break

            val = None
            m = re.findall(r'THREADS\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
            if m and int(m[0]) not in (2025, 2026, 2027):
                val = int(m[0])

            if val is None:
                m_alt = re.findall(r'(\d+)\s+threads', text, re.IGNORECASE)
                if m_alt and int(m_alt[0]) not in (2025, 2026, 2027):
                    val = int(m_alt[0])

            if val is not None:
                LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (THREADS Sayacı Doğrulandı)"
                return val, None, latest_post_text

            LAST_AUDIT_REPORT[key] = "✅ Araştırıldı (Sabit Değer Korundu)"
            return (current_state_val if current_state_val is not None else default_val), None, latest_post_text

        return (current_state_val if current_state_val is not None else default_val), None, None
    except Exception as e:
        LAST_AUDIT_REPORT[key] = f"❌ Hata: {str(e)[:25]}"
        return (current_state_val if current_state_val is not None else default_val), None, None


def run_check():
    global IS_TRACKING_PAUSED
    if IS_TRACKING_PAUSED:
        return

    current_state = load_json(STATE_FILE, {})
    pages = get_pages()
    changes = []
    change_buttons = []
    new_story_covers = []

    for key, info in pages.items():
        old_val = current_state.get(key, -1)
        count, cover_url, latest_text = check_page_count(key, info, current_state_val=old_val)

        if old_val == -1:
            current_state[key] = count
            continue

        if count != old_val:
            fark = count - old_val
            target_url = info.get("view_url") or info.get("url", "https://threadlook.com")
            
            line = f"• {info['name']}: {old_val} ➔ {count} ({fark:+d})\n  🔗 Profil: {target_url}"

            if fark > 0 and info.get("type") == "threads" and latest_text:
                preview = (latest_text[:280] + '...') if len(latest_text) > 280 else latest_text
                line += f"\n  📝 Son Paylaşım: \"{preview}\""

            changes.append(line)
            change_buttons.append([{"text": f"🔗 {info['name']} Görüntüle", "url": target_url}])
            
            if fark > 0 and info.get("type") == "story" and cover_url:
                new_story_covers.append((cover_url, f"📸 {info['name']} için yeni hikaye paylaşıldı!"))

            current_state[key] = count

    save_json(STATE_FILE, current_state)

    if changes:
        for c_url, c_caption in new_story_covers:
            send_telegram_photo(c_url, caption=c_caption)

        custom_keyboard = {"inline_keyboard": change_buttons + get_inline_keyboard()["inline_keyboard"]}
        msg = "🔔 İçerik Değişikliği Algılandı!\n\n" + "\n\n".join(changes)
        send_telegram_message(msg, reply_markup=custom_keyboard)


def get_status_report_text():
    current_state = load_json(STATE_FILE, {})
    pages = get_pages()
    lines = ["📊 GÜNCEL DURUM VE ARAŞTIRMA RAPORU\n"]
    for key, info in pages.items():
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

    elif callback_data == "btn_aralik":
        send_telegram_message(
            f"⏱ Mevcut aralık: {CHECK_INTERVAL_SECONDS // 60} dakika.\n"
            "Değiştirmek için sohbete komut yazın:\nÖrnek: `/aralik 5` (5 dakikada bir kontrol eder)"
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
    global CHECK_INTERVAL_SECONDS
    if str(chat_id) != str(TELEGRAM_CHAT_ID):
        return

    text_clean = text.strip()

    if text_clean.startswith("/aralik "):
        parts = text_clean.split()
        if len(parts) == 2 and parts[1].isdigit():
            dakika = int(parts[1])
            if dakika >= 1:
                CHECK_INTERVAL_SECONDS = dakika * 60
                send_telegram_message(f"⏱ Tarama sıklığı {dakika} dakika olarak ayarlandı.", reply_markup=get_inline_keyboard())
                return
            else:
                send_telegram_message("Aralık en az 1 dakika olmalıdır.")
                return

    if text_clean.startswith("/ekle "):
        parts = text_clean.split()
        if len(parts) == 3:
            tur, user = parts[1].lower(), parts[2].lower()
            pages = get_pages()
            key = f"{user}_{tur}"

            if tur in ["repost", "reposts"]:
                pages[key] = {
                    "username": user,
                    "view_url": f"https://viewoo.co/u/{user}?tab=reposts",
                    "name": f"{user} Repostlar",
                    "type": "viewoo_reposts",
                    "default_val": 0
                }
            elif tur in ["hikaye", "story"]:
                pages[key] = {
                    "url": f"https://viewoo.co/u/{user}",
                    "name": f"{user} Hikayeler",
                    "type": "story",
                    "default_val": 0
                }
            elif tur in ["threads"]:
                pages[key] = {
                    "url": f"https://threadlook.com/profile/{user}",
                    "name": f"{user} Threads",
                    "type": "threads",
                    "default_val": 0
                }
            else:
                send_telegram_message("Geçersiz tür! Kullanım:\n`/ekle repost kullanici`\n`/ekle hikaye kullanici`\n`/ekle threads kullanici`")
                return

            save_json(PAGES_FILE, pages)
            send_telegram_message(f"✅ Yeni hedef başarıyla eklendi:\n• {pages[key]['name']}", reply_markup=get_inline_keyboard())
            return

    if text_clean.startswith(("/cikar ", "/sil ")):
        parts = text_clean.split()
        if len(parts) == 2:
            target = parts[1].lower()
            pages = get_pages()
            silinenler = []

            for k in list(pages.keys()):
                if target in k:
                    silinenler.append(pages[k]["name"])
                    del pages[k]

            if silinenler:
                save_json(PAGES_FILE, pages)
                send_telegram_message(f"🗑 Takip listesinden çıkarıldı:\n• " + "\n• ".join(silinenler), reply_markup=get_inline_keyboard())
                return
            else:
                send_telegram_message(f"'{target}' ismini içeren bir hedef bulunamadı.")
                return

    if text_clean.startswith("/set "):
        parts = text_clean.split()
        if len(parts) == 3 and parts[2].isdigit():
            k, v = parts[1], int(parts[2])
            current_state = load_json(STATE_FILE, {})
            current_state[k] = v
            save_json(STATE_FILE, current_state)
            send_telegram_message(f"✅ {k} taban değeri {v} yapıldı.", reply_markup=get_inline_keyboard())
            return

    if "durum" in text_clean.lower() or text_clean == "/durum":
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())
        return

    if text_clean in ["/start", "/yardim", "anasayfa"]:
        rehber = (
            "👋 **Takip Botu Komutları:**\n\n"
            "⏱ **Tarama Sıklığı:**\n"
            "• `/aralik 5` ➔ Kontrol süresini 5 dakika yapar.\n\n"
            "🎯 **Hedef Yönetimi:**\n"
            "• `/ekle repost kullanici` ➔ Yeni repost takibi başlatır.\n"
            "• `/ekle hikaye kullanici` ➔ Yeni hikaye takibi başlatır.\n"
            "• `/ekle threads kullanici` ➔ Yeni Threads takibi başlatır.\n"
            "• `/cikar kullanici` ➔ Kullanıcıyı tüm takiplerden çıkarır.\n\n"
            "⚙️ **Sayaç Ayarı:**\n"
            "• `/set anahtar_adi deger` ➔ Sayacı manuel eşitler."
        )
        send_telegram_message(rehber, reply_markup=get_inline_keyboard())


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


def loop_tracker():
    """Arka planda düzenli tarama döngüsü."""
    while True:
        run_check()
        time.sleep(CHECK_INTERVAL_SECONDS)


def main():
    print("Master Takip Botu Başlatıldı...")

    pages = get_pages()
    current_state = load_json(STATE_FILE, {})
    for key, info in pages.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)

    save_json(STATE_FILE, current_state)

    # 1. Telegram dinleme thread'i
    t_telegram = threading.Thread(target=listen_telegram, daemon=True)
    t_telegram.start()

    # 2. Arka plan tarama thread'i
    t_tracker = threading.Thread(target=loop_tracker, daemon=True)
    t_tracker.start()

    send_telegram_message("🚀 Bot Başlatıldı! Fly.io üzerinde aktif.", reply_markup=get_inline_keyboard())

    # 3. Fly.io'nun kapanmaması için HTTP sunucusunu ana thread'de açık tut
    start_health_server()


if __name__ == "__main__":
    main()
