from datetime import datetime
import logging
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg"
CHAT_ID = "6009524525"

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

  # 1. Viewoo Kontrolü
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
          send_msg(f"🔔 **Viewoo Güncellemesi!**\n{url}\n✨ Yeni hikaye eklendi!")
        else:
          send_msg(f"🔔 **Viewoo Güncellemesi!**\n{url}\n🗑️ Hikaye kaldırıldı.")
  except Exception as e:
    logger.error(f"Viewoo hata: {e}")

  # 2. Tik.watch 1. Profil
  try:
    url = "https://tik.watch/tr/@sillagunerrr?tab=reposts"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      page_text = res.text
      if last_states["tik_1"] is None:
        last_states["tik_1"] = page_text
      elif last_states["tik_1"] != page_text:
        last_states["tik_1"] = page_text
        send_msg(
            f"🔔 **Tik.watch 1 Güncellemesi!**\n{url}\n🔄 Değişiklik algılandı!"
        )
  except Exception as e:
    logger.error(f"Tik.watch 1 hata: {e}")

  # 3. Tik.watch 2. Profil
  try:
    url = "https://tik.watch/tr/@userr44559014?tab=reposts"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      page_text = res.text
      if last_states["tik_2"] is None:
        last_states["tik_2"] = page_text
      elif last_states["tik_2"] != page_text:
        last_states["tik_2"] = page_text
        send_msg(
            f"🔔 **Tik.watch 2 Güncellemesi!**\n{url}\n🔄 Değişiklik algılandı!"
        )
  except Exception as e:
    logger.error(f"Tik.watch 2 hata: {e}")

  # 4. Threadlook Kontrolü
  try:
    url = "https://threadlook.com/profile/sillagunerr"
    res = requests.get(url, headers=headers, timeout=15)
    if res.status_code == 200:
      page_text = res.text
      has_119 = "119" in page_text
      if last_states["threadlook"] is None:
        last_states["threadlook"] = has_119
      elif last_states["threadlook"] != has_119:
        last_states["threadlook"] = has_119
        send_msg(
            f"🔔 **Threadlook Güncellemesi!**\n{url}\n⚠️ 119 değerinde değişiklik"
            " oldu!"
        )
  except Exception as e:
    logger.error(f"Threadlook hata: {e}")


async def cmd_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🔍 Siteler kontrol ediliyor...")
  check_sites_logic(context.bot)
  await update.message.reply_text("✅ Kontrol tamamlandı!")


async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
  durum_metni = (
      f"🤖 **Bot Çalışıyor!**\n\n"
      f"⏱️ **Son Kontrol:** `{last_check_time}`\n"
      f"📡 **Siteler:**\n"
      f"• Viewoo\n"
      f"• Tik.watch (1)\n"
      f"• Tik.watch (2)\n"
      f"• Threadlook"
  )
  await update.message.reply_text(durum_metni, parse_mode="Markdown")


def scheduled_job():
  temp_bot = Bot(token=TOKEN)
  check_sites_logic(temp_bot)


if __name__ == "__main__":
  scheduler = BackgroundScheduler()
  scheduler.add_job(scheduled_job, "interval", minutes=10)
  scheduler.start()

  app = ApplicationBuilder().token(TOKEN).build()
  app.add_handler(CommandHandler("kontrol", cmd_kontrol))
  app.add_handler(CommandHandler("durum", cmd_durum))

  logger.info("Bot Aktif ve Çalışıyor!")
  app.run_polling()
