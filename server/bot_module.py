# ============================================================== 
# bot_module.py – SmartDoor Telegram Bot (REGISTER v6.2 RESUME ✅)
# Improved: better error messages, lightweight retries, configurable SERVER_BASE
# ==============================================================

import os
import requests
import base64
import asyncio
import time
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

# ------------------ KONFIG (bisa override via ENV) ------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7988607195:AAHMr7Dacs_xbL8P-W8vUKpJepoAqh-1av8")
ADMIN_CHAT_ID  = int(os.environ.get("ADMIN_CHAT_ID", 7856437512))
SERVER_BASE    = os.environ.get("SERVER_BASE", "http://10.149.52.169:8000")  # IP SERVER

RASPI_START    = f"{SERVER_BASE}/raspi/register/start"
RASPI_STOP     = f"{SERVER_BASE}/raspi/register/stop"
RASPI_CAPTURE  = f"{SERVER_BASE}/raspi/register/capture"
SAVE_FACE      = f"{SERVER_BASE}/register/save"
FINALIZE_USER  = f"{SERVER_BASE}/register/finalize"

# ------------------ PARAMETER ------------------
ASK_NAME, RUN = range(2)

TOTAL_PHOTOS            = int(os.environ.get("TOTAL_PHOTOS", 15))
MAX_NOFACE_RETRIES      = int(os.environ.get("MAX_NOFACE_RETRIES", 10))
DELAY_BETWEEN_ATTEMPTS  = float(os.environ.get("DELAY_BETWEEN_ATTEMPTS", 3.0))
DELAY_BETWEEN_PHOTOS    = float(os.environ.get("DELAY_BETWEEN_PHOTOS", 3.0))

CAPTURE_TIMEOUT_SEC     = int(os.environ.get("CAPTURE_TIMEOUT_SEC", 15))
SAVE_TIMEOUT_SEC        = int(os.environ.get("SAVE_TIMEOUT_SEC", 20))
FINALIZE_TIMEOUT_SEC    = int(os.environ.get("FINALIZE_TIMEOUT_SEC", 90))
RASPI_CMD_TIMEOUT_SEC   = int(os.environ.get("RASPI_CMD_TIMEOUT_SEC", 12))

# ------------------ UTIL ------------------
def get_msg(update: Update):
    return update.message

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != ADMIN_CHAT_ID:
            await get_msg(update).reply_text("❌ Anda bukan admin.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper

def unwrap_raspi(resp_json: dict) -> dict:
    """Jika server membungkus hasil dari Raspi ke dalam kunci 'raspi', unwrap."""
    if isinstance(resp_json, dict) and "raspi" in resp_json and isinstance(resp_json["raspi"], dict):
        return resp_json["raspi"]
    return resp_json or {}

def http_get_json(url, timeout=15):
    """GET dengan JSON parsing + debug-friendly return."""
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except Exception as e:
            return {"ok": False, "error": f"invalid_json: {e}", "status_code": r.status_code, "text": r.text[:500]}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "error": f"conn_error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def http_post_json(url: str, payload: dict, timeout: int=10):
    """POST dengan JSON parsing + debug-friendly return."""
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except Exception as e:
            return {"success": False, "error": f"invalid_json: {e}", "status_code": r.status_code, "text": r.text[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def raspi_safe_stop():
    """Try to stop register mode on Raspi (best-effort)."""
    try:
        requests.get(RASPI_STOP, timeout=5)
    except:
        pass

# ------------------ HANDLERS ------------------
@admin_only
async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = get_msg(update)
    text = (msg.text or "").strip()
    args = text.split(maxsplit=1)

    context.user_data.clear()
    context.user_data["running"] = True
    context.user_data["photo_count"] = 0

    if len(args) > 1:
        name = args[1].strip()
        context.user_data["name"] = name
        await msg.reply_text(f"✅ Nama user: *{name}*", parse_mode="Markdown")
        await countdown_then_start(update, context)
        await auto_register_loop(update, context)
        return ConversationHandler.END
    else:
        await msg.reply_text("📝 Ketik nama user (balas pesan ini):")
        return ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_msg(update)
    name = (msg.text or "").strip()
    if not name:
        await msg.reply_text("⚠️ Nama tidak boleh kosong. Ketik lagi:")
        return ASK_NAME

    context.user_data["name"] = name
    await msg.reply_text(f"✅ Nama user: *{name}*", parse_mode="Markdown")
    await countdown_then_start(update, context)
    await auto_register_loop(update, context)
    return ConversationHandler.END

# -----------------------------------------------------------
async def countdown_then_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_msg(update)
    await msg.reply_text("🎯 Arahkan wajah ke kamera...\n3️⃣")
    await asyncio.sleep(1)
    await msg.reply_text("2️⃣")
    await asyncio.sleep(1)
    await msg.reply_text("1️⃣")
    await asyncio.sleep(1)

    msg_wait = await msg.reply_text("🔄 Mengaktifkan kamera dalam mode REGISTER...")
    # coba 2x start untuk robust
    tries = 0
    while tries < 2:
        tries += 1
        result = http_get_json(RASPI_START, timeout=RASPI_CMD_TIMEOUT_SEC)
        r = unwrap_raspi(result)

        # send debug info if not ok
        if not r.get("ok", False):
            # tampilkan JSON supaya kamu tahu kenapa gagal
            debug = r.copy()
            await msg_wait.edit_text(f"⚠️ START attempt {tries} gagal. Server returned: `{debug}`", parse_mode="Markdown")
            await asyncio.sleep(0.8)
            continue

        # ok
        await msg_wait.edit_text("📸 Kamera siap! Mode REGISTER aktif.")
        await asyncio.sleep(0.8)
        return

    # jika gagal semua
    await msg_wait.edit_text("⚠️ Kamera tidak merespon (START). Proses dibatalkan.\nPeriksa: IP Raspberry, service `/register/start` pada server, serta koneksi jaringan.")
    raise Exception("raspi_not_ready")

# -----------------------------------------------------------
async def auto_register_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_msg(update)
    name = context.user_data.get("name")
    if not name:
        await msg.reply_text("⚠️ Nama belum di-set. Batalkan.")
        await raspi_safe_stop()
        return

    photo_count = 0
    no_face_retries = 0

    try:
        while photo_count < TOTAL_PHOTOS and context.user_data.get("running", False):
            resp = http_get_json(RASPI_CAPTURE, timeout=CAPTURE_TIMEOUT_SEC)
            r = unwrap_raspi(resp)

            # debug: bila server returned error, tampilkan dan retry
            if not isinstance(r, dict):
                await msg.reply_text(f"⚠️ Capture response type unexpected: {r}")
                await asyncio.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            if r.get("ok") is False and r.get("error"):
                # contoh: {'ok': False, 'error': 'raspi_unreachable'}
                no_face_retries += 1
                await msg.reply_text(f"⚠️ Capture gagal: `{r.get('error')}` ({no_face_retries}/{MAX_NOFACE_RETRIES})", parse_mode="Markdown")
                if no_face_retries >= MAX_NOFACE_RETRIES:
                    await msg.reply_text("🚫 Kamera error berulang. Register batal.")
                    break
                await asyncio.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            # jika server mengembalikan no_face = True
            if r.get("no_face"):
                no_face_retries += 1
                await msg.reply_text(f"⚠️ Tidak terlihat wajah. Coba lagi ({no_face_retries}/{MAX_NOFACE_RETRIES})...")
                if no_face_retries >= MAX_NOFACE_RETRIES:
                    await msg.reply_text("🚫 Tetap tidak terlihat wajah. Register batal.")
                    break
                await asyncio.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            img_b64 = r.get("image")
            if not img_b64:
                no_face_retries += 1
                await msg.reply_text(f"⚠️ Frame kosong ({no_face_retries}/{MAX_NOFACE_RETRIES})...")
                if no_face_retries >= MAX_NOFACE_RETRIES:
                    await msg.reply_text("🚫 Frame kosong berulang. Register batal.")
                    break
                await asyncio.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            # success capture
            no_face_retries = 0
            photo_count += 1
            context.user_data["photo_count"] = photo_count

            # try show preview (bisa fail kalau file besar)
            try:
                await msg.reply_photo(
                    photo=base64.b64decode(img_b64),
                    caption=f"📷 Foto {photo_count}/{TOTAL_PHOTOS} - {name}"
                )
            except Exception:
                await msg.reply_text(f"ℹ️ Preview gagal (Foto {photo_count}). Lanjut simpan.")

            # simpan ke server (2 attempts)
            saved = False
            for attempt in range(2):
                res = http_post_json(SAVE_FACE, {"name": name, "image": img_b64}, timeout=SAVE_TIMEOUT_SEC)
                if res.get("success"):
                    saved = True
                    break
                await asyncio.sleep(1.0)

            if not saved:
                await msg.reply_text(f"⚠️ Gagal simpan foto {photo_count}. Ulangi...")
                photo_count -= 1
                await asyncio.sleep(DELAY_BETWEEN_ATTEMPTS)
                continue

            if photo_count < TOTAL_PHOTOS:
                await asyncio.sleep(DELAY_BETWEEN_PHOTOS)

        # -----------------------------------------------------------
        # Embedding finalisasi
        # -----------------------------------------------------------
        if photo_count >= TOTAL_PHOTOS:
            await msg.reply_text("✅ Semua foto terkumpul!\n🧠 Membuat embedding...")
            res = http_post_json(FINALIZE_USER, {"name": name}, timeout=FINALIZE_TIMEOUT_SEC)

            if res.get("success"):
                await msg.reply_text(f"🏁 *{name}* berhasil didaftarkan ✅", parse_mode="Markdown")

                # aktifkan kembali FSM Liveness (stop register mode di Raspi)
                await msg.reply_text("🔓 Mengaktifkan kembali sistem SmartDoor (Liveness ON)...")
                result = http_get_json(RASPI_STOP, timeout=RASPI_CMD_TIMEOUT_SEC)
                r = unwrap_raspi(result)
                if r.get("ok", False):
                    await msg.reply_text("✅ FSM liveness kembali aktif.")
                else:
                    await msg.reply_text(f"⚠️ Gagal aktifkan FSM kembali. Server returned: `{r}`", parse_mode="Markdown")
            else:
                await msg.reply_text(f"⚠️ Embedding gagal: `{res}`", parse_mode="Markdown")
        else:
            await msg.reply_text("⏹️ Register dihentikan.")

    finally:
        context.user_data["running"] = False

@admin_only
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_msg(update)
    context.user_data["running"] = False
    await raspi_safe_stop()
    await msg.reply_text("❌ Register dibatalkan.")
    return ConversationHandler.END

# ------------------ START BOT ------------------
def start_bot():
    print("[BOT] Telegram bot polling...")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("register", cmd_register)],
        states={ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=False,
        per_chat=True,
    )

    app.add_handler(conv)
    loop.run_until_complete(app.run_polling(stop_signals=None))
