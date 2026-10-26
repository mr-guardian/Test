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

last_states = {
    "viewoo": None,
    "tik_1": None,
    "tik_2": None,
    "threadlook": None,
}

last_check_time = "Henüz kontrol yapılmadı"


def fetch_site_data():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      )
  }

  results = {}

  # 1. Viewoo
  try:
    res = requests.get(
        "https://viewoo.co/u/sillagunerrr", headers=headers, timeout=15
    )
    if res.status_code == 200:
      text = res.text.lower()
      results["viewoo"] = (
          "Hikaye Yok / Bulunamadı"
          if "hikaye yok" in text or "no story" in text
          else "Hikaye Var Olabilir!"
      )
    else:
      results["viewoo"] = f"Hata kod: {res.status_code}"
  except Exception as e:
    results["viewoo"] = f"Hata: {e}"

  # 2. Tik.watch 1
  try:
    res = requests.get(
        "https://tik.watch/tr/@sillagunerrr?tab=reposts",
        headers=headers,
        timeout=15,
    )
    if res.status_code == 200:
      soup = BeautifulSoup(res.text, "html.parser")
      # Sayfadaki tüm metni veya rakamları ayıkla
      nums = re.findall(r"\d+", soup.get_text())
      results["tik_1"] = (
          f"Bulunan ilk rakamlar: {nums[:5]}"
          if nums
          else "Rakam bulunamadı (Dinamik olabilir)"
      )
    else:
      results["tik_1"] = f"Hata kod: {res.status_code}"
  except Exception as e:
    results["tik_1"] = f"Hata: {e}"

  # 3. Tik.watch 2
  try:
    res = requests.get(
        "https://tik.watch/tr/@userr44559014?tab=reposts",
        headers=headers,
        timeout=15,
    )
    if res.status_code == 200:
      soup = BeautifulSoup(res.text, "html.parser")
      nums = re.findall(r"\d+", soup.get_text())
      results["tik_2"] = (
          f"Bulunan ilk rakamlar: {nums[:5]}"
          if nums
          else "Rakam bulunamadı (Dinamik olabilir)"
      )
    else:
      results["tik_2"] = f"Hata kod: {res.status_code}"
  except Exception as e:
    results["tik_2"] = f"Hata: {e}"

  # 4. Threadlook
  try:
    res = requests.get(
        "https://threadlook.com/profile/sillagunerr",
        headers=headers,
        timeout=15,
    )
    if res.status_code == 200:
      soup = BeautifulSoup(res.text, "html.parser")
      nums = re.findall(r"\b\d+\b", soup.get_text())
      results["threadlook"] = (
          f"Sayfada geçen sayılar: {nums[:10]}"
          if nums
          else "Sayı bulunamadı"
      )
    else:
      results["threadlook"] = f"Hata kod: {res.status_code}"
  except Exception as e:
    results["threadlook"] = f"Hata: {e}"

  return results


def check_sites_logic(bot_instance):
  global last_states, last_check_time
  last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  def send_msg(text):
    try:
      bot_instance.send_message(
          chat_id=CHAT_ID, text=text, parse_mode="Markdown"
      )
    except Exception as e:
      logger.error(f"Mesaj gönderilemedi: {e}")

  # Normal otomatik kontrol döngüsü buraya eklenebilir...


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text(
      "🔍 Siteler taranıyor ve analiz ediliyor..."
  )
  data = fetch_site_data()

  report = (
      f"📊 **Anlık Site Test Raporu**\n\n"
      f"✨ **Viewoo:** {data.get('viewoo')}\n"
      f"🔄 **Tik.watch (1):** {data.get('tik_1')}\n"
      f"🔄 **Tik.watch (2):** {data.get('tik_2')}\n"
      f"📌 **Threadlook:** {data.get('threadlook')}"
  )
  await update.message.reply_text(report, parse_mode="Markdown")


async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
  durum_metni = (
      f"🤖 **Bot Çalışıyor!**\n\n"
      f"⏱️ **Son Kontrol Zamanı:** `{last_check_time}`\n"
      f"💡 *Sitelerdeki anlık sayıları görmek için* `/test` *yazabilirsin.*"
  )
  await update.message.reply_text(durum_metni, parse_mode="Markdown")


def scheduled_job():
  temp_bot = Bot(token=TOKEN)
  # Otomatik kontroller burada çalışır


if __name__ == "__main__":
  scheduler = BackgroundScheduler()
  scheduler.add_job(scheduled_job, "interval", minutes=10)
  scheduler.start()

  app = ApplicationBuilder().token(TOKEN).build()
  app.add_handler(CommandHandler("test", cmd_test))
  app.add_handler(CommandHandler("durum", cmd_durum))

  logger.info("Test Komutlu Bot Aktif!")
  app.run_polling()
