# =============================================================
# liveness_detection.py – v6.3 (Anti-Paper + Human-Friendly)
# =============================================================

import cv2
import mediapipe as mp
import numpy as np
from collections import deque

class Config:
    # EAR / blink
    EAR_BASE = 0.28
    EAR_ADAPT_RATE = 0.0
    SYNC_EAR_DIFF = 0.10
    BLINK_MIN_CLOSED_FRAMES = 3
    BLINK_MAX_CLOSED_FRAMES = 12
    EAR_HISTORY_LEN = 6

    # Optical flow
    FLOW_RES = (96, 96)
    FLOW_NORM = 4.0
    MOTION_WINDOW = 6

    # Region flow (anti-photo/paper)
    REGION_ROWS = 3
    REGION_COLS = 3
    REGION_VAR_THR = 0.012      # dinaikkan dari 0.0035

    # Brightness smoothing (dibalik logika)
    BRIGHT_VAR = 20
    BRIGHT_WINDOW = 6

    # Face tilt tolerance
    FACE_TILT_MAX = 45

    # Scoring weights
    W_BLINK = 0.35
    W_MOTION = 0.50
    W_BRIGHT = 0.15

    LIVE_SCORE_THR = 0.50

class LivenessDetector:
    def __init__(self, config=Config):
        self.cfg = config
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.40,
            min_tracking_confidence=0.40
        )

        self.prev_gray = None
        self.motion_hist = deque(maxlen=self.cfg.MOTION_WINDOW)
        self.bright_hist = deque(maxlen=self.cfg.BRIGHT_WINDOW)
        self.ear_history = deque(maxlen=self.cfg.EAR_HISTORY_LEN)

        self.blink_state = "idle"
        self.closed_start_frame = 0
        self.frame_index = 0
        self.blink_count = 0

        self.smooth_pts = None
        self.smooth_alpha = 0.55

        self.last_result = None

    # ---------------------------------------------------------
    def reset(self):
        self.prev_gray = None
        self.motion_hist.clear()
        self.bright_hist.clear()
        self.ear_history.clear()

        self.blink_state = "idle"
        self.closed_start_frame = 0
        self.frame_index = 0
        self.blink_count = 0

        self.smooth_pts = None
        self.last_result = None

    # ---------------------------------------------------------
    def _smooth(self, pts):
        if self.smooth_pts is None:
            self.smooth_pts = pts.astype(float)
            return pts
        self.smooth_pts = (
            self.smooth_alpha * pts + 
            (1 - self.smooth_alpha) * self.smooth_pts
        )
        return self.smooth_pts.astype(int)

    def _ear(self, pts):
        A = np.linalg.norm(pts[1] - pts[5])
        B = np.linalg.norm(pts[2] - pts[4])
        C = np.linalg.norm(pts[0] - pts[3])
        return (A + B) / (2.0 * C) if C > 0 else 0.0

    def _face_angle_ok(self, pts):
        left = pts[33]; right = pts[263]
        dx = right[0] - left[0]
        dy = right[1] - left[1]
        ang = abs(np.degrees(np.arctan2(dy, dx)))
        return ang < self.cfg.FACE_TILT_MAX

    def _region_flow_variance(self, flow, roi_shape):
        h, w = roi_shape
        rows = self.cfg.REGION_ROWS
        cols = self.cfg.REGION_COLS
        r_h = max(1, h // rows)
        r_w = max(1, w // cols)

        means = []
        for ry in range(rows):
            for rx in range(cols):
                y1 = ry * r_h
                y2 = h if ry == rows - 1 else (ry + 1) * r_h
                x1 = rx * r_w
                x2 = w if rx == cols - 1 else (rx + 1) * r_w

                sub = flow[y1:y2, x1:x2]
                if sub.size == 0:
                    means.append(0.0)
                    continue

                mag, _ = cv2.cartToPolar(sub[...,0], sub[...,1])
                means.append(float(np.mean(mag)))

        means = np.array(means, dtype=np.float32)
        return float(np.std(means)), float(np.mean(means))

    # ---------------------------------------------------------
    # MAIN
    # ---------------------------------------------------------
    def process_frame(self, frame):

        self.frame_index += 1
        h, w = frame.shape[:2]

        # Mediapipe square mapping
        size = max(h, w)
        pad_x = (size - w) // 2
        pad_y = (size - h) // 2
        square = cv2.copyMakeBorder(
            frame, pad_y, pad_y, pad_x, pad_x,
            cv2.BORDER_CONSTANT, value=[0,0,0]
        )

        rgb = cv2.cvtColor(square, cv2.COLOR_BGR2RGB)
        res = self.mesh.process(rgb)

        # ---------------------------------------------------------
        if not res.multi_face_landmarks:
            self.blink_state = "idle"
            self.ear_history.clear()
            out = {"status": "no_face", "frame": frame}
            self.last_result = out
            return out

        lm = res.multi_face_landmarks[0].landmark

        # Map landmark to original coords
        pts = []
        for l in lm:
            x_s = int(l.x * size) - pad_x
            y_s = int(l.y * size) - pad_y
            x_c = np.clip(x_s, 0, w - 1)
            y_c = np.clip(y_s, 0, h - 1)
            pts.append((x_c, y_c))
        pts = np.array(pts, dtype=int)
        pts = self._smooth(pts)

        if not self._face_angle_ok(pts):
            out = {"status": "aborted_angle", "frame": frame}
            self.last_result = out
            return out

        # EAR + blink
        L = pts[[33,160,158,133,153,144]]
        R = pts[[362,385,387,263,373,380]]
        ear_left = self._ear(L)
        ear_right = self._ear(R)
        ear_avg = (ear_left + ear_right) / 2.0

        thresh = self.cfg.EAR_BASE  # no brightness adaptation
        self.ear_history.append(ear_avg)

        blink_detected = False

        if ear_avg < thresh:
            if self.blink_state == "idle":
                self.blink_state = "closed"
                self.closed_start_frame = self.frame_index

        else:
            if self.blink_state == "closed":
                closed_len = self.frame_index - self.closed_start_frame
                if self.cfg.BLINK_MIN_CLOSED_FRAMES <= closed_len <= self.cfg.BLINK_MAX_CLOSED_FRAMES:
                    if abs(ear_left - ear_right) <= self.cfg.SYNC_EAR_DIFF:
                        blink_detected = True
            self.blink_state = "idle"

        if blink_detected:
            self.blink_count += 1

        # ROI
        x1, y1 = int(np.min(pts[:,0])), int(np.min(pts[:,1]))
        x2, y2 = int(np.max(pts[:,0])), int(np.max(pts[:,1]))
        pad_face = int(0.20 * max(x2-x1, y2-y1))

        x1 = max(0, x1 - pad_face)
        y1 = max(0, y1 - pad_face)
        x2 = min(w, x2 + pad_face)
        y2 = min(h, y2 + pad_face)

        roi = frame[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            out = {"status": "aborted_roi", "frame": frame}
            self.last_result = out
            return out

        # Optical flow
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        motion_mean = 0.0
        region_var = 0.0

        if (
            self.prev_gray is not None and 
            self.prev_gray.shape == gray.shape
        ):
            g1 = cv2.resize(self.prev_gray, self.cfg.FLOW_RES)
            g2 = cv2.resize(gray, self.cfg.FLOW_RES)

            flow = cv2.calcOpticalFlowFarneback(
                g1, g2, None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, _ = cv2.cartToPolar(flow[...,0], flow[...,1])
            motion_mean = float(np.mean(mag))

            flow_resized = cv2.resize(flow, (gray.shape[1], gray.shape[0]))
            region_var, _ = self._region_flow_variance(flow_resized, gray.shape)

        self.prev_gray = gray.copy()

        motion_score = min(1.0, motion_mean / self.cfg.FLOW_NORM)
        self.motion_hist.append(motion_score)
        motion_score = np.mean(self.motion_hist)

        # Bright_score dibalik logika
        br = float(np.std(gray))
        self.bright_hist.append(br)
        bright_score = min(1.0, (np.mean(self.bright_hist) / self.cfg.BRIGHT_VAR))

        # ---------------------------------------------------------
        # Anti-paper rule (utama)
        # ---------------------------------------------------------
        hard_spoof = (
            region_var < self.cfg.REGION_VAR_THR and
            motion_score < 0.05
        )

        # FINAL SCORING
        blink_score = 1.0 if self.blink_count > 0 else 0.0

        live_score = (
            blink_score * self.cfg.W_BLINK +
            motion_score * self.cfg.W_MOTION +
            bright_score * self.cfg.W_BRIGHT
        )

        if hard_spoof:
            live_score = max(0.0, live_score - 0.35)

        live_score = float(np.clip(live_score, 0.0, 1.0))
        status = "live" if (live_score >= self.cfg.LIVE_SCORE_THR) else "not_live"

        is_closed = ear_avg < thresh

        out = {
            "status": status,
            "frame": frame,
            "score": round(live_score, 3),
            "live_score": round(live_score, 3),
            "blink_score": float(self.blink_count),
            "flow_score": round(motion_score, 3),
            "bright_score": round(bright_score, 3),
            "region_var": round(float(region_var), 6),
            "spoof_score": int(hard_spoof),
            "is_closed": bool(is_closed),
            "ear_avg": float(ear_avg)
        }

        self.last_result = out
        return out
