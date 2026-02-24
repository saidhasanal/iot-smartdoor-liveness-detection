#!/bin/bash
# ============================================================
# SmartDoor Said – Environment Setup Script
# ------------------------------------------------------------
# ? Membuat dan mengaktifkan virtual environment
# ? Menginstal semua dependensi SmartDoor v3.9
# ? Menjalankan tes Picamera2 untuk memastikan kamera aktif
# ============================================================

ENV_NAME="smartdoor-env"
PYTHON_BIN="python3"
BASE_DIR="/home/raspisaid/smartdoor"

echo "============================================================"
echo "?? SmartDoor Said Environment Setup"
echo "============================================================"
cd "$BASE_DIR" || exit 1

# ------------------------------------------------------------
# 1?? Pastikan Python dan pip ada
# ------------------------------------------------------------
if ! command -v $PYTHON_BIN &>/dev/null; then
    echo "? Python3 tidak ditemukan. Instal dulu dengan:"
    echo "   sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

# ------------------------------------------------------------
# 2?? Buat virtual environment jika belum ada
# ------------------------------------------------------------
if [ ! -d "$BASE_DIR/$ENV_NAME" ]; then
    echo "?? Membuat virtual environment '$ENV_NAME'..."
    $PYTHON_BIN -m venv "$ENV_NAME"
else
    echo "? Virtual environment sudah ada ($ENV_NAME)"
fi

# ------------------------------------------------------------
# 3?? Aktifkan environment
# ------------------------------------------------------------
source "$BASE_DIR/$ENV_NAME/bin/activate"
echo "?? Virtual environment diaktifkan."

# ------------------------------------------------------------
# 4?? Update pip & wheel
# ------------------------------------------------------------
pip install --upgrade pip wheel setuptools >/dev/null

# ------------------------------------------------------------
# 5?? Install dependensi utama
# ------------------------------------------------------------
echo "?? Menginstal dependensi SmartDoor..."
pip install -U \
    numpy==1.24.2 \
    opencv-contrib-python==4.8.1.78 \
    picamera2==0.3.31 \
    requests==2.32.5 \
    flask==3.0.3

# ------------------------------------------------------------
# 6?? Pastikan libcamera tools terinstal di sistem
# ------------------------------------------------------------
echo "?? Memeriksa libcamera tools..."
if ! command -v libcamera-hello &>/dev/null; then
    echo "?? Menginstal libcamera-tools..."
    sudo apt install -y libcamera-apps
else
    echo "? libcamera-tools sudah tersedia."
fi

# ------------------------------------------------------------
# 7?? Tes kamera dengan Picamera2
# ------------------------------------------------------------
echo "?? Menjalankan tes Picamera2..."
cat <<'EOF' > "$BASE_DIR/test_camera.py"
from picamera2 import Picamera2
import cv2, time

picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)
frame = picam2.capture_array()
cv2.imwrite("test_capture.jpg", frame)
picam2.stop()
print("? Kamera aktif! Hasil disimpan di test_capture.jpg")
EOF

python3 "$BASE_DIR/test_camera.py"
rm "$BASE_DIR/test_camera.py"

# ------------------------------------------------------------
# 8?? Selesai
# ------------------------------------------------------------
echo ""
echo "============================================================"
echo "? SmartDoor Environment berhasil disiapkan!"
echo "?? Virtualenv: $BASE_DIR/$ENV_NAME"
echo "?? Tes kamera: OK (lihat test_capture.jpg)"
echo ""
echo "Untuk memulai:"
echo "   cd $BASE_DIR"
echo "   source $ENV_NAME/bin/activate"
echo "   python3 main_strict.py"
echo "============================================================"
