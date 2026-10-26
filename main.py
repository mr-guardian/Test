#!/usr/bin/env python3
"""
Tikvib, Viewoo, Tik.watch ve Threadlook Master Takip ve Yönetim Botu
(Tik.watch Repost Sorunu Giderilmiş Tam Sürüm)
"""

import os
import re
import sys
import time
import json
import threading
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from datetime import datetime

# Cloudscraper varsa Cloudflare korumalarını otomatik aşar
try:
    import cloudscraper
    HTTP_CLIENT = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    IS_CLOUDSCRAPER = True
    print("[*] Cloudscraper aktif: Cloudflare korumaları otomatik aşılacak.")
except Exception:
    HTTP_CLIENT = requests.Session()
    IS_CLOUDSCRAPER = False
    print("[*] Standart requests oturumu aktif.")

# ==========================================
# 1. BİLDİRİM VE BOT AYARLARI
# ==========================================
TELEGRAM_BOT_TOKEN = "8505559116:AAFeQfxuwWLTe7kqS2lcRa6AZNKHPpie8vs"
TELEGRAM_CHAT_ID = ""  # İlk mesajınızla otomatik tanımlanır

CHECK_INTERVAL_SECONDS = 900  # Varsayılan 15 dakika
IS_TRACKING_PAUSED = False     # /durdur ile True olur
SILENT_MODE = False            # /sessiz ile ayarlanır

STATE_FILE = "tracker_state.json"
HISTORY_FILE = "tracker_history.json"
CONFIG_FILE = "tracker_config.json"

DEFAULT_PAGES = {
    "sillagunerrr_story": {
        "url": "https://viewoo.co/u/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "tikvib_story"
    },
    "sillagunerrr_reposts": {
        "url": "https://tik.watch/tr/@sillagunerrr?tab=reposts",
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

ALT_MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9"
}

LAST_ERRORS = {}


def load_pages() -> dict:
    pages = DEFAULT_PAGES.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                pages.update(saved)
                for default_key in ("sillagunerrr_story", "sillagunerrr_reposts"):
                    if default_key in pages:
                        pages[default_key]["url"] = DEFAULT_PAGES[default_key]["url"]
        except Exception:
            pass
    return pages


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
        print(f"[!] Gönderim hatası: {e}")
        return False


def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Durum"}, {"text": "🔍 Canlı Kontrol"}],
            [{"text": "📜 Son Değişiklikler"}, {"text": "📑 24s Raporu"}],
            [{"text": "🩺 Sistem Sağlığı"}, {"text": "🔬 Sayfa Analizi"}],
            [{"text": "🔗 Sayfalar"}, {"text": "⏸ Takibi Durdur"}, {"text": "▶️ Takibi Başlat"}]
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


def fetch_url(url: str, extra_headers=None):
    hdrs = HEADERS.copy()
    if extra_headers:
        hdrs.update(extra_headers)
    if IS_CLOUDSCRAPER:
        resp = HTTP_CLIENT.get(url, headers=hdrs if extra_headers else None, timeout=25)
    else:
        resp = HTTP_CLIENT.get(url, headers=hdrs, timeout=25)
    if resp.status_code == 403:
        mob_hdrs = ALT_MOBILE_HEADERS.copy()
        if extra_headers:
            mob_hdrs.update(extra_headers)
        resp = requests.get(url, headers=mob_hdrs, timeout=25)
    return resp


def try_tikwatch_reposts_api(url: str, html_text: str, soup: BeautifulSoup) -> int:
    """
    Tik.watch repost sekmesindeki 1 yanlış sayım sorununu çözen gelişmiş ayrıştırıcı:
    1. Next.js (__NEXT_DATA__) JSON verilerini tarar.
    2. Sayfadaki repost sayaç rozetlerini ve sekme metinlerini okur.
    3. Dahili API uç noktalarını yoklar.
    """
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Kullanıcı adını URL'den çıkar
    username_match = re.search(r'@([A-Za-z0-9_.]+)', url)
    if not username_match:
        username_match = re.search(r'/profile/([A-Za-z0-9_.]+)', url)
    username = username_match.group(1) if username_match else "sillagunerrr"

    # 1. Next.js (__NEXT_DATA__) gömülü JSON kontrolü (En güvenilir yöntem)
    next_data_script = soup.find("script", id="__NEXT_DATA__")
    if next_data_script and next_data_script.string:
        try:
            data = json.loads(next_data_script.string)
            # JSON yapısı içinde repost listesi veya öğelerini özyinelemeli (recursive) arayalım
            def search_dict(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ("reposts", "repostList", "itemList", "items") and isinstance(v, list):
                            if len(v) > 0:
                                return len(v)
                        res = search_dict(v)
                        if res is not None:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = search_dict(item)
                        if res is not None:
                            return res
                return None
            
            json_count = search_dict(data)
            if json_count is not None and json_count > 0:
                return json_count
        except Exception:
            pass

    # 2. HTML içinde regex ile "reposts": [...] veya benzeri dizi yakalama
    repost_json_match = re.search(r'"(?:reposts|repostList)"\s*:\s*(\[.*?\])', html_text, re.DOTALL)
    if repost_json_match:
        ids_in_json = set(re.findall(r'\b7[0-6]\d{17}\b', repost_json_match.group(1)))
        if ids_in_json:
            return len(ids_in_json)

    # 3. Sayfa üzerindeki tüm 19 haneli TikTok ID'lerini topla (Eğer 1'den fazlaysa doğrudan döndür)
    all_tiktok_ids = set(re.findall(r'\b7[0-6]\d{17}\b', html_text))
    if len(all_tiktok_ids) > 1:
        return len(all_tiktok_ids)

    # 4. Tik.watch API uç noktalarına doğrudan istek atma denemesi
    sec_uid_match = re.search(r'"secUid"\s*:\s*"([^"]+)"', html_text)
    sec_uid = sec_uid_match.group(1) if sec_uid_match else ""

    candidate_endpoints = [
        f"{base_url}/api/reposts?username={username}",
        f"{base_url}/api/user/reposts?username={username}",
        f"{base_url}/api/profile/{username}/reposts",
        f"{base_url}/tr/api/reposts?username={username}",
    ]
    if sec_uid:
        candidate_endpoints.insert(0, f"{base_url}/api/reposts?secUid={sec_uid}")

    api_headers = {"Accept": "application/json, text/plain, */*", "Referer": url, "X-Requested-With": "XMLHttpRequest"}
    for ep in candidate_endpoints:
        try:
            r_api = fetch_url(ep, extra_headers=api_headers)
            if r_api.status_code == 200 and len(r_api.text) > 5:
                if r_api.text.strip().startswith(("{", "[")):
                    api_data = r_api.json()
                    def count_lists(d):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k in ("items", "itemList", "reposts", "data", "list") and isinstance(v, list):
                                    return len(v)
                                res = count_lists(v)
                                if res is not None:
                                    return res
                        return None
                    found_len = count_lists(api_data)
                    if found_len is not None:
                        return found_len
        except Exception:
            continue

    # 5. Eğer yukarıdakilerin hepsi sonuç vermezse ve sayfada sadece 1 öğe görünüyorsa, 
    # gerçek değerin (örneğin 5) alınabilmesi için hata döndürmek yerine son bilinen güvenli değeri veya 
    # sayfadaki video/k Kart eleman sayısını verelim.
    cards = soup.select("div[class*='repost'], div[class*='video-item'], article, .grid > div")
    if len(cards) > 1:
        return len(cards)

    return -1


def check_page_count(page_info: dict, key: str) -> int:
    """Sayfadaki gerçek öğe sayısını tam tekil seçicilerle çeker."""
    global LAST_ERRORS
    url = page_info["url"]
    p_type = page_info["type"]
    
    try:
        resp = fetch_url(url)
        if resp.status_code != 200:
            LAST_ERRORS[key] = f"HTTP {resp.status_code}"
            return -1

        soup = BeautifulSoup(resp.text, "html.parser")
        title_text = soup.title.string.strip().lower() if (soup.title and soup.title.string) else ""

        if any(w in title_text for w in ["just a moment", "attention required", "security check"]):
            LAST_ERRORS[key] = "Cloudflare Doğrulama Ekranı"
            return -1

        html_lower = resp.text.lower()
        text_lower = soup.get_text().lower()

        # 1. REPOSTLAR (Tik.watch ve Tikvib Desteği)
        if p_type in ("tikvib_reposts", "tikwatch_reposts", "reposts"):
            if "tik.watch" in url:
                tw_count = try_tikwatch_reposts_api(url, resp.text, soup)
                if tw_count != -1:
                    if key in LAST_ERRORS:
                        del LAST_ERRORS[key]
                    return tw_count

            # Tikvib veya diğerleri için standart bağlantı ve ID sayımı
            unique_media_links = set()
            for a in soup.select("a[href*='/media/'], a[href*='/video/'], a[href*='video?']"):
                href = (a.get("href") or "").strip()
                if not href or any(nav in href.lower() for nav in ("video-viewer", "story-viewer", "repost-viewer")):
                    continue
                unique_media_links.add(href.split("#")[0])

            tiktok_video_ids = set(re.findall(r'\b7[0-6]\d{17}\b', resp.text))

            if len(tiktok_video_ids) > len(unique_media_links):
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(tiktok_video_ids)

            if unique_media_links:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(unique_media_links)

            if key in LAST_ERRORS:
                del LAST_ERRORS[key]
            return 0

        # 2. HİKAYELER (Viewoo ve Tikvib)
        elif p_type in ("tikvib_story", "viewoo_story", "story"):
            empty_phrases = ("no stories", "no active stories", "0 stories", "has no active stories")
            if any(p in text_lower for p in empty_phrases):
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 0

            story_items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            story_items = [el for el in story_items if "story-viewer" not in (el.get("href") or "").lower()]
            
            if story_items:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return len(story_items)

            if bool(soup.find_all("video")) or "data-story" in html_lower:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return 1

            if key in LAST_ERRORS:
                del LAST_ERRORS[key]
            return 0

        # 3. THREADS
        elif p_type == "threads":
            matches = re.findall(r'THREADS\s*(\d+)', soup.get_text(), re.IGNORECASE)
            if matches:
                if key in LAST_ERRORS:
                    del LAST_ERRORS[key]
                return int(matches[0])
            return 0

    except Exception as e:
        LAST_ERRORS[key] = str(e)[:80]
        return -1


def analyze_page_structure(url: str) -> str:
    try:
        resp = fetch_url(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        tiktok_ids = list(set(re.findall(r'\b7[0-6]\d{17}\b', resp.text)))
        return f"🔬 *Analiz ({url})*\n• Durum: `{resp.status_code}`\n• TikTok ID Sayısı: `{len(tiktok_ids)}` ({', '.join(tiktok_ids[:3]) if tiktok_ids else 'Yok'})"
    except Exception as e:
        return f"❌ Analiz hatası: {str(e)[:80]}"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "sillagunerrr_story": 1,
        "sillagunerrr_reposts": 5,  # Doğru değer referansı
        "userr44559014_reposts": 14,
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
        msg = f"🔔 *Değişiklik Bildirimi*\n\n" + "\n\n".join(changes)
        markup = {"inline_keyboard": buttons} if buttons else None
        send_telegram_message(target, msg, reply_markup=markup)
        save_state(current_state)
    elif manual_chat_id:
        if error_list:
            send_telegram_message(manual_chat_id, "⚠️ *Uyarı:* Bazı sayfalar okunamadı:\n\n" + "\n".join(error_list))
        else:
            send_telegram_message(manual_chat_id, "✅ *Canlı Kontrol Tamamlandı:* Tüm sayfalar güncel, yeni değişiklik yok.")


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
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "").strip()

                if not TELEGRAM_CHAT_ID:
                    TELEGRAM_CHAT_ID = chat_id

                if text in ["/start", "/yardim", "Yardım"]:
                    yardim = (
                        "👋 *Sosyal Medya Takip Paneli*\n\n"
                        "📊 `/durum` - Sayı özetini gösterir\n"
                        "🔍 `/kontrol` - Anlık tarama yapar\n"
                        "🔬 `/analiz` - Sayfa yapılarını inceler\n"
                        "🔄 `/sifirla` - Değerleri güncel gerçek sayılara eşitler\n"
                        "⏸ `/durdur` / `/baslat` - Takibi durdurur/başlatır"
                    )
                    send_telegram_message(chat_id, yardim, reply_markup=get_main_keyboard())

                elif text in ["/durum", "📊 Durum"]:
                    satirlar = ["📊 *Mevcut Durum Özeti:*"]
                    for k, inf in PAGES.items():
                        c = current_state.get(k, 0)
                        satirlar.append(f"• {inf['name']}: `{c}`")
                    send_telegram_message(chat_id, "\n".join(satirlar), reply_markup=get_main_keyboard())

                elif text in ["/kontrol", "🔍 Canlı Kontrol"]:
                    send_telegram_message(chat_id, "🔎 Sayfalar taranıyor...")
                    run_single_check(current_state, manual_chat_id=chat_id)

                elif text in ["/analiz", "🔬 Sayfa Analizi"]:
                    raporlar = [analyze_page_structure(inf["url"]) for inf in PAGES.values()]
                    send_telegram_message(chat_id, "\n\n".join(raporlar), reply_markup=get_main_keyboard())

                elif text in ["/sifirla"]:
                    send_telegram_message(chat_id, "🔄 Sayfalar taranıp referanslar eşitleniyor...")
                    for k, inf in PAGES.items():
                        c = check_page_count(inf, k)
                        if c != -1:
                            current_state[k] = c
                    save_state(current_state)
                    send_telegram_message(chat_id, "✅ Referanslar güncellendi!")

                elif text in ["/durdur", "⏸ Takibi Durdur"]:
                    IS_TRACKING_PAUSED = True
                    send_telegram_message(chat_id, "⏸ Takip duraklatıldı.")

                elif text in ["/baslat", "▶️ Takibi Başlat"]:
                    IS_TRACKING_PAUSED = False
                    send_telegram_message(chat_id, "▶️ Takip başlatıldı!")

        except Exception:
            time.sleep(5)
        time.sleep(1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ["--once", "once", "tek"]:
        st = load_state()
        run_single_check(st, manual_chat_id=None)
        save_state(st)
        sys.exit(0)

    print("Master Takip Botu Çalışıyor...")
    current_state = load_state()
    cmd_thread = threading.Thread(target=listen_telegram_commands, args=(current_state,), daemon=True)
    cmd_thread.start()

    while True:
        run_single_check(current_state, manual_chat_id=None)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
