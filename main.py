import json
import os
import re
import threading
import time
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
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
          [{"text": "🔬 Sayfa Röntgeni (Bana Bas)", "callback_data": "btn_debug"}],
      ]
  }


def send_telegram_message(text, reply_markup=None):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    return
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": text[:4000],  # Telegram karakter sınırı koruması
      "disable_notification": SILENT_MODE,
  }
  if reply_markup:
    payload["reply_markup"] = reply_markup
  try:
    requests.post(url, json=payload, timeout=10)
  except Exception as e:
    print(f"[!] Gönderim hatası: {e}")


def fetch_url(url):
  try:
    if IS_CLOUDSCRAPER:
      return HTTP_CLIENT.get(url, timeout=12)
    return requests.get(url, headers=HEADERS, timeout=12)
  except Exception:
    return None


def run_debug_xray():
  """Viewoo sayfasının iç yapısını çözüp Telegram'a raporlar."""
  target_url = "https://viewoo.co/u/emin_htp?tab=reposts"
  resp = fetch_url(target_url)

  if not resp:
    send_telegram_message("❌ Siteye hiç ulaşılamadı (Response None).")
    return

  html = resp.text
  soup = BeautifulSoup(html, "html.parser")

  # 1. Tüm class isimlerini topla
  classes = set()
  for el in soup.find_all(class_=True):
    for c in el.get("class", []):
      classes.add(c)

  # 2. Script ve API ipuçlarını topla
  scripts_info = []
  for s in soup.find_all("script"):
    src = s.get("src", "")
    if src:
      scripts_info.append(f"SRC: {src}")
    elif s.string:
      snippet = s.string.strip()[:120].replace("\n", " ")
      scripts_info.append(f"INLINE: {snippet}...")

  # 3. İçinde 'repost', 'api', 'video', 'item', 'card', 'count' geçen satırları yakala
  keywords_found = re.findall(
      r".{0,40}(?:repost|api|secUid|itemList|video|count).{0,40}",
      html,
      re.IGNORECASE,
  )
  sample_matches = list(set(keywords_found))[:15]

  visible_text = re.sub(r"\s+", " ", soup.get_text()).strip()[:400]

  report = (
      "🔬 SAYFA RÖNTGENİ RAPORU\n"
      f"Durum Kodu: {resp.status_code}\n"
      f"HTML Boyutu: {len(html)} karakter\n\n"
      f"📌 Görünen Metin:\n{visible_text}\n\n"
      f"🏷 Bulunan Class'lar (İlk 30):\n{', '.join(list(classes)[:30])}\n\n"
      "📜 Scriptler:\n"
      + "\n".join(scripts_info[:8])
      + "\n\n"
      "🔑 Kod İçi İpuçları:\n"
      + "\n".join(sample_matches)
  )

  send_telegram_message(report, reply_markup=get_inline_keyboard())


def check_page_count(page_info, current_state_val=0):
  url = page_info["url"]
  p_type = page_info["type"]
  default_val = page_info.get("default_val", 0)

  try:
    resp = fetch_url(url)
    if not resp or resp.status_code != 200:
      return current_state_val if current_state_val > 0 else default_val

    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text()
    text_lower = text.lower()

    if p_type == "viewoo_reposts":
      tiktok_ids = set(re.findall(r"\b7\d{18}\b", html_text))
      if tiktok_ids:
        return len(tiktok_ids)
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

    return current_state_val if current_state_val > 0 else default_val
  except Exception:
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
    send_telegram_message("🔎 Sayfalar taranıyor...")
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

  elif callback_data == "btn_debug":
    send_telegram_message(
        "🔬 Sayfa röntgeni çekiliyor, lütfen 3 saniye bekle..."
    )
    run_debug_xray()


def handle_message(text, chat_id):
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
  print("Master Takip Botu Başlatıldı...")

  current_state = load_state()
  for key, info in PAGES.items():
    if key not in current_state:
      current_state[key] = info.get("default_val", 0)
  save_state(current_state)

  t = threading.Thread(target=listen_telegram, daemon=True)
  t.start()

  send_telegram_message(
      "🚀 Bot Başlatıldı! Röntgen butonuna basarak sayfa yapısını"
      " çözebiliriz:",
      reply_markup=get_inline_keyboard(),
  )

  while True:
    run_check()
    time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
  main()
