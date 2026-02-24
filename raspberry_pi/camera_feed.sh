#!/bin/bash
echo "[INFO] Starting rpicam-vid → ffmpeg TCP stream on port 8554 (no preview, low-latency)..."

rpicam-vid \
    --width 640 --height 480 --framerate 25 \
    --codec yuv420 --libav-format rawvideo \
    --inline --denoise cdn_off --awb auto --nopreview \
    --brightness -0.05 --contrast 1.2 --saturation 0.85 \
    --timeout 0 --output - \
| ffmpeg -hide_banner -loglevel warning \
    -f rawvideo -pix_fmt yuv420p -s 640x480 -r 25 -thread_queue_size 64 -i - \
    -fflags nobuffer -flags low_delay -tune zerolatency \
    -vcodec mjpeg -q:v 5 -f mjpeg -listen 1 tcp://0.0.0.0:8554/
