from picamera2 import Picamera2
import cv2, numpy as np, requests, base64, time, os

# === Konfigurasi dasar ===
##SERVER_URL = "http://192.168.18.19:8000/register"
SERVER_URL = "http://10.149.52.169:8000/register"
BASE_DIR = "/home/raspisaid/smartdoor"
os.makedirs(BASE_DIR, exist_ok=True)

# === Inisialisasi kamera (sama seperti main.py) ===
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)

# === Path fallback untuk Haar Cascade ===
cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
if not os.path.exists(cascade_path):
    cascade_path = "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"
if not os.path.exists(cascade_path):
    raise FileNotFoundError("? Haarcascade tidak ditemukan. Install dulu: sudo apt install libopencv-data")

face_cascade = cv2.CascadeClassifier(cascade_path)

print("[INFO] Kamera siap. Tekan 'C' untuk mulai registrasi wajah, 'Q' untuk keluar.")


def send_to_server(name, frame):
    """Kirim gambar ke API register"""
    _, buffer = cv2.imencode(".jpg", frame)
    img_b64 = base64.b64encode(buffer).decode("utf-8")

    try:
        res = requests.post(SERVER_URL, json={"name": name, "image": img_b64}, timeout=10)
        if res.status_code == 200:
            print("[?] Berhasil kirim ke server:", res.json())
        else:
            print("[??] Gagal kirim. Status:", res.status_code, res.text)
    except Exception as e:
        print("[?] Error koneksi:", e)


def capture_face(frame):
    """Ambil wajah dominan di layar"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.2, 5)

    if len(faces) == 0:
        print("[WARN] Tidak ada wajah terdeteksi.")
        return None

    # Pilih wajah terbesar (dominan)
    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    face_crop = frame[y:y+h, x:x+w]
    return face_crop


try:
    while True:
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)  # ?? Pastikan warna natural

        # Deteksi wajah realtime
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.2, 5)

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        cv2.putText(frame, "Tekan 'C' untuk Capture, 'Q' untuk Keluar", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Register Mode - SmartDoor", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("[INFO] Keluar dari mode register.")
            break
        elif key == ord("c"):
            name = input("Masukkan nama pengguna: ").strip()
            if not name:
                print("[WARN] Nama tidak boleh kosong!")
                continue

            print(f"[INFO] Mulai ambil 15 foto untuk '{name}' ...")
            captured = 0
            while captured < 15:
                frame = picam2.capture_array()
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                face_img = capture_face(frame)
                if face_img is not None:
                    captured += 1
                    print(f"??  Foto {captured}/20 diambil.")
                    send_to_server(f"{name}_{captured}", face_img)
                    time.sleep(3.0)  # jeda antar-foto

            print(f"[?] Registrasi '{name}' selesai.\n")
            time.sleep(1)

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("[INFO] Kamera dimatikan.")
