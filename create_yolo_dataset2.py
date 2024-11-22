"""
create_yolo_dataset.py

Author: Isaac Assegai Travers
Date: 11/5/2024

Description:
This script processes video annotations, splits them into training and evaluation datasets,
and creates YOLO-compatible annotation files. It ensures that all annotations associated
with a specific `observation_id` remain in the same dataset. Additionally, it interpolates
annotations for frames between keyframes and generates a `classnames.yaml` file for mapping
class names to IDs.

Features:
- Reads video annotations via an API.
- Splits annotations into training and evaluation datasets.
- Interpolates annotations for frames between keyframes.
- Outputs YOLO-compatible annotation files and organizes them into separate folders.
- Generates a `classnames.yaml` file for mapping class names to IDs.

Usage Instructions:
1. Install dependencies: 'pip install opencv-python requests pyyaml'.
2. Adjust paths for input videos and output dataset folders as necessary.
3. Run the script: 'python create_yolo_dataset.py'.

Dependencies:
- Python 3.x
- OpenCV (cv2)
- Requests library (requests)
- PyYAML (yaml)
"""

import os
import random
import cv2
import yaml
from database_video_annotations import AnnotationRectangle, DatabaseVideoAnnotationsRangeFinder
import functions

# Set paths for input videos and output dataset folders
input_video_folder = "input_video"
output_dataset_folder = "yolo_dataset"
classnames_file = os.path.join(output_dataset_folder, "classnames.yaml")

# Subfolders for training and evaluation data
human_review_folder = os.path.join(output_dataset_folder, "for_human_review")
train_images_folder = os.path.join(output_dataset_folder, "train", "images")
train_labels_folder = os.path.join(output_dataset_folder, "train", "labels")
eval_images_folder = os.path.join(output_dataset_folder, "eval", "images")
eval_labels_folder = os.path.join(output_dataset_folder, "eval", "labels")
human_review_folder = os.path.join(output_dataset_folder, "for_human_review")


# Create necessary folders
os.makedirs(train_images_folder, exist_ok=True)
os.makedirs(train_labels_folder, exist_ok=True)
os.makedirs(eval_images_folder, exist_ok=True)
os.makedirs(eval_labels_folder, exist_ok=True)
os.makedirs(human_review_folder, exist_ok=True)


# Get video files
video_files = [
    f for f in os.listdir(input_video_folder)
    if os.path.isfile(os.path.join(input_video_folder, f)) and f.lower().endswith(('.mp4', '.avi', '.mov'))
]

if not video_files:
    print(f"No video files found in '{input_video_folder}'. Exiting.")
    exit()

# Extract unique class names
unique_classnames = set()

# Split observation IDs into training and evaluation sets
observation_ids = set()
annotations_by_video = {}

for video_name in video_files:
    print(f"Fetching annotations for video: {video_name}")
    observations = functions.getObservationsByVideo(video_name)

    for obs in observations:
        observation_ids.add(obs["observation_id"])
        annotations_by_video.setdefault(video_name, []).append(obs)

        # Extract unique class names
        for keyframe in obs["keyframes"]:
            unique_classnames.add(keyframe["comname"])

# Write class names to classnames.yaml
classnames_list = sorted(unique_classnames)  # Sort class names for consistent ordering
classnames_to_ids = {classname: idx for idx, classname in enumerate(classnames_list)}  # Map to IDs

classnames_data = {
    "names": classnames_list,  # List of class names
    "nc": len(classnames_list),  # Number of classes
    "train": os.path.abspath(train_images_folder),  # Absolute path to training images folder
    "val": os.path.abspath(eval_images_folder)  # Absolute path to evaluation images folder
}

# Save the data to classnames.yaml
with open(classnames_file, "w") as yaml_file:
    yaml.dump(classnames_data, yaml_file)

print(f"Class names and dataset paths saved to {classnames_file}")

# Shuffle and split observation IDs
observation_ids = list(observation_ids)
random.shuffle(observation_ids)
split_idx = int(len(observation_ids) * 0.8)
train_ids = set(observation_ids[:split_idx])
eval_ids = set(observation_ids[split_idx:])

# Subfolder for human review, organized by class_name
human_review_folder = os.path.join(output_dataset_folder, "for_human_review")
os.makedirs(human_review_folder, exist_ok=True)

# Process videos
for video_name, observations in annotations_by_video.items():
    video_path = os.path.join(input_video_folder, video_name)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: Cannot open video file '{video_path}'. Skipping.")
        continue

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Prepare annotations
    annotations_by_frame = {}
    range_finder = DatabaseVideoAnnotationsRangeFinder()

    for obs in observations:
        for keyframe in obs["keyframes"]:
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
            annotations_by_frame.setdefault(annotation.framenum, []).append(annotation)

    # Reload range finder
    range_finder.reload(annotations_by_frame)

    # Process each frame
    frame_index = 0
    while frame_index < total_frames:
        ret, frame = cap.read()

        if not ret:
            break

        # Provide a progress update every 200 frames
        if frame_index % 50 == 0:
            functions.printSymbolBasedOnProgress(".", frame_index, total_frames)

        # Track annotations for the current frame
        target_annotations = {}

        # Get annotations for the current frame if available
        if frame_index in annotations_by_frame:
            for annotation in annotations_by_frame[frame_index]:
                key = f"{annotation.observation_id}_{annotation.subset}"
                target_annotations[key] = annotation

        # Add interpolated annotations for the current frame
        surrounding_annotations = range_finder.get_surrounding_annotations(frame_index)
        for key, (previous, next_frame) in surrounding_annotations.items():
            if key in target_annotations:
                continue

            if previous and next_frame:
                # Perform interpolation
                ratio = (frame_index - previous.framenum) / (next_frame.framenum - previous.framenum)
                new_annotation = AnnotationRectangle(
                    x_center=previous.x_center + ratio * (next_frame.x_center - previous.x_center),
                    y_center=previous.y_center + ratio * (next_frame.y_center - previous.y_center),
                    width_norm=previous.width_norm + ratio * (next_frame.width_norm - previous.width_norm),
                    height_norm=previous.height_norm + ratio * (next_frame.height_norm - previous.height_norm),
                    class_name=previous.class_name,
                    type="interpolated",
                    observation_id=previous.observation_id,
                    subset=previous.subset,
                    framenum=frame_index
                )
                target_annotations[key] = new_annotation

        # Only save the frame and labels if annotations exist for this frame
        if target_annotations:
            dataset_type = "train" if any(annotation.observation_id in train_ids for annotation in target_annotations.values()) else "eval"
            images_folder = train_images_folder if dataset_type == "train" else eval_images_folder
            labels_folder = train_labels_folder if dataset_type == "train" else eval_labels_folder

            # Save the image
            image_filename = f"{video_name}_frame_{frame_index:04d}.jpg"
            image_path = os.path.join(images_folder, image_filename)
            cv2.imwrite(image_path, frame)

            # Save the YOLO label
            label_filename = f"{video_name}_frame_{frame_index:04d}.txt"
            label_path = os.path.join(labels_folder, label_filename)
            with open(label_path, "w") as label_file:
                for annotation in target_annotations.values():
                    class_id = classnames_to_ids[annotation.class_name]
                    label_file.write(f"{class_id} {annotation.x_center} {annotation.y_center} {annotation.width_norm} {annotation.height_norm} \n")

                    # Extract the bounding box for human review
                    x_center_px = int(annotation.x_center * width)
                    y_center_px = int(annotation.y_center * height)
                    box_width_px = int(annotation.width_norm * width)
                    box_height_px = int(annotation.height_norm * height)

                    x1 = max(0, int(x_center_px - box_width_px / 2))
                    y1 = max(0, int(y_center_px - box_height_px / 2))
                    x2 = min(width, int(x_center_px + box_width_px / 2))
                    y2 = min(height, int(y_center_px + box_height_px / 2))

                    # Crop the annotation region from the frame
                    cropped_annotation = frame[y1:y2, x1:x2]

                    # Create class-specific subfolder in `for_human_review`
                    class_folder = os.path.join(human_review_folder, annotation.class_name)
                    os.makedirs(class_folder, exist_ok=True)

                    # Save the cropped annotation
                    human_review_filename = f"{video_name}_frame_{frame_index:04d}_{annotation.observation_id}_{annotation.subset}.jpg"
                    human_review_path = os.path.join(class_folder, human_review_filename)
                    cv2.imwrite(human_review_path, cropped_annotation)

        frame_index += 1

    cap.release()

print("\nYOLO dataset and human review images have been created successfully!")
