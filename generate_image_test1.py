import torch
import torch.nn.functional as F
from ultralytics import YOLO
import torchvision.transforms as T
import cv2
import numpy as np
from PIL import Image
import os, random, string
from datetime import datetime

# -------------------------
# 1. Load YOLO model
# -------------------------
model = YOLO("models/campa2025_test3wpanenome.pt").to("cuda")

# -------------------------
# 2. Load background image (natural prior, e.g. ocean)
# -------------------------
bg_path = "ocean.jpg"   # replace with your own background image
H, W = 512, 512       # resolution of hallucination

transform = T.Compose([
    T.Resize((H, W)),
    T.ToTensor()
])

bg_img = transform(Image.open(bg_path).convert("RGB")).unsqueeze(0).to("cuda")

# Initial blur so YOLO doesn’t latch onto real features
init_blur = T.GaussianBlur(kernel_size=1, sigma=2.0)
#img = init_blur(bg_img).clone().detach()
img = bg_img
img.requires_grad = True

# -------------------------
# 3. Optimizer & regularization
# -------------------------
optimizer = torch.optim.Adam([img], lr=0.05)

def total_variation(x):
    """Total variation loss: encourages smoothness"""
    return torch.mean(torch.abs(x[:, :, :-1, :] - x[:, :, 1:, :])) + \
           torch.mean(torch.abs(x[:, :, :, :-1] - x[:, :, :, 1:]))

# Adaptive color prior: match background’s average color
target_mean_color = bg_img.mean(dim=[2,3], keepdim=True).detach()

target_class = 1       # class index to hallucinate
steps = 200000            # optimization steps

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

cv2.namedWindow("Hallucination", cv2.WINDOW_NORMAL)  # resizable window

# snapshot schedule: 30 evenly spaced
snapshot_steps = [int(i * steps / 50) for i in range(1, 51)]

# -------------------------
# 5. Optimization loop
# -------------------------
for step in range(steps):
    optimizer.zero_grad()

    # Forward pass into YOLO (raw outputs)
    raw_preds = model.model(img)
    if isinstance(raw_preds, (tuple, list)):
        raw_preds = raw_preds[0]

    # Extract class scores
    class_scores = raw_preds[..., 5:]
    score = class_scores[0, :100, target_class].mean()  # first 100 anchors

    # NaN guard
    if torch.isnan(score):
        print(f"⚠️ NaN at step {step}, resetting score to 0")
        score = torch.tensor(0.0, device=img.device)

    # Regularization
    tv_loss = 1e-4 * total_variation(img)
    color_loss = ((img.mean(dim=[2,3], keepdim=True) - target_mean_color)**2).mean()

    # Final loss
    loss = -score + tv_loss + 0.05 * color_loss

    loss.backward()
    optimizer.step()

    with torch.no_grad():
        img.clamp_(0, 1)

        # Progressive blur: strong early, weaker later
        blur_strength = max(0.5, 5.0 - step / 1000)
        dynamic_blur = T.GaussianBlur(kernel_size=5, sigma=blur_strength)
        blurred = dynamic_blur(img)

        # Blend blurred and current image gradually
        img[:] = 0.9 * img + 0.1 * blurred

        # Momentum image blending for stability
        img[:] = 0.9 * img + 0.1 * img.detach()

        # Every 2% of total steps, blend 5% of the base background back in
        if step > 0 and step % max(1, steps // 250) == 0:
            img[:] = 0.60 * img + 0.40 * bg_img
            print(f"� Blended base image at step {step}")

        # Convert to numpy for display
        vis = (img.cpu().squeeze().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        vis_bgr = cv2.cvtColor(vis, cv2.COLOR_RGB2BGR)

    # Live preview + MP4
    if step % 7 == 0:
        cv2.imshow("Hallucination", vis_bgr)
        out.write(vis_bgr)

    # Snapshots
    if step in snapshot_steps:
        snap_path = os.path.join("hallucinations", f"{run_id}_{step}.png")
        cv2.imwrite(snap_path, vis_bgr)
        print(f"� Snapshot saved: {snap_path}")

    if step % 20 == 0:
        print(f"Step {step}, score {score.item():.4f}")

    # Break if ESC pressed or window closed
    key = cv2.waitKey(1) & 0xFF
    if key == 27 or cv2.getWindowProperty("Hallucination", cv2.WND_PROP_VISIBLE) < 1:
        print("⏹ Interrupted by user")
        break

# -------------------------
# 6. Cleanup
# -------------------------
out.release()
cv2.destroyAllWindows()
print(f"✅ Finished. Video saved to {video_path}")