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
    cv2.putText(out, text, (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2, cv2.LINE_AA)
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

# =============================
# ORIENTATION COLORED EDGES
# =============================
def orientation_colored_edges(gx, gy, mag_u8):
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0
    edge_ang = (ang + 90.0) % 180.0
    hue = np.uint8((edge_ang / 180.0) * 179.0)
    sat = np.full_like(hue, 255)
    val = mag_u8
    hsv = cv2.merge([hue, sat, val])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return bgr, edge_ang

# =============================
# NEW IMPRESSIVE FEATURES
# =============================
def texture_energy(gray):
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    tex = cv2.magnitude(gx, gy)
    return normalize_u8(tex), float(np.mean(tex))

def local_contrast(gray):
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    return normalize_u8(cv2.absdiff(gray, blur))

def saliency_map(gray):
    f = np.fft.fft2(gray.astype(np.float32))
    log_amp = np.log(np.abs(f) + 1e-6)
    phase = np.angle(f)
    avg = cv2.GaussianBlur(log_amp, (0, 0), 3)
    res = log_amp - avg
    sal = np.abs(np.fft.ifft2(np.exp(res + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal, (0, 0), 5)
    sal_u8 = normalize_u8(sal)
    return sal_u8, float(np.mean(sal_u8))

# =============================
# BANDS FOR GRAPHS
# =============================
band_names = [
    "Intensity (V)",
    "Gradient",
    "Edges Fine",
    "Edges Mid",
    "Edges Coarse",
    "Texture Energy",
    "Saliency Energy",
    "Confidence"
]

num_bands = len(band_names)
series = [deque(maxlen=MAX_POINTS) for _ in range(num_bands)]
waterfall = np.zeros((num_bands, MAX_POINTS), dtype=np.float32)

# =============================
# PLOTS
# =============================
plt.ioff()
fig_line, ax_line = plt.subplots(figsize=(4, 3), dpi=100)
fig_line.patch.set_facecolor("#111111")
ax_line.set_facecolor("#111111")

lines = []
for n in band_names:
    ln, = ax_line.plot([], [], label=n)
    lines.append(ln)

ax_line.set_ylim(0, 255)
ax_line.set_xlim(0, MAX_POINTS)
ax_line.legend(fontsize=6, ncol=2)
ax_line.grid(True, alpha=0.3)
ax_line.tick_params(colors="white")
for s in ax_line.spines.values():
    s.set_color("white")
fig_line.tight_layout()

fig_wf, ax_wf = plt.subplots(figsize=(4, 3), dpi=100)
fig_wf.patch.set_facecolor("#111111")
ax_wf.set_facecolor("#111111")

wf_img = ax_wf.imshow(waterfall, aspect="auto", cmap="turbo", vmin=0, vmax=255)
ax_wf.set_yticks(range(num_bands))
ax_wf.set_yticklabels(band_names, color="white")
ax_wf.tick_params(colors="white")
fig_wf.tight_layout()

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

    orient_bgr, _ = orientation_colored_edges(gx, gy, grad_u8)

    scales = []
    for s in BLUR_SIGMAS:
        g = gaussian_if_needed(gray, s)
        m, _, _ = grad_mag(g)
        scales.append(normalize_u8(m))

    fine, mid, coarse = scales

    tex_u8, tex_energy = texture_energy(gray)
    sal_u8, sal_energy = saliency_map(gray)

    material_comp = cv2.merge([tex_u8, local_contrast(gray), V])
    feature_proj = cv2.merge([grad_u8, tex_u8, sal_u8])
    overlay = cv2.addWeighted(frame, 0.75, colorize(sal_u8), 0.25, 0)

    conf = float(np.mean(sal_u8))

    band_vals = [
        np.mean(V),
        np.mean(grad_u8),
        np.mean(fine),
        np.mean(mid),
        np.mean(coarse),
        tex_energy,
        sal_energy,
        conf,
    ]

    for i, v in enumerate(band_vals):
        series[i].append(v)
        waterfall[i, :-1] = waterfall[i, 1:]
        waterfall[i, -1] = v
        lines[i].set_data(range(len(series[i])), series[i])

    wf_img.set_data(waterfall)

    line_img = render_fig(fig_line)
    wf_vis = render_fig(fig_wf)

    tile_w, tile_h = frame.shape[1], frame.shape[0]

    # ---- tiles ----
    tile_original = label_tile(resize_tile(frame, (tile_w, tile_h)), "Original Video")
    tile_gradient = label_tile(resize_tile(colorize(grad_u8), (tile_w, tile_h)), "Gradient Magnitude")
    tile_multiscale = label_tile(
        resize_tile(multiscale := cv2.merge([fine, mid, coarse]), (tile_w, tile_h)),
        "Multi Scale Edge Composite"
    )
    tile_pseudo = label_tile(
        resize_tile(pseudo := cv2.merge([grad_u8, mid, V]), (tile_w, tile_h)),
        "Pseudo Hyperspectral Composite"
    )
    tile_material = label_tile(
        resize_tile(material_comp, (tile_w, tile_h)),
        "Material Contrast Composite"
    )

    tile_line = label_tile(resize_tile(line_img, (tile_w, tile_h)), "Temporal Spectral Response")
    tile_waterfall = label_tile(resize_tile(wf_vis, (tile_w, tile_h)), "Spectral Waterfall")

    # Optional blank tile (dark)
    blank = np.zeros_like(tile_original)

    # ---- rows ----
    row1 = np.hstack([tile_original, tile_gradient, tile_line])
    row2 = np.hstack([tile_multiscale, tile_pseudo, tile_waterfall])
    row3 = np.hstack([tile_material, tile_original, blank])

    mosaic = np.vstack([row1, row2, row3])

    if writer is None:
        writer = cv2.VideoWriter(
            OUTPUT_VIDEO, fourcc, FPS,
            (mosaic.shape[1], mosaic.shape[0])
        )

    writer.write(mosaic)
    cv2.imshow("Hyperspectral Mosaic Demo", mosaic)

    if cv2.waitKey(1) == 27:
        break

cap.release()
writer.release()
cv2.destroyAllWindows()
plt.close("all")

print(f"Saved demo video to: {OUTPUT_VIDEO}")
