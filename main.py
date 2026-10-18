#!/usr/bin/env python3
"""
Tikvib ve Threadlook Master Takip ve Yönetim Botu
(Tamamen Doğrulanmış Gerçek DOM Seçicileri: posts__video-item, /media/)
"""

import os
import re
import time
import json
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 1. BİLDİRİM VE BOT AYARLARI
# ==========================================
TELEGRAM_BOT_TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
TELEGRAM_CHAT_ID = ""  # İlk mesajınızla otomatik tanımlanır

CHECK_INTERVAL_SECONDS = 900  # Varsayılan 15 dakika
IS_TRACKING_PAUSED = False     # /durdur ile True olur
SILENT_MODE = False            # /sessiz ile ayarlanır

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
        "url": "https://www.tikvib.com/reposts/sillagunerrr",
        "name": "sillagunerrr Repostlar",
        "type": "tikvib_reposts"
    },
    "userr44559014_reposts": {
        "url": "https://www.tikvib.com/reposts/userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "tikvib_reposts"
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads"
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

LAST_ERRORS = {}


def load_pages() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_PAGES.copy()


def save_pages(pages: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)


PAGES = load_pages()


def send_telegram_message(chat_id: str, text: str, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
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
        print(f"[!] Gönderim hatası: {e}")
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
    """Sayfadaki gerçek öğe sayısını tam CSS seçicileriyle çeker."""
    global LAST_ERRORS
    url = page_info["url"]
    p_type = page_info["type"]
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            err_msg = f"HTTP {resp.status_code}"
            LAST_ERRORS[key] = err_msg
            return -1
        
        if key in LAST_ERRORS:
            del LAST_ERRORS[key]

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        # 1. TIKVIB REPOSTLARI
        if p_type == "tikvib_reposts":
            items = soup.select(".posts__video-item, div.posts-video > div, a.posts__video-item-a")
            if items:
                return len(items)
            
            media_links = soup.select("a[href*='/media/']")
            if media_links:
                return len(media_links)
            
            earnings = soup.select(".posts__video-item-earnings, .earnings-toggle")
            if earnings:
                return len(earnings)

            matches = re.findall(r'/media/\d+', resp.text)
            if matches:
                return len(set(matches))
            
            return 0

        # 2. TIKVIB HİKAYELERİ
        elif p_type == "tikvib_story":
            if "user has no stories" in text.lower() or "no stories" in text.lower():
                return 0
            
            items = soup.select(".posts__video-item, a[href*='/media/'], a[download], button[download], .story-item")
            if items:
                return len(items)
            
            if "download" in resp.text.lower() or bool(soup.find_all("video")) or bool(soup.find_all("source")):
                return 1
            return 0

        # 3. THREADLOOK THREADS
        elif p_type == "threads":
            matches = re.findall(r'THREADS\s*(\d+)', text, re.IGNORECASE)
            if matches:
                return int(matches[0])
            matches_alt = re.findall(r'(\d+)\s*threads', text, re.IGNORECASE)
            if matches_alt:
                return int(matches_alt[0])
            return -1

    except Exception as e:
        err_str = str(e)
        if "Tunnel connection failed: 403" in err_str:
            err_clean = "Proxy Engeli (403 Forbidden)"
        elif "timed out" in err_str.lower():
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
        "sillagunerrr_reposts": 4,
        "userr44559014_reposts": 7,
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

                if text in ["/start", "/yardim", "Yardım", "⚙️ Ayarlar & Yardım"]:
                    yardim = (
                        f"👋 Merhaba {sender.get('first_name')}!\n"
                        "Sosyal Medya Master Takip Paneli Komutları:\n\n"
                        "📊 `/durum` - İçerik sayılarını listeler\n"
                        "🔍 `/kontrol` - Hemen canlı tarama yapar (Hata varsa detayını söyler)\n"
                        "🩺 `/saglik` - Konsolun ve internet bağlantısının sağlık durumunu gösterir\n"
                        "📜 `/gecmis` - Son değişikliklerin zaman kayıtları\n"
                        "📑 `/ozet` - Son 24 saatteki hareketlerin dökümü\n"
                        "⏱ `/sure 10` - Kontrol sıklığını 10 dakika yapar\n"
                        "🔔 `/test` - Bildirim sesini ve bağlantıyı test eder\n"
                        "🔕 `/sessiz` - Sessiz modu açar veya kapatır\n"
                        "⏸ `/durdur` & `/baslat` - Takibi duraklatır/başlatır\n"
                        "🔗 `/sayfalar` - Takip edilen profil linkleri\n"
                        "🔄 `/sifirla` - Canlı sayıları yeni referans yapar\n"
                        "➕ `/sayfa_ekle <anahtar> <isim> <url> <tur>`\n"
                        "🗑 `/gecmis_temizle` - Geçmiş kayıtlarını sıfırlar"
                    )
                    send_telegram_message(chat_id, yardim, reply_markup=get_main_keyboard())

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
                            durum_eki = " ⚠️ *(Erişim Hatası)*"
                        satirlar.append(f"• {inf['name']}: `{c}`{durum_eki}")
                    send_telegram_message(chat_id, "\n".join(satirlar), reply_markup=get_main_keyboard())

                elif text in ["/kontrol", "🔍 Canlı Kontrol"]:
                    send_telegram_message(chat_id, "🔎 Sayfalar canlı taranıyor...")
                    run_single_check(current_state, manual_chat_id=chat_id)

                elif text in ["/saglik", "🩺 Sistem Sağlığı"]:
                    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                    if LAST_ERRORS:
                        hatalar = [f"❌ *{PAGES[k]['name']}:*\n`{err}`" for k, err in LAST_ERRORS.items() if k in PAGES]
                        msg = f"🩺 *Sistem Sağlık Raporu - HATA VAR!* ({now_str})\n\nBot çalışıyor ancak sunucu şu sayfalara erişemiyor:\n\n" + "\n\n".join(hatalar)
                    else:
                        msg = f"🩺 *Sistem Sağlık Raporu - MÜKEMMEL!* ({now_str})\n\n[✓] Python konsolu aktif çalışıyor.\n[✓] Telegram bağlantısı sorunsuz.\n[✓] Tüm sayfalara erişim açık, hiçbir bağlantı veya proxy hatası yok."
                    send_telegram_message(chat_id, msg, reply_markup=get_main_keyboard())

                elif text in ["/gecmis", "📜 Son Değişiklikler"]:
                    if os.path.exists(HISTORY_FILE):
                        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                            hist = json.load(f)
                        if hist:
                            kayitlar = [f"• `{h['time']}` - {h['text']}" for h in hist[:10]]
                            send_telegram_message(chat_id, "📜 *Son Değişiklikler:*\n\n" + "\n".join(kayitlar))
                        else:
                            send_telegram_message(chat_id, "ℹ️ Henüz kaydedilmiş bir değişiklik yok.")
                    else:
                        send_telegram_message(chat_id, "ℹ️ Henüz kaydedilmiş bir değişiklik yok.")

                elif text in ["/ozet", "📑 24s Raporu"]:
                    if os.path.exists(HISTORY_FILE):
                        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                            hist = json.load(f)
                        cutoff = time.time() - 86400
                        son_24 = [f"• `{h['time']}` - {h['text']}" for h in hist if h.get("timestamp", 0) >= cutoff]
                        if son_24:
                            send_telegram_message(chat_id, f"📑 *Son 24 Saat Raporu ({len(son_24)} olay):*\n\n" + "\n".join(son_24))
                        else:
                            send_telegram_message(chat_id, "📑 *Son 24 Saat Raporu:*\nSon 24 saatte hiçbir yeni içerik veya silinme kaydedilmedi.")
                    else:
                        send_telegram_message(chat_id, "📑 *Son 24 Saat Raporu:*\nKayıtlı olay bulunmuyor.")

                elif text in ["/test"]:
                    send_telegram_message(chat_id, "🔔 *Test Bildirimi!*\nKonsol ve Telegram bağlantısı aktif.")

                elif text in ["/sayfalar", "/sayfa", "🔗 Sayfalar"]:
                    links = ["🔗 *Takip Edilen Sayfalar:*"]
                    for k, inf in PAGES.items():
                        links.append(f"• [{inf['name']}]({inf['url']}) (`{k}`)")
                    send_telegram_message(chat_id, "\n".join(links), reply_markup=get_main_keyboard())

                elif text in ["/durdur", "⏸ Takibi Durdur"]:
                    IS_TRACKING_PAUSED = True
                    send_telegram_message(chat_id, "⏸ *Otomatik takip duraklatıldı.*", reply_markup=get_main_keyboard())

                elif text in ["/baslat", "▶️ Takibi Başlat"]:
                    IS_TRACKING_PAUSED = False
                    send_telegram_message(chat_id, "▶️ *Otomatik takip başlatıldı!*", reply_markup=get_main_keyboard())

                elif text in ["/sessiz"]:
                    SILENT_MODE = not SILENT_MODE
                    durum = "AÇIK (Sessiz)" if SILENT_MODE else "KAPALI (Sesli)"
                    send_telegram_message(chat_id, f"🔕 Sessiz bildirim modu: *{durum}*")

                elif text.startswith("/sure"):
                    parts = text.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        yeni_dakika = int(parts[1])
                        CHECK_INTERVAL_SECONDS = yeni_dakika * 60
                        send_telegram_message(chat_id, f"⏱ Kontrol sıklığı *{yeni_dakika} dakika* yapıldı.")
                    else:
                        send_telegram_message(chat_id, "⚠️ Kullanım: `/sure 10`")

                elif text in ["/sifirla"]:
                    send_telegram_message(chat_id, "🔄 Sayfalar taranıyor ve referanslar eşitleniyor...")
                    for k, inf in PAGES.items():
                        c = check_page_count(inf, k)
                        if c != -1:
                            current_state[k] = c
                    save_state(current_state)
                    send_telegram_message(chat_id, "✅ Tüm referans sayıları güncel durumla eşitlendi!")

                elif text in ["/gecmis_temizle"]:
                    if os.path.exists(HISTORY_FILE):
                        os.remove(HISTORY_FILE)
                    send_telegram_message(chat_id, "🗑 Değişiklik geçmişi günlüğü temizlendi.")

                elif text.startswith("/sayfa_ekle"):
                    parts = text.split(maxsplit=4)
                    if len(parts) == 5:
                        _, key, name, url, ptype = parts
                        PAGES[key] = {"name": name, "url": url, "type": ptype}
                        save_pages(PAGES)
                        c = check_page_count(PAGES[key], key)
                        current_state[key] = c if c != -1 else 0
                        save_state(current_state)
                        send_telegram_message(chat_id, f"✅ *{name}* takibe eklendi! (Mevcut: `{current_state[key]}`)")
                    else:
                        send_telegram_message(chat_id, "⚠️ Kullanım: `/sayfa_ekle <anahtar> <isim> <url> <tur>`")

                elif text.startswith("/sayfa_sil"):
                    parts = text.split()
                    if len(parts) == 2:
                        key = parts[1]
                        if key in PAGES:
                            del PAGES[key]
                            save_pages(PAGES)
                            send_telegram_message(chat_id, f"🗑 `{key}` sayfadan çıkarıldı.")
                        else:
                            send_telegram_message(chat_id, "⚠️ Belirtilen anahtar bulunamadı.")
                    else:
                        send_telegram_message(chat_id, "⚠️ Kullanım: `/sayfa_sil <anahtar>`")

        except Exception as e:
            time.sleep(5)

        time.sleep(1)


def main():
    print("=" * 60)
    print("Master Takip Botu Çalışıyor!")
    print(f"Kontrol sıklığı: {CHECK_INTERVAL_SECONDS // 60} dakika")
    print("=" * 60)

    current_state = load_state()

    cmd_thread = threading.Thread(target=listen_telegram_commands, args=(current_state,), daemon=True)
    cmd_thread.start()

    while True:
        run_single_check(current_state, manual_chat_id=None)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
