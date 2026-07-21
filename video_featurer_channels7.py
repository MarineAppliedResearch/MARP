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
OUTPUT_VIDEO = "hyperspectral_mosaic_demo_longer.mp4"
BLUR_SIGMAS = (0.0, 2.0, 5.0)

# =============================
# HELPERS
# =============================
def normalize_u8(img):
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

def colorize(gray):
    return cv2.applyColorMap(gray, COLORMAP)

def resize_tile(img, size):
    return cv2.resize(img, size)

def label_tile(img, text):
    out = img.copy()
    bar_h = 30
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (out.shape[1], bar_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, out, 0.4, 0, out)
    cv2.putText(
        out, text, (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
        (255, 255, 255), 2, cv2.LINE_AA
    )
    return out

def grad_mag(gray, ksize=3):
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=ksize)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=ksize)
    mag = cv2.magnitude(gx, gy)
    return mag, gx, gy

def gaussian_if_needed(gray, sigma):
    if sigma <= 0.0:
        return gray
    k = int(max(3, (sigma * 6) // 2 * 2 + 1))
    return cv2.GaussianBlur(gray, (k, k), sigmaX=sigma, sigmaY=sigma)

def texture_energy(gray):
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    tex = cv2.magnitude(gx, gy)
    return normalize_u8(tex), float(np.mean(tex))

def local_contrast(gray):
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    return normalize_u8(cv2.absdiff(gray, blur))

def percentile_normalize(gray_u8, low=2, high=98):
    lo = np.percentile(gray_u8, low)
    hi = np.percentile(gray_u8, high)
    if hi <= lo:
        return gray_u8
    out = np.clip((gray_u8 - lo) * 255.0 / (hi - lo), 0, 255)
    return out.astype(np.uint8)

def scale_for_display(arr, low=5, high=95):
    lo = np.percentile(arr, low)
    hi = np.percentile(arr, high)
    if hi <= lo:
        return arr
    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0, 1)

# =============================
# BANDS (GRAPHS)
# =============================
band_names = [
    "Intensity (V)",
    "Gradient",
    "Edges Fine",
    "Edges Mid",
    "Edges Coarse",
    "Texture Energy",
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
    ln, = ax_line.plot([], [], label=name)
    lines.append(ln)

ax_line.set_ylim(0, 255)
ax_line.set_xlim(0, MAX_POINTS)
ax_line.legend(fontsize=6, ncol=2)
ax_line.grid(True, alpha=0.3)
ax_line.tick_params(colors="white")
for spine in ax_line.spines.values():
    spine.set_color("white")
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
    vmin=0.0,
    vmax=1.0
)
ax_wf.set_yticks(range(num_bands))
ax_wf.set_yticklabels(band_names, color="white", fontsize=7)
ax_wf.tick_params(colors="white")
fig_wf.tight_layout()

# =============================
# MATPLOTLIB: CORRELATION
# =============================
fig_corr, ax_corr = plt.subplots(figsize=(4, 3), dpi=100)
fig_corr.patch.set_facecolor("#111111")
ax_corr.set_facecolor("#111111")

corr_img = ax_corr.imshow(
    np.zeros((num_bands, num_bands), dtype=np.float32),
    cmap="turbo",
    vmin=-1.0,
    vmax=1.0
)

ax_corr.set_title("Band Correlation", color="white")
ax_corr.set_xticks(range(num_bands))
ax_corr.set_yticks(range(num_bands))
ax_corr.set_xticklabels(band_names, rotation=45, ha="right", fontsize=6, color="white")
ax_corr.set_yticklabels(band_names, fontsize=6, color="white")
ax_corr.tick_params(colors="white")
for spine in ax_corr.spines.values():
    spine.set_color("white")
fig_corr.tight_layout()

def render_fig(fig):
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    img = buf[:, :, :3].copy()
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

# =============================
# VIDEO LOOP
# =============================
cap = cv2.VideoCapture(video_path)
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = None

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (RESIZE_WIDTH, int(h * RESIZE_WIDTH / w)))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    V = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2]

    mag, gx, gy = grad_mag(gray)
    grad_u8 = normalize_u8(mag)

    scale_mags = []
    for s in BLUR_SIGMAS:
        g = gaussian_if_needed(gray, s)
        m, _, _ = grad_mag(g)
        scale_mags.append(normalize_u8(m))

    fine, mid, coarse = scale_mags
    multiscale = cv2.merge([fine, mid, coarse])
    pseudo = cv2.merge([grad_u8, mid, V])

    tex_u8, tex_energy = texture_energy(gray)
    material_comp = cv2.merge([tex_u8, local_contrast(gray), V])

    V_stretched = percentile_normalize(V, low=2, high=98)
    false_color_intensity = colorize(V_stretched)

    band_vals = [
        float(np.mean(V)),
        float(np.mean(grad_u8)),
        float(np.mean(fine)),
        float(np.mean(mid)),
        float(np.mean(coarse)),
        tex_energy,
    ]

    for i, v in enumerate(band_vals):
        series[i].append(v)
        waterfall[i, :-1] = waterfall[i, 1:]
        waterfall[i, -1] = v
        lines[i].set_data(range(len(series[i])), series[i])

    wf_disp = scale_for_display(waterfall, low=5, high=95)
    wf_img.set_data(wf_disp)

    if all(len(s) > 5 for s in series):
        data = np.stack([np.array(s) for s in series], axis=0)
        data = (data - data.mean(axis=1, keepdims=True)) / (
            data.std(axis=1, keepdims=True) + 1e-6
        )
        corr_img.set_data(np.corrcoef(data))

    line_img = render_fig(fig_line)
    wf_vis = render_fig(fig_wf)
    corr_vis = render_fig(fig_corr)

    tile_w, tile_h = frame.shape[1], frame.shape[0]

    row1 = np.hstack([
        label_tile(resize_tile(frame, (tile_w, tile_h)), "Original Video"),
        label_tile(resize_tile(colorize(grad_u8), (tile_w, tile_h)), "Gradient Magnitude"),
        label_tile(resize_tile(line_img, (tile_w, tile_h)), "Temporal Spectral Response"),
    ])

    row2 = np.hstack([
        label_tile(resize_tile(multiscale, (tile_w, tile_h)), "Multi Scale Edge Composite"),
        label_tile(resize_tile(pseudo, (tile_w, tile_h)), "Hyperspectral Composite"),
        label_tile(resize_tile(wf_vis, (tile_w, tile_h)), "Spectral Waterfall"),
    ])

    row3 = np.hstack([
        label_tile(resize_tile(material_comp, (tile_w, tile_h)), "Material Contrast Composite"),
        label_tile(resize_tile(false_color_intensity, (tile_w, tile_h)), "Color Intensity"),
        label_tile(resize_tile(corr_vis, (tile_w, tile_h)), "Band Correlation"),
    ])

    mosaic = np.vstack([row1, row2, row3])

    WRITE_SCALE = 1

    if writer is None:
        out_w = int(mosaic.shape[1] * WRITE_SCALE)
        out_h = int(mosaic.shape[0] * WRITE_SCALE)
        writer = cv2.VideoWriter(
            OUTPUT_VIDEO,
            fourcc,
            FPS,
            (out_w, out_h)
        )
        
    mosaic_out = cv2.resize(
        mosaic,
        (out_w, out_h)
    )
    writer.write(mosaic_out)

    #writer.write(mosaic)
    cv2.imshow("Hyperspectral Mosaic Demo", mosaic_out)

    if cv2.waitKey(1) == 27:
        break

cap.release()
writer.release()
cv2.destroyAllWindows()
plt.close("all")

print(f"Saved demo video to: {OUTPUT_VIDEO}")
