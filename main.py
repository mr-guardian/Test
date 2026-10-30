import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup

TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
CHAT_ID = "6009524525"
ARALIK = 900  # 15 dakika
STATE_FILE = "state.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}

PAGES = {
    "sillagunerrr_story": {"type": "story", "name": "sillagunerrr Hikayeler", "url": "https://viewoo.co/u/sillagunerrr", "val": 0},
    "sillagunerrr_reposts": {"type": "repost", "name": "sillagunerrr Repostlar", "user": "sillagunerrr", "url": "https://viewoo.co/u/sillagunerrr?tab=reposts", "val": 6},
    "userr44559014_reposts": {"type": "repost", "name": "userr44559014 Repostlar", "user": "userr44559014", "url": "https://viewoo.co/u/userr44559014?tab=reposts", "val": 1},
    "emin_htp_reposts": {"type": "repost", "name": "emin_htp Repostlar", "user": "emin_htp", "url": "https://viewoo.co/u/emin_htp?tab=reposts", "val": 11},
    "sillagunerr_threads": {"type": "threads", "name": "sillagunerr Threads", "url": "https://threadlook.com/profile/sillagunerr", "val": 122}
}


def notify(text, photo=None):
    try:
        if photo:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", json={"chat_id": CHAT_ID, "photo": photo, "caption": text[:1024]}, timeout=10)
        else:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text[:4000]}, timeout=10)
    except Exception as e:
        print(f"[!] Bildirim iletilemedi: {e}")


def get_count(info, fallback):
    t = info["type"]
    try:
        if t == "repost":
            resp = requests.get(f"https://viewoo.co/api/reposts?username={info['user']}&_={int(time.time())}", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code} yanıtı alındı.")
            r = resp.json()
            return len(r) if isinstance(r, list) else len(r.get("items", r.get("reposts", []))) or fallback, None, None

        resp = requests.get(info["url"], headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} yanıtı alındı.")

        soup = BeautifulSoup(resp.text, "html.parser")

        if t == "story":
            items = soup.select("[data-story], [data-story-id], .story-item, a[href*='/story/']")
            img = items[0].select_one("img").get("src") if items and items[0].select_one("img") else None
            return len(items), img, None

        if t == "threads":
            post = soup.select_one(".thread-content, .post-content, article")
            post_txt = post.get_text().strip() if post else None
            m = re.findall(r'threads\s*[:\s]?\s*(\d+)', soup.get_text(), re.I)
            val = next((int(x) for x in m if int(x) not in (2025, 2026, 2027)), fallback)
            return val, None, post_txt

    except Exception as e:
        notify(f"⚠️ Erişim Hatası: {info['name']}\nNedeni: {e}\n🔗 Link: {info['url']}")
        return fallback, None, None


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
    state = {k: state.get(k, v["val"]) for k, v in PAGES.items()}

    print("[*] Bot aktif, değişiklikler ve erişim hataları Telegram'a iletilecek.")

    while True:
        for k, info in PAGES.items():
            old = state[k]
            new, photo, post_txt = get_count(info, old)

            if new != old:
                fark = new - old
                url = info["url"]
                msg = f"🔔 {info['name']}: {old} ➔ {new} ({fark:+d})\n🔗 {url}"
                if fark > 0 and post_txt:
                    msg += f"\n📝 Son Gönderi: \"{post_txt[:200]}\""

                notify(msg, photo if (fark > 0 and info["type"] == "story") else None)
                state[k] = new

                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f)

        time.sleep(ARALIK)


if __name__ == "__main__":
    main()
