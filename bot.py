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


def notify(text, reply_markup=None):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text[:4000]
        }
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


def send_media(media_url, caption=""):
    try:
        v_url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
        res = requests.post(v_url, json={"chat_id": CHAT_ID, "video": media_url, "caption": caption}, timeout=25)
        if res.status_code == 200:
            return True

        p_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        res = requests.post(p_url, json={"chat_id": CHAT_ID, "photo": media_url, "caption": caption}, timeout=25)
        if res.status_code == 200:
            return True
            
        log(f"[!] Medya gonderilemedi: {res.text}")
        return False
    except Exception as e:
        log(f"[!] Telegram medya hatasi: {e}")
        return False


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

            # Hikaye medyası çekme isteği varsa
            if has_story and extract_story_media:
                try:
                    avatar_el = page.query_selector('[data-e2e="user-avatar"], [class*="AvatarContainer"]')
                    if avatar_el:
                        avatar_el.click()
                        time.sleep(3)
                        story_media_url = page.evaluate('''() => {
                            const vid = document.querySelector('video source, video');
                            if (vid && vid.src) return vid.src;
                            const img = document.querySelector('img[class*="Story"], img[class*="story"], div[class*="Story"] img');
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


def fetch_and_send_sillagunerrr_story():
    notify("⏳ sillagunerrr hikayesi aliniyor, bekleyiniz...")
    _, has_st, st_url = get_tiktok_data("sillagunerrr", extract_story_media=True)
    if has_st and st_url:
        ok = send_media(st_url, caption="📸 sillagunerrr Güncel Hikayesi")
        if not ok:
            notify(f"🔗 Hikaye Medya Linki:\n{st_url}")
    else:
        notify("❌ Aktif hikaye bulunamadi veya medya yuklenemedi.")


def get_threads_count(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Son Threads metnini hassas seçicilerle tara
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
                with open(STATE_FILE, "r
