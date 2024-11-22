"""
Script to perform object tracking using ByteTrack and YOLOv8 on a user-selected video.
The script allows the user to select the YOLOv8 model and a video dynamically through a file selection dialog.
It uses ByteTrack to track detected objects across frames.
The script checks for GPU availability and uses CUDA if available, otherwise falls back to CPU.

Features:
1. Uses YOLOv8 for detection.
2. Integrates ByteTrack for tracking across frames.
3. Allows dynamic file selection for both model and video files.
4. Outputs annotated video and tracking results in CSV format.
"""

from ultralytics import YOLO
import cv2
import csv
import os
import signal
import logging
import warnings
import numpy as np
import torch
import tkinter as tk
from tkinter import filedialog
from yolox.tracker.byte_tracker import BYTETracker  # ByteTrack tracker import


def check_device():
    """
    Checks if a GPU (CUDA) is available and returns the appropriate device.
    Returns:
        str: "cuda" if GPU is available, otherwise "cpu".
    """
    return "cuda" if torch.cuda.is_available() else "cpu"


def select_file(title, filetypes):
    """
    Opens a file selection dialog and returns the chosen file path.
    Args:
        title (str): Title of the dialog window.
        filetypes (list): List of allowed file types in the format [("Description", "*.ext")].
    Returns:
        str: Path to the selected file.
    """
    root = tk.Tk()
    root.withdraw()  # Hide the root tkinter window
    filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
    return filepath


if __name__ == "__main__":
    # Configure logging and warnings
    logging.getLogger("ultralytics").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=FutureWarning)

    # Handle graceful shutdown via SIGINT
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # Check device availability
    device = check_device()
    print(f"Using device: {device}")

    # File selection for model
    model_path = select_file("Select YOLO Model File", [("YOLO Model Files", "*.pt"), ("All Files", "*.*")])
    if not model_path:
        print("No model selected. Exiting...")
        exit()

    # Load the YOLOv8 model
    model = YOLO(model_path)

    # File selection for video
    video_path = select_file("Select Video File", [("Video Files", "*.mp4;*.avi;*.mov"), ("All Files", "*.*")])
    if not video_path:
        print("No video selected. Exiting...")
        exit()

    # Open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video.")
        exit()

    # Video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Output paths
    video_dir = os.path.dirname(video_path)
    output_video_path = os.path.join(video_dir, f"{os.path.basename(model_path).split('.')[0]}_output_tracking.mp4")
    csv_file_path = os.path.join(video_dir, f"{os.path.basename(model_path).split('.')[0]}_tracking.csv")

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output_video = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    # Open CSV file for writing tracking results
    csv_file = open(csv_file_path, mode='a', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['frameNum', 'trackID', 'classNum', 'className', 'confidence', 'x1', 'y1', 'x2', 'y2'])

    # Initialize ByteTrack
    tracker = BYTETracker()

    frame_count = 0
    print("Starting video processing...")
    while True:
        # Read the next frame
        ret, frame = cap.read()
        if not ret:
            break

        # Run inference on the frame
        results = model(frame)
        predictions = []
        for result in results:
            if result.boxes:
                for box in result.boxes:
                    coords = box.xyxy.tolist()[0]
                    x1, y1, x2, y2 = map(int, coords)
                    predictions.append({
                        'class': int(box.cls),
                        'name': result.names[int(box.cls)],
                        'confidence': float(box.conf),
                        'bbox': (x1, y1, x2, y2)
                    })

        # Format detections for ByteTrack
        detections = []
        for pred in predictions:
            x1, y1, x2, y2 = pred['bbox']
            detections.append([x1, y1, x2, y2, pred['confidence'], pred['class']])

        # Update tracker
        tracked_objects = tracker.update(np.array(detections), frame.shape)

        # Annotate frame and write tracking results
        for obj in tracked_objects:
            track_id = obj.track_id
            x1, y1, x2, y2 = map(int, obj.tlbr)
            class_id = obj.cls
            confidence = obj.score
            class_name = obj.name

            # Draw bounding box and track ID
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {track_id} {class_name} {confidence:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Write to CSV
            csv_writer.writerow([frame_count, track_id, class_id, class_name, confidence, x1, y1, x2, y2])

        # Write the annotated frame to the output video
        output_video.write(frame)
        frame_count += 1

    # Cleanup
    print("Processing complete. Cleaning up...")
    cap.release()
    output_video.release()
    csv_file.close()

    print(f"Output saved: {output_video_path}")
    print(f"Tracking results saved: {csv_file_path}")
