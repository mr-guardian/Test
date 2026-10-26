from datetime import datetime
import json
import os
import re
import threading
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests

try:
  import cloudscraper

  HTTP_CLIENT = cloudscraper.create_scraper(
      browser={"browser": "chrome", "platform": "windows", "desktop": True}
  )
  IS_CLOUDSCRAPER = True
except Exception:
  HTTP_CLIENT = requests.Session()
  IS_CLOUDSCRAPER = False

TELEGRAM_BOT_TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
TELEGRAM_CHAT_ID = "6009524525"

CHECK_INTERVAL_SECONDS = 900  # 15 dakikada bir kontrol
STATE_FILE = "tracker_state.json"

PAGES = {
    "sillagunerrr_story": {
        "url": "https://viewoo.co/u/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "story",
    },
    "sillagunerrr_reposts": {
        "url": "sillagunerrr",
        "name": "sillagunerrr Repostlar",
        "type": "api_reposts",
    },
    "userr44559014_reposts": {
        "url": "userr44559014",
        "name": "userr44559014 Repostlar",
        "type": "api_reposts",
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,application/xhtml+xml,*/*",
}


def send_telegram_message(text):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    return
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": text,
      "parse_mode": "Markdown",
  }
  try:
    requests.post(url, json=payload, timeout=15)
  except Exception as e:
    print(f"[!] Gönderim hatası: {e}")


def check_page_count(page_info):
  url_or_user = page_info["url"]
  p_type = page_info["type"]
  try:
    # 1. API Üzerinden Repost Sayımı (POST isteği ile hatasız çekim)
    if p_type == "api_reposts":
      api_url = "https://tikwm.com/api/user/posts"
      payload = {"unique_id": url_or_user, "count": 35}
      resp = requests.post(api_url, data=payload, headers=HEADERS, timeout=15)
      if resp.status_code == 200:
        data = resp.json()
        if data.get("code") == 0:
          videos = data.get("data", {}).get("videos", [])
          return len(videos)
      return 0

    # Diğer siteler için standart GET
    if IS_CLOUDSCRAPER:
      resp = HTTP_CLIENT.get(url_or_user, timeout=25)
    else:
      resp = requests.get(url_or_user, headers=HEADERS, timeout=25)

    if not resp or resp.status_code != 200:
      return 0

    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text()
    text_lower = text.lower()

    # 2. Hikaye Sayımı
    if p_type == "story":
      empty_phrases = (
          "user has no stories",
          "no stories",
          "no active stories",
          "hikaye yok",
          "0 stories",
      )
      if any(p in text_lower for p in empty_phrases):
        return 0

      story_items = soup.select(
          "[data-story], [data-story-id], .story-item, a[href*='/story/']"
      )
      story_items = [
          el
          for el in story_items
          if "story-viewer" not in (el.get("href") or "").lower()
      ]
      if story_items:
        return len(set(str(el) for el in story_items))

      if bool(soup.find_all("video")) or "data-story" in html_text.lower():
        return 1
      return 0

    # 3. Threads Sayımı
    elif p_type == "threads":
      matches = re.findall(r"THREADS\s*(\d+)", text, re.IGNORECASE)
      if matches:
        return int(matches[0])
      matches_alt = re.findall(r"(\d+)\s*threads", text, re.IGNORECASE)
      if matches_alt:
        return int(matches_alt[0])

      numbers = [int(n) for n in re.findall(r"\b\d+\b", text) if len(n) <= 4]
      if numbers:
        return max(numbers)

    return 0
  except Exception:
    return 0


def load_state():
  if os.path.exists(STATE_FILE):
    try:
      with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return {}


def save_state(state):
  with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)


def run_check():
  current_state = load_state()
  changes = []

  for key, info in PAGES.items():
    count = check_page_count(info)
    old_count = current_state.get(key, count)
    if current_state.get(key) is None:
      current_state[key] = count
      continue

    if count != old_count:
      fark = count - old_count
      changes.append(
          f"• *{info['name']}*: `{old_count}` ➔ `{count}` ({fark:+d})"
      )
      current_state[key] = count

  save_state(current_state)

  if changes:
    msg = "🔔 *İçerik Değişikliği Algılandı!*\n\n" + "\n".join(changes)
    send_telegram_message(msg)


def listen_telegram():
  last_update_id = 0
  print("[*] Telegram komut dinleyici aktif.")
  while True:
    try:
      url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
      r = requests.get(url, params={"offset": last_update_id + 1, "timeout": 20})
      resp = r.json()

      for item in resp.get("result", []):
        last_update_id = item["update_id"]
        msg = item.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id != TELEGRAM_CHAT_ID:
          continue

        if text in ["/durum", "📊 Durum", "/kontrol"]:
          current_state = load_state()
          lines = ["📑 *Takip Edilen Sayfalar:*\n"]
          for key, info in PAGES.items():
            val = check_page_count(info)
            current_state[key] = val
            c = current_state.get(key, 0)
            lines.append(f"• *{info['name']}*: `{c}`")
          save_state(current_state)
          send_telegram_message("\n".join(lines))

    except Exception:
      time.sleep(5)
    time.sleep(1)


def main():
  print("Master Takip Botu Başlatıldı...")
  t = threading.Thread(target=listen_telegram, daemon=True)
  t.start()

  current_state = load_state()
  for key, info in PAGES.items():
    if key not in current_state:
      current_state[key] = check_page_count(info)
  save_state(current_state)

  while True:
    run_check()
    time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
  main()
