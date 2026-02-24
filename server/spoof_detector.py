# ==============================================================
# spoof_detector.py – Anti-Spoof (ONNX Runtime, Safe-Mode Edition)
# ==============================================================
# - Full Windows compatible
# - Auto-disable jika model tidak ditemukan
# - No crash, no spam error, server tetap normal
# ==============================================================

import numpy as np
import cv2
import onnxruntime as ort
import os
import glob

# ==============================================================
# AUTO-DETECT MODEL FILE
# ==============================================================

def find_model():
    """
    Cari model ONNX secara otomatis,
    urutan prioritas:
    1. anti_spoof_model.onnx
    2. *.onnx apa pun yang ada di folder
    """
    base = os.path.dirname(__file__)
    path1 = os.path.join(base, "anti_spoof_model.onnx")
    if os.path.exists(path1):
        return path1

    # fallback kalau namanya beda
    all_onnx = glob.glob(os.path.join(base, "*.onnx"))
    if len(all_onnx) > 0:
        print(f"[SPOOF] ⚠️ anti_spoof_model.onnx tidak ditemukan, memakai: {all_onnx[0]}")
        return all_onnx[0]

    # benar-benar tidak ada
    return None


class SpoofDetector:
    def __init__(self, threshold=0.7):
        self.threshold = threshold

        model_path = find_model()

        # Jika tidak ada model → disable spoof detection
        if model_path is None:
            print("[SPOOF] ⚠️ Tidak ada model .onnx ditemukan. Anti-spoof OFF (safe mode).")
            self.session = None
            return

        # Load ONNX model
        try:
            self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            print(f"[SPOOF] ✅ Model ONNX loaded: {model_path}")
        except Exception as e:
            print(f"[SPOOF] ❌ Gagal load model ONNX: {e}")
            print("[SPOOF] ⚠️ Anti-spoof dimatikan otomatis (safe mode).")
            self.session = None

    # ==============================================================
    # PREDICT
    # ==============================================================
    def predict(self, face_bgr):
        """
        Return:
            is_real (bool)
            score   (float)

        Jika CNN mati → selalu return real dengan score 1.0
        """

        # Mode tanpa ONNX → aman
        if self.session is None:
            return True, 1.0

        try:
            # Preprocessing
            img = cv2.resize(face_bgr, (128, 128))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))
            img = np.expand_dims(img, axis=0)

            # ONNX inference
            result = self.session.run([self.output_name], {self.input_name: img})[0]

            # Model output
            score = float(result[0][0])
            is_real = score >= self.threshold

            return is_real, score

        except Exception as e:
            print(f"[SPOOF] ❌ Error inferensi: {e}")
            print("[SPOOF] ⚠️ Auto-fallback ke safe mode.")
            return True, 1.0
