# ==============================================================
# SmartDoor Server – FINAL v5.3
# Fokus: Clear Logging, Adaptive Threshold, Academic-Safe
# ==============================================================

from flask import Flask, request, jsonify
import os, io, base64, threading, time, cv2
import numpy as np
import face_recognition
from datetime import datetime
from notifier import send_text, send_photo
from bot_module import start_bot
from PIL import Image

# --------------------------------------------------------------
# INIT
# --------------------------------------------------------------
app = Flask(__name__)

BASE_DIR   = os.getcwd()
FACES_DIR  = os.path.join(BASE_DIR, "faces")
EMB_DIR    = os.path.join(BASE_DIR, "embeddings")
LOG_DIR    = os.path.join(BASE_DIR, "logs")
LOG_FILE   = os.path.join(BASE_DIR, "server_log.txt")

RASPI_BASE = "http://10.149.52.55:5000"

os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(EMB_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------
def log_event(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# --------------------------------------------------------------
# TELEGRAM (ASYNC / AUDIT ONLY)
# --------------------------------------------------------------
def async_photo(path, caption):
    threading.Thread(
        target=send_photo,
        args=(path, caption),
        daemon=True
    ).start()

def async_text(message):
    threading.Thread(
        target=send_text,
        args=(message,),
        daemon=True
    ).start()

# --------------------------------------------------------------
# EMBEDDING CACHE
# --------------------------------------------------------------
EMB_CACHE = {}
EMB_LASTLOAD = 0
LOCK = threading.Lock()

def load_embeddings(force=False):
    global EMB_CACHE, EMB_LASTLOAD
    now = time.time()

    with LOCK:
        if not force and EMB_CACHE and (now - EMB_LASTLOAD < 300):
            return EMB_CACHE

        EMB_CACHE.clear()
        for f in os.listdir(EMB_DIR):
            if f.endswith(".npy"):
                try:
                    arr = np.load(os.path.join(EMB_DIR, f))
                    if arr.shape == (128,):
                        EMB_CACHE[os.path.splitext(f)[0]] = arr
                except:
                    pass

        EMB_LASTLOAD = now
        log_event(f"[EMBEDDING] Loaded {len(EMB_CACHE)} embeddings")

    return EMB_CACHE

def embedding_auto_refresh():
    while True:
        try:
            load_embeddings(force=True)
        except Exception as e:
            log_event(f"[EMBEDDING] Auto-refresh error: {e}")
        time.sleep(300)

# --------------------------------------------------------------
# FAST FACE ENCODING
# --------------------------------------------------------------
def get_largest_face_encoding_fast(image):
    h, w, _ = image.shape
    small = cv2.resize(image, (int(w * 0.75), int(h * 0.75)))
    boxes = face_recognition.face_locations(small)

    if not boxes:
        return None, None

    sh, sw = small.shape[:2]
    scale_y, scale_x = h / sh, w / sw

    boxes = [
        (int(t*scale_y), int(r*scale_x),
         int(b*scale_y), int(l*scale_x))
        for t, r, b, l in boxes
    ]

    areas = [(b - t) * (r - l) for t, r, b, l in boxes]
    idx = int(np.argmax(areas))

    enc = face_recognition.face_encodings(image, [boxes[idx]])[0]
    return enc, boxes[idx]

# --------------------------------------------------------------
# ADAPTIVE THRESHOLD
# --------------------------------------------------------------
THRESHOLD_BASE = 0.38
THRESHOLD_MINMAX = (0.34, 0.46)
DIST_HISTORY = []

def adjust_threshold():
    global THRESHOLD_BASE
    if not DIST_HISTORY:
        return THRESHOLD_BASE

    avg = float(np.mean(DIST_HISTORY[-20:]))
    THRESHOLD_BASE = float(np.clip(avg + 0.04, *THRESHOLD_MINMAX))
    return THRESHOLD_BASE

# --------------------------------------------------------------
# FACE RECOGNITION ENDPOINT
# --------------------------------------------------------------
@app.route("/recognize", methods=["POST"])
def recognize():
    try:
        data = request.json or {}
        image_b64 = data.get("image")
        status = (data.get("status") or "live").lower()

        if not image_b64:
            return jsonify({"recognized": False}), 400

        img = np.array(
            Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
        )

        # ======================================================
        # PHASE 1 – RECEIVE
        # ======================================================
        log_event("[RECEIVE] Image received from Raspberry Pi")

        # ======================================================
        # LIVENESS FAIL
        # ======================================================
        if status == "fail":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(LOG_DIR, f"spoof_{ts}.jpg")
            Image.fromarray(img).save(path)

            log_event("[SECURITY] Liveness failed → access denied")

            async_photo(
                path,
                "🚨 <b>Upaya spoofing terdeteksi</b>\nAkses ditolak."
            )

            return jsonify({"recognized": False}), 200

        # ======================================================
        # PHASE 2 – DECISION
        # ======================================================
        embeddings = load_embeddings()
        if not embeddings:
            log_event("[DECISION] No embeddings available")
            return jsonify({"recognized": False, "name": "unknown"})

        enc, _ = get_largest_face_encoding_fast(img)
        if enc is None:
            log_event("[DECISION] No face detected")
            return jsonify({"recognized": False, "name": "unknown"})

        names = list(embeddings.keys())
        vectors = np.stack(list(embeddings.values()))
        dists = np.linalg.norm(vectors - enc, axis=1)

        idx = int(np.argmin(dists))
        best_name = names[idx]
        D = float(dists[idx])
        T = adjust_threshold()

        recognized = D < T
        jam = datetime.now().strftime("%H:%M:%S")

        log_event(
            f"[DECISION] name={best_name if recognized else 'UNKNOWN'} "
            f"D={D:.3f} TH={T:.3f} "
            f"result={'RECOGNIZED' if recognized else 'REJECTED'}"
        )

        # ======================================================
        # PHASE 3 – RESPONSE + AUDIT
        # ======================================================
        fname = f"{'known' if recognized else 'unknown'}_D{D:.3f}_T{T:.3f}.jpg"
        path = os.path.join(LOG_DIR, fname)
        Image.fromarray(img).save(path)

        if recognized:
            DIST_HISTORY.append(D)

            async_photo(
                path,
                f"✅ <b>{best_name}</b> dikenali\n"
                f"D : {D:.3f}\nThreshold : {T:.3f}\nJam : {jam}"
            )

            log_event("[RESPONSE] UNLOCK command sent to Raspberry Pi")
            return jsonify({"recognized": True, "name": best_name})

        else:
            async_photo(
                path,
                f"🚨 <b>Wajah tidak dikenal</b>\n"
                f"D : {D:.3f}\nThreshold : {T:.3f}\nJam : {jam}"
            )

            log_event("[RESPONSE] LOCK decision sent to Raspberry Pi")
            return jsonify({"recognized": False, "name": "unknown"})

    except Exception as e:
        log_event(f"[ERROR] recognize: {e}")
        return jsonify({"recognized": False}), 500

# --------------------------------------------------------------
# MAIN
# --------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    threading.Thread(target=embedding_auto_refresh, daemon=True).start()

    log_event("[SYSTEM] Telegram bot active")
    load_embeddings(force=True)
    log_event("[SYSTEM] SmartDoor server running on port 8000")

    app.run(host="0.0.0.0", port=8000)
