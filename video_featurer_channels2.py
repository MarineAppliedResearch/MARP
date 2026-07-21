import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt
from collections import deque

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
RESIZE_WIDTH = 720
COLORMAP = cv2.COLORMAP_TURBO
MAX_POINTS = 300  # how much time history to show

# =============================
# HELPERS
# =============================
def normalize_u8(img):
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

def colorize(gray):
    return cv2.applyColorMap(gray, COLORMAP)

# =============================
# SPECTRAL BAND DEFINITIONS
# =============================
band_names = [
    "Hue",
    "Saturation",
    "Value",
    "LAB L",
    "LAB A",
    "LAB B",
    "Excess Green",
    "Gradient"
]

num_bands = len(band_names)

# Deques store rolling time series
time_series = [deque(maxlen=MAX_POINTS) for _ in range(num_bands)]
time_axis = deque(maxlen=MAX_POINTS)

# =============================
# MATPLOTLIB SETUP
# =============================
plt.ion()
fig, ax = plt.subplots(figsize=(10, 4))

lines = []
for i in range(num_bands):
    line, = ax.plot([], [], label=band_names[i])
    lines.append(line)

ax.set_ylim(0, 255)
ax.set_xlim(0, MAX_POINTS)
ax.set_xlabel("Time (frames)")
ax.set_ylabel("Band Response")
ax.set_title("Temporal Spectral Response (Synthetic Bands)")
ax.legend(loc="upper left", ncol=2)
ax.grid(True)

plt.tight_layout()

frame_idx = 0

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

    if RESIZE_WIDTH is not None:
        h, w = frame.shape[:2]
        scale = RESIZE_WIDTH / w
        frame = cv2.resize(frame, (RESIZE_WIDTH, int(h * scale)))

    frame_f = frame.astype(np.float32)

    # =============================
    # COLOR SPACES
    # =============================
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # =============================
    # EXCESS GREEN
    # =============================
    Bb, Gb, Rb = cv2.split(frame_f)
    ExG = 2 * Gb - Rb - Bb
    ExG_u8 = normalize_u8(ExG)

    # =============================
    # GRADIENT
    # =============================
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)
    grad_u8 = normalize_u8(grad_mag)

    # =============================
    # BAND MEANS (THE "WAVELENGTHS")
    # =============================
    band_values = [
        np.mean(H),
        np.mean(S),
        np.mean(V),
        np.mean(L),
        np.mean(A),
        np.mean(B),
        np.mean(ExG_u8),
        np.mean(grad_u8),
    ]

    # =============================
    # UPDATE TIME SERIES
    # =============================
    time_axis.append(frame_idx)
    for i, val in enumerate(band_values):
        time_series[i].append(val)

    frame_idx += 1

    # =============================
    # UPDATE PLOT
    # =============================
    for i, line in enumerate(lines):
        line.set_data(
            np.arange(len(time_series[i])),
            list(time_series[i])
        )

    ax.set_xlim(0, MAX_POINTS)
    fig.canvas.draw()
    fig.canvas.flush_events()

    # =============================
    # VISUAL OUTPUTS
    # =============================
    cv2.imshow("Original Video", frame)
    cv2.imshow("Hue", colorize(H))
    cv2.imshow("Saturation", colorize(S))
    cv2.imshow("Value", colorize(V))
    cv2.imshow("LAB L", colorize(L))
    cv2.imshow("LAB A", colorize(A))
    cv2.imshow("LAB B", colorize(B))
    cv2.imshow("Excess Green Index", colorize(ExG_u8))
    cv2.imshow("Gradient Magnitude", colorize(grad_u8))

    # =============================
    # BAND EXPLORER (EYE CANDY)
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

    idx = frame_idx % len(bands)
    name, band = bands[idx]
    viewer = colorize(band)

    cv2.putText(
        viewer,
        f"Spectral Band: {name}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2
    )

    cv2.imshow("Hyperspectral Band Explorer", viewer)

    # =============================
    # INPUT
    # =============================
    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()
plt.close()
