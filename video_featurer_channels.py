import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog

# =============================
# FILE PICKER
# =============================
root = tk.Tk()
root.withdraw()

video_path = filedialog.askopenfilename(
    title="Select Video File",
    filetypes=[
        ("Video files", "*.mp4 *.avi *.mov *.mkv"),
        ("All files", "*.*"),
    ]
)

if not video_path:
    raise RuntimeError("No video selected")

print(f"Selected video: {video_path}")

# =============================
# CONFIG
# =============================
RESIZE_WIDTH = 720  # None to disable resize
COLORMAP = cv2.COLORMAP_TURBO  # looks very 'science-y'

# =============================
# HELPERS
# =============================
def normalize_u8(img):
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

def colorize(gray):
    return cv2.applyColorMap(gray, COLORMAP)

# =============================
# OPEN VIDEO
# =============================
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError("Could not open video")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Resize for performance
    if RESIZE_WIDTH is not None:
        h, w = frame.shape[:2]
        scale = RESIZE_WIDTH / w
        frame = cv2.resize(frame, (RESIZE_WIDTH, int(h * scale)))

    frame_f = frame.astype(np.float32)

    # =============================
    # COLOR SPACE CONVERSIONS
    # =============================
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # =============================
    # EXCESS GREEN INDEX
    # =============================
    Bb, Gb, Rb = cv2.split(frame_f)
    ExG = 2 * Gb - Rb - Bb
    ExG_u8 = normalize_u8(ExG)

    # =============================
    # GRADIENT MAGNITUDE
    # =============================
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)
    grad_u8 = normalize_u8(grad_mag)

    # =============================
    # FALSE COLOR VIEWS
    # =============================
    cv2.imshow("Spectral Band - Hue", colorize(H))
    cv2.imshow("Spectral Band - Saturation", colorize(S))
    cv2.imshow("Spectral Band - Value", colorize(V))

    cv2.imshow("Spectral Band - LAB L", colorize(L))
    cv2.imshow("Spectral Band - LAB A", colorize(A))
    cv2.imshow("Spectral Band - LAB B", colorize(B))

    cv2.imshow("Index - Excess Green", colorize(ExG_u8))
    cv2.imshow("Band - Gradient Magnitude", colorize(grad_u8))

    # =============================
    # COMPOSITES (THE WOW FACTOR)
    # =============================

    # LAB composite (real color space recomposition)
    lab_composite = cv2.cvtColor(cv2.merge([L, A, B]), cv2.COLOR_LAB2BGR)

    # Pseudo hyperspectral RGB composite
    pseudo_hyper = cv2.merge([
        ExG_u8,      # "green sensitive band"
        grad_u8,     # "structural band"
        V            # intensity band
    ])

    cv2.imshow("LAB Composite", lab_composite)
    cv2.imshow("Pseudo Hyperspectral Composite", pseudo_hyper)

    # =============================
    # ANIMATED SPECTRAL SCROLL
    # =============================
    bands = [
        ("Hue", H),
        ("Saturation", S),
        ("Value", V),
        ("LAB L", L),
        ("LAB A", A),
        ("LAB B", B),
        ("Excess Green", ExG_u8),
        ("Gradient", grad_u8),
    ]

    idx = int((cv2.getTickCount() / cv2.getTickFrequency()) * 0.7) % len(bands)
    name, band = bands[idx]

    viewer = colorize(band)
    cv2.putText(
        viewer,
        f"Spectral Band: {name}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.imshow("Hyperspectral Band Explorer", viewer)

    # =============================
    # ORIGINAL FOR CONTEXT
    # =============================
    cv2.imshow("Original Video", frame)

    # =============================
    # INPUT
    # =============================
    key = cv2.waitKey(1)
    if key == 27:  # ESC
        break

cap.release()
cv2.destroyAllWindows()
