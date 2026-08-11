#!/usr/bin/env python3
"""Pick good reference frames for the FlashHead avatar from a video.

A good reference image = frontal face, eyes open, mouth closed. This tool
scores every frame with a lightweight heuristic (Haar face/eyes + mouth
darkness) and saves the top-N candidates.

Usage:
  python scripts/pick_gaze_frame.py --video video.mp4 --out ./picked [--top 5] [--every 2]
"""
import argparse
import os

import cv2
import numpy as np

FRONTAL = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
EYE = cv2.data.haarcascades + "haarcascade_eye.xml"


def score_frame(bgr, face_cas, eye_cas):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = face_cas.detectMultiScale(gray, 1.1, 5, minSize=(100, 100))
    if len(faces) != 1:
        return -1.0, None, None  # need exactly one clear frontal face
    (x, y, w, h) = faces[0]
    # Eyes inside the upper third of the face
    eyes = eye_cas.detectMultiScale(
        gray[y:y + h // 2, x:x + w], 1.1, 4, minSize=(int(w * 0.1), int(w * 0.1))
    )
    eye_score = min(2, len(eyes)) / 2.0  # 0..1, want ~2 eyes

    # Mouth region (lower part of the face); closed mouth => low dark fraction
    mx = x + int(w * 0.2)
    my = y + int(h * 0.62)
    mw = int(w * 0.6)
    mh = int(h * 0.2)
    mouth = gray[my:my + mh, mx:mx + mw]
    dark_frac = float((mouth < 90).mean())  # darker => more open
    mouth_score = 1.0 - min(1.0, dark_frac * 6)

    face_size = w * h
    size_score = min(1.0, face_size / (300.0 * 300.0))
    score = 0.45 * eye_score + 0.35 * mouth_score + 0.2 * size_score
    return score, (x, y, w, h), mouth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="./picked", help="output directory")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--every", type=int, default=1, help="sample every N frames")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    face_cas = cv2.CascadeClassifier(FRONTAL)
    eye_cas = cv2.CascadeClassifier(EYE)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {args.video}")

    ranked = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % args.every != 0:
            idx += 1
            continue
        score, _box, _mouth = score_frame(frame, face_cas, eye_cas)
        if score > 0:
            ranked.append((score, idx, frame))
        idx += 1
    cap.release()

    ranked.sort(key=lambda r: r[0], reverse=True)
    print(f"scored {len(ranked)} frames, top {args.top}:")
    for i, (score, fidx, frame) in enumerate(ranked[:args.top]):
        out = os.path.join(args.out, f"frame_{fidx:06d}_score{score:.2f}.jpg")
        cv2.imwrite(out, frame)
        print(f"  {out}  (score={score:.2f})")


if __name__ == "__main__":
    main()
