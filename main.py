#!/usr/bin/env python3
"""
Master Takip ve Yönetim Botu
(Easycomment, Tikvib ve Threadlook Destekli - Railway Uyumlu)
"""

import os
import re
import time
import json
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Cloudscraper varsa korumaları aşmak için kullanılır
try:
    import cloudscraper
    HTTP_CLIENT = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    print("[*] Cloudscraper aktif: Cloudflare korumaları otomatik aşılacak.")
except Exception:
    HTTP_CLIENT = requests.Session()
    print("[*] Standart requests oturumu aktif.")

# ==========================================
# 1. BİLDİRİM VE BOT AYARLARI
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8902458393:AAFbMG-7nAuIFnBdWsBw5xilDiUCetSkSEg")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL_SECONDS = 900  # 15 dakika
IS_TRACKING_PAUSED = False
SILENT_MODE = False

STATE_FILE = "tracker_state.json"
HISTORY_FILE = "tracker_history.json"
CONFIG_FILE = "tracker_config.json"

DEFAULT_PAGES = {
    "sillagunerrr_story": {
        "url": "https://www.tikvib.com/story/sillagunerrr",
        "name": "sillagunerrr Hikayeler",
        "type": "tikvib_story"
    },
    "sillagunerrr_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=sillagunerrr&tab=reposts",
        "name": "sillagunerrr Repostlar",
        "type": "easycomment_reposts"
    },
    "userr44559014_reposts": {
        "url": "https://easycomment.ai/tiktok/user?viewer=account&username=userr44559014&tab=reposts",
        "name": "userr44559014 Repostlar",
        "type": "easycomment_reposts"
    },
    "sillagunerr_threads": {
        "url": "https://threadlook.com/profile/sillagunerr",
        "name": "sillagunerr Threads",
        "type": "threads"
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1"
}

LAST_ERRORS = {}


def load_pages() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                updated = False
                for target_key in ["sillagunerrr_reposts", "userr44559014_reposts"]:
                    if target_key in data and "tikvib.com" in data[target_key].get("url", ""):
                        data[target_key] = DEFAULT_PAGES[target_key]
                        updated = True

                if updated:
                    save_pages(data)
                return data
        except Exception:
            pass
    return DEFAULT_PAGES.copy()


def save_pages(pages: dict):
    with
