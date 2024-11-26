"""
Object Tracking with YOLOv8 and BYTETracker
===========================================

This script performs object detection using YOLOv8 and tracks objects across video frames using BYTETracker. 
The results are saved in an output video with bounding boxes, object names, and tracking IDs. Additionally, 
a CSV file is generated with frame-by-frame tracking details.

Inputs:
- YOLOv8 model (.pt file)
- Video file for tracking (.mp4, .avi, etc.)

Outputs:
- Annotated video with "_output" appended to the filename
- CSV file with "_output.csv" appended to the filename

CSV Columns:
- Frame: The frame number
- Object Name: Name of the detected object (e.g., "person", "car")
- Track_ID: The unique ID assigned by BYTETracker
- X: Normalized x-center of the bounding box
- Y: Normalized y-center of the bounding box
- Width: Normalized width of the bounding box
- Height: Normalized height of the bounding box
"""

import numpy as np
import cv2
import os
import csv
from ultralytics import YOLO
from tkinter import Tk, filedialog
from yolox.tracker.byte_tracker import BYTETracker

# Alias np.float to the built-in float to handle deprecated usage
if not hasattr(np, 'float'):
    np.float = float

def calculate_iou(box1, box2):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.

    Parameters:
    - box1: Tuple (x1, y1, x2, y2) representing the first box
    - box2: Tuple (x1, y1, x2, y2) representing the second box

    Returns:
    - IoU value (float): Intersection over Union
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    # Calculate the area of overlap
    intersection = max(0, x2 - x1) * max(0, y2 - y1)

    # Calculate the area of each rectangle
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])

    # Calculate the union area
    union = area1 + area2 - intersection

    # Avoid division by zero and return IoU
    return intersection / union if union > 0 else 0


def select_file(file_type, file_extensions):
    """
    Opens a file dialog to select a file.

    Parameters:
    - file_type (str): Description of the file type (e.g., "YOLOv8 model")
    - file_extensions (str): File extensions to filter (e.g., "*.pt")

    Returns:
    - str: Path to the selected file
    """
    root = Tk()
    root.withdraw()  # Hide the root window
    file_path = filedialog.askopenfilename(
        title=f"Select {file_type}",
        filetypes=[(f"{file_type} files", file_extensions)]
    )
    root.destroy()  # Destroy the root window after selection
    return file_path


class Args:
    """
    Custom arguments for BYTETracker.
    """
    def __init__(self):
        self.track_thresh = 0.5
        self.match_thresh = 0.8
        self.track_buffer = 30
        self.mot20 = False


# Step 1: Ask the user to select the YOLOv8 model file
print("Please select your YOLOv8 model file...")
yolo_model_path = select_file("YOLOv8 model", "*.pt")
if not yolo_model_path:
    print("No YOLO model selected. Exiting...")
    exit()

# Step 2: Ask the user to select the video file
print("Please select the video file for tracking...")
video_path = select_file("video", "*.mp4 *.avi *.mov")
if not video_path:
    print("No video file selected. Exiting...")
    exit()

# Step 3: Load the selected YOLOv8 model
print(f"Loading YOLOv8 model from: {yolo_model_path}")
model = YOLO(yolo_model_path)

# Step 4: Initialize BYTETracker for object tracking
tracker = BYTETracker(Args())

# Step 5: Open the selected video file
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print(f"Error: Unable to open video file: {video_path}")
    exit()

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
frame_rate = int(cap.get(cv2.CAP_PROP_FPS))

# Create output video filename
output_video_path = os.path.splitext(video_path)[0] + "_output.mp4"
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_video_path, fourcc, frame_rate, (frame_width, frame_height))

# Create output CSV filename
csv_file_path = os.path.splitext(video_path)[0] + "_output.csv"

# Open the CSV file for writing
with open(csv_file_path, mode='w', newline='') as csvfile:
    csv_writer = csv.writer(csvfile)
    # Write CSV header
    csv_writer.writerow(["Frame", "Object Name", "Track_ID", "X", "Y", "Width", "Height"])

    frame_idx = 0  # Frame counter

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("End of video reached or failed to read frame.")
            break

        # Step 7: Run YOLOv8 detection on the current frame
        results = model(frame)
        detections = results[0]

        detection_boxes = []
        for i, box in enumerate(detections.boxes.xyxy.cpu().numpy()):
            x1, y1, x2, y2 = box[:4]
            confidence = detections.boxes.conf.cpu().numpy()[i]
            detection_boxes.append([x1, y1, x2, y2, confidence])

        if len(detection_boxes) > 0:
            detection_boxes = np.array(detection_boxes)
        else:
            detection_boxes = np.empty((0, 5))

        # Update tracker with detections
        img_info = [frame_height, frame_width]
        tracked_objects = tracker.update(detection_boxes, img_info, (frame_height, frame_width))

        track_id_to_class_id = {}

        for track in tracked_objects:
            x1, y1, x2, y2 = map(int, track.tlbr)
            track_id = track.track_id

            if track_id not in track_id_to_class_id:
                for i, det_box in enumerate(detections.boxes.xyxy.cpu().numpy()):
                    det_x1, det_y1, det_x2, det_y2 = det_box[:4]
                    iou = calculate_iou((x1, y1, x2, y2), (det_x1, det_y1, det_x2, det_y2))
                    if iou > 0.5:
                        track_id_to_class_id[track_id] = int(detections.boxes.cls.cpu().numpy()[i])
                        break

            class_id = track_id_to_class_id.get(track_id, -1)
            object_name = model.names[class_id] if class_id != -1 else "Unknown"

            xCenter = (x1 + x2) / 2 / frame_width
            yCenter = (y1 + y2) / 2 / frame_height
            width = (x2 - x1) / frame_width
            height = (y2 - y1) / frame_height

            csv_writer.writerow([frame_idx, object_name, track_id, xCenter, yCenter, width, height])

            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, object_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            # Draw the ID and confidence at the bottom of the bounding box
            label = f"ID: {track_id}, Conf: {confidence:.2f}"
            cv2.putText(frame, label, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        out.write(frame)
        cv2.imshow('Object Tracking with BYTETracker', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("User terminated the process.")
            break

        frame_idx += 1

cap.release()
out.release()
cv2.destroyAllWindows()

print(f"Tracking complete. Results saved to:\nVideo: {output_video_path}\nCSV: {csv_file_path}")
