import torch
import torch.nn.functional as F
from ultralytics import YOLO
import torchvision.transforms as T
import cv2
import numpy as np
from PIL import Image
import os, random, string, time
from datetime import datetime

# -------------------------
# 1. Load YOLO model
# -------------------------
model = YOLO("models/campa2025_group1_test1.pt").to("cuda")

# -------------------------
# 2. Load background image
# -------------------------
bg_path = "ocean.jpg"   # replace with your own
H, W = 512, 512

transform = T.Compose([
    T.Resize((H, W)),
    T.ToTensor()
])

bg_img = transform(Image.open(bg_path).convert("RGB")).unsqueeze(0).to("cuda")

# Start with blurred background
init_blur = T.GaussianBlur(kernel_size=11, sigma=5.0)
img = init_blur(bg_img).clone().detach()
img.requires_grad = True

# -------------------------
# 3. Optimizer & helpers
# -------------------------
optimizer = torch.optim.Adam([img], lr=0.05)

def frequency_loss(x):
    fft = torch.fft.fft2(x, norm="ortho")
    fft_shift = torch.fft.fftshift(fft)
    high_freq = torch.abs(fft_shift[:, :, H//4:, W//4:])
    return high_freq.mean()

def edge_emphasis(x):
    """Encourages sharper edges by maximizing gradient contrast"""
    gx = x[:,:,:,1:] - x[:,:,:,:-1]
    gy = x[:,:,1:,:] - x[:,:,:-1,:]
    return -(gx.abs().mean() + gy.abs().mean())

target_mean_color = bg_img.mean(dim=[2,3], keepdim=True).detach()

target_class = 1
steps = 2000

# -------------------------
# 4. Setup output folder
# -------------------------
os.makedirs("hallucinations", exist_ok=True)
def random_tag(n=4): return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
run_id = f"hallucination_{timestamp}_{random_tag()}"

video_path = os.path.join("hallucinations", f"{run_id}.mp4")

fps = 20
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(video_path, fourcc, fps, (W, H))

cv2.namedWindow("Hallucination", cv2.WINDOW_NORMAL)

# -------------------------
# 5. Snapshot setup (30 evenly spaced)
# -------------------------
snapshot_steps = [int(i * steps / 30) for i in range(1, 31)]

# -------------------------
# 6. Define phase boundaries
# -------------------------
phase1_end = int(0.50 * steps)
phase2_end = int(0.80 * steps)

# -------------------------
# 7. Optimization loop
# -------------------------
start_time = time.time()
for step in range(steps):
    frac = step / steps

    # ---------------------
    # Phase 1: Fast (0–50%)
    # ---------------------
    if step < phase1_end:
        phase_name = "Fast"
        phase_step = step
        phase_total = phase1_end
        tv_w, color_w, freq_w, edge_w = 1e-4, 0.05, 0.0, 0.0
        blur_strength = max(0.5, 5.0 - step/1000)
        lr = 0.05

    # ---------------------
    # Phase 2: Careful (50–80%)
    # ---------------------
    elif step < phase2_end:
        phase_name = "Careful"
        phase_step = step - phase1_end
        phase_total = phase2_end - phase1_end
        tv_w, color_w, freq_w, edge_w = 2e-4, 0.05, 0.01, 0.0
        blur_strength = max(0.5, 2.0 - (step-0.5*steps)/2000)
        lr = 0.01

    # ---------------------
    # Phase 3: Baking (80–100%)
    # ---------------------
    else:
        phase_name = "Baking"
        phase_step = step - phase2_end
        phase_total = steps - phase2_end
        tv_w, color_w, freq_w, edge_w = 1e-5, 0.05, 0.02, 0.01  # almost no TV, strong edge
        blur_strength = 0.0  # disable blur
        lr = 0.0005

    # Apply LR change
    for g in optimizer.param_groups:
        g['lr'] = lr

    optimizer.zero_grad()
    raw_preds = model.model(img)
    if isinstance(raw_preds, (tuple, list)):
        raw_preds = raw_preds[0]

    class_scores = raw_preds[..., 5:]
    if phase_name == "Baking":
        score = class_scores[0, :50, target_class].mean()
    else:
        score = class_scores[0, :100, target_class].mean()

    if torch.isnan(score):
        score = torch.tensor(0.0, device=img.device)

    # Border-weighted TV loss
    border_weight = torch.ones((1,1,H,W), device=img.device)
    border_weight[:,:, :H//8,:] = 2.0
    border_weight[:,:, -H//8:,:] = 2.0
    border_weight[:,:,:, :W//8] = 2.0
    border_weight[:,:,:, -W//8:] = 2.0
    tv_x = (border_weight[:,:,:-1,:] * (img[:,:,:-1,:] - img[:,:,1:,:]).abs()).mean()
    tv_y = (border_weight[:,:,:,:-1] * (img[:,:,:,:-1] - img[:,:,:,1:]).abs()).mean()
    tv_loss = tv_w * (tv_x + tv_y)

    # Color prior (masked to center, not borders)
    mask = torch.ones_like(img)
    mask[:, :, :H//8, :] = 0
    mask[:, :, -H//8:, :] = 0
    mask[:, :, :, :W//8] = 0
    mask[:, :, :, -W//8:] = 0
    color_loss = color_w * (((img.mean(dim=[2,3], keepdim=True) - target_mean_color) * mask).pow(2)).mean()

    freq_reg = freq_w * frequency_loss(img)
    edge_reg = edge_w * edge_emphasis(img)

    loss = -score + tv_loss + color_loss + freq_reg + edge_reg

    loss.backward()
    optimizer.step()

    with torch.no_grad():
        img.clamp_(0, 1)

        if blur_strength > 0:
            dynamic_blur = T.GaussianBlur(kernel_size=5, sigma=blur_strength)
            blurred = dynamic_blur(img)
            img[:] = 0.9 * img + 0.1 * blurred

        if phase_name == "Baking":
            img[:] = 0.99 * img + 0.01 * img.detach()  # light EMA

        vis = (img.cpu().squeeze().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        vis_bgr = cv2.cvtColor(vis, cv2.COLOR_RGB2BGR)

    if step % 7 == 0:
        cv2.imshow("Hallucination", vis_bgr)
        out.write(vis_bgr)

    if step in snapshot_steps:
        snap_path = os.path.join("hallucinations", f"{run_id}_{step}.png")
        cv2.imwrite(snap_path, vis_bgr)
        print(f"� Snapshot saved: {snap_path}")

    if step % 100 == 0 and step > 0:
        elapsed = time.time() - start_time
        eta = (steps - step) * (elapsed / step)
        print(f"Step {step}/{steps} "
              f"(Phase {phase_name}: {phase_step}/{phase_total}), "
              f"score {score.item():.4f}, ETA {eta/60:.1f} min")

    key = cv2.waitKey(1) & 0xFF
    if key == 27 or cv2.getWindowProperty("Hallucination", cv2.WND_PROP_VISIBLE) < 1:
        print("⏹ Interrupted by user")
        break

# -------------------------
# 8. Cleanup
# -------------------------
out.release()
cv2.destroyAllWindows()
print(f"✅ Finished. Video saved to {video_path}")
