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
    filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")]
)

if not video_path:
    raise RuntimeError("No video selected")

# =============================
# CONFIG
# =============================
RESIZE_WIDTH = 480
COLORMAP = cv2.COLORMAP_TURBO
MAX_POINTS = 200
OUTPUT_VIDEO = "hyperspectral_mosaic_demo.mp4"
FPS = 20

# =============================
# HELPERS
# =============================
def normalize_u8(img):
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

def colorize(gray):
    return cv2.applyColorMap(gray, COLORMAP)

def resize_tile(img, size):
    return cv2.resize(img, size)

# =============================
# SPECTRAL BANDS
# =============================
band_names = [
    "Hue", "Sat", "Val", "L", "A", "B", "ExG", "Grad"
]
num_bands = len(band_names)

series = [deque(maxlen=MAX_POINTS) for _ in range(num_bands)]

# =============================
# MATPLOTLIB GRAPH SETUP
# =============================
plt.ioff()
fig, ax = plt.subplots(figsize=(4, 3), dpi=100)

lines = []
for name in band_names:
    line, = ax.plot([], [], label=name)
    lines.append(line)

ax.set_ylim(0, 255)
ax.set_xlim(0, MAX_POINTS)
ax.set_title("Temporal Spectral Response")
ax.set_xlabel("Time")
ax.set_ylabel("Response")
ax.legend(fontsize=6, ncol=2)
ax.grid(True)

ax.set_facecolor("#111111")
fig.patch.set_facecolor("#111111")
ax.tick_params(colors="white")
ax.yaxis.label.set_color("white")
ax.xaxis.label.set_color("white")
ax.title.set_color("white")
for spine in ax.spines.values():
    spine.set_color("white")
    
fig.tight_layout()

def render_graph():
    fig.canvas.draw()

    # TkAgg-compatible way
    buf = np.asarray(fig.canvas.buffer_rgba())
    img = buf[:, :, :3].copy()  # drop alpha channel

    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

# =============================
# VIDEO SETUP
# =============================
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError("Could not open video")

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = None

frame_idx = 0

# =============================
# MAIN LOOP
# =============================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    scale = RESIZE_WIDTH / w
    frame = cv2.resize(frame, (RESIZE_WIDTH, int(h * scale)))
    frame_f = frame.astype(np.float32)

    # Color spaces
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # ExG
    Bb, Gb, Rb = cv2.split(frame_f)
    ExG = normalize_u8(2 * Gb - Rb - Bb)

    # Gradient
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    Grad = normalize_u8(cv2.magnitude(gx, gy))

    # Band means
    band_vals = [
        np.mean(H), np.mean(S), np.mean(V),
        np.mean(L), np.mean(A), np.mean(B),
        np.mean(ExG), np.mean(Grad)
    ]

    for i, val in enumerate(band_vals):
        series[i].append(val)
        lines[i].set_data(range(len(series[i])), series[i])

    graph_img = render_graph()

    # Composites
    pseudo_hyper = cv2.merge([ExG, Grad, V])
    hue_fc = colorize(H)

    # =============================
    # MOSAIC LAYOUT (2x3)
    # =============================
    tile_w, tile_h = frame.shape[1], frame.shape[0]

    tiles = [
        resize_tile(frame, (tile_w, tile_h)),
        resize_tile(hue_fc, (tile_w, tile_h)),
        resize_tile(pseudo_hyper, (tile_w, tile_h)),
        resize_tile(colorize(Grad), (tile_w, tile_h)),
        resize_tile(colorize(ExG), (tile_w, tile_h)),
        resize_tile(graph_img, (tile_w, tile_h))
    ]

    row1 = np.hstack(tiles[:3])
    row2 = np.hstack(tiles[3:])

    mosaic = np.vstack([row1, row2])

    if writer is None:
        mh, mw = mosaic.shape[:2]
        writer = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, FPS, (mw, mh))

    writer.write(mosaic)
    cv2.imshow("Hyperspectral Mosaic Demo", mosaic)

    frame_idx += 1
    if cv2.waitKey(1) == 27:
        break

cap.release()
writer.release()
cv2.destroyAllWindows()
plt.close()

print(f"Saved demo video to: {OUTPUT_VIDEO}")
