#!/usr/bin/env python3
"""
Master Takip ve Yönetim Botu
(Easycomment, Tikvib ve Threadlook Destekli - Railway Uyumlu)
"""

import os
import re
import time
import json
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Cloudscraper varsa korumaları aşmak için kullanılır
try:
    import cloudscraper
    HTTP_CLIENT = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    print("[*] Cloudscraper aktif: Cloudflare korumaları otomatik aşılacak.")
except Exception:
    HTTP_CLIENT = requests.Session()
    print("[*] Standart requests oturumu aktif.")

# ==========================================
# 1. BİLDİRİM VE BOT AYARLARI
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # İlk mesajınızla otomatik tanımlanır

CHECK_INTERVAL_SECONDS = 900  # 15 dakika
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"
HISTORY_FILE = "tracker_history.json"
CONFIG_FILE = "tracker_config.json"

DEFAULT_PAGES = {
    "sillagunerrr_story": {
        "url": "https://www.tikvib.com/story/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "tikvib_story"
    },
    "sillagunerrr_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=sillagunerrr&tab=reposts",
        "name": "sillagunerrr Repostlar",
        "type": "easycomment_reposts"
    },
    "userr44559014_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=userr44559014&tab=reposts",
        "name": "userr44559014 Repostlar",
        "type": "easycomment_reposts"
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads"
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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
                
                # Eski Tikvib bağlantılarını otomatik olarak Easycomment ile güncelle
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
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)


PAGES = load_pages()


def send_telegram_message(chat_id: str, text: str, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
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
    
    history.insert(0, {"time": datetime.now().strftime("%d.%m.%Y %H:%M"), "text": entry, "timestamp": time.time()})
    history = history[:50]
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def check_page_count(page_info: dict, key: str) -> int:
    """Sayfadaki gerçek öğe sayısını çeker."""
    global LAST_ERRORS
    url = page_info["url"]
    p_type = page_info["type"]
    
    try:
        resp = HTTP_CLIENT.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            err_msg = f"HTTP {resp.status_code}"
            LAST_ERRORS[key] = err_msg
            return -1

        soup = BeautifulSoup(resp.text, "html.parser")
        title_text = soup.title.string.strip().lower() if (soup.title and soup.title.string) else ""

        # Cloudflare JS Challenge Ekranı Tespiti
        if any(cf in title_text for cf in ["just a moment", "attention required", "security check"]):
            LAST_ERRORS[key] = "Cloudflare Doğrulama Ekranı (JS Challenge)"
            return -1

        html_lower = resp.text.lower()
        text = soup.get_text()

        # 1. EASYCOMMENT REPOSTLARI
        if p_type == "easycomment_reposts":
            tab_match = re.search(r'reposts?\s*\(?(\d+)\)?', text, re.IGNORECASE)
            if tab_match:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return int(tab_match.group(1))

            unique_video_links = set(
                a["href"] for a in soup.find_all("a", href=True)
                if "/video/" in a["href"] or "tiktok.com/@" in a["href"]
            )
            if unique_video_links:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(unique_video_links)

            state_match = re.search(r'"repost(?:Count|s)?"\s*:\s*(\d+)', resp.text, re.IGNORECASE)
            if state_match:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return int(state_match.group(1))

            if "no reposts" in html_lower or "no videos" in html_lower:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 0

            LAST_ERRORS[key] = "Easycomment içerik sayısı okunamadı"
            return -1

        # 2. TIKVIB REPOSTLARI
        elif p_type == "tikvib_reposts":
            unique_media_links = set(
                a["href"] for a in soup.select("a[href*='/media/']")
                if a.get("href") and len(a["href"]) > 8
            )
            if unique_media_links:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(unique_media_links)

            cards = soup.select("div.posts__video-item")
            if cards:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(cards)

            matches = set(re.findall(r'/media/(\d+)', resp.text))
            if matches:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(matches)

            if any(n in html_lower for n in ["no reposts", "user has no reposts", "no videos"]):
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 0

            LAST_ERRORS[key] = "İçerik listesi okunamadı"
            return -1

        # 3. TIKVIB HİKAYELERİ
        elif p_type == "tikvib_story":
            if "user has no stories" in text.lower() or "no stories" in text.lower():
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 0

            unique_downloads = set(
                a["href"] for a in soup.select("a[download]")
                if a.get("href") and not a["href"].startswith("#")
            )
            if unique_downloads:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(unique_downloads)

            if "download" in html_lower or bool(soup.find_all("video")) or "data-story" in html_lower:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 1

            if key in LAST_ERRORS:
                del LAST_ERRORS[key]
            return 0

        # 4. THREADLOOK THREADS
        elif p_type == "threads":
            matches = re.findall(r'THREADS\s*(\d+)', text, re.IGNORECASE)
            if matches:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return int(matches[0])
            matches_alt = re.findall(r'(\d+)\s*threads', text, re.IGNORECASE)
            if matches_alt:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return int(matches_alt[0])
            
            LAST_ERRORS[key] = "Thread sayısı ayrıştırılamadı"
            return -1

    except Exception as e:
        err_str = str(e)
        if "timed out" in err_str.lower():
            err_clean = "Bağlantı Zaman Aşımı"
        else:
            err_clean = err_str[:80]

        LAST_ERRORS[key] = err_clean
        print(f"[!] Tarama hatası ({url}): {err_clean}")
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_single_check(current_state: dict, manual_chat_id=None):
    global IS_TRACKING_PAUSED, LAST_ERRORS
    if IS_TRACKING_PAUSED and not manual_chat_id:
        return

    changes = []
    buttons = []
    error_list = []

    for key, info in PAGES.items():
        count = check_page_count(info, key)
        if count == -1:
            error_list.append(f"• *{info['name']}:* {LAST_ERRORS.get(key, 'Bilinmeyen Hata')}")
            continue
        
        old_count = current_state.get(key, 0)
        if count != old_count:
            fark = count - old_count
            if fark > 0:
                durum = f"➕ *{info['name']}* sayfasına *{fark} yeni içerik* eklendi!\nÖnceki: `{old_count}` ➔ Yeni: `{count}`"
                log_entry = f"{info['name']}: +{fark} yeni eklendi ({count})"
            else:
                durum = f"➖ *{info['name']}* sayfasından *{abs(fark)} içerik silindi!*\nÖnceki: `{old_count}` ➔ Yeni: `{count}`"
                log_entry = f"{info['name']}: -{abs(fark)} silindi ({count})"
            
            changes.append(durum)
            add_history_entry(log_entry)
            buttons.append([{"text": f"🔗 {info['name']} Aç", "url": info["url"]}])
            current_state[key] = count

    target = manual_chat_id or TELEGRAM_CHAT_ID

    if changes and target:
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        msg = f"🔔 *Değişiklik Bildirimi* ({now_str})\n\n" + "\n\n".join(changes)
        markup = {"inline_keyboard": buttons} if buttons else None
        send_telegram_message(target, msg, reply_markup=markup)
        save_state(current_state)

    elif manual_chat_id:
        now_str = datetime.now().strftime("%H:%M:%S")
        if error_list:
            hata_mesaji = f"⚠️ *Canlı Kontrol Sırasında Hata Oluştu!* ({now_str})\nSunucu bazı sayfalara erişemedi:\n\n" + "\n".join(error_list)
            send_telegram_message(manual_chat_id, hata_mesaji)
        else:
            send_telegram_message(manual_chat_id, f"✅ *Canlı Kontrol Tamamlandı* ({now_str})\nTüm sayfalar başarıyla okundu. Yeni eklenen veya silinen bir içerik yok.")


def listen_telegram_commands(current_state: dict):
    global CHECK_INTERVAL_SECONDS, TELEGRAM_CHAT_ID, IS_TRACKING_PAUSED, SILENT_MODE, PAGES, LAST_ERRORS
    last_update_id = 0
    print("[*] Telegram komut dinleyici hazır.")

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
                sender = message.get("from", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "").strip()

                if not TELEGRAM_CHAT_ID:
                    TELEGRAM_CHAT_ID = chat_id

                print(f"[KOMUT]: {text} (Gönderen: {sender.get('first_name')})")

                # 1. Başlangıç & Yardım
                if text in ["/start", "/yardim", "Yardım", "⚙️ Ayarlar & Yardım"]:
                    yardim = (
                        f"👋 Merhaba {sender.get('first_name')}!\n"
                        "Sosyal Medya Master Takip Paneli Komutları:\n\n"
                        "📊 `/durum` - İçerik sayılarını listeler\n"
                        "🔍 `/kontrol` - Hemen canlı tarama yapar\n"
                        "🩺 `/saglik` - Konsol ve bağlantı sağlık durumu\n"
                        "📜 `/gecmis` - Son değişikliklerin zaman kayıtları\n"
                        "📑 `/ozet` - Son 24 saatteki hareketlerin dökümü\n"
                        "⏱ `/sure 10` - Kontrol sıklığını 10 dakika yapar\n"
                        "🔔 `/test` - Bildirim sesini ve bağlantıyı test eder\n"
                        "🔕 `/sessiz` - Sessiz modu açar veya kapatır\n"
                        "⏸ `/durdur` & `/baslat` - Takibi duraklatır/başlatır\n"
                        "🔗 `/sayfalar` - Takip edilen profil linkleri\n"
                        "🔄 `/sifirla` - Canlı sayıları yeni referans yapar\n"
                        "🧹 `/hatalari_temizle` - Ekrandaki uyarı bayraklarını temizler\n"
                        "➕ `/sayfa_ekle <anahtar> <isim> <url> <tur>`\n"
                        "🗑 `/gecmis_temizle` - Geçmiş kayıtlarını sıfırlar"
                    )
                    send_telegram_message(chat_id, yardim, reply_markup=get_main_keyboard())

                # 2. Durum Raporu
                elif text in ["/durum", "📊 Durum"]:
                    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                    status_text = "⏸ Duraklatıldı" if IS_TRACKING_PAUSED else "▶️ Aktif Çalışıyor"
                    silent_text = "Açık (Sessiz)" if SILENT_MODE else "Kapalı (Sesli)"
                    satirlar = [
                        f"📊 *Mevcut Durum Özeti* ({now_str})",
                        f"• Bot Durumu: `{status_text}`",
                        f"• Sessiz Mod: `{silent_text}`",
                        f"• Kontrol Sıklığı: `{CHECK_INTERVAL_SECONDS // 60} dakikada bir`\n",
                        "📑 *Takip Edilen Sayfalar:*"
                    ]
                    for k, inf in PAGES.items():
                        c = current_state.get(k, 0)
                        durum_eki = ""
                        if k in LAST_ERRORS:
                            durum_eki = f" ⚠️ *({LAST_ERRORS[k]})*"
                        satirlar.append(f"• {inf['name']}: `{c}`{durum_eki}")
                    send_telegram
