from datetime import datetime
import json
import os
import re
import threading
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests

TELEGRAM_BOT_TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
TELEGRAM_CHAT_ID = "6009524525"

CHECK_INTERVAL_SECONDS = 900
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"

PAGES = {
    "sillagunerrr_story": {
        "url": "https://viewoo.co/u/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "story",
    },
    "sillagunerrr_reposts": {
        "url": "https://viewoo.co/u/sillagunerrr?tab=reposts",
        "name": "sillagunerrr Repostlar",
        "type": "viewoo_reposts",
        "default_val": 5,
    },
    "userr44559014_reposts": {
        "url": "https://viewoo.co/u/userr44559014?tab=reposts",
        "name": "userr44559014 Repostlar",
        "type": "viewoo_reposts",
        "default_val": 1,
    },
    "emin_htp_reposts": {
        "url": "https://viewoo.co/u/emin_htp?tab=reposts",
        "name": "emin_htp Repostlar",
        "type": "viewoo_reposts",
        "default_val": 0,
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads",
    },
}


def get_inline_keyboard():
  return {
      "inline_keyboard": [
          [
              {"text": "📊 Durum", "callback_data": "btn_durum"},
              {"text": "🔍 Canlı Kontrol", "callback_data": "btn_kontrol"},
          ],
          [
              {"text": "🔗 Sayfalar", "callback_data": "btn_sayfalar"},
              {"text": "🔕 Sessiz Mod", "callback_data": "btn_sessiz"},
          ],
          [
              {"text": "⏸ Durdur", "callback_data": "btn_durdur"},
              {"text": "▶️ Başlat", "callback_data": "btn_baslat"},
          ],
      ]
  }


def send_telegram_message(text, reply_markup=None):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    return
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": text,
      "disable_notification": SILENT_MODE,
  }
  if reply_markup:
    payload["reply_markup"] = reply_markup
  try:
    requests.post(url, json=payload, timeout=10)
  except Exception as e:
    print(f"[!] Gönderim hatası: {e}")


def check_page_count(page_info, current_state_val=0):
  url = page_info["url"]
  p_type = page_info["type"]
  default_val = page_info.get("default_val", 0)

  try:
    with sync_playwright() as p:
      browser = p.chromium.launch(
          headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
      )
      page = browser.new_page(
          user_agent=(
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
          )
      )
      page.goto(url, timeout=40000)
      page.wait_for_timeout(
          4000
      )  # JavaScript verilerinin yüklenmesi için bekleme

      text = page.evaluate("document.body.innerText")
      text_lower = text.lower()
      content = page.content()

      if p_type == "viewoo_reposts":
        # 1. Sekme üzerindeki veya yazılardaki repost sayısını ara (Örn: "Reposts 5")
        match_tab = re.search(
            r"reposts?\s*[\(\:]?\s*(\d+)", text_lower, re.IGNORECASE
        )
        if match_tab:
          browser.close()
          return int(match_tab.group(1))

        # 2. JavaScript ile sayfadaki repost sekmesi veya sayaç elementlerini tara
        count_val = page.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('a, button, div, span, .badge, .count'));
                    for (let el of elements) {
                        if (el.innerText && el.innerText.toLowerCase().includes('repost')) {
                            const match = el.innerText.match(/\\d+/);
                            if (match) return parseInt(match[0]);
                        }
                    }
                    return null;
                """)
        if count_val is not None:
          browser.close()
          return count_val

        # 3. Sayfadaki yüklenen video/repost kartlarını say
        cards_count = page.locator(
            "div.posts__video-item, .video-card, .post-card, a[href*='/video/']"
        ).count()
        browser.close()
        if cards_count > 0:
          return cards_count

        browser.close()
        return current_state_val if current_state_val > 0 else default_val

      elif p_type == "story":
        empty_phrases = (
            "user has no stories",
            "no stories",
            "no active stories",
            "hikaye yok",
            "0 stories",
        )
        if any(p in text_lower for p in empty_phrases):
          browser.close()
          return 0

        story_count = page.locator(
            "[data-story], [data-story-id], .story-item, a[href*='/story/']"
        ).count()
        has_video = page.locator("video").count() > 0
        browser.close()

        if story_count > 0:
          return story_count
        if has_video or "data-story" in content.lower():
          return 1
        return 0

      elif p_type == "threads":
        matches = re.findall(r"THREADS\s*(\d+)", text, re.IGNORECASE)
        browser.close()
        if matches:
          return int(matches[0])
        matches_alt = re.findall(r"(\d+)\s*threads", text, re.IGNORECASE)
        if matches_alt:
          return int(matches_alt[0])

        numbers = [int(n) for n in re.findall(r"\b\d+\b", text) if len(n) <= 4]
        if numbers:
          return max(numbers)

      browser.close()
      return current_state_val if current_state_val > 0 else default_val
  except Exception as e:
    print(f"[!] Playwright tarama hatası: {e}")
    return current_state_val if current_state_val > 0 else default_val


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
  global IS_TRACKING_PAUSED
  if IS_TRACKING_PAUSED:
    return

  current_state = load_state()
  changes = []

  for key, info in PAGES.items():
    old_val = current_state.get(key, -1)
    count = check_page_count(info, current_state_val=old_val)

    if old_val == -1:
      current_state[key] = count
      continue

    if count != old_val:
      fark = count - old_val
      changes.append(f"• {info['name']}: {old_val} ➔ {count} ({fark:+d})")
      current_state[key] = count

  save_state(current_state)

  if changes:
    msg = "🔔 İçerik Değişikliği Algılandı!\n\n" + "\n".join(changes)
    send_telegram_message(msg, reply_markup=get_inline_keyboard())


def handle_callback(callback_data, chat_id):
  global CHECK_INTERVAL_SECONDS, IS_TRACKING_PAUSED, SILENT_MODE

  if callback_data == "btn_durum":
    current_state = load_state()
    lines = ["📑 Takip Edilen Sayfalar:\n"]
    for key, info in PAGES.items():
      val = current_state.get(key, info.get("default_val", 0))
      lines.append(f"• {info['name']}: {val}")
    send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())

  elif callback_data == "btn_kontrol":
    send_telegram_message("🔎 Sayfalar taranıyor (Tarayıcı motoru aktif)...")
    run_check()
    send_telegram_message(
        "✅ Canlı kontrol tamamlandı.", reply_markup=get_inline_keyboard()
    )

  elif callback_data == "btn_sayfalar":
    links = ["🔗 Takip Edilen Sayfalar:"]
    for k, inf in PAGES.items():
      links.append(f"• {inf['name']}: {inf['url']}")
    send_telegram_message("\n".join(links), reply_markup=get_inline_keyboard())

  elif callback_data == "btn_durdur":
    IS_TRACKING_PAUSED = True
    send_telegram_message(
        "⏸ Otomatik takip duraklatıldı.", reply_markup=get_inline_keyboard()
    )

  elif callback_data == "btn_baslat":
    IS_TRACKING_PAUSED = False
    send_telegram_message(
        "▶️ Otomatik takip başlatıldı!", reply_markup=get_inline_keyboard()
    )

  elif callback_data == "btn_sessiz":
    SILENT_MODE = not SILENT_MODE
    durum = "AÇIK (Sessiz)" if SILENT_MODE else "KAPALI (Sesli)"
    send_telegram_message(
        f"🔕 Sessiz mod: {durum}", reply_markup=get_inline_keyboard()
    )


def handle_message(text, chat_id):
  global CHECK_INTERVAL_SECONDS, IS_TRACKING_PAUSED, SILENT_MODE

  if str(chat_id) != str(TELEGRAM_CHAT_ID):
    return

  text_clean = text.strip().lower()

  if "durum" in text_clean or text_clean == "/durum":
    current_state = load_state()
    lines = ["📑 Takip Edilen Sayfalar:\n"]
    for key, info in PAGES.items():
      val = current_state.get(key, info.get("default_val", 0))
      lines.append(f"• {info['name']}: {val}")
    send_telegram_message("\n".join(lines), reply_markup=get_inline_keyboard())
    return

  if text_clean in ["/start", "/yardim", "anasayfa"]:
    send_telegram_message(
        "👋 Bot aktif! Yönetmek için aşağıdaki butonları kullanabilirsin:",
        reply_markup=get_inline_keyboard(),
    )


def listen_telegram():
  try:
    requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True",
        timeout=10,
    )
  except Exception:
    pass

  last_update_id = 0
  print("[*] Telegram tarayıcı tabanlı dinleyici devrede.")

  while True:
    try:
      resp = requests.get(
          f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
          params={"offset": last_update_id + 1, "timeout": 20, "limit": 10},
          timeout=25,
      ).json()

      if resp.get("ok"):
        for item in resp.get("result", []):
          last_update_id = item["update_id"]

          msg = item.get("message", {})
          text = msg.get("text", "").strip()
          chat_id = str(msg.get("chat", {}).get("id", ""))
          if text and chat_id:
            handle_message(text, chat_id)

          callback_query = item.get("callback_query")
          if callback_query:
            cb_data = callback_query.get("data")
            cb_chat_id = str(
                callback_query.get("message", {}).get("chat", {}).get("id", "")
            )
            cb_id = callback_query.get("id")
            try:
              requests.post(
                  f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": cb_id},
                  timeout=5,
              )
            except Exception:
              pass

            if cb_data and cb_chat_id == str(TELEGRAM_CHAT_ID):
              handle_callback(cb_data, cb_chat_id)

    except Exception as e:
      print(f"[!] Dinleme hatası: {e}")
      time.sleep(3)

    time.sleep(0.5)


def main():
  print("Tarayıcı Tabanlı Master Takip Botu Başlatıldı...")

  current_state = load_state()
  for key, info in PAGES.items():
    if key not in current_state:
      current_state[key] = info.get("default_val", 0)
  save_state(current_state)

  t = threading.Thread(target=listen_telegram, daemon=True)
  t.start()

  send_telegram_message(
      "🚀 Bot Tarayıcı Modunda Başlatıldı! Kontrol paneli:",
      reply_markup=get_inline_keyboard(),
  )

  while True:
    run_check()
    time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
  main()
