import cv2
import os
import numpy as np
from pathlib import Path
from tkinter import Tk, filedialog
import functions

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

def create_mosaic_video(base_folder, output_file="mosaic_video.avi", frame_rate=10):
    """
    Create a mosaic video from observation frames.

    Parameters:
        base_folder (str): Path to the folder containing subfolders of observations.
        output_file (str): Name of the output video file.
        frame_rate (int): Frame rate for the output video.
    """
    observation_folders = get_observation_folders(base_folder)

    if not observation_folders:
        print("No observation folders found in the specified directory.")
        return

    # Load all frames from each observation folder, grouped by observation key
    observations = []
    i = 0
    for folder in observation_folders:
        grouped_frames = get_frames_for_observation(folder)
        for key, frames in grouped_frames.items():
            if(i % 500 == 0):
                print(".", end="")
            if frames:
                i = i + 1
                observations.append([cv2.imread(str(frame)) for frame in frames])

    if not observations:
        print("No frames found in the observation folders.")
        return

    # Define output video dimensions
    video_width = 1920
    video_height = 1080


    # Calculate frame dimensions for observations
    frame_width = video_width // 8
    frame_height = video_height // 8

    print("Resizing all observations.")

    # Resize all frames to match the standard size for the outline
    for obs_idx, obs in enumerate(observations):
        observations[obs_idx] = [cv2.resize(frame, (frame_width, frame_height)) for frame in obs]

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_file, fourcc, frame_rate, (video_width, video_height))

    # Track observations currently playing in each grid cell
    outline_cells = []

    # Top row
    for col in range(video_width // frame_width):
        outline_cells.append((0, col * frame_width))
    # Right column
    for row in range(1, video_height // frame_height - 1):
        outline_cells.append((row * frame_height, video_width - frame_width))
    # Bottom row
    for col in range(video_width // frame_width - 1, -1, -1):
        outline_cells.append((video_height - frame_height, col * frame_width))
    # Left column
    for row in range(video_height // frame_height - 2, 0, -1):
        outline_cells.append((row * frame_height, 0))

    grid_observations = [-1] * len(outline_cells)
    available_observations = list(range(len(observations)))

    max_frames = max(len(obs) for obs in observations)

    for frame_idx in range(max_frames):
        # Create a blank frame
        mosaic_frame = np.zeros((video_height, video_width, 3), dtype=np.uint8)

        if(frame_idx % 25 == 0):
            functions.printSymbolBasedOnProgress(".", frame_idx, max_frames)

        for idx, (y_start, x_start) in enumerate(outline_cells):
            y_end = y_start + frame_height
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
    output_file = "mosaic_video7.avi"
    create_mosaic_video(base_folder, output_file)
