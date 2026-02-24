# ==============================================================
# notifier.py – SmartDoor Telegram Notifier (FINAL v2.1)
# Digunakan oleh server.py untuk notifikasi sistem
# ==============================================================

import requests
import os
from datetime import datetime

# ==============================================================
# KONFIGURASI TELEGRAM
# ==============================================================

BOT_TOKEN = "7988607195:AAHMr7Dacs_xbL8P-W8vUKpJepoAqh-1av8"
ADMIN_CHAT_ID = 7856437512

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==============================================================
# LOGGING (SERVER SIDE)
# ==============================================================

BASE_DIR = os.getcwd()
LOG_FILE = os.path.join(BASE_DIR, "server_log.txt")

def log_event(msg: str):
    """
    Menulis log aktivitas notifier ke file server_log.txt
    Digunakan untuk audit pengiriman notifikasi.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[NOTIFIER_LOG_ERROR] {e}")

# ==============================================================
# KIRIM PESAN TEKS
# ==============================================================

def send_text(message: str) -> bool:
    """
    Mengirim pesan teks ke admin Telegram.
    Digunakan untuk notifikasi status sistem dan hasil pengenalan.
    """
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        log_event("[NOTIFIER] Token atau Chat ID belum dikonfigurasi")
        return False

    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json=payload,
            timeout=5
        )

        if r.status_code == 200:
            log_event("[NOTIFIER] Text notification sent")
            return True
        else:
            log_event(
                f"[NOTIFIER] Text send failed "
                f"(HTTP {r.status_code})"
            )
            return False

    except Exception as e:
        log_event(f"[NOTIFIER] Text send error: {e}")
        return False

# ==============================================================
# KIRIM FOTO + CAPTION
# ==============================================================

def send_photo(image_path: str, caption: str = "") -> bool:
    """
    Mengirim foto ke admin Telegram dengan caption.
    Digunakan untuk dokumentasi wajah dikenali, tidak dikenali,
    dan percobaan spoofing.
    """
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        log_event("[NOTIFIER] Token atau Chat ID belum dikonfigurasi")
        return False

    if not os.path.exists(image_path):
        log_event(f"[NOTIFIER] Image not found: {image_path}")
        return False

    try:
        with open(image_path, "rb") as img_file:
            files = {"photo": img_file}
            data = {
                "chat_id": ADMIN_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            }

            r = requests.post(
                f"{BASE_URL}/sendPhoto",
                data=data,
                files=files,
                timeout=10
            )

        if r.status_code == 200:
            log_event("[NOTIFIER] Photo notification sent")
            return True
        else:
            log_event(
                f"[NOTIFIER] Photo send failed "
                f"(HTTP {r.status_code})"
            )
            return False

    except Exception as e:
        log_event(f"[NOTIFIER] Photo send error: {e}")
        return False
