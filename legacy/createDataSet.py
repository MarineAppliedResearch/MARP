import os
import cv2
import requests
import random
import yaml

# Function to convert mediaPosition to seconds
def media_position_to_seconds(media_position):
    try:
        time_parts = media_position.split(':')
        if len(time_parts) != 3:
            raise ValueError(f"Invalid mediaPosition format: {media_position}")
        hours = int(time_parts[0])
        minutes = int(time_parts[1])
        seconds = float(time_parts[2])
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds
    except ValueError as e:
        print(f"Error parsing mediaPosition '{media_position}': {e}")
        return None

# Function to extract a frame from a video at a specific time
def extract_frame(video_path, time_in_seconds, output_path):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_in_seconds * 1000)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_path, frame)
        print(f"Saved frame at {time_in_seconds}s to {output_path}")
    else:
        print(f"Failed to extract frame at {time_in_seconds}s from {video_path}")
    cap.release()

# Function to parse the annotation string into a list of annotations
def parse_annotation(annotation_str):
    annotations = []
    object_strs = annotation_str.strip().split('-')
    for obj_str in object_strs:
        coords = obj_str.strip().split('_')
        if len(coords) != 4:
            print(f"Invalid annotation format: {obj_str}")
            continue
        x_center = float(coords[0])
        y_center = float(coords[1])
        width = float(coords[2])
        height = float(coords[3])
        annotations.append((x_center, y_center, width, height))
    return annotations

# Function to write the YOLO annotation file
def write_yolo_annotation(output_path, annotations, class_id):
    with open(output_path, 'w') as f:
        for ann in annotations:
            x_center, y_center, width, height = ann
            # Ensure the values are between 0 and 1
            x_center = min(max(x_center, 0), 1)
            y_center = min(max(y_center, 0), 1)
            width = min(max(width, 0), 1)
            height = min(max(height, 0), 1)
            f.write(f"{class_id} {x_center} {y_center} {width} {height}\n")

# Path to the input_video folder
input_video_folder = 'input_video'  # Adjust the path if necessary

# Define a tuple of video file extensions to filter video files
video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')

# Get a list of all video files in the input_video folder
try:
    all_files = os.listdir(input_video_folder)
except FileNotFoundError:
    print(f"The folder '{input_video_folder}' does not exist.")
    all_files = []

# Filter the list to include only video files
video_files = [
    file_name for file_name in all_files
    if os.path.isfile(os.path.join(input_video_folder, file_name))
    and file_name.lower().endswith(video_extensions)
]

# API endpoint base URL
api_base_url = 'http://localhost:3081/api/getObservationsByVideo'

# Dictionary to map combined class names (comname + taxserial) to class IDs
classname_to_class_id = {}
current_class_id = 0

# List to store all observations across all videos
all_observations = []

# Process each video file
for video_name in video_files:
    print(f"Processing video: {video_name}")
    
    # Set up the parameters for the GET request
    params = {'videoName': video_name}
    
    try:
        # Make the GET request to the API endpoint
        response = requests.get(api_base_url, params=params)
        
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        
        # Parse the response data as JSON
        observations = response.json()
        
        if not observations:
            print(f"No observations found for video '{video_name}'.")
            continue
        
        # Add observations to the global list
        all_observations.extend(observations)
        
        # Map class names (comname + taxserial) to class IDs
        for obs in observations:
            comname = obs['comname']
            taxserial = obs['taxserial']
            classname = f"{comname}_{taxserial}"  # Combine comname and taxserial to form classname
            
            if classname not in classname_to_class_id:
                classname_to_class_id[classname] = current_class_id
                current_class_id += 1
                
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred for '{video_name}': {http_err}")
    except requests.exceptions.RequestException as err:
        print(f"Error occurred for '{video_name}': {err}")
    except Exception as e:
        print(f"An unexpected error occurred for '{video_name}': {e}")

# Check if any observations were retrieved
if not all_observations:
    print("No observations were retrieved from the API.")
    exit()

# Create necessary directories
os.makedirs('dataset/images/train', exist_ok=True)
os.makedirs('dataset/images/val', exist_ok=True)
os.makedirs('dataset/labels/train', exist_ok=True)
os.makedirs('dataset/labels/val', exist_ok=True)

# Shuffle and split observations into training and validation sets
random.shuffle(all_observations)
split_index = int(0.8 * len(all_observations))
train_obs = all_observations[:split_index]
val_obs = all_observations[split_index:]

# Process observations function
def process_observations(observations, image_dir, label_dir):
    for obs in observations:
        video_path = obs['videoLocation']
        media_position = obs['mediaPosition']
        time_in_seconds = media_position_to_seconds(media_position)
        observation_id = obs['observation_id']
        
        # Ensure the video file exists
        if not os.path.isfile(video_path):
            print(f"Video file not found: {video_path}")
            continue
        
        # Extract frame
        image_filename = f"{observation_id}.jpg"
        image_output_path = os.path.join(image_dir, image_filename)
        extract_frame(video_path, time_in_seconds, image_output_path)
        
        # Parse annotations
        annotations = parse_annotation(obs['annotation'])
        if not annotations:
            print(f"No valid annotations for observation {observation_id}")
            continue
        
        # Write annotation file
        annotation_filename = f"{observation_id}.txt"
        annotation_output_path = os.path.join(label_dir, annotation_filename)
        classname = f"{obs['comname']}_{obs['taxserial']}"
        class_id = classname_to_class_id[classname]
        write_yolo_annotation(annotation_output_path, annotations, class_id)

# Process training observations
process_observations(train_obs, 'dataset/images/train', 'dataset/labels/train')

# Process validation observations
process_observations(val_obs, 'dataset/images/val', 'dataset/labels/val')

# Create classes.names file
with open('classes.names', 'w') as f:
    for classname, class_id in sorted(classname_to_class_id.items(), key=lambda item: item[1]):
        f.write(f"{classname}\n")

# Create data.yaml file
data = {
    'train': os.path.abspath('dataset/images/train'),
    'val': os.path.abspath('dataset/images/val'),
    'nc': len(classname_to_class_id),
    'names': [classname for classname, _ in sorted(classname_to_class_id.items(), key=lambda item: item[1])]
}

with open('data.yaml', 'w') as f:
    yaml.dump(data, f)
