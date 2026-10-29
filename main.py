import os
import re
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from bs4 import BeautifulSoup

# --- RENDER PORT DİNLEYİCİSİ (PORT TIMEOUT HATASINI ENGELLER) ---
class RenderHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot Aktif!")

    def log_message(self, format, *args):
        pass  # Log kalabalığını önler

def start_render_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderHealthServer)
    server.serve_forever()

# Render servisi ayağa kaldırırken portu anında açık bulsun diye thread hemen başlatılır
threading.Thread(target=start_render_server, daemon=True).start()


# --- BOT TANIMLARI VE AYARLAR ---
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://viewoo.co/"
}

LAST_AUDIT_REPORT = {}


# --- VERİ YÖNETİMİ ---
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


# --- TELEGRAM İŞLEMLERİ ---
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
        print(f"[!] Fotoğraf hatası: {e}")


# --- KONTROL MEKANİZMALARI ---
def fetch_viewoo_reposts(username):
    url = f"https://viewoo.co/api/reposts?username={username}&_={int(time.time())}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return len(data), f"API ({len(data)} Repost)"
            if isinstance(data, dict):
                for k in ["items", "reposts", "data", "videos", "posts"]:
                    if isinstance(data.get(k), list):
                        return len(data[k]), f"API ({len(data[k])} Repost)"
                if isinstance(data.get("count"), int):
                    return data["count"], f"Sayaç ({data['count']})"
            ids = set(re.findall(r'\b7\d{18}\b', json.dumps(data)))
            if ids:
                return len(ids), f"Video ID ({len(ids)} Repost)"
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, f"Hata: {str(e)[:20]}"


def check_page_count(key, page_info, current_state_val=0):
    global LAST_AUDIT_REPORT
    p_type = page_info["type"]
    fallback = current_state_val if current_state_val is not None else page_info.get("default_val", 0)

    try:
        if p_type == "viewoo_reposts":
            count, detail = fetch_viewoo_reposts(page_info["username"])
            if count is not None:
                LAST_AUDIT_REPORT[key] = f"✅ {detail}"
                return count, None, None
            LAST_AUDIT_REPORT[key] = f"⚠️ {detail} (Korundu)"
            return fallback, None, None

        resp = requests.get(page_info["url"], headers=HEADERS, timeout=8)
        if not resp or resp.status_code != 200:
            LAST_AUDIT_REPORT[key] = "❌ Yanıt Yok"
            return fallback, None, None

        soup = BeautifulSoup(resp.text, "html.parser")

        if p_type == "story":
            text_lower = resp.text.lower()
            if any(p in text_lower for p in ("no active stories", "no stories", "0 stories", "hikaye yok")):
                LAST_AUDIT_REPORT[key] = "✅ Hikaye Yok"
                return 0, None, None

            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            if story_items:
                img = story_items[0].select_one("img")
                story_img = img.get("src") if img else story_items[0].get("data-cover")
                c = len(set(str(el) for el in story_items))
                LAST_AUDIT_REPORT[key] = f"✅ {c} Aktif Hikaye"
                return c, story_img, None

            LAST_AUDIT_REPORT[key] = "✅ Hikaye Yok"
            return 0, None, None

        if p_type == "threads":
            text = soup.get_text()
            latest_post = None
            for sel in [".thread-content", ".post-content", "[data-press-container]", "article"]:
                el = soup.select_one(sel)
                if el:
                    clean = el.get_text().strip()
                    if len(clean) > 5 and not any(k in clean.lower() for k in ["threads", "followers"]):
                        latest_post = clean
                        break

            m = re.findall(r'threads\s*[:\s]?\s*(\d+)', text, re.I) or re.findall(r'(\d+)\s+threads', text, re.I)
            val = next((int(x) for x in m if int(x) not in (2025, 2026, 2027)), None)

            if val is not None:
                LAST_AUDIT_REPORT[key] = "✅ Doğrulandı"
                return val, None, latest_post

            LAST_AUDIT_REPORT[key] = "✅ Değer Korundu"
            return fallback, None, latest_post

        return fallback, None, None
    except Exception as e:
        LAST_AUDIT_REPORT[key] = f"❌ {str(e)[:20]}"
        return fallback, None, None


def run_check():
    if IS_TRACKING_PAUSED:
        return

    current_state = load_json(STATE_FILE, {})
    pages = get_pages()
    changes, change_buttons, new_stories = [], [], []

    for key, info in pages.items():
        old_val = current_state.get(key, -1)
        count, cover_url, latest_text = check_page_count(key, info, current_state_val=old_val)

        if old_val == -1:
            current_state[key] = count
            continue

        if count != old_val:
            fark = count - old_val
            target_url = info.get("view_url") or info.get("url", "")
            line = f"• {info['name']}: {old_val} ➔ {count} ({fark:+d})\n  🔗 Profil: {target_url}"

            if fark > 0 and info.get("type") == "threads" and latest_text:
                preview = (latest_text[:280] + '...') if len(latest_text) > 280 else latest_text
                line += f"\n  📝 Son Paylaşım: \"{preview}\""

            changes.append(line)
            change_buttons.append([{"text": f"🔗 {info['name']} Görüntüle", "url": target_url}])

            if fark > 0 and info.get("type") == "story" and cover_url:
                new_stories.append((cover_url, f"📸 {info['name']} yeni hikaye paylaştı!"))

            current_state[key] = count

    save_json(STATE_FILE, current_state)

    if changes:
        for c_url, c_caption in new_stories:
            send_telegram_photo(c_url, caption=c_caption)

        custom_keyboard = {"inline_keyboard": change_buttons + get_inline_keyboard()["inline_keyboard"]}
        send_telegram_message("🔔 Değişiklik Algılandı!\n\n" + "\n\n".join(changes), reply_markup=custom_keyboard)


def get_status_report_text():
    current_state = load_json(STATE_FILE, {})
    pages = get_pages()
    lines = ["📊 GÜNCEL DURUM RAPORU\n"]
    for key, info in pages.items():
        val = current_state.get(key, info.get("default_val", 0))
        lines.append(f"📌 {info['name']}: {val}\n   └ Durum: {LAST_AUDIT_REPORT.get(key, 'Taranmadı')}\n")
    return "\n".join(lines)


# --- TELEGRAM MESAJ VE ETKİLEŞİM ---
def handle_callback(callback_data):
    global IS_TRACKING_PAUSED, SILENT_MODE

    if callback_data == "btn_durum":
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())
    elif callback_data == "btn_kontrol":
        send_telegram_message("🔎 Canlı tarama yapılıyor...")
        run_check()
        send_telegram_message("✅ Tamamlandı!\n\n" + get_status_report_text(), reply_markup=get_inline_keyboard())
    elif callback_data == "btn_aralik":
        send_telegram_message(f"⏱ Aralık: {CHECK_INTERVAL_SECONDS // 60} dk.\nDeğiştirmek için: `/aralik 5`")
    elif callback_data == "btn_durdur":
        IS_TRACKING_PAUSED = True
        send_telegram_message("⏸ Takip duraklatıldı.", reply_markup=get_inline_keyboard())
    elif callback_data == "btn_baslat":
        IS_TRACKING_PAUSED = False
        send_telegram_message("▶️ Takip başlatıldı!", reply_markup=get_inline_keyboard())
    elif callback_data == "btn_sessiz":
        SILENT_MODE = not SILENT_MODE
        send_telegram_message(f"🔕 Sessiz mod: {'AÇIK' if SILENT_MODE else 'KAPALI'}", reply_markup=get_inline_keyboard())


def handle_message(text):
    global CHECK_INTERVAL_SECONDS
    parts = text.strip().split()
    if not parts:
        return
    cmd = parts[0].lower()

    if cmd == "/aralik" and len(parts) == 2 and parts[1].isdigit():
        CHECK_INTERVAL_SECONDS = max(1, int(parts[1])) * 60
        send_telegram_message(f"⏱ Tarama sıklığı {parts[1]} dk yapıldı.", reply_markup=get_inline_keyboard())

    elif cmd == "/ekle" and len(parts) == 3:
        tur, user = parts[1].lower(), parts[2].lower()
        pages = get_pages()
        key = f"{user}_{tur}"

        if tur in ["repost", "reposts"]:
            pages[key] = {"username": user, "view_url": f"https://viewoo.co/u/{user}?tab=reposts", "name": f"{user} Repost", "type": "viewoo_reposts", "default_val": 0}
        elif tur in ["hikaye", "story"]:
            pages[key] = {"url": f"https://viewoo.co/u/{user}", "name": f"{user} Hikaye", "type": "story", "default_val": 0}
        elif tur == "threads":
            pages[key] = {"url": f"https://threadlook.com/profile/{user}", "name": f"{user} Threads", "type": "threads", "default_val": 0}
        else:
            send_telegram_message("Kullanım: `/ekle [repost|hikaye|threads] kullanici`")
            return

        save_json(PAGES_FILE, pages)
        send_telegram_message(f"✅ Eklendi: {pages[key]['name']}", reply_markup=get_inline_keyboard())

    elif cmd in ["/cikar", "/sil"] and len(parts) == 2:
        pages = get_pages()
        silinenler = [pages.pop(k)["name"] for k in list(pages.keys()) if parts[1].lower() in k]
        if silinenler:
            save_json(PAGES_FILE, pages)
            send_telegram_message("🗑 Çıkarıldı:\n• " + "\n• ".join(silinenler), reply_markup=get_inline_keyboard())
        else:
            send_telegram_message("Hedef bulunamadı.")

    elif cmd == "/set" and len(parts) == 3 and parts[2].isdigit():
        state = load_json(STATE_FILE, {})
        state[parts[1]] = int(parts[2])
        save_json(STATE_FILE, state)
        send_telegram_message(f"✅ {parts[1]} = {parts[2]} yapıldı.", reply_markup=get_inline_keyboard())

    elif cmd in ["/durum", "durum"]:
        send_telegram_message(get_status_report_text(), reply_markup=get_inline_keyboard())

    elif cmd in ["/start", "/yardim"]:
        rehber = (
            "👋 **Takip Botu Komutları:**\n\n"
            "• `/aralik 5` ➔ Süreyi 5 dk yapar.\n"
            "• `/ekle repost kullanici` ➔ Repost takibi.\n"
            "• `/ekle hikaye kullanici` ➔ Hikaye takibi.\n"
            "• `/ekle threads kullanici` ➔ Threads takibi.\n"
            "• `/cikar kullanici` ➔ Takipten çıkarır.\n"
            "• `/set anahtar deger` ➔ Sayacı manuel eşitler."
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
                params={"offset": last_update_id + 1, "timeout": 20},
                timeout=25
            ).json()

            for item in resp.get("result", []):
                last_update_id = item["update_id"]

                cb = item.get("callback_query")
                if cb and str(cb.get("message", {}).get("chat", {}).get("id")) == str(TELEGRAM_CHAT_ID):
                    try:
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"]}, timeout=4)
                    except Exception:
                        pass
                    if cb.get("data"):
                        handle_callback(cb["data"])
                    continue

                msg = item.get("message", {})
                if str(msg.get("chat", {}).get("id")) == str(TELEGRAM_CHAT_ID) and msg.get("text"):
                    handle_message(msg["text"])
        except Exception:
            time.sleep(2)
        time.sleep(0.3)


def loop_tracker():
    while True:
        try:
            run_check()
        except Exception as e:
            print(f"[!] Tarama hatası: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


def main():
    pages = get_pages()
    current_state = load_json(STATE_FILE, {})
    for key, info in pages.items():
        if key not in current_state:
            current_state[key] = info.get("default_val", 0)
    save_json(STATE_FILE, current_state)

    threading.Thread(target=loop_tracker, daemon=True).start()
    send_telegram_message("🚀 Bot Başlatıldı! Render üzerinde aktif.", reply_markup=get_inline_keyboard())
    listen_telegram()


if __name__ == "__main__":
    main()
