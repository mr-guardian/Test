import os
import re
import time
import json
import threading
import io
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

TOKEN = os.getenv("TELEGRAM_TOKEN", "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6009524525")
SESSION_ID = os.getenv("TIKTOK_SESSION_ID", "f4eccac8039e5041af6c42a73a6cb4c4")
ARALIK = int(os.getenv("CHECK_INTERVAL", "900"))  # 15 dakika

DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/tmp")
STATE_FILE = os.path.join(DATA_DIR, "tiktok_bot_state.json")

TARGETS = {
    "sillagunerrr_story": {
        "platform": "tiktok_story",
        "name": "sillagunerrr Hikayeler",
        "username": "sillagunerrr"
    },
    "sillagunerrr_reposts": {
        "platform": "tiktok_reposts",
        "name": "sillagunerrr Repostlar",
        "username": "sillagunerrr"
    },
    "userr44559014_reposts": {
        "platform": "tiktok_reposts",
        "name": "userr44559014 Repostlar",
        "username": "userr44559014"
    },
    "emin_htp_reposts": {
        "platform": "tiktok_reposts",
        "name": "emin_htp Repostlar",
        "username": "emin_htp"
    },
    "sillagunerr_threads": {
        "platform": "threads",
        "name": "sillagunerr Threads",
        "url": "https://threadlook.com/profile/sillagunerr"
    }
}

lock = threading.Lock()
memory_state = {}


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def notify(text, reply_markup=None):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text[:4000]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            log(f"[!] Telegram Hatasi: {res.status_code} - {res.text}")
    except Exception as e:
        log(f"[!] Telegram bildirim hatasi: {e}")


def answer_callback(callback_query_id, text=None):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def send_bytes_photo(img_bytes, caption=""):
    try:
        p_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        res = requests.post(
            p_url,
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": ("story.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            timeout=30
        )
        return res.status_code == 200
    except Exception as e:
        log(f"[!] Telegram fotoğraf gönderme hatası: {e}")
        return False


def send_media(media_url, is_video=False, caption=""):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.tiktok.com/"
        }
        res = requests.get(media_url, headers=headers, timeout=25)
        if res.status_code == 200:
            file_data = io.BytesIO(res.content)
            if is_video:
                v_url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
                r = requests.post(v_url, data={"chat_id": CHAT_ID, "caption": caption}, files={"video": ("story.mp4", file_data, "video/mp4")}, timeout=30)
                if r.status_code == 200:
                    return True
            else:
                p_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
                r = requests.post(p_url, data={"chat_id": CHAT_ID, "caption": caption}, files={"photo": ("story.jpg", file_data, "image/jpeg")}, timeout=30)
                if r.status_code == 200:
                    return True

        endpoint = "sendVideo" if is_video else "sendPhoto"
        key = "video" if is_video else "photo"
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{endpoint}", json={"chat_id": CHAT_ID, key: media_url, "caption": caption}, timeout=20)
        return r.status_code == 200
    except Exception as e:
        log(f"[!] Telegram medya hatasi: {e}")
        return False


def get_tiktok_data(username, extract_story_media=False):
    reposts_count = None
    has_story = 0
    story_media_url = None
    story_screenshot_bytes = None
    is_video = False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1440,900"
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                viewport={"width": 1440, "height": 900}
            )

            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            context.add_cookies([{
                "name": "sessionid",
                "value": SESSION_ID,
                "domain": ".tiktok.com",
                "path": "/"
            }])

            page = context.new_page()
            captured_reposts = []
            captured_story_urls = []

            # Ağ trafiğini dinle: Hem repostları hem de hikaye akışı CDN URL'lerini yakalar
            def on_response(response):
                url = response.url.lower()
                if "item_list" in url and "repost" in url:
                    try:
                        res_json = response.json()
                        items = res_json.get("itemList", [])
                        if items is not None:
                            captured_reposts.append(len(items))
                    except Exception:
                        pass
                
                # TikTok hikaye video CDN isteklerini yakala
                if any(x in url for x in [".tiktokcdn.com", "byteoversea.com"]) and any(x in url for x in [".mp4", "video/tos", "playwm", "mime_type=video"]):
                    captured_story_urls.append(response.url)

            page.on("response", on_response)

            url = f"https://www.tiktok.com/@{username}?lang=tr-TR"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            page.keyboard.press("Escape")
            for sel in [
                '[data-e2e="modal-close-inner-button"]',
                '#login-modal-close',
                'button:has-text("Kabul")',
                'button:has-text("Accept")',
                'button[aria-label="Close"]'
            ]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click(timeout=800)
                except Exception:
                    pass

            # 1. Hikaye Tespiti (Halka veya SVG)
            has_story = page.evaluate('''() => {
                const svgStory = document.querySelector('circle[stroke*="url"], svg[class*="story"], div[class*="avatar-story"]');
                if (svgStory) return 1;
                const avatar = document.querySelector('[data-e2e="user-avatar"], [class*="AvatarContainer"]');
                if (avatar) {
                    const style = window.getComputedStyle(avatar);
                    if (avatar.innerHTML.includes("circle") || avatar.innerHTML.includes("story") || style.borderColor.includes("rgb")) {
                        return 1;
                    }
                }
                return 0;
            }''')

            # Hikaye Detayını Çekme
            if has_story and extract_story_media:
                try:
                    # Hikaye dairesine (avatara) tıkla
                    avatar_el = page.query_selector('circle[stroke*="url"], svg[class*="story"], [data-e2e="user-avatar"]')
                    if not avatar_el:
                        avatar_el = page.query_selector('[class*="AvatarContainer"]')

                    if avatar_el:
                        avatar_el.click(force=True)
                        time.sleep(3)

                        # Oynatıcı modalının yüklenmesini bekle
                        modal_area = page.query_selector('div[data-e2e="story-modal"], div[class*="StoryPlayer"], div[role="dialog"]')
                        
                        # Eğer ağdan bir video CDN linki yakalandıysa öncelikle onu al
                        if captured_story_urls:
                            story_media_url = captured_story_urls[-1]
                            is_video = True
                        else:
                            # DOM üzerinde doğrudan hikaye elementinin görüntüsünü veya linkini al
                            media_info = page.evaluate('''() => {
                                const v = document.querySelector('div[role="dialog"] video, div[class*="story"] video, video');
                                if (v && (v.currentSrc || v.src) && !v.src.startsWith("blob:")) {
                                    return { url: v.currentSrc || v.src, is_video: true };
                                }
                                const img = document.querySelector('div[role="dialog"] img, div[class*="story"] img');
                                if (img && img.src && !img.closest('[data-e2e="user-avatar"]')) {
                                    return { url: img.src, is_video: false };
                                }
                                return null;
                            }''')

                            if media_info:
                                story_media_url = media_info["url"]
                                is_video = media_info["is_video"]
                            elif modal_area:
                                # Blob korumalı video ise doğrudan oynatıcı modalının ekran görüntüsünü al
                                story_screenshot_bytes = modal_area.screenshot()

                        page.keyboard.press("Escape")
                        time.sleep(1)
                except Exception as story_err:
                    log(f"[!] Hikaye yakalama hatasi: {story_err}")

            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(1)

            # 2. Repost Sekmesine Tıkla
            tab_clicked = page.evaluate('''() => {
                const tabs = Array.from(document.querySelectorAll('[role="tab"], div[data-e2e*="tab"], p, span'));
                let target = tabs.find(el => {
                    const txt = (el.innerText || "").trim().toLowerCase();
                    const e2e = (el.getAttribute("data-e2e") || "").toLowerCase();
                    return (
                        e2e === "repost-tab" || 
                        e2e === "reposts-tab" ||
                        txt === "reposts" || 
                        txt === "repost" || 
                        txt === "yeniden gönderilenler" || 
                        txt === "yeniden"
                    );
                });

                if (!target) {
                    target = tabs.find(el => {
                        const html = el.innerHTML.toLowerCase();
                        return html.includes("repost") && el.getAttribute("role") === "tab";
                    });
                }

                if (target) {
                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                    target.click();
                    return true;
                }
                return false;
            }''')

            if tab_clicked:
                time.sleep(3.5)
                page.evaluate("window.scrollBy(0, 200)")
                time.sleep(1)

            # 3. Repost Sayımı
            if captured_reposts:
                reposts_count = captured_reposts[-1]
            elif tab_clicked:
                dom_count = page.evaluate('''() => {
                    const container = document.querySelector('div[data-e2e="user-repost-list"], div[data-e2e="user-post-item-list"]');
                    if (!container) return 0;
                    const items = container.querySelectorAll('[data-e2e="user-post-item"], a[href*="/video/"]');
                    const links = Array.from(items).map(i => i.href || i.querySelector('a')?.href).filter(Boolean);
                    return new Set(links.map(l => l.split('?')[0])).size;
                }''')
                reposts_count = dom_count
            else:
                reposts_count = 0

            page.close()
            context.close()
            browser.close()

    except Exception as e:
        log(f"[!] Playwright hatasi (@{username}): {e}")
        return None, None, None, None, False

    return reposts_count, has_story, story_media_url, story_screenshot_bytes, is_video


def fetch_and_send_sillagunerrr_story():
    notify("⏳ sillagunerrr hikayesi alınıyor, bekleyiniz...")
    _, has_st, st_url, st_bytes, is_vid = get_tiktok_data("sillagunerrr", extract_story_media=True)
    
    if has_st:
        if st_url:
            ok = send_media(st_url, is_video=is_vid, caption="📸 sillagunerrr Güncel Hikayesi")
            if ok:
                return
        if st_bytes:
            ok = send_bytes_photo(st_bytes, caption="📸 sillagunerrr Güncel Hikaye Önizlemesi")
            if ok:
                return
    
    notify("❌ Hikaye penceresi açılamadı veya medya çekilemedi.")


def get_threads_count(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            post = soup.select_one(".thread-content, .post-content, .thread-text, [class*='content'], article")
            post_txt = post.get_text().strip() if post else None

            m = re.findall(r'threads\s*[:\s]?\s*(\d+)', soup.get_text(), re.I)
            val = next((int(x) for x in m if int(x) not in (2025, 2026, 2027)), None)
            return val, post_txt
    except Exception as e:
        log(f"[!] Threads Hatasi: {e}")
    return None, None


def run_full_check(is_manual=False):
    global memory_state
    with lock:
        state = memory_state.copy()
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                pass

        current_summary = []
        tiktok_cache = {}

        for k, info in TARGETS.items():
            old_val = state.get(k)
            new_val = None
            post_txt = None
            p = info["platform"]

            if p.startswith("tiktok"):
                uname = info["username"]
                if uname not in tiktok_cache:
                    log(f"[*] TikTok taraniyor: @{uname}...")
                    rep_cnt, st_cnt, st_media, st_bytes, is_vid = get_tiktok_data(uname, extract_story_media=(uname == "sillagunerrr"))
                    tiktok_cache[uname] = {
                        "reposts": rep_cnt,
                        "story": st_cnt,
                        "story_media": st_media,
                        "story_bytes": st_bytes,
                        "is_video": is_vid
                    }

                cached = tiktok_cache[uname]
                if p == "tiktok_reposts":
                    new_val = cached["reposts"]
                elif p == "tiktok_story":
                    new_val = cached["story"]

            elif p == "threads":
                log(f"[*] Threads taraniyor: {info['url']}...")
                new_val, post_txt = get_threads_count(info["url"])

            if new_val is None:
                current_summary.append(f"• {info['name']}: Deger Alinamadi")
                log(f"[-] {info['name']} icin deger alinamadi.")
                continue

            current_summary.append(f"• {info['name']}: {new_val}")
            log(f"[+] {info['name']} -> Guncel: {new_val} (Onceki: {old_val})")

            # YALNIZCA DEĞİŞİKLİK OLDUĞUNDA BİLDİRİM
            if old_val is not None and new_val != old_val:
                fark = new_val - old_val
                target_url = f"https://www.tiktok.com/@{info.get('username')}" if "username" in info else info["url"]
                msg = f"🔔 {info['name']}: {old_val} ➔ {new_val} ({fark:+d})\n🔗 {target_url}"
                
                if p == "threads" and post_txt:
                    msg += f"\n\n📝 Son Threads Gönderisi:\n\"{post_txt[:400]}\""

                reply_markup = None
                if k == "sillagunerrr_story":
                    reply_markup = {
                        "inline_keyboard": [[
                            {"text": "📸 Son Hikayeyi Gönder", "callback_data": "get_story"}
                        ]]
                    }

                notify(msg, reply_markup=reply_markup)

                # Yeni hikaye açıldıysa doğrudan medyayı gönder
                if k == "sillagunerrr_story" and new_val > old_val:
                    c_data = tiktok_cache.get("sillagunerrr", {})
                    if c_data.get("story_media"):
                        send_media(c_data["story_media"], is_video=c_data.get("is_video", False), caption="📸 sillagunerrr Yeni Hikaye")
                    elif c_data.get("story_bytes"):
                        send_bytes_photo(c_data["story_bytes"], caption="📸 sillagunerrr Yeni Hikaye")

            state[k] = new_val

        memory_state = state.copy()

        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as file_err:
            log(f"[!] Dosya yazma uyarisi: {file_err}")

        if is_manual:
            return "\n".join(current_summary)
        return None


def tracker_thread():
    while True:
        time.sleep(ARALIK)
        log("Zamanlanmis rutin kontrol (Sessiz mod)...")
        run_full_check(is_manual=False)


def bot_listener():
    last_update_id = 0
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass

    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            resp = requests.get(url, params={"offset": last_update_id + 1, "timeout": 20}, timeout=25).json()

            for item in resp.get("result", []):
                last_update_id = item["update_id"]

                # Buton Tıklamaları
                if "callback_query" in item:
                    cb = item["callback_query"]
                    cb_id = cb["id"]
                    cb_data = cb.get("data")
                    answer_callback(cb_id, "İşlem yapılıyor...")

                    if cb_data == "get_story":
                        threading.Thread(target=fetch_and_send_sillagunerrr_story, daemon=True).start()
                    elif cb_data == "run_check":
                        notify("🔍 Sayfalar taranıyor...")
                        summary = run_full_check(is_manual=True)
                        notify(f"📊 Canlı Durum:\n\n{summary}")

                # Metin Mesajları
                msg = item.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip().lower()

                if chat_id == str(CHAT_ID) and text:
                    main_buttons = {
                        "inline_keyboard": [
                            [{"text": "📸 sillagunerrr Son Hikaye", "callback_data": "get_story"}],
                            [{"text": "🔍 Canlı Kontrol", "callback_data": "run_check"}]
                        ]
                    }

                    if text in ["/kontrol", "kontrol", "🔎 canli kontrol"]:
                        notify("🔍 Sayfalar taranıyor, bekleyiniz...")
                        summary = run_full_check(is_manual=True)
                        notify(f"📊 Canlı Durum Raporu:\n\n{summary}", reply_markup=main_buttons)

                    elif text in ["/hikaye", "hikaye", "story"]:
                        threading.Thread(target=fetch_and_send_sillagunerrr_story, daemon=True).start()

                    elif text in ["/durum", "durum"]:
                        summary = [f"• {info['name']}: {memory_state.get(k, 'Kayit yok')}" for k, info in TARGETS.items()]
                        notify("📋 Kayıtlı Veriler:\n\n" + "\n".join(summary), reply_markup=main_buttons)

                    elif text in ["/start", "start", "yardim", "/yardim"]:
                        notify(
                            "🤖 Takip Botu Aktif!\n\n"
                            "• Değişiklik olmadıkça sessiz çalışır.\n"
                            "• Threads sayısı değişirse son metin iletilir.\n"
                            "• Butonla anında hikaye talep edebilirsiniz.",
                            reply_markup=main_buttons
                        )

        except Exception:
            time.sleep(2)
        time.sleep(0.5)


if __name__ == "__main__":
    log("Bulut Takip Botu Başlatılıyor...")
    start_markup = {
        "inline_keyboard": [
            [{"text": "📸 sillagunerrr Son Hikaye", "callback_data": "get_story"}],
            [{"text": "🔍 Canlı Kontrol", "callback_data": "run_check"}]
        ]
    }
    notify("🚀 Bot aktif edildi! Değişiklik olmadıkça rapor gelmeyecek.", reply_markup=start_markup)
    run_full_check(is_manual=False)
    threading.Thread(target=tracker_thread, daemon=True).start()
    bot_listener()
