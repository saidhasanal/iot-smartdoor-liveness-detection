# ==============================================================
# lock_controller.py – Raspberry Pi 5 Safe Version
# ==============================================================
# ? Menggunakan gpiozero.OutputDevice (lebih stabil di Pi 5)
# ? Default pin: GPIO17 (board pin 11)
# ? Otomatis retry 3x jika inisialisasi gagal
# ? Tidak error meskipun relay dilepas
# ==============================================================

import time
from gpiozero import OutputDevice

LOCK_PIN = 17  # default: GPIO17

# --- Inisialisasi dengan retry ---
lock_pin = None
for attempt in range(1, 4):
    try:
        lock_pin = OutputDevice(LOCK_PIN, active_high=True, initial_value=False)
        print(f"[LOCK] ? GPIO{LOCK_PIN} siap (HIGH = terkunci)")
        break
    except Exception as e:
        print(f"[LOCK] ?? Gagal inisialisasi GPIO{LOCK_PIN} (attempt {attempt}/3): {e}")
        time.sleep(1)

if lock_pin is None:
    raise RuntimeError(f"[LOCK] ? Gagal inisialisasi GPIO{LOCK_PIN} setelah 3 kali percobaan")

# ==============================================================
# Fungsi kontrol kunci
# ==============================================================
def unlock_door(duration=15):
    """Membuka solenoid (LOW) selama `duration` detik, lalu kunci kembali (HIGH)."""
    print("[LOCK] ?? Membuka kunci...")
    try:
        lock_pin.on()      # HIGH = buka (relay NO)
        time.sleep(duration)
    finally:
        lock_pin.off()       # LOW = kunci lagi
        print("[LOCK] ?? Terkunci kembali.")

def lock_door():
    """Pastikan kunci dalam keadaan terkunci (LOW)."""
    lock_pin.off()
    print("[LOCK] ?? Kunci dipaksa dalam posisi LOCK.")

def cleanup():
    """Matikan relay dan bersihkan konfigurasi GPIO."""
    try:
        lock_pin.off()
    except:
        pass
    print("[LOCK] ?? GPIO cleanup selesai.")
