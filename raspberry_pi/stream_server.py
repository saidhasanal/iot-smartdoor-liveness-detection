# ==============================================================
# stream_server.py – untuk cek yang ditampilkan kamera supaya beban raspi berkurang
# ==============================================================

from flask import Flask, Response, render_template_string
import cv2, os, time

app = Flask(__name__)

FRAME_PATH = "/home/raspisaid/smartdoor/current_frame.jpg"

HTML_PAGE = """
<html>
<head>
    <title>SmartDoor Camera Stream</title>
    <style>
        body { background-color: #111; color: #eee; text-align: center; font-family: Arial; }
        img { border: 4px solid #555; border-radius: 10px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>?? SmartDoor Live Camera Stream</h1>
    <img src="/video_feed" width="640" height="480">
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

def generate_frames():
    while True:
        if os.path.exists(FRAME_PATH):
            frame = cv2.imread(FRAME_PATH)
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("[INFO] Server streaming aktif di http://<IP_RASPI>:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)
