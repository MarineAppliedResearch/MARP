import cv2
import os
import numpy as np
from pathlib import Path
from tkinter import Tk, filedialog

def get_observation_folders(base_folder):
    """Get all subfolders containing observation images."""
    return [subfolder for subfolder in Path(base_folder).iterdir() if subfolder.is_dir()]

def group_frames_by_observation(frames):
    """Group frames by observation key extracted from filenames."""
    observations = {}
    for frame in frames:
        key = '_'.join(frame.stem.split('_')[:2])  # Extract the observation key (first part of the filename before the second underscore)
        if key not in observations:
            observations[key] = []
        observations[key].append(frame)
    # Sort frames for each observation
    for key in observations:
        observations[key] = sorted(observations[key])
    return observations

def get_frames_for_observation(observation_folder):
    """Get all image frames grouped by observation key in an observation folder."""
    frames = sorted(observation_folder.glob("*.jpg"))
    return group_frames_by_observation(frames)

def create_mosaic_video(base_folder, output_file="mosaic_video2.avi", frame_rate=8, grid_size=4):
    """
    Create a mosaic video from observation frames.

    Parameters:
        base_folder (str): Path to the folder containing subfolders of observations.
        output_file (str): Name of the output video file.
        frame_rate (int): Frame rate for the output video.
        grid_size (int): Fixed grid size for the mosaic (e.g., 20x20).
    """
    observation_folders = get_observation_folders(base_folder)

    if not observation_folders:
        print("No observation folders found in the specified directory.")
        return

    # Load all frames from each observation folder, grouped by observation key
    observations = []
    for folder in observation_folders:
        grouped_frames = get_frames_for_observation(folder)
        for key, frames in grouped_frames.items():
            if frames:
                observations.append([cv2.imread(str(frame)) for frame in frames])

    if not observations:
        print("No frames found in the observation folders.")
        return

    # Get frame dimensions from the first frame of the first observation
    # This will be the standard size for all frames
    frame_height, frame_width, _ = observations[0][0].shape

    # Resize all frames to match the standard size
    for obs_idx, obs in enumerate(observations):
        observations[obs_idx] = [cv2.resize(frame, (frame_width, frame_height)) for frame in obs]

    # Determine output video dimensions
    mosaic_height = frame_height * grid_size
    mosaic_width = frame_width * grid_size

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_file, fourcc, frame_rate, (mosaic_width, mosaic_height))

    # Track observations currently playing in each grid cell
    grid_observations = [-1] * (grid_size * grid_size)
    available_observations = list(range(len(observations)))

    max_frames = max(len(obs) for obs in observations)

    for frame_idx in range(max_frames):
        mosaic_frame = np.zeros((mosaic_height, mosaic_width, 3), dtype=np.uint8)

        for idx in range(grid_size * grid_size):
            row = idx // grid_size
            col = idx % grid_size

            y_start = row * frame_height
            y_end = y_start + frame_height
            x_start = col * frame_width
            x_end = x_start + frame_width

            if grid_observations[idx] == -1 and available_observations:
                # Assign a new observation to this grid cell if available
                grid_observations[idx] = available_observations.pop(0)

            if grid_observations[idx] != -1:
                current_obs_idx = grid_observations[idx]
                current_obs = observations[current_obs_idx]

                if frame_idx < len(current_obs):
                    mosaic_frame[y_start:y_end, x_start:x_end] = current_obs[frame_idx]
                else:
                    # Mark this grid cell as available when observation finishes
                    grid_observations[idx] = -1
                    if current_obs_idx not in available_observations:
                        available_observations.append(current_obs_idx)

        out.write(mosaic_frame)

    out.release()
    print(f"Mosaic video saved as {output_file}")

if __name__ == "__main__":
    root = Tk()
    root.withdraw()  # Hide the root window
    base_folder = filedialog.askdirectory(title="Select Folder Containing Observation Subfolders")
    if not base_folder:
        print("No folder selected. Exiting.")
        exit()
    output_file = "mosaic_video2.avi"
    create_mosaic_video(base_folder, output_file)