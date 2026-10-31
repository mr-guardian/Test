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
ARALIK = int(os.getenv("CHECK_INTERVAL", "900"))  # 15 dk

DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/tmp")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

TARGETS = {
    "sillagunerrr_story": {"platform": "viewwo_story", "name": "sillagunerrr Hikayeler", "username": "sillagunerrr"},
    "sillagunerrr_following": {"platform": "viewwo_following", "name": "sillagunerrr Takip Sayısı", "username": "sillagunerrr"},
    "sillagunerrr_reposts": {"platform": "viewwo_reposts", "name": "sillagunerrr Repostlar", "username": "sillagunerrr"},
    "userr44559014_reposts": {"platform": "viewwo_reposts", "name": "userr44559014 Repostlar", "username": "userr44559014"},
    "emin_htp_reposts": {"platform": "viewwo_reposts", "name": "emin_htp Repostlar", "username": "emin_htp"},
    "sillagunerr_threads": {"platform": "threads", "name": "sillagunerr Threads", "url": "https://threadlook.com/profile/sillagunerr"}
}

memory_state = {}


def notify(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text[:4000]},
            timeout=10
        )
    except Exception as e:
        print(f"[!] Telegram bildirim hatası: {e}", flush=True)


def get_viewwo_data(username):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page()
            page.goto(f"https://viewwo.com/profile/{username}", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            data = page.evaluate('''() => {
                const text = document.body.innerText;

                // Takip Sayısı
                let following = null;
                const fMatch = text.match(/(\\d+)\\s*(Following|Takip)/i);
                if (fMatch) following = parseInt(fMatch[1], 10);

                // Hikaye Sayısı
                let story = 0;
                const sMatch = text.match(/stories?\\s*\\((\\d+)\\)/i) || text.match(/hikaye\\s*\\((\\d+)\\)/i);
                if (sMatch) {
                    story = parseInt(sMatch[1], 10);
                } else if (document.querySelector('.has-story, circle[stroke*="url"], svg[class*="story"]')) {
                    story = 1;
                }

                // Repost Sayısı
                let reposts = null;
                const rMatch = text.match(/reposts?\\s*\\((\\d+)\\)/i) || text.match(/yeniden\\s*\\((\\d+)\\)/i);
                if (rMatch) {
                    reposts = parseInt(rMatch[1], 10);
                } else {
                    reposts = document.querySelectorAll('.video-card, .post-item, a[href*="/video/"]').length;
                }

                return { reposts, story, following };
            }''')

            browser.close()
            return data["reposts"], data["story"], data["following"]
    except Exception as e:
        print(f"[!] Viewwo hatası (@{username}): {e}", flush=True)
        return None, None, None


def get_threads_count(url):
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            post_el = soup.select_one(".thread-content, .post-content, article")
            post_txt = post_el.get_text().strip() if post_el else None
            m = re.findall(r'threads\s*[:\s]?\s*(\d+)', soup.get_text(), re.I)
            val = next((int(x) for x in m if int(x) not in (2025, 2026, 2027)), None)
            return val, post_txt
    except Exception as e:
        print(f"[!] Threads hatası: {e}", flush=True)
    return None, None


def run_full_check(is_manual=False):
    global memory_state
    state = memory_state.copy()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    summary = []
    viewwo_cache = {}

    for k, info in TARGETS.items():
        old_val = state.get(k)
        new_val = None
        post_txt = None
        p = info["platform"]

        if p.startswith("viewwo"):
            uname = info["username"]
            if uname not in viewwo_cache:
                rep, st, fol = get_viewwo_data(uname)
                viewwo_cache[uname] = {"reposts": rep, "story": st, "following": fol}

            new_val = viewwo_cache[uname][p.replace("viewwo_", "")]

        elif p == "threads":
            new_val, post_txt = get_threads_count(info["url"])

        if new_val is None:
            summary.append(f"• {info['name']}: Değer Alınamadı")
            continue

        summary.append(f"• {info['name']}: {new_val}")

        # Değişiklik kontrolü ve anlık bildirim
        if old_val is not None and new_val != old_val:
            fark = new_val - old_val
            if not (k == "sillagunerrr_following" and fark <= 0):
                url = f"https://viewwo.com/profile/{info.get('username')}" if "username" in info else info["url"]
                msg = f"🔔 {info['name']}: {old_val} ➔ {new_val} ({fark:+d})\n🔗 {url}"
                if p == "threads" and post_txt:
                    msg += f"\n\n📝 Son Gönderi:\n\"{post_txt[:300]}\""
                notify(msg)

        state[k] = new_val

    memory_state = state.copy()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

    return "\n".join(summary) if is_manual else None


def tracker_thread():
    while True:
        time.sleep(ARALIK)
        run_full_check(is_manual=False)


def bot_listener():
    last_id = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset": last_id + 1, "timeout": 20},
                timeout=25
            ).json()

            for item in resp.get("result", []):
                last_id = item["update_id"]
                msg = item.get("message", {})
                if str(msg.get("chat", {}).get("id")) == str(CHAT_ID):
                    text = msg.get("text", "").strip().lower()
                    if text in ["/kontrol", "kontrol"]:
                        notify("🔍 Sayfalar taranıyor...")
                        report = run_full_check(is_manual=True)
                        notify(f"📊 Canlı Durum:\n\n{report}")
                    elif text in ["/durum", "durum"]:
                        status = "\n".join(f"• {v['name']}: {memory_state.get(k, 'Kayıt yok')}" for k, v in TARGETS.items())
                        notify(f"📋 Kayıtlı Veriler:\n\n{status}")
        except Exception:
            time.sleep(2)
        time.sleep(0.5)


if __name__ == "__main__":
    notify("🚀 Takip Botu başlatıldı (Sessiz mod).")
    run_full_check(is_manual=False)
    threading.Thread(target=tracker_thread, daemon=True).start()
    bot_listener()
