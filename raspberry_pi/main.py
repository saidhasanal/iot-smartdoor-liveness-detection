# ==============================================================
# main.py – SmartDoor FINAL v4.6
# Human-Safe Liveness + Anti-Paper
# (Log diperjelas, logika TIDAK diubah)
# ==============================================================

import os, time, cv2, base64, threading, requests
import numpy as np
from datetime import datetime
from flask import Flask, Response, jsonify
from picamera2 import Picamera2

from liveness_detection import LivenessDetector, Config
from lock_controller import unlock_door, lock_door

# ==============================================================
# INIT PATH & LOG
# ==============================================================

BASE_DIR = "/home/raspisaid/smartdoor"
LOG_FILE = os.path.join(BASE_DIR, "smartdoor_activity.log")
os.makedirs(BASE_DIR, exist_ok=True)

def log_local(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ==============================================================
# SERVER CONFIG
# ==============================================================

SERVER_URL = "http://10.149.52.169:8000/recognize"

# ==============================================================
# FLASK STREAM (MONITORING ONLY)
# ==============================================================

app = Flask(__name__)
SHARED_FRAME = None
FRAME_LOCK = threading.Lock()

@app.route("/")
def index():
    return "<h2>SmartDoor Camera Stream</h2><img src='/video_feed' width='640'>"

def generate_frames():
    while True:
        with FRAME_LOCK:
            frame = SHARED_FRAME.copy() if SHARED_FRAME is not None else None
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                yield b"--frame\r\nContent-Type:image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        time.sleep(0.04)

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

def run_flask():
    app.run(host="0.0.0.0", port=5000, threaded=True)

# ==============================================================
# CAMERA INIT
# ==============================================================

picam2 = Picamera2()
cam_cfg = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.set_controls({
    "AeConstraintMode": 1,
    "ExposureTime": 12000,
    "AnalogueGain": 4.0
})
picam2.configure(cam_cfg)
picam2.start()
time.sleep(2)

log_local("[CAMERA] Picamera2 aktif")
lock_door()
log_local("[LOCK] Pintu terkunci (default)")

# ==============================================================
# FACE DETECTOR
# ==============================================================

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ==============================================================
# LIVENESS MODULE
# ==============================================================

detector = LivenessDetector(Config)

# ==============================================================
# FSM CONFIG
# ==============================================================

STATE_IDLE, STATE_LIVENESS = 0, 1
state = STATE_IDLE

start_time = 0
face_last_seen = 0
door_is_open = False

freeze_until = 0
unknown_cooldown_until = 0
post_lock_cooldown_until = 0

MAX_LIVENESS_TIME = 5.0
FACE_DROP_TOL = 0.4
LIVE_THRESHOLD = 0.50

# ==============================================================
# SERVER COMM
# ==============================================================

def send_to_server(frame, status):
    try:
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        payload = {
            "image": base64.b64encode(buf).decode("utf-8"),
            "status": status
        }
        log_local(f"[SERVER] Mengirim status '{status}'")
        r = requests.post(SERVER_URL, json=payload, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        log_local(f"[SERVER] Error: {e}")
        return None

# ==============================================================
# START STREAM SERVER
# ==============================================================

threading.Thread(target=run_flask, daemon=True).start()
log_local("[STREAM] Live stream aktif (port 5000)")
log_local("[INFO] FSM aktif – Human-Safe Mode")

# ==============================================================
# MAIN LOOP
# ==============================================================

try:
    while True:
        now = time.time()

        # cooldown & blocking
        if (
            door_is_open or
            now < freeze_until or
            now < unknown_cooldown_until or
            now < post_lock_cooldown_until
        ):
            frame_rgb = picam2.capture_array()
            frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            with FRAME_LOCK:
                SHARED_FRAME = frame
            continue

        frame_rgb = picam2.capture_array()
        frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        display = frame.copy()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = FACE_CASCADE.detectMultiScale(gray, 1.2, 5, minSize=(96, 96))
        face_exists = len(faces) > 0

        if face_exists:
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 0), 2)
            face_last_seen = now

        with FRAME_LOCK:
            SHARED_FRAME = display

        # ---------------- STATE IDLE ----------------
        if state == STATE_IDLE:
            if face_exists:
                log_local("[STATE] Face detected → LIVENESS")
                detector.reset()
                start_time = now
                state = STATE_LIVENESS
            continue

        # ---------------- STATE LIVENESS ----------------
        if state == STATE_LIVENESS:

            if now - face_last_seen > FACE_DROP_TOL:
                log_local("[LIVENESS] face lost → FAIL → IDLE")
                state = STATE_IDLE
                continue

            res = detector.process_frame(frame)
            if not res or res.get("status") == "no_face":
                continue

            blink = float(res.get("blink_score", 0.0))
            motion = float(res.get("flow_score", 0.0))
            bright = float(res.get("bright_score", 0.0))
            score = float(res.get("live_score", 0.0))

            # RAW SCORE (LOG ONLY)
            raw = (
                0.60 * (1.0 if blink > 0 else 0.0) +
                0.25 * motion +
                0.15 * bright
            )

            log_local(
                f"[LIVENESS] "
                f"blink={blink:.0f} "
                f"motion={motion:.3f} "
                f"bright={bright:.3f} "
                f"raw={raw:.3f} "
                f"score={score:.3f}"
            )

            if score >= LIVE_THRESHOLD:
                log_local("[LIVENESS] SUCCESS → sending to server")
                state = STATE_IDLE

                result = send_to_server(frame, "live")
                if not result:
                    continue

                if result.get("recognized"):
                    name = result.get("name", "unknown")
                    log_local(f"[ACCESS] recognized {name} → unlocking door")
                    door_is_open = True

                    def door_task():
                        global door_is_open, post_lock_cooldown_until
                        unlock_door()
                        door_is_open = False
                        post_lock_cooldown_until = time.time() + 5

                    threading.Thread(target=door_task, daemon=True).start()

                else:
                    log_local("[ACCESS] unknown → cooldown 10 detik")
                    unknown_cooldown_until = now + 10

            if now - start_time >= MAX_LIVENESS_TIME:
                log_local("[LIVENESS] timeout → IDLE")
                freeze_until = now + 4
                state = STATE_IDLE

except KeyboardInterrupt:
    log_local("[SYSTEM] Shutdown manual")
