import os
import re
import time
import json
import threading
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


def notify(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": CHAT_ID, "text": text[:4000]}, timeout=10)
        if res.status_code != 200:
            log(f"[!] Telegram Hatasi: {res.status_code} - {res.text}")
    except Exception as e:
        log(f"[!] Telegram bildirim hatasi: {e}")


def send_media(media_url, caption=""):
    try:
        # Önce video olarak göndermeyi dene
        v_url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
        res = requests.post(v_url, json={"chat_id": CHAT_ID, "video": media_url, "caption": caption}, timeout=20)
        if res.status_code == 200:
            return

        # Video değilse görsel olarak gönder
        p_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        res = requests.post(p_url, json={"chat_id": CHAT_ID, "photo": media_url, "caption": caption}, timeout=20)
        if res.status_code != 200:
            log(f"[!] Medya gonderilemedi: {res.text}")
    except Exception as e:
        log(f"[!] Telegram medya hatasi: {e}")


def get_tiktok_data(username, extract_story_media=False):
    reposts_count = None
    has_story = 0
    story_media_url = None

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

            # 1. Hikaye Tespiti
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

            # Hikaye varsa ve medya çekilmesi isteniyorsa doğrudan tıkla ve medya URL'ini al
            if has_story and extract_story_media:
                try:
                    avatar_el = page.query_selector('[data-e2e="user-avatar"], [class*="AvatarContainer"]')
                    if avatar_el:
                        avatar_el.click()
                        time.sleep(2.5)
                        story_media_url = page.evaluate('''() => {
                            const vid = document.querySelector('video source, video');
                            if (vid && vid.src) return vid.src;
                            const img = document.querySelector('img[class*="Story"], img[class*="story"]');
                            if (img && img.src) return img.src;
                            return null;
                        }''')
                        page.keyboard.press("Escape")
                        time.sleep(1)
                except Exception as story_err:
                    log(f"[!] Hikaye medyasi alinirken hata: {story_err}")

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
        return None, None, None

    return reposts_count, has_story, story_media_url


def get_threads_count(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            post = soup.select_one(".thread-content, .post-content, article")
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
                    # sillagunerrr hesabı taranırken hikaye medyasını da yakala
                    need_media = (uname == "sillagunerrr")
                    rep_cnt, st_cnt, st_media = get_tiktok_data(uname, extract_story_media=need_media)
                    tiktok_cache[uname] = {
                        "reposts": rep_cnt,
                        "story": st_cnt,
                        "story_media": st_media
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

            # YALNIZCA DEĞİŞİKLİK OLDUĞUNDA BİLDİRİM GÖNDER
            if old_val is not None and new_val != old_val:
                fark = new_val - old_val
                target_url = f"https://www.tiktok.com/@{info.get('username')}" if "username" in info else info["url"]
                msg = f"🔔 {info['name']}: {old_val} ➔ {new_val} ({fark:+d})\n🔗 {target_url}"
                
                if fark > 0 and post_txt:
                    msg += f"\n📝 Son Gonderi: \"{post_txt[:200]}\""
                notify(msg)

                # sillagunerrr yeni bir hikaye paylaştıysa medyayı doğrudan gönder
                if k == "sillagunerrr_story" and new_val > old_val:
                    st_media = tiktok_cache.get("sillagunerrr", {}).get("story_media")
                    if st_media:
                        send_media(st_media, caption="📸 sillagunerrr Yeni Hikaye")

            state[k] = new_val

        memory_state = state.copy()

        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as file_err:
            log(f"[!] Dosya yazma uyarisi: {file_err}")

        # Yalnızca manuel tetiklendiğinde raporu döndür
        if is_manual:
            return "\n".join(current_summary)
        return None


def tracker_thread():
    while True:
        time.sleep(ARALIK)
        log("Zamanlanmis rutin kontrol calisiyor (Sessiz mod)...")
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
                msg = item.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip().lower()

                if chat_id == str(CHAT_ID) and text:
                    if text in ["/kontrol", "kontrol"]:
                        notify("🔍 Sayfalar taraniyor, bekleyiniz...")
                        summary = run_full_check(is_manual=True)
                        notify(f"📊 Canli Durum Raporu:\n\n{summary}")

                    elif text in ["/durum", "durum"]:
                        summary = [f"• {info['name']}: {memory_state.get(k, 'Kayit yok')}" for k, info in TARGETS.items()]
                        notify("📋 Kayitli Veriler:\n\n" + "\n".join(summary))

        except Exception:
            time.sleep(2)
        time.sleep(0.5)


if __name__ == "__main__":
    log("Bulut Takip Botu Baslatiliyor...")
    # İlk başlangıçta sadece takip durumunu doğrular, sohbeti raporla doldurmaz
    notify("🚀 Bot aktif edildi! Degisiklik olmadikca rapor gonderilmeyecek, yalnizca yeni hareketlerde bildirim alacaksiniz.")
    run_full_check(is_manual=False)
    threading.Thread(target=tracker_thread, daemon=True).start()
    bot_listener()
