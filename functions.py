import cv2
import yaml
from database_video_annotations import DatabaseVideoAnnotationsRangeFinder, AnnotationRectangle
import requests

api_base_url = 'http://192.168.1.32:3081/api/getObservationsByVideo'  # API endpoint base URL
data_yaml_path = 'data.yaml'               # Path to the data.yaml file containing class names

# Initialize the range finder
range_finder = DatabaseVideoAnnotationsRangeFinder()


def getObservationsByVideo(video_name):
        
    # Set up the parameters for the GET request
    params = {'videoName': video_name}
    
    # Make the GET request to the API endpoint
    response = requests.get(api_base_url, params=params)
    response.raise_for_status()  # Raise an exception if the request was unsuccessful
    observations = response.json()

    return observations

# Function to convert mediaPosition (in format HH:MM:SS.SSS) to seconds
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
    
# Load classnames from data_yaml_path
def loadClassNames():

    returnVal = None

    # Load class names from data.yaml
    try:
        with open(data_yaml_path, 'r') as f:
            data = yaml.safe_load(f)
            class_names = data['names']
            print(f"Loaded {len(class_names)} class names from '{data_yaml_path}'.")
            returnVal = class_names
    except FileNotFoundError:
        print(f"Error: The file '{data_yaml_path}' was not found.")
    except Exception as e:
        print(f"Error loading data.yaml: {e}")

    return returnVal
    

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


def printSymbolBasedOnProgress(symbolToPrint, progress, totalPossibleProgress):
    # Progressively change the color of the printed period as frame_index approaches 200
    progress = (progress % totalPossibleProgress) / totalPossibleProgress  # Normalize progress between 0 and 1
    red = int(255 * progress)  # Red increases with progress
    green = int(255 * (1 - progress))  # Green decreases with progress

    # Generate ANSI escape code for the color
    color_code = f"\033[38;2;{red};{green};0m"

    # Print the colored period
    print(f'{color_code}.', end='', flush=True)

    # Reset the color back to default after printing
    print("\033[0m", end='', flush=True)




