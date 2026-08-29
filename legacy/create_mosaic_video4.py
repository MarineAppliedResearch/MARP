import cv2
import numpy as np
from pathlib import Path
from tkinter import Tk, filedialog
from collections import defaultdict

GRID_SIZE = 7
FRAME_RATE = 15

def get_all_observations(root_folder):
    """
    Recursively find for_human_review images and group them by observation key.
    Collect all frames per observation ID, across all species folders, deduplicating exact paths.
    """
    jpgs = sorted(Path(root_folder).rglob("for_human_review/*/*.jpg"))
    print(f"[🔍] Found {len(jpgs)} .jpg files")

    all_obs = {}
    for path in jpgs:
        parts = path.stem.split("_")
        if len(parts) < 5 or not parts[4].isdigit():
            print(f"[⚠️] Skipping malformed filename: {path.name}")
            continue

        obs_key = f"{parts[1]}_{parts[2]}"
        frame_num = int(parts[4])
        if obs_key not in all_obs:
            all_obs[obs_key] = {}
        if frame_num not in all_obs[obs_key]:
            all_obs[obs_key][frame_num] = path

    # Convert frame dicts into sorted frame lists
    observations = []
    for obs_key, frame_dict in all_obs.items():
        sorted_paths = [p for _, p in sorted(frame_dict.items())]
        #print(f"[📦] Observation {obs_key}: {len(sorted_paths)} frames")
        observations.append(sorted_paths)

    print(f"[✅] Total unique observations: {len(observations)}")
    return observations

def create_mosaic_video(observations, output_path="mosaic_output_rockfish1.avi"):
    if not observations:
        print("No observations found.")
        return

    # Load one image to determine size
    test_img = cv2.imread(str(observations[0][0]))
    if test_img is None:
        print("Failed to load test image.")
        return

    frame_height, frame_width, _ = test_img.shape
    mosaic_width = frame_width * GRID_SIZE
    mosaic_height = frame_height * GRID_SIZE

    # Prepare video writer
    #fourcc = cv2.VideoWriter_fourcc(*"XVID")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, FRAME_RATE,
                          (mosaic_width, mosaic_height))

    num_tiles = GRID_SIZE * GRID_SIZE
    grid_obs = [-1] * num_tiles      # Which observation is shown in each grid slot
    grid_idx = [0] * num_tiles       # Which frame index for each observation
    used_obs = set()                 # Observation indices already used
    obs_queue = list(range(len(observations)))  # All available observation indices

    frame_count = 0

    while True:
        mosaic = np.zeros((mosaic_height, mosaic_width, 3), dtype=np.uint8)
        active = False

        for i in range(num_tiles):
            row, col = divmod(i, GRID_SIZE)
            y1, y2 = row * frame_height, (row + 1) * frame_height
            x1, x2 = col * frame_width, (col + 1) * frame_width

            # Refill finished slots with next unused observation
            if grid_obs[i] == -1 and obs_queue:
                next_obs = obs_queue.pop(0)
                grid_obs[i] = next_obs
                grid_idx[i] = 0
                used_obs.add(next_obs)

            obs_id = grid_obs[i]
            if obs_id == -1:
                continue

            frames = observations[obs_id]
            f_idx = grid_idx[i]

            if f_idx < len(frames):
                img = cv2.imread(str(frames[f_idx]))
                if img is not None:
                    img = cv2.resize(img, (frame_width, frame_height))
                    mosaic[y1:y2, x1:x2] = img
                    active = True
                grid_idx[i] += 1
            else:
                # Observation done – replace immediately if more are in the queue
                if obs_queue:
                    new_obs = obs_queue.pop(0)
                    grid_obs[i] = new_obs
                    grid_idx[i] = 0

                    new_frames = observations[new_obs]
                    if new_frames:
                        img = cv2.imread(str(new_frames[0]))
                        if img is not None:
                            img = cv2.resize(img, (frame_width, frame_height))
                            mosaic[y1:y2, x1:x2] = img
                        grid_idx[i] += 1
                        active = True
                else:
                    grid_obs[i] = -1

        if not active:
            break

        out.write(mosaic)
        frame_count += 1
        if frame_count % 2000 == 0:
            print(f"[🎞️] {frame_count} mosaic frames written...")

    out.release()
    print(f"[✅] Done. Video saved: {output_path}")

if __name__ == "__main__":
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Select root folder with subdatasets")
    if not folder:
        print("No folder selected.")
    else:
        print("[📁] Scanning...")
        obs = get_all_observations(folder)
        print(f"[🎞️] Loaded {len(obs)} unique observations.")
        create_mosaic_video(obs, "mosaic_output17.avi")