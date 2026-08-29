from ultralytics import YOLO
import yolov5
import cv2
import csv
import os
import signal
import logging
import warnings
import numpy as np
from typing import Union, List, Optional
import torch
import datetime

class YOLOv5:
    """Wrapper class for loading and running YOLO model"""

    def __init__(self, model_path: str, device: Optional[str] = None):
        self.model = yolov5.load(model_path, device=device)
        if isinstance(self.model, dict):
            self.model = self.model['model']
        if device:
            self.model.to(device)

    def __call__(self, img: Union[str, np.ndarray], conf_threshold: float = 0.25, iou_threshold: float = 0.45, image_size: int = None, classes: Optional[List[int]] = None) -> torch.Tensor:
        self.model.conf = conf_threshold
        self.model.iou = iou_threshold
        if image_size is None:
            image_size = int(img.shape[0])
        if classes is not None:
            self.model.classes = classes
        detections = self.model(img, size=image_size)
        return detections

# Configure logging
logging.getLogger("ultralytics").setLevel(logging.ERROR)
logging.getLogger("yolov5").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=FutureWarning)

# Load models
model_vulnerable_marine_ecosystems = YOLO("mbari-vulnerable-marine-ecosystems_3-11-24.pt")
model_megalodon = YOLO("mbari-megalodon_3-11-24.pt")
model_midwater_supercategory_detector = YOLOv5("mbari-midwater-supercategory-detector_5-18-23.pt", device='cpu')
mbari_benthic_detector = YOLOv5("mbari-mb-benthic-33k.pt", device='cpu')


# Inference function for YOLOv5
def run_inference_yolov5(model, frame, frame_count):
    predictions = model(frame)
    top_predictions = []
    if predictions is not None and len(predictions.xyxy) > 0:
        pred_array = predictions.xyxy[0]
        for pred in pred_array:
            class_index = int(pred[5])
            top_predictions.append({
                'class': class_index,
                'name': predictions.names.get(class_index, "Unknown"),
                'confidence': float(pred[4]),
                'bbox': pred[:4].tolist()
            })
    return sorted(top_predictions, key=lambda x: x['confidence'], reverse=True)[:3]

# Inference function for YOLOv11
def run_inference_yolov11(model, frame, frame_count):
    results = model(frame, save_crop=True)
    top_predictions = []
    for result in results:
        if result.boxes:
            for box in result.boxes:
                coords = box.xyxy.tolist()[0]
                x1, y1, x2, y2 = coords
                conf = box.conf
                class_id = int(box.cls)
                class_name = result.names[class_id]
                top_predictions.append({
                    'class': class_id,
                    'name': class_name,
                    'confidence': float(conf),
                    'bbox': coords
                })
    return sorted(top_predictions, key=lambda x: x['confidence'], reverse=True)

# Frame processing function
def process_frame(frame, frame_count, models, outputs, csv_writers, video_dirs):

    print(str(frame_count) + " frame processing")

    for model_name, model in models:
        frame_copy = frame.copy()  # Create a copy of the frame for each model

        if model_name == "mbari-midwater-supercategory-detector_5-18-23.pt":
            predictions = run_inference_yolov5(model, frame_copy, frame_count)
        elif model_name == "mbari-mb-benthic-33k.pt":
            predictions = run_inference_yolov5(model, frame_copy, frame_count)
        else:
            predictions = run_inference_yolov11(model, frame_copy, frame_count)

        # If predictions are available, draw bounding boxes and write CSV entries
        if predictions:
            for pred in predictions:
                x1, y1, x2, y2 = map(int, pred['bbox'])
                cv2.rectangle(frame_copy, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame_copy, f"{pred['name']} {pred['confidence']:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                csv_writers[model_name].writerow([frame_count, pred['class'], pred['name'], pred['confidence'], x1, y1, x2, y2])

            # Save the annotated frame as an image
            output_filename = os.path.join(video_dirs[model_name], f"{model_name}_frame_{frame_count}.png")
            #cv2.imwrite(output_filename, frame_copy)
            print(f"Predicted: {str(predictions)}")

        # Write the frame to the corresponding video
        outputs[model_name].write(frame_copy)

def signal_handler(sig, frame):
    print("Gracefully shutting down...")
    cap.release()
    for model_name, output in outputs.items():
        output.release()  # Ensure each video writer is released
        temp_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_temp_output.mp4")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        final_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_output_{timestamp}.mp4")

        os.rename(temp_output_video_path, final_output_video_path)
        print(f"Processed video for model: {model_name} has been saved as {final_output_video_path}")

        # Close the corresponding CSV file handle
        if model_name in csv_file_handles:
            csv_file_handles[model_name].close()  # Close the CSV file handle
    exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    video_path = "video/testvid2.mp4"
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Error: Could not open video.")
        exit()

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    video_dir = os.path.dirname(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    models = [
        ("mbari-vulnerable-marine-ecosystems_3-11-24.pt", model_vulnerable_marine_ecosystems),
        ("mbari-megalodon_3-11-24.pt", model_megalodon),
        ("mbari-midwater-supercategory-detector_5-18-23.pt", model_midwater_supercategory_detector),
        ("mbari-mb-benthic-33k.pt", mbari_benthic_detector)
    ]


    outputs = {}
    csv_writers = {}
    csv_file_handles = {}  # Dictionary to hold file handles
    video_dirs = {}

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    for model_name, _ in models:
        video_dirs[model_name] = video_dir
        temp_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_temp_output.mp4")
        final_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_output.mp4")
        csv_file_path = os.path.join(video_dirs[model_name], f"{model_name}_predictions.csv")

        outputs[model_name] = cv2.VideoWriter(temp_output_video_path, fourcc, fps, (width, height))

        csv_file = open(csv_file_path, mode='a', newline='')
        csv_writers[model_name] = csv.writer(csv_file)
        csv_writers[model_name].writerow(['frameNum', 'classNum', 'className', 'confidence', 'x1', 'y1', 'x2', 'y2'])

        # Store the file handle in the dictionary
        csv_file_handles[model_name] = csv_file

    skip_frames = 300
    cap.set(cv2.CAP_PROP_POS_FRAMES, skip_frames)

    frame_count = skip_frames
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        process_frame(frame, frame_count, models, outputs, csv_writers, video_dirs)
        frame_count += 1

    cap.release()
    for model_name, output in outputs.items():
        output.release()
        temp_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_temp_output.mp4")
        final_output_video_path = os.path.join(video_dirs[model_name], f"{model_name}_output.mp4")
        os.rename(temp_output_video_path, final_output_video_path)
        print(f"Done processing for model: {model_name}")

    # Close all CSV file handles at the end
    for model_name in csv_file_handles:
        csv_file_handles[model_name].close()
