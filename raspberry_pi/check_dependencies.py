# ==============================================================
# check_dependencies.py – SmartDoor Self-Healing Dependency Tool
# by ChatGPT (for Bro)
# ==============================================================
import importlib
import subprocess
import sys
import pkg_resources
from typing import List

# ==============================================================
# Daftar dependency SmartDoor
# ==============================================================
DEPENDENCIES = {
    "flask": None,
    "requests": None,
    "mediapipe": "0.10.18",
    "numpy": "<2.0",
    "opencv-contrib-python": "4.8.1.78",
    "pillow": None,
    "face_recognition": None,
    "dlib": None,
    "imutils": None,
    "jax": None,
    "jaxlib": None,
    "sentencepiece": None
}

# ==============================================================
# Fungsi bantu
# ==============================================================
def install_package(pkg: str, version: str = None):
    """Install satu paket"""
    try:
        if version is None:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg], check=True)
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", f"{pkg}=={version}"], check=True)
        print(f"? Installed {pkg}{'=='+version if version else ''}")
    except subprocess.CalledProcessError:
        print(f"? Gagal install {pkg}")

def check_and_fix_dependencies():
    """Cek dan install dependency yang hilang atau salah versi"""
    print("\n?? Mengecek dependency SmartDoor...\n")
    installed = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
    repaired: List[str] = []

    for pkg, required_version in DEPENDENCIES.items():
        current_ver = installed.get(pkg.lower())

        if current_ver is None:
            print(f"??  {pkg} belum terinstall.")
            install_package(pkg, required_version)
            repaired.append(pkg)
        else:
            # Cek versi numpy dan opencv
            if pkg == "numpy" and float(current_ver.split(".")[0]) >= 2.0:
                print(f"??  {pkg} versi {current_ver} tidak kompatibel (harus <2.0)")
                subprocess.run([sys.executable, "-m", "pip", "install", "numpy<2.0"], check=True)
                repaired.append(pkg)
            elif pkg == "opencv-contrib-python" and not current_ver.startswith("4.8.1"):
                print(f"??  {pkg} versi {current_ver} tidak cocok (disarankan 4.8.1.78)")
                install_package(pkg, "4.8.1.78")
                repaired.append(pkg)
            else:
                print(f"? {pkg} sudah terinstall (versi {current_ver})")

    if repaired:
        print("\n?? Dependency diperbaiki:", ", ".join(repaired))
    else:
        print("\n? Semua dependency lengkap & kompatibel.")

    print("\n?? Menjalankan pip check...\n")
    subprocess.run([sys.executable, "-m", "pip", "check"])

# ==============================================================
# Main
# ==============================================================
if __name__ == "__main__":
    try:
        check_and_fix_dependencies()
        print("\n?? Semua dependency siap. Jalankan SmartDoor dengan:")
        print("   python3 main.py\n")
    except KeyboardInterrupt:
        print("\n? Dibatalkan user.")
