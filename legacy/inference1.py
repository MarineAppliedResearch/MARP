from ultralytics import YOLO
import yolov5
import cv2  # Import OpenCV
import csv  # Import CSV module
import os
import signal
import logging
from huggingface_hub import login
import warnings
import numpy as np
from typing import Union, List, Optional
import torch

# Set your Hugging Face token
#hf_token = "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"
#login(token=hf_token)

# -----------------------------------------------------------------------------
# YOLOv5 class
# -----------------------------------------------------------------------------

class YOLOv5:
    """Wrapper class for loading and running YOLO model"""

    def __init__(self, model_path: str, device: Optional[str] = None):
        # Load the model with yolov5.load to handle the necessary initialization
        self.model = yolov5.load(model_path, device=device)

        # Check if the model is a dict and extract the model
        if isinstance(self.model, dict):
            # Extract model (check your model structure, assuming 'model' is the key)
            self.model = self.model['model']  # This might differ based on how the model is saved

        if device:
            self.model.to(device)

    def __call__(
            self,
            img: Union[str, np.ndarray],
            conf_threshold: float = 0.25,
            iou_threshold: float = 0.45,
            image_size: int = None,
            classes: Optional[List[int]] = None) -> torch.Tensor:
        # Set confidence and IOU thresholds
        self.model.conf = conf_threshold
        self.model.iou = iou_threshold

        if(image_size is None):
            image_size = int(img.shape[0])

        if classes is not None:
            self.model.classes = classes

        # Perform inference
        detections = self.model(img, size=image_size)
        
        return detections


# Suppress warnings from the YOLO model
logging.getLogger("ultralytics").setLevel(logging.ERROR)  # Set logging level to ERROR
logging.getLogger("yolov5").setLevel(logging.CRITICAL)  # Set logging level to ERROR

# Suppress specific warnings from torch (like FutureWarnings)
warnings.filterwarnings("ignore", category=FutureWarning)

# Set the Model Name
#modelName = "mbari-megalodon_3-11-24.pt"
#modelName = "mbari-vulnerable-marine-ecosystems_3-11-24.pt"
modelName = "mbari-midwater-supercategory-detector_5-18-23.pt"

model_vulnerable_marine_ecosystems = YOLO("mbari-vulnerable-marine-ecosystems_3-11-24.pt")  
model_megalodon = YOLO("mbari-megalodon_3-11-24.pt")
#model_midwater_supercategory_detector = yolov5.load("mbari-midwater-supercategory-detector_5-18-23.pt")
model_midwater_supercategory_detector = YOLOv5("mbari-midwater-supercategory-detector_5-18-23.pt", device='cpu')

 

""" # Run batched inference on a list of images
results = model(["1.png", "2.png"])  # return a list of Results objects

# Process results list
for result in results:
    boxes = result.boxes  # Boxes object for bounding box outputs
    masks = result.masks  # Masks object for segmentation masks outputs
    keypoints = result.keypoints  # Keypoints object for pose outputs
    probs = result.probs  # Probs object for classification outputs
    obb = result.obb  # Oriented boxes object for OBB outputs
    result.show()  # display to screen
    result.save(filename="result.png")  # save to disk """



def run_inference_yolov5(model, frame, frame_count):
    """Helper function to execute the inference and return top predictions."""
    
    # Ensure frame is a valid format (NumPy array with 3 channels)
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        print(f"Invalid frame format for frame {frame_count}. Expected (H, W, 3).")
        return None

    # Run the inference
    predictions = model(frame)

    # Debugging: Print raw predictions structure
    print(f"Raw predictions for frame {frame_count}: {predictions}")

    # Check if predictions are available
    if predictions is not None and len(predictions.xyxy) > 0:
        # Extract predictions and convert to a list
        pred_array = predictions.xyxy[0]  # Get the first image predictions
        top_predictions = []
        print("Processing predictions for frame #: " + str(frame_count))

        for pred in pred_array:
            # pred[5]: class, pred[4]: confidence, pred[:4]: bounding box
            class_index = int(pred[5])
            top_predictions.append({
                'class': class_index,  # Class index
                'name': predictions.names.get(class_index, "Unknown"),
                'confidence': float(pred[4]),  # Confidence score
                'bbox': pred[:4].tolist()  # Bounding box [x1, y1, x2, y2]
            })
        
        # Sort by confidence and get the top 3 predictions
        top_predictions = sorted(top_predictions, key=lambda x: x['confidence'], reverse=True)[:3]
        return top_predictions

    print(f"No predictions for frame {frame_count}.")
    return None


def run_inference_yolov11(model, frame, frame_count):
    """Helper function to execute the inference and return top predictions."""

    #results = model(frame, imgsz=(frame.shape[0]*1, frame.shape[1]*1), save_crop=True)
    #results = model(frame, imgsz=(frame.shape[0]/2, frame.shape[1]/2))
    results = model(frame, save_crop=True)

    top_predictions = []

    print("testing frame #: " + str(frame_count))
    
    # Process each result
    for result in results:
        #print("Original Image Shape:", result.orig_shape)
        if result.boxes:  # If bounding boxes were detected
            for box in result.boxes:
                # Extract box coordinates and class info
                # Assuming box.xyxy returns a tensor or array-like object
                coords = box.xyxy.tolist()[0]  # Convert to list and unpack the first set of coordinates
                x1, y1, x2, y2 = coords  # Unpack
                conf = box.conf  # Confidence score
                class_id = int(box.cls)  # Convert tensor to integer
                class_name = result.names[class_id]  # Get class name
                #result.save(filename="video/" + str(frame_count)+"_"+str(class_name)+"_crop.png")
                #print(f"Detected {class_name} with confidence {float(conf)} at [{x1}, {y1}, {x2}, {y2}]")

                # Save our predictions
                top_predictions.append({
                    'class': class_id,  # Class index
                    'name': class_name,
                    'confidence': float(conf),  # Confidence score
                    'bbox': coords  # Bounding box [x1, y1, x2, y2]
                })

    top_predictions = sorted(top_predictions, key=lambda x: x['confidence'], reverse=True)
    return top_predictions

# Function to handle graceful termination
def signal_handler(sig, frame):
    print("Gracefully shutting down...")
    cap.release()
    out.release()
    exit(0)

def choose_inference(frame, frame_count, modelName, model):

    if(modelName == "mbari-midwater-supercategory-detector_5-18-23.pt"):
        return run_inference_yolov5(model, frame, frame_count)
    elif(modelName == "mbari-vulnerable-marine-ecosystems_3-11-24.pt"):
        return run_inference_yolov11(model, frame, frame_count)
    elif(modelName == "mbari-megalodon_3-11-24.pt"):
        return run_inference_yolov11(model, frame, frame_count)
    

def choose_model(m_name):
    model = None

    if(m_name == "mbari-midwater-supercategory-detector_5-18-23.pt"):
        model = model_midwater_supercategory_detector
    elif(m_name == "mbari-vulnerable-marine-ecosystems_3-11-24.pt"):
        model = model_vulnerable_marine_ecosystems
    elif(m_name == "mbari-megalodon_3-11-24.pt"):
        model = model_megalodon

    return model


if __name__ == "__main__":

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Specify the path to your video file
    video_path = "video/testvid1.mp4"  # Update with your video file path

    # Open the video file
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Error: Could not open video.")
        exit()

    # Get the video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if True:

        # Skip the first 300 frames
        skip_frames = 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, skip_frames)

        # Get video filename without extension and create output directory if needed
        video_dir = os.path.dirname(video_path)
        video_filename = os.path.splitext(os.path.basename(video_path))[0]

        # Initialize VideoWriter to save the output video with bounding boxes
        temp_output_video_path = os.path.join(video_dir, f"{video_filename}_temp_output.mp4")
        final_output_video_path = os.path.join(video_dir, f"{video_filename}_output.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Define the codec
        out = cv2.VideoWriter(temp_output_video_path, fourcc, fps, (width, height))

        # CSV file path
        csv_file_path = os.path.join(video_dir, f"{video_filename}_predictions.csv")
        
        # Flag to check if headers are written
        headers_written = False

        frame_count = skip_frames
        while True:

            if(frame_count % 200 == 0):
                print("Skipping Frame: " + str(frame_count))
                out.write(frame)
                frame_count += 1
                continue

            ret, frame = cap.read()  # Read a frame from the video
            if not ret:
                break  # Break the loop if no frame is returned

            # Run inference on the current frame
            model = choose_model(modelName)
            predictions = choose_inference(frame, frame_count, modelName, model)

            if predictions:  # Check if predictions are not None
                print(f"Predictions for frame {frame_count}:")
                for idx, pred in enumerate(predictions):
                    print(f"  {idx + 1}: Name: {pred['name']}, Class: {pred['class']}, Confidence: {pred['confidence']:.2f}, BBox: {pred['bbox']}")
                    
                    # Draw bounding box on the frame
                    x1, y1, x2, y2 = map(int, pred['bbox'])  # Convert bbox coordinates to integers
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)  # Draw rectangle
                    cv2.putText(frame, f"{pred['name']} {pred['confidence']:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)  # Put class name and confidence

                    # Write prediction data to CSV
                    with open(csv_file_path, mode='a', newline='') as csv_file:  # Append to the CSV file
                        csv_writer = csv.writer(csv_file)
                        if not headers_written:  # Write headers only once
                            csv_writer.writerow(['frameNum', 'classNum', 'className', 'confidence', 'x1', 'y1', 'x2', 'y2'])
                            headers_written = True  # Set the flag to indicate headers have been written
                        
                        csv_writer.writerow([frame_count, pred['class'], pred['name'], pred['confidence'], x1, y1, x2, y2])

                # Save the modified frame as an image
                output_filename = os.path.join(video_dir, f"{video_filename}_frame_{frame_count}.png")
                cv2.imwrite(output_filename, frame)  # Save the frame as an image
                print(f"Saved: {output_filename}")


            # Write the frame (with or without bounding boxes) to the video
            out.write(frame)
            frame_count += 1

        # Release the video capture object
        cap.release()
        out.release()

        # Rename the temporary output video to the final output name
        os.rename(temp_output_video_path, final_output_video_path)

        print("Done.")