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
    filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")]
)

if not video_path:
    raise RuntimeError("No video selected")

# =============================
# CONFIG
# =============================
RESIZE_WIDTH = 480
COLORMAP = cv2.COLORMAP_TURBO
MAX_POINTS = 200
FPS = 20
OUTPUT_VIDEO = "hyperspectral_mosaic_demo.mp4"

# Multi-scale settings (crisp, not smeary)
BLUR_SIGMAS = (0.0, 2.0, 5.0)  # fine, mid, coarse

# =============================
# HELPERS
# =============================
def normalize_u8(img):
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

def colorize(gray_u8):
    return cv2.applyColorMap(gray_u8, COLORMAP)

def resize_tile(img, size):
    return cv2.resize(img, size)

def label_tile(img, text):
    labeled = img.copy()
    bar_h = 30
    overlay = labeled.copy()
    cv2.rectangle(overlay, (0, 0), (labeled.shape[1], bar_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.60, labeled, 0.40, 0, labeled)
    cv2.putText(
        labeled, text, (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
        (255, 255, 255), 2, cv2.LINE_AA
    )
    return labeled

def grad_mag(gray_u8, ksize=3):
    gx = cv2.Sobel(gray_u8, cv2.CV_32F, 1, 0, ksize=ksize)
    gy = cv2.Sobel(gray_u8, cv2.CV_32F, 0, 1, ksize=ksize)
    mag = cv2.magnitude(gx, gy)
    return mag, gx, gy

def gaussian_if_needed(gray_u8, sigma):
    if sigma <= 0.0:
        return gray_u8
    # Kernel size rule of thumb: ~6*sigma rounded odd
    k = int(max(3, (sigma * 6) // 2 * 2 + 1))
    return cv2.GaussianBlur(gray_u8, (k, k), sigmaX=sigma, sigmaY=sigma)

def orientation_colored_edges(gx, gy, mag_u8):
    """
    Crisp edge visualization:
    Hue encodes edge orientation, Value encodes edge strength.
    """
    # Gradient angle in degrees [0, 180)
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0

    # Convert gradient direction to edge direction (perpendicular)
    edge_ang = (ang + 90.0) % 180.0

    # Map 0..180 -> 0..179 hue range
    hue = np.uint8((edge_ang / 180.0) * 179.0)
    sat = np.full_like(hue, 255, dtype=np.uint8)
    val = mag_u8  # already 0..255

    hsv = cv2.merge([hue, sat, val])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return bgr, edge_ang

def orientation_bin_means(edge_ang_deg, mag_u8):
    """
    Scalar responses for graphs:
    mean magnitude within orientation bins (horizontal/vertical/diagonal edges).
    """
    mag_f = mag_u8.astype(np.float32)

    # Bins on edge orientation (degrees):
    # horizontal edges around 0 (or 180)
    horiz = (edge_ang_deg <= 15.0) | (edge_ang_deg >= 165.0)
    # vertical edges around 90
    vert = (edge_ang_deg >= 75.0) & (edge_ang_deg <= 105.0)
    # diagonal = everything else
    diag = ~(horiz | vert)

    def masked_mean(mask):
        cnt = np.count_nonzero(mask)
        if cnt == 0:
            return 0.0
        return float(mag_f[mask].mean())

    return masked_mean(horiz), masked_mean(vert), masked_mean(diag)

# =============================
# "SPECTRAL" BANDS (CRISP + DEFENSIBLE)
# These are what feed the graphs + waterfall
# =============================
band_names = [
    "Intensity (V)",
    "Gradient",
    "Edges: Horizontal",
    "Edges: Vertical",
    "Edges: Diagonal",
    "Edges: Fine Scale",
    "Edges: Mid Scale",
    "Edges: Coarse Scale",
]
num_bands = len(band_names)

series = [deque(maxlen=MAX_POINTS) for _ in range(num_bands)]
waterfall = np.zeros((num_bands, MAX_POINTS), dtype=np.float32)

# =============================
# MATPLOTLIB: LINE GRAPH
# =============================
plt.ioff()

fig_line, ax_line = plt.subplots(figsize=(4, 3), dpi=100)
fig_line.patch.set_facecolor("#111111")
ax_line.set_facecolor("#111111")

lines = []
for name in band_names:
    line, = ax_line.plot([], [], label=name)
    lines.append(line)

ax_line.set_ylim(0, 255)
ax_line.set_xlim(0, MAX_POINTS)
ax_line.set_title("Temporal Spectral Response", color="white")
ax_line.set_xlabel("Time", color="white")
ax_line.set_ylabel("Response", color="white")
ax_line.tick_params(colors="white")
for spine in ax_line.spines.values():
    spine.set_color("white")
ax_line.legend(fontsize=6, ncol=2)
ax_line.grid(True, alpha=0.3)
fig_line.tight_layout()

# =============================
# MATPLOTLIB: WATERFALL
# =============================
fig_wf, ax_wf = plt.subplots(figsize=(4, 3), dpi=100)
fig_wf.patch.set_facecolor("#111111")
ax_wf.set_facecolor("#111111")

wf_img = ax_wf.imshow(
    waterfall,
    aspect="auto",
    cmap="turbo",
    vmin=0,
    vmax=255
)

ax_wf.set_title("Spectral Waterfall", color="white")
ax_wf.set_xlabel("Time", color="white")
ax_wf.set_ylabel("Band", color="white")
ax_wf.set_yticks(range(num_bands))
ax_wf.set_yticklabels(band_names, color="white")
ax_wf.tick_params(colors="white")
for spine in ax_wf.spines.values():
    spine.set_color("white")
fig_wf.tight_layout()

# =============================
# FIG RENDER (TkAgg-safe)
# =============================
def render_fig(fig):
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    img = buf[:, :, :3].copy()
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

# =============================
# VIDEO SETUP
# =============================
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError("Could not open video")

writer = None
fourcc = cv2.VideoWriter_fourcc(*"mp4v")

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

    # Intensity channel
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    V = hsv[..., 2]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Base gradient (sharp and impressive)
    mag, gx, gy = grad_mag(gray, ksize=3)
    grad_u8 = normalize_u8(mag)

    # Orientation colored edges (sharp, no blur)
    orient_bgr, edge_ang = orientation_colored_edges(gx, gy, grad_u8)

    # Multi-scale edges (fine/mid/coarse) -> composite
    scale_mags_u8 = []
    for sigma in BLUR_SIGMAS:
        g = gaussian_if_needed(gray, sigma)
        m, _, _ = grad_mag(g, ksize=3)
        scale_mags_u8.append(normalize_u8(m))

    fine_u8, mid_u8, coarse_u8 = scale_mags_u8

    # Multi-scale composite (looks like "hidden layers")
    multiscale_comp = cv2.merge([fine_u8, mid_u8, coarse_u8])

    # Pseudo hyperspectral composite (crisp + visually rich)
    pseudo_hyper = cv2.merge([grad_u8, mid_u8, V])

    # Scalars for graphs
    h_mean, v_mean, d_mean = orientation_bin_means(edge_ang, grad_u8)

    band_vals = [
        float(np.mean(V)),
        float(np.mean(grad_u8)),
        h_mean,
        v_mean,
        d_mean,
        float(np.mean(fine_u8)),
        float(np.mean(mid_u8)),
        float(np.mean(coarse_u8)),
    ]

    # Update time series + waterfall + line plot
    for i, val in enumerate(band_vals):
        series[i].append(val)
        waterfall[i, :-1] = waterfall[i, 1:]
        waterfall[i, -1] = val
        lines[i].set_data(range(len(series[i])), series[i])

    wf_img.set_data(waterfall)

    line_img = render_fig(fig_line)
    waterfall_img = render_fig(fig_wf)

    # =============================
    # MOSAIC (2 x 4 GRID)
    # =============================
    tile_w, tile_h = frame.shape[1], frame.shape[0]

    tiles = [
        label_tile(resize_tile(frame, (tile_w, tile_h)), "Original Video"),
        label_tile(resize_tile(colorize(grad_u8), (tile_w, tile_h)), "Gradient Magnitude"),
        label_tile(resize_tile(orient_bgr, (tile_w, tile_h)), "Orientation Colored Edges"),
        label_tile(resize_tile(multiscale_comp, (tile_w, tile_h)), "Multi Scale Edge Composite"),

        label_tile(resize_tile(pseudo_hyper, (tile_w, tile_h)), "Pseudo Hyperspectral Composite"),
        label_tile(resize_tile(line_img, (tile_w, tile_h)), "Temporal Spectral Response"),
        label_tile(resize_tile(waterfall_img, (tile_w, tile_h)), "Spectral Waterfall"),
        label_tile(resize_tile(frame, (tile_w, tile_h)), "Reference View"),
    ]

    row1 = np.hstack(tiles[:4])
    row2 = np.hstack(tiles[4:])
    mosaic = np.vstack([row1, row2])

    # Init writer once we know size
    if writer is None:
        mh, mw = mosaic.shape[:2]
        writer = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, FPS, (mw, mh))

    writer.write(mosaic)
    cv2.imshow("Hyperspectral Mosaic Demo", mosaic)

    if cv2.waitKey(1) == 27:  # ESC
        break

cap.release()
if writer is not None:
    writer.release()
cv2.destroyAllWindows()
plt.close("all")

print(f"Saved demo video to: {OUTPUT_VIDEO}")
