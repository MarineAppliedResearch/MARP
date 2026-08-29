import numpy as np
import cv2
import os
import csv
from ultralytics import YOLO
from tkinter import Tk, filedialog
from yolox.tracker.byte_tracker import BYTETracker
from multiprocessing import Pool, cpu_count

# Alias np.float to the built-in float to handle deprecated usage
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

def select_folder():
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select Folder with Videos")
    root.destroy()
    return folder_path

class Args:
    def __init__(self):
        self.track_thresh = 0.5
        self.match_thresh = 0.8
        self.track_buffer = 30
        self.mot20 = False

def process_video(video_path, model_path):
    try:
        print(f"Processing video: {os.path.basename(video_path)}")
        
        # Initialize YOLO model and BYTETracker
        model = YOLO(model_path)
        tracker = BYTETracker(Args())

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Unable to open video file: {video_path}")
            return

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Create output filenames
        output_video_path = os.path.splitext(video_path)[0] + "_output.mp4"
        csv_file_path = os.path.splitext(video_path)[0] + "_output.csv"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_video_path, fourcc, frame_rate, (frame_width, frame_height))

        with open(csv_file_path, mode='w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(["Frame", "Object Name", "Track_ID", "X", "Y", "Width", "Height"])

            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                print(f"Processing Frame {frame_idx + 1} of {total_frames} for {os.path.basename(video_path)}...")

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
                            if iou > 0.5:
                                track_id_to_class_id[track_id] = int(detections.boxes.cls.cpu().numpy()[i])
                                break

                    class_id = track_id_to_class_id.get(track_id, -1)
                    object_name = model.names[class_id] if class_id != -1 else "Unknown"

                    # Normalize bounding box
                    xCenter = (x1 + x2) / 2 / frame_width
                    yCenter = (y1 + y2) / 2 / frame_height
                    width = (x2 - x1) / frame_width
                    height = (y2 - y1) / frame_height

                    csv_writer.writerow([frame_idx, object_name, track_id, xCenter, yCenter, width, height])

                    # Draw bounding box and labels
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    cv2.putText(frame, object_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    # Draw the ID and confidence at the bottom of the bounding box
                    label = f"ID: {track_id}, Conf: {confidence:.2f}"
                    cv2.putText(frame, label, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                out.write(frame)
                frame_idx += 1

        cap.release()
        out.release()
        print(f"Processing complete for {os.path.basename(video_path)}")
        print(f"Results saved to:\nVideo: {output_video_path}\nCSV: {csv_file_path}")

    except Exception as e:
        print(f"Error processing video {video_path}: {e}")

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

    video_files = [
        os.path.join(video_folder, f)
        for f in os.listdir(video_folder)
        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
    ]

    if not video_files:
        print("No video files found in the selected folder.")
        return

    print(f"Found {len(video_files)} video(s) in the folder. Starting processing...")

    # Use multiprocessing to process videos concurrently
    with Pool(cpu_count()) as pool:
        pool.starmap(process_video, [(video, yolo_model_path) for video in video_files])

if __name__ == "__main__":
    main()
