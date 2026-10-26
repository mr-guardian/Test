#!/usr/bin/env python3
"""
Master Takip ve Yönetim Botu
(Easycomment, Tikvib ve Threadlook Hibrit Destekli - Railway Uyumlu)
"""

import os
import re
import html
import time
import json
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Cloudscraper varsa Cloudflare korumalarını aşmak için devreye girer
try:
    import cloudscraper
    HTTP_CLIENT = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    print("[*] Cloudscraper aktif.")
except Exception:
    HTTP_CLIENT = requests.Session()
    print("[*] Standart requests oturumu aktif.")

# ==========================================
# 1. AYARLAR VE YAPILANDIRMA
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL_SECONDS = 900  # 15 dakika
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"
HISTORY_FILE = "tracker_history.json"
CONFIG_FILE = "tracker_config.json"

STATE_LOCK = threading.Lock()

DEFAULT_PAGES = {
    "sillagunerrr_story": {
        "url": "https://www.tikvib.com/story/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "tikvib_story"
    },
    "sillagunerrr_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=sillagunerrr&tab=reposts",
        "name": "sillagunerrr Repostlar",
        "type": "easycomment_reposts",
        "username": "sillagunerrr"
    },
    "userr44559014_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=userr44559014&tab=reposts",
        "name": "userr44559014 Repostlar",
        "type": "easycomment_reposts",
        "username": "userr44559014"
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads"
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1"
}

LAST_ERRORS = {}


def load_pages() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                updated = False
                for target_key in ["sillagunerrr_reposts", "userr44559014_reposts"]:
                    if target_key in data and "tikvib.com" in data[target_key].get("url", ""):
                        data[target_key] = DEFAULT_PAGES[target_key]
                        updated = True
                if updated:
                    save_pages(data)
                return data
        except Exception:
            pass
    return DEFAULT_PAGES.copy()


def save_pages(pages: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


PAGES = load_pages()


def send_telegram_message(chat_id: str, text: str, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": SILENT_MODE
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        print(f"[!] Telegram bildirim hatası: {e}")
        return False


def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Durum"}, {"text": "🔍 Canlı Kontrol"}],
            [{"text": "📜 Son Değişiklikler"}, {"text": "📑 24s Raporu"}],
            [{"text": "🩺 Sistem Sağlığı"}, {"text": "🔗 Sayfalar"}],
            [{"text": "⏸ Takibi Durdur"}, {"text": "▶️ Takibi Başlat"}]
        ],
        "resize_keyboard": True
    }


def add_history_entry(entry: str):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.insert(0, {
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "text": entry,
        "timestamp": time.time()
    })
    history = history[:50]

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_easycomment_count(username: str, page_url: str) -> int:
    """Easycomment üzerinden repost sayısını hem HTML/Next.js hem de API ile çeker."""
    # 1. Yöntem: Sayfa HTML ve JSON Hydration State Analizi
    try:
        resp = HTTP_CLIENT.get(page_url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            text = resp.text

            # Next.js Data bloğu tespiti
            soup = BeautifulSoup(text, "html.parser")
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data and next_data.string:
                try:
                    js_data = json.loads(next_data.string)
                    dumped = json.dumps(js_data)
                    matches = re.findall(r'"repost(?:Count|s)?"\s*:\s*(\d+)', dumped, re.I)
                    if matches:
                        return int(matches[0])
                except Exception:
                    pass

            # Sekme etiketindeki sayı: örn. Reposts (15) veya Reposts: 15
            clean_text = soup.get_text()
            tab_match = re.search(r'reposts?\s*\(?(\d+)\)?', clean_text, re.IGNORECASE)
            if tab_match:
                return int(tab_match.group(1))

            # Doğrudan gömülü video bağlantıları
            video_links = set(
                a["href"] for a in soup.find_all("a", href=True)
                if "/video/" in a["href"] or "tiktok.com/@" in a["href"]
            )
            if video_links:
                return len(video_links)

            if "no reposts" in text.lower() or "no videos" in text.lower():
                return 0
    except Exception:
        pass

    # 2. Yöntem: Arka plan Dahili API Çağrısı
    api_candidates = [
        f"https://easycomment.ai/api/tiktok/user?username={username}&tab=reposts",
        f"https://easycomment.ai/api/tiktok/posts?username={username}&type=repost",
        f"https://easycomment.ai/api/user/info?username={username}"
    ]
    api_headers = HEADERS.copy()
    api_headers.update({
        "Accept": "application/json, text/plain, */*",
        "Referer": page_url
    })

    for api_url in api_candidates:
        try:
            r = HTTP_CLIENT.get(api_url, headers=api_headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                dumped = json.dumps(data)
                m = re.findall(r'"(?:total|count|reposts?)"\s*:\s*(\d+)', dumped, re.I)
                if m:
                    return int(m[0])
        except Exception:
            continue

    return -1


def check_page_count(page_info: dict, key: str) -> int:
    """Sayfadaki gerçek öğe sayısını çeker."""
    global LAST_ERRORS
    url = page_info["url"]
    p_type = page_info["type"]

    try:
        # Easycomment Repostları
        if p_type == "easycomment_reposts":
            uname = page_info.get("username", key.replace("_reposts", ""))
            count = fetch_easycomment_count(uname, url)
            if count != -1:
                LAST_ERRORS.pop(key, None)
                return count
            LAST_ERRORS[key] = "İçerik sayısı okunamadı"
            return -1

        # Tikvib ve Threadlook İstekleri
        resp = HTTP_CLIENT.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            LAST_ERRORS[key] = f"HTTP {resp.status_code}"
            return -1

        soup = BeautifulSoup(resp.text, "html.parser")
        title_text = soup.title.string.strip().lower() if (soup.title and soup.title.string) else ""

        if any(cf in title_text for cf in ["just a moment", "attention required", "security check"]):
            LAST_ERRORS[key] = "Cloudflare Doğrulama Ekranı"
            return -1

        html_lower = resp.text.lower()
        text = soup.get_text()

        # Tikvib Repostları
        if p_type == "tikvib_reposts":
            unique_media_links = set(
                a["href"] for a in soup.select("a[href*='/media/']")
                if a.get("href") and len(a["href"]) > 8
            )
            if unique_media_links:
                LAST_ERRORS.pop(key, None)
                return len(unique_media_links)

            cards = soup.select("div.posts__video-item")
            if cards:
                LAST_ERRORS.pop(key, None)
                return len(cards)

            matches = set(re.findall(r'/media/(\d+)', resp.text))
            if matches:
                LAST_ERRORS.pop(key, None)
                return len(matches)

            if any(n in html_lower for n in ["no reposts", "user has no reposts", "no videos"]):
                LAST_ERRORS.pop(key, None)
                return 0

            LAST_ERRORS[key] = "İçerik listesi okunamadı"
            return -1

        # Tikvib Hikayeleri
        elif p_type == "tikvib_story":
            if "user has no stories" in text.lower() or "no stories" in text.lower():
                LAST_ERRORS.pop(key, None)
                return 0

            unique_downloads = set(
                a["href"] for a in soup.select("a[download]")
                if a.get("href") and not a["href"].startswith("#")
            )
            if unique_downloads:
                LAST_ERRORS.pop(key, None)
                return len(unique_downloads)

            if "download" in html_lower or bool(soup.find_all("video")) or "data-story" in html_lower:
                LAST_ERRORS.pop(key, None)
                return 1

            LAST_ERRORS.pop(key, None)
            return 0

        # Threadlook Threads
        elif p_type == "threads":
            matches = re.findall(r'THREADS\s*(\d+)', text, re.IGNORECASE)
            if matches:
                LAST_ERRORS.pop(key, None)
                return int(matches[0])
            matches_alt = re.findall(r'(\d+)\s*threads', text, re.IGNORECASE)
            if matches_alt:
                LAST_ERRORS.pop(key, None)
                return int(matches_alt[0])

            LAST_ERRORS[key] = "Thread sayısı ayrıştırılamadı"
            return -1

    except Exception as e:
        err_msg = str(e)
        clean_err = "Zaman Aşımı" if "timeout" in err_msg.lower() else err_msg[:50]
        LAST_ERRORS[key] = clean_err
        return -1


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "sillagunerrr_story": 1,
        "sillagunerrr_reposts": 0,
        "userr44559014_reposts": 0,
        "sillagunerr_threads": 105
    }


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_single_check(current_state: dict, manual_chat_id=None):
    global IS_TRACKING_PAUSED, LAST_ERRORS
    if IS_TRACKING_PAUSED and not manual_chat_id:
        return

    changes = []
    buttons = []
    error_list = []

    with STATE_LOCK:
        for key, info in PAGES.items():
            count = check_page_count(info, key)
            name_esc = html.escape(info["name"])

            if count == -1:
                err_text = html.escape(LAST_ERRORS.get(key, "Bilinmeyen Hata"))
                error_list.append(f"• <b>{name_esc}:</b> {err_text}")
                continue

            old_count = current_state.get(key, 0)
            if count != old_count:
                fark = count - old_count
                if fark > 0:
                    durum = f"➕ <b>{name_esc}</b> sayfasına <b>{fark} yeni içerik</b> eklendi!\nÖnceki: <code>{old_count}</code> ➔ Yeni: <code>{count}</code>"
                    log_entry = f"{info['name']}: +{fark} yeni ({count})"
                else:
                    durum = f"➖ <b>{name_esc}</b> sayfasından <b>{abs(fark)} içerik silindi!</b>\nÖnceki: <code>{old_count}</code> ➔ Yeni: <code>{count}</code>"
                    log_entry = f"{info['name']}: -{abs(fark)} silindi ({count})"

                changes.append(durum)
                add_history_entry(log_entry)
                buttons.append([{"text": f"🔗 {info['name']} Aç", "url": info["url"]}])
                current_state[key] = count

        target = manual_chat_id or TELEGRAM_CHAT_ID

        if changes and target:
            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            msg = f"🔔 <b>Değişiklik Bildirimi</b> ({now_str})\n\n" + "\n\n".join(changes)
            markup = {"inline_keyboard": buttons} if buttons else None
            send_telegram_message(target, msg, reply_markup=markup)
            save_state(current_state)

        elif manual_chat_id:
            now_str = datetime.now().strftime("%H:%M:%S")
            if error_list:
                hata_mesaji = f"⚠️ <b>Canlı Kontrol Hatası</b> ({now_str})\n\n" + "\n".join(error_list)
                send_telegram_message(manual_chat_id, hata_mesaji)
            else:
                send_telegram_message(manual_chat_id, f"✅ <b>Canlı Kontrol Tamamlandı</b> ({now_str})\nTüm sayfalar kontrol edildi, yeni değişiklik yok.")


def listen_telegram_commands(current_state: dict):
    global CHECK_INTERVAL_SECONDS, TELEGRAM_CHAT_ID, IS_TRACKING_PAUSED, SILENT_MODE, PAGES, LAST_ERRORS
    last_update_id = 0
    print("[*] Telegram dinleyici hazır.")

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 15}
            r = requests.get(url, params=params, timeout=20)
            resp = r.json()

            if not resp.get("ok"):
                time.sleep(5)
                continue

            for item in resp.get("result", []):
                last_update_id = item["update_id"]
                message = item.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "").strip()

                if not TELEGRAM_CHAT_ID:
                    TELEGRAM_CHAT_ID = chat_id

                if text in ["/start", "/yardim", "Yardım"]:
                    yardim = (
                        "👋 <b>Master Takip Botu Aktif!</b>\n\n"
                        "📊 <code>/durum</code> - Güncel sayıları gösterir\n"
                        "🔍 <code>/kontrol</code> - Hemen canlı tarama yapar\n"
                        "🩺 <code>/saglik</code> - Bağlantı ve sistem durumu\n"
                        "📜 <code>/gecmis</code> - Son değişiklik kayıtları\n"
                        "📑 <code>/ozet</code> - Son 24 saatlik döküm\n"
                        "⏱ <code>/sure 10</code> - Kontrol aralığı (dk)\n"
                        "🔄 <code>/sifirla</code> - Canlı sayıları yeni referans yapar\n"
                        "⏸ <code>/durdur</code> & ▶️ <code>/baslat</code>"
                    )
                    send_telegram_message(chat_id, yardim, reply_markup=get_main_keyboard())

                elif text in ["/durum", "📊 Durum"]:
                    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                    status_str = "⏸ Duraklatıldı" if IS_TRACKING_PAUSED else "▶️ Aktif"
                    satirlar = [
                        f"📊 <b>Mevcut Durum Özeti</b> ({now_str})",
                        f"• Bot Durumu: <code>{status_str}</code>",
                        f"• Sıklık: <code>{CHECK_INTERVAL_SECONDS // 60} dakikada bir</code>\n",
                        "📑 <b>Takip Edilen Sayfalar:</b>"
                    ]
                    with STATE_LOCK:
                        for k, inf in PAGES.items():
                            c = current_state.get(k, 0)
                            err_str = f" ⚠️ <i>({html.escape(LAST_ERRORS[k])})</i>" if k in LAST_ERRORS else ""
                            satirlar.append(f"• {html.escape(inf['name'])}: <code>{c}</code>{err_str}")
                    send_telegram_message(chat_id, "\n".join(satirlar), reply_markup=get_main_keyboard())

                elif text in ["/kontrol", "🔍 Canlı Kontrol"]:
                    send_telegram_message(chat_id, "🔎 Canlı kontrol başlatıldı, sayfalar taranıyor...")
                    run_single_check(current_state, manual_chat_id=chat_id)

                elif text in ["/saglik", "🩺 Sistem Sağlığı"]:
                    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                    if LAST_ERRORS:
                        hatalar = [f"❌ <b>{html.escape(PAGES[k]['name'])}:</b> <code>{html.escape(err)}</code>" for k, err in LAST_ERRORS.items() if k in PAGES]
                        send_telegram_message(chat_id, f"🩺 <b>Sağlık Uyarısı</b> ({now_str})\n\n" + "\n\n".join(hatalar))
                    else:
                        send_telegram_message(chat_id, f"🩺 <b>Sistem Sağlığı Mükemmel!</b> ({now_str})\nTüm sayfalara sorunsuz erişiliyor.")

                elif text in ["/sifirla"]:
                    send_telegram_message(chat_id, "🔄 Sayfalar taranıyor ve referanslar eşitleniyor...")
                    basarili, korunan = [], []
                    with STATE_LOCK:
                        for k, inf in PAGES.items():
                            c = check_page_count(inf, k)
                            if c != -1:
                                current_state[k] = c
                                basarili.append(f"• <b>{html.escape(inf['name'])}:</b> <code>{c}</code>")
                            else:
                                old_c = current_state.get(k, 0)
                                korunan.append(f"• <b>{html.escape(inf['name'])}:</b> <code>{old_c}</code> (Korundu)")
                        save_state(current_state)

                    sonuc = "✅ <b>Referans Eşitleme Tamamlandı</b>\n\n"
                    if basarili:
                        sonuc += "<b>Güncellenenler:</b>\n" + "\n".join(basarili) + "\n\n"
                    if korunan:
                        sonuc += "⚠️ <b>Hata Nedeniyle Korunanlar:</b>\n" + "\n".join(korunan)
                    send_telegram_message(chat_id, sonuc)

                elif text in ["/durdur", "⏸ Takibi Durdur"]:
                    IS_TRACKING_PAUSED = True
                    send_telegram_message(chat_id, "⏸ <b>Otomatik takip duraklatıldı.</b>")

                elif text in ["/baslat", "▶️ Takibi Başlat"]:
                    IS_TRACKING_PAUSED = False
                    send_telegram_message(chat_id, "▶️ <b>Otomatik takip başlatıldı!</b>")

                elif text in ["/sayfalar", "🔗 Sayfalar"]:
                    links = ["🔗 <b>Takip Edilen Sayfalar:</b>"]
                    for k, inf in PAGES.items():
                        links.append(f"• <a href=\"{inf['url']}\">{html.escape(inf['name'])}</a>")
                    send_telegram_message(chat_id, "\n".join(links))

        except Exception as e:
            print(f"[!] Hata: {e}")
            time.sleep(5)

        time.sleep(1)


def main():
    print("=" * 60)
    print("Master Takip Botu Başlatıldı...")
    print(f"Kontrol Sıklığı: {CHECK_INTERVAL_SECONDS // 60} dakika")
    print("=" * 60)

    current_state = load_state()

    cmd_thread = threading.Thread(target=listen_telegram_commands, args=(current_state,), daemon=True)
    cmd_thread.start()

    while True:
        run_single_check(current_state, manual_chat_id=None)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
