"""Check available cameras and attempt to read a frame.

Usage:
  python tools/check_camera.py [max_index]

Prints whether each index could be opened and whether a frame could be read.
"""
import cv2
import sys

max_idx = 4
if len(sys.argv) > 1:
    try:
        max_idx = int(sys.argv[1])
    except:
        pass

for idx in range(0, max_idx+1):
    print(f"Checking camera index {idx}...")
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    opened = cap.isOpened()
    print(f"  isOpened: {opened}")
    if not opened:
        # try without CAP_DSHOW
        cap.release()
        cap = cv2.VideoCapture(idx)
        print(f"  fallback isOpened: {cap.isOpened()}")

    if cap.isOpened():
        ret, frame = cap.read()
        print(f"  read frame success: {ret}")
        if ret and frame is not None:
            h, w = frame.shape[:2]
            print(f"  frame size: {w}x{h}")
        cap.release()
    print('')

print('Done')
