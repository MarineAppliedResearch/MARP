
import sys
sys.path.append('./ByteTrack')  # or the absolute path if needed
import os
import cv2
import csv
import numpy as np
import torch
from concurrent.futures import ThreadPoolExecutor
from ultralytics import YOLO
from tkinter import Tk, filedialog, messagebox
from yolox.tracker.byte_tracker import BYTETracker
from itertools import islice
import math

COMNAME_TO_TAXSERIAL = {
    "California sea cucumber": 158344,
    "Rockfish": 123456,
    "Sea star": 987654,
    # add more...
}


# Alias np.float to handle deprecated usage
if not hasattr(np, 'float'):
    np.float = float

def calculate_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0

class Args:
    def __init__(self):
        self.confidence_threshold = 0.05
        self.track_thresh = 0.05
        self.match_thresh = 0.80
        self.track_buffer = 240
        self.mot20 = True

def select_folder():
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select Folder with Videos")
    root.destroy()
    return folder_path

def batch_videos(video_files, batch_size):
    """Yield successive batches of videos from the list."""
    it = iter(video_files)
    while True:
        batch = list(islice(it, batch_size))
        if not batch:
            break
        yield batch

def process_video(video_path, yolo_model_path, view_videos, position=None, tile_size=None):
    try:
        print(f"Processing video: {os.path.basename(video_path)}")

        # Load a separate YOLO model instance for each thread
        model = YOLO(yolo_model_path).to('cuda' if torch.cuda.is_available() else 'cpu')

        # Create a separate tracker instance for each thread
        tracker = BYTETracker(Args())

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Unable to open video file: {video_path}")
            return

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        model_name = os.path.splitext(os.path.basename(yolo_model_path))[0]  # Strip path and extension

        # Create the output directory based on the model name
        output_folder = os.path.join(os.path.dirname(video_path), model_name)
        os.makedirs(output_folder, exist_ok=True)  # Ensure the folder exists

        # Create output filenames inside the output folder
        base_name = os.path.splitext(os.path.basename(video_path))[0]  # Extract the video filename without extension
        output_video_path = os.path.join(output_folder, f"{base_name}_output.mp4")
        csv_file_path = os.path.join(output_folder, f"{base_name}_output.csv")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_video_path, fourcc, frame_rate, (frame_width, frame_height))

        # Resizing dimensions for live preview
        display_width = frame_width // 2
        display_height = frame_height // 2

        if view_videos:
            window_title = f"{os.path.basename(video_path)} - YOLOv8 Model"
            cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

            if tile_size and position:
                tile_width, tile_height = tile_size
                col, row = position
                cv2.resizeWindow(window_title, tile_width, tile_height)
                cv2.moveWindow(window_title, col * tile_width, row * tile_height)

        with open(csv_file_path, mode='w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(["Frame", "Object Name", "Track_ID", "X", "Y", "Width", "Height", "Confidence"])

            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                #print(f"Processing Frame {frame_idx + 1} of {total_frames} for {os.path.basename(video_path)}...")

                # YOLOv8 detection
                results = model(frame)
                detections = results[0]

                detection_boxes = []
                for i, box in enumerate(detections.boxes.xyxy.cpu().numpy()):
                    x1, y1, x2, y2 = box[:4]
                    confidence = detections.boxes.conf.cpu().numpy()[i]
                    detection_boxes.append([x1, y1, x2, y2, confidence])

                detection_boxes = np.array(detection_boxes) if detection_boxes else np.empty((0, 5))
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
                            if iou > 0.4:
                                track_id_to_class_id[track_id] = (int(detections.boxes.cls.cpu().numpy()[i]), detections.boxes.conf.cpu().numpy()[i])
                                break

                    class_id, confidence = track_id_to_class_id.get(track_id, (-1, 0.0))
                    object_name = model.names[class_id] if class_id != -1 else "Unknown"

                    # Normalize bounding box
                    xCenter = (x1 + x2) / 2 / frame_width
                    yCenter = (y1 + y2) / 2 / frame_height
                    width = (x2 - x1) / frame_width
                    height = (y2 - y1) / frame_height

                    csv_writer.writerow([frame_idx, object_name, track_id, xCenter, yCenter, width, height, confidence])

                    # Draw bounding box and labels
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    cv2.putText(frame, object_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    # Draw the ID and confidence at the bottom of the bounding box
                    label = f"ID: {track_id}, Conf: {confidence:.2f}"
                    cv2.putText(frame, label, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                out.write(frame)

                if view_videos:
                    # Display the frame without resizing manually
                    cv2.imshow(window_title, frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print(f"User terminated video preview for {os.path.basename(video_path)}.")
                        break

                frame_idx += 1

        cap.release()
        out.release()
        if view_videos:
            cv2.destroyWindow(window_title)
        print(f"Processing complete for {os.path.basename(video_path)}")
        print(f"Results saved to:\nVideo: {output_video_path}\nCSV: {csv_file_path}")

    except Exception as e:
        print(f"Error processing video {video_path}: {e}")




from concurrent.futures import ThreadPoolExecutor, as_completed

def main():
    print("Please select the folder containing videos...")
    video_folder = select_folder()
    if not video_folder:
        print("No folder selected. Exiting...")
        return

    print("Please select your YOLOv8 model file...")
    yolo_model_path = filedialog.askopenfilename(
        title="Select YOLOv8 Model",
        filetypes=[("YOLOv8 Model", "*.pt")]
    )
    if not yolo_model_path:
        print("No YOLO model selected. Exiting...")
        return

    view_videos = messagebox.askyesno("View Videos", "Do you want to view the videos while processing?")

    video_files = [
        os.path.join(video_folder, f)
        for f in os.listdir(video_folder)
        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
    ]

    if not video_files:
        print("No video files found in the selected folder.")
        return

    print(f"Found {len(video_files)} video(s) in the folder. Starting processing in batches of 2...")

    screen_width, screen_height = 1920, 1080  # adjust or detect
    batch_size = 5
    cols = math.ceil(math.sqrt(batch_size))
    rows = math.ceil(batch_size / cols)
    tile_size = (screen_width // cols, screen_height // rows)

    for batch in batch_videos(video_files, batch_size):
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = []
            for idx, video in enumerate(batch):
                col = idx % cols
                row = idx // cols
                futures.append(executor.submit(
                    process_video,
                    video,
                    yolo_model_path,
                    view_videos,
                    (col, row),
                    tile_size
                ))



if __name__ == "__main__":
    main()
