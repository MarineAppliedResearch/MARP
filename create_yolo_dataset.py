"""
create_yolo_dataset.py

Author: Isaac Assegai Travers
Date: 11/5/2024

Description:
This script processes video annotations, splits them into training and evaluation datasets,
and creates YOLO-compatible annotation files. The script ensures that all annotations
associated with a specific `observation_id` remain in the same dataset.

Features:
- Reads video annotations via an API.
- Splits annotations into training and evaluation datasets.
- Outputs YOLO-compatible annotation files and organizes them into separate folders.
- Generates corresponding image files from video frames.

Usage Instructions:
1. Ensure that you have the required dependencies installed:
   - OpenCV: Install via 'pip install opencv-python requests'.
2. Adjust the following paths in the script as necessary:
   - `input_video_folder`: Path to your input videos.
   - `output_dataset_folder`: Path where you want to save YOLO datasets.
3. Run the script using the command:
   - 'python create_yolo_dataset.py'

Dependencies:
- Python 3.x
- OpenCV (cv2)
- Requests library (requests)
"""

import os
import random
import cv2
import functions
from database_video_annotations import AnnotationRectangle

# Set the paths for input and output folders
input_video_folder = "input_video"  # Path to input videos
output_dataset_folder = "yolo_dataset"  # Path to output YOLO dataset

# Subfolders for training and evaluation data
train_images_folder = os.path.join(output_dataset_folder, "train", "images")
train_labels_folder = os.path.join(output_dataset_folder, "train", "labels")
eval_images_folder = os.path.join(output_dataset_folder, "eval", "images")
eval_labels_folder = os.path.join(output_dataset_folder, "eval", "labels")

# Create the necessary folders if they don't exist
os.makedirs(train_images_folder, exist_ok=True)
os.makedirs(train_labels_folder, exist_ok=True)
os.makedirs(eval_images_folder, exist_ok=True)
os.makedirs(eval_labels_folder, exist_ok=True)

# Get a list of all video files in the input folder
video_files = [
    f for f in os.listdir(input_video_folder)
    if os.path.isfile(os.path.join(input_video_folder, f)) and f.lower().endswith(('.mp4', '.avi', '.mov'))
]

# Ensure there are videos to process
if not video_files:
    print(f"No video files found in '{input_video_folder}'. Exiting.")
    exit()

# Split observation IDs into training and evaluation sets
observation_ids = set()
annotations_by_video = {}

# Fetch annotations for each video
for video_name in video_files:
    print(f"Fetching annotations for video: {video_name}")
    observations = functions.getObservationsByVideo(video_name)

    for obs in observations:
        observation_ids.add(obs["observation_id"])
        annotations_by_video.setdefault(video_name, []).append(obs)

# Shuffle and split observation IDs
observation_ids = list(observation_ids)
random.shuffle(observation_ids)
split_idx = int(len(observation_ids) * 0.8)  # 80% training, 20% evaluation
train_ids = set(observation_ids[:split_idx])
eval_ids = set(observation_ids[split_idx:])

# Process videos to generate YOLO dataset
for video_name, observations in annotations_by_video.items():
    video_path = os.path.join(input_video_folder, video_name)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: Cannot open video file '{video_path}'. Skipping.")
        continue

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))

    print(f"Processing video: {video_name} (Frames: {total_frames}, FPS: {fps})")

    # Prepare annotations for the current video
    for obs in observations:
        dataset_type = "train" if obs["observation_id"] in train_ids else "eval"
        images_folder = train_images_folder if dataset_type == "train" else eval_images_folder
        labels_folder = train_labels_folder if dataset_type == "train" else eval_labels_folder

        for keyframe in obs["keyframes"]:
            frame_index = keyframe["framenum"]
            annotation = AnnotationRectangle(
                x_center=keyframe["x"],
                y_center=keyframe["y"],
                width_norm=keyframe["width"],
                height_norm=keyframe["height"],
                class_name=keyframe["comname"],
                type=keyframe["type"],
                observation_id=keyframe["observation_id"],
                subset=keyframe["subset"],
                framenum=keyframe["framenum"]
            )

            # Set the frame position and read the frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret:
                print(f"Warning: Cannot read frame {frame_index} from '{video_name}'. Skipping.")
                continue

            # Save the image
            image_filename = f"{video_name}_frame_{frame_index:04d}.jpg"
            image_path = os.path.join(images_folder, image_filename)
            cv2.imwrite(image_path, frame)

            # Save the YOLO label
            label_filename = f"{video_name}_frame_{frame_index:04d}.txt"
            label_path = os.path.join(labels_folder, label_filename)
            with open(label_path, "w") as label_file:
                # YOLO format: <class_id> <x_center> <y_center> <width> <height>
                class_id = 0  # You can map `annotation.class_name` to specific class IDs if needed
                label_file.write(f"{class_id} {annotation.x_center} {annotation.y_center} {annotation.width_norm} {annotation.height_norm}\n")

    cap.release()

print("YOLO dataset has been created successfully!")
