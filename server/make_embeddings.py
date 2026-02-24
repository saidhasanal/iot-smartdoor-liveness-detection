# ==============================================================
# make_embeddings.py – Generate Weighted Face Embedding
# ==============================================================
import os, numpy as np, face_recognition, cv2
from datetime import datetime

BASE_DIR   = os.getcwd()
FACES_DIR  = os.path.join(BASE_DIR, "faces")
EMB_DIR    = os.path.join(BASE_DIR, "embeddings")

os.makedirs(EMB_DIR, exist_ok=True)

def enhance_lighting(image):
    """Perbaiki pencahayaan sebelum encoding"""
    img_yuv = cv2.cvtColor(image, cv2.COLOR_RGB2YUV)
    img_yuv[:, :, 0] = cv2.equalizeHist(img_yuv[:, :, 0])
    return cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)

def compute_weighted_embedding(name):
    """
    Buat embedding rata-rata (weighted) untuk wajah dengan nama tertentu.
    Hasil disimpan sebagai embeddings/{name}.npy
    """
    person_files = [f for f in os.listdir(FACES_DIR) if f.startswith(name + "_")]
    if not person_files:
        print(f"[WARN] Tidak ada file wajah untuk {name}")
        return None

    encodings = []
    for file in person_files:
        path = os.path.join(FACES_DIR, file)
        try:
            img = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            img = enhance_lighting(img)
            faces = face_recognition.face_encodings(img)
            if faces:
                encodings.append(faces[0])
                print(f"[INFO] {file} -> OK")
            else:
                print(f"[SKIP] {file}: no face found")
        except Exception as e:
            print(f"[ERROR] {file}: {e}")

    if not encodings:
        print(f"[FAIL] Tidak ada encoding valid untuk {name}")
        return None

    # Hitung weighted average: semakin baru, bobot lebih tinggi
    weights = np.linspace(0.6, 1.0, len(encodings))
    weights /= np.sum(weights)
    weighted = np.average(np.stack(encodings), axis=0, weights=weights)

    out_path = os.path.join(EMB_DIR, f"{name}.npy")
    np.save(out_path, weighted)
    print(f"[DONE] Weighted embedding untuk {name} disimpan ke {out_path}")
    return weighted
