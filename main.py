from datetime import datetime
import logging
import re
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
CHAT_ID = "6009524525"

# Son durumları sayısal / metinsel olarak takip etmek için
last_states = {
    "viewoo": None,
    "tik_1": None,
    "tik_2": None,
    "threadlook": None,
}

last_check_time = "Henüz kontrol yapılmadı"


def check_sites_logic(bot_instance):
  global last_states, last_check_time
  last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  logger.info(f"Siteler kontrol ediliyor... Zaman: {last_check_time}")

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      )
  }

  def send_msg(text):
    try:
      bot_instance.send_message(
          chat_id=CHAT_ID, text=text, parse_mode="Markdown"
      )
    except Exception as e:
      logger.error(f"Telegram mesajı gönderilemedi: {e}")

  # 1. Viewoo Kontrolü (Hikaye)
  try:
    url = "https://viewoo.co/u/sillagunerrr"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      page_text = res.text.lower()
      has_story = (
          "hikaye yok" not in page_text and "no story" not in page_text
      )
      if last_states["viewoo"] is None:
        last_states["viewoo"] = has_story
      elif last_states["viewoo"] != has_story:
        last_states["viewoo"] = has_story
        if has_story:
          send_msg(f"🔔 **Viewoo Güncellemesi!**\n{url}\n✨ **Yeni hikaye eklendi!**")
        else:
          send_msg(
              f"🔔 **Viewoo Güncellemesi!**\n{url}\n🗑️ **Hikaye kaldırıldı.**"
          )
  except Exception as e:
    logger.error(f"Viewoo hata: {e}")

  # 2. Tik.watch 1. Profil (Repost Sayısı)
  try:
    url = "https://tik.watch/tr/@sillagunerrr?tab=reposts"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      soup = BeautifulSoup(res.text, "html.parser")
      page_text = soup.get_text()

      # Sayfadaki sayıları veya repost belirten metinleri yakalama
      if last_states["tik_1"] is None:
        last_states["tik_1"] = page_text
      elif last_states["tik_1"] != page_text:
        last_states["tik_1"] = page_text
        send_msg(
            f"🔔 **Tik.watch 1 Güncellemesi!**\n{url}\n🔄 **Repost listesinde veya"
            " sayısında değişiklik oldu!**"
        )
  except Exception as e:
    logger.error(f"Tik.watch 1 hata: {e}")

  # 3. Tik.watch 2. Profil (Repost Sayısı)
  try:
    url = "https://tik.watch/tr/@userr44559014?tab=reposts"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      soup = BeautifulSoup(res.text, "html.parser")
      page_text = soup.get_text()

      if last_states["tik_2"] is None:
        last_states["tik_2"] = page_text
      elif last_states["tik_2"] != page_text:
        last_states["tik_2"] = page_text
        send_msg(
            f"🔔 **Tik.watch 2 Güncellemesi!**\n{url}\n🔄 **Repost listesinde veya"
            " sayısında değişiklik oldu!**"
        )
  except Exception as e:
    logger.error(f"Tik.watch 2 hata: {e}")

  # 4. Threadlook Kontrolü (Değer Tespiti)
  try:
    url = "https://threadlook.com/profile/sillagunerr"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 2
