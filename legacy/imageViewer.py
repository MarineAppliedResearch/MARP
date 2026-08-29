"""
imageViewer.py

Author: Isaac Assegai Travers
Date: 11/5/2024

Description:
This script allows users to view images in a dataset folder with their corresponding YOLO-format annotations.
It recursively searches through 'train' and 'val' subdirectories in the 'dataset/images' folder.
As each image is displayed, the script reads the associated label file from the corresponding 'train' or 'val' subdirectory in 'dataset/labels',
draws the bounding box annotations on the image, and displays it to the user. The user can then choose to save the annotated image to a
separate folder or continue viewing the next image.

Features:
- Recursively displays images from the 'train' and 'val' subdirectories of the specified dataset folder.
- Reads YOLO-format label files and overlays bounding boxes on images.
- Supports viewing multiple images sequentially.
- Allows users to save annotated images to a designated output folder.
- Simple keyboard controls for user interaction.

Usage Instructions:
1. Ensure that you have the required dependencies installed:
   - OpenCV: Install via 'pip install opencv-python pyyaml'
2. Adjust the following paths in the script as necessary:
   - 'dataset_image_folder': Path to your dataset images.
   - 'dataset_label_folder': Path to your YOLO-format label files.
   - 'output_folder': Path where you want to save annotated images.
3. Run the script using the command:
   - 'python imageViewer.py'
4. While the script is running:
   - Press 's' to save the currently displayed annotated image.
   - Press 'q' to quit the viewer.
   - Press any other key to view the next image.

Dependencies:
- Python 3.x
- OpenCV (cv2)
- PyYAML (yaml)

Notes:
- The script assumes that image files and label files have the same base name,
  with images having extensions like '.jpg', '.jpeg', or '.png', and label files
  having the extension '.txt'.
- The YOLO annotation format is expected to be in normalized coordinates:
  '<class_id> <x_center> <y_center> <width> <height>'.

License:
This script is provided as-is without any warranty. You are free to use, modify,
and distribute it as needed.

"""

import os
import cv2
import glob
import yaml

# Set the paths to your dataset and output folders
dataset_image_folder = 'dataset/images'   # Adjust the path if necessary
dataset_label_folder = 'dataset/labels'   # Adjust the path if necessary
output_folder = 'annotated_images'        # Folder to save annotated images
data_yaml_path = 'data.yaml'              # Path to the data.yaml file containing class names

# Create the output folder if it doesn't exist
os.makedirs(output_folder, exist_ok=True)

# Load class names from data.yaml
try:
    with open(data_yaml_path, 'r') as f:
        data = yaml.safe_load(f)
        class_names = data['names']
except FileNotFoundError:
    print(f"Error: The file '{data_yaml_path}' was not found.")
    exit()
except Exception as e:
    print(f"Error loading data.yaml: {e}")
    exit()

# Debug: Print the class names loaded
print(f"Loaded {len(class_names)} class names from '{data_yaml_path}'.")

# Get a list of all images in the dataset image folder and its subfolders
image_files = glob.glob(os.path.join(dataset_image_folder, '**', '*.*'), recursive=True)
image_files = [
    f for f in image_files
    if os.path.isfile(f) and f.lower().endswith(('.jpg', '.jpeg', '.png'))
]

# Debug: Print the list of image files found
print(f"Found {len(image_files)} image(s) in '{dataset_image_folder}' and its subfolders.")

# Check if any images were found
if not image_files:
    print("\nNo images were found in the specified folder.")
    print("Please check the following:")
    print(f"- Ensure that the path '{dataset_image_folder}' is correct.")
    print("- Verify that the 'train' and 'val' subdirectories contain image files.")
    print("- Confirm that the image files have extensions like '.jpg', '.jpeg', or '.png'.")
    exit()

# Function to read YOLO annotation files
def read_yolo_annotations(label_path, img_width, img_height):
    annotations = []
    try:
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 5:
                    print(f"Invalid annotation format in file {label_path}: {line.strip()}")
                    continue
                class_id, x_center_norm, y_center_norm, width_norm, height_norm = parts
                class_id = int(class_id)
                if class_id < 0 or class_id >= len(class_names):
                    print(f"Invalid class ID '{class_id}' in file {label_path}")
                    continue
                
                x_center = float(x_center_norm) * img_width
                y_center = float(y_center_norm) * img_height
                width = float(width_norm) * img_width
                height = float(height_norm) * img_height
                x1 = int(x_center - width / 2)
                y1 = int(y_center - height / 2)
                x2 = int(x_center + width / 2)
                y2 = int(y_center + height / 2)
                annotations.append((class_id, x1, y1, x2, y2))
    except Exception as e:
        print(f"Error reading label file {label_path}: {e}")
    return annotations

# Main loop to display images with annotations
for idx, image_path in enumerate(sorted(image_files)):
    image_file = os.path.basename(image_path)
    # Determine the subfolder ('train' or 'val')
    subfolder = os.path.relpath(image_path, dataset_image_folder).split(os.sep)[0]
    label_subfolder = os.path.join(dataset_label_folder, subfolder)
    label_file = os.path.splitext(image_file)[0] + '.txt'
    label_path = os.path.join(label_subfolder, label_file)

    print(f"\nProcessing image {idx + 1}/{len(image_files)}: {image_file}")
    print(f"Image path: {image_path}")
    print(f"Label path: {label_path}")

    # Read the image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to read image: {image_path}")
        continue

    img_height, img_width = image.shape[:2]

    # Check if the corresponding label file exists
    if os.path.isfile(label_path):
        print(f"Reading annotations from: {label_path}")
        # Read annotations and draw bounding boxes
        annotations = read_yolo_annotations(label_path, img_width, img_height)
        if not annotations:
            print(f"No annotations found in label file: {label_path}")
        for class_id, x1, y1, x2, y2 in annotations:
            # Draw rectangle on the image
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Split the class name into two parts
            class_name = class_names[class_id]
            class_name_parts = class_name.split('_', 1)
            first_part = class_name_parts[0] if len(class_name_parts) > 0 else ""
            second_part = class_name_parts[1] if len(class_name_parts) > 1 else ""

            # Put the first part of the class name at the top of the bounding box
            cv2.putText(image, first_part, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (36, 255, 12), 2)
            # Put the second part of the class name at the bottom of the bounding box
            cv2.putText(image, second_part, (x1, y2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (36, 255, 12), 2)
    else:
        print(f"No label file found for image: {image_file} at {label_path}")

    # Display the image
    cv2.imshow('Image Viewer', image)
    print("Press 's' to save annotated image, 'q' to quit, any other key to continue.")

    # Wait for a key press
    key = cv2.waitKey(0) & 0xFF

    if key == ord('s'):
        # Save the image with annotations to the output folder
        output_path = os.path.join(output_folder, f"{subfolder}_{image_file}")
        cv2.imwrite(output_path, image)
        print(f"Saved annotated image to: {output_path}")
    elif key == ord('q'):
        # Exit the loop and close the viewer
        print("Exiting the image viewer.")
        break
    else:
        # Continue to the next image
        pass

# Close all OpenCV windows
cv2.destroyAllWindows()
