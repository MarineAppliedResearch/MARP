""
"""
videoAnnotator.py

Author: Isaac Assegai Travers
Date: 11/5/2024

Description:
This script reads videos from the 'input_video' folder, queries an API to get annotations for each video,
and creates a copy of each video with annotations overlaid directly on the video frames. The annotated videos
are saved to a designated output folder.

Features:
- Reads videos from the specified input folder.
- Queries an API to retrieve annotation information.
- Overlays bounding boxes on video frames with annotations.
- Saves the annotated video to a designated output folder.

Usage Instructions:
1. Ensure that you have the required dependencies installed:
   - OpenCV: Install via 'pip install opencv-python requests pyyaml'
2. Adjust the following paths in the script as necessary:
   - 'input_video_folder': Path to your input videos.
   - 'output_folder': Path where you want to save annotated videos.
3. Run the script using the command:
   - 'python videoAnnotator.py'

Dependencies:
- Python 3.x
- OpenCV (cv2)
- Requests library (requests)
- PyYAML (yaml)

Notes:
- The script expects the API endpoint to return a JSON response containing annotations.
- The YOLO annotation format is expected in the following structure:
  '<class_id> <x_center> <y_center> <width> <height>'.
"""

import os
import cv2
import requests
import functions
from database_video_annotations import DatabaseVideoAnnotationsRangeFinder, AnnotationRectangle



# Set the paths to your dataset and output folders
input_video_folder = 'C:/Users/isaac/Videos/AI_VIDEO/test'         # Adjust the path if necessary
output_folder = '185645_annotate'         # Folder to save annotated videos



# Create the output folder if it doesn't exist
os.makedirs(output_folder, exist_ok=True)


# Get a list of all video files in the input video folder
video_files = [
    f for f in os.listdir(input_video_folder)
    if os.path.isfile(os.path.join(input_video_folder, f))
    and f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'))
]

# Debug: Print the list of video files found
print(f"Found {len(video_files)} video(s) in '{input_video_folder}'.")

# Check if any videos were found
if not video_files:
    print("No videos were found in the specified folder.")
    print("Please check the following:")
    print(f"- Ensure that the path '{input_video_folder}' is correct.")
    print("- Confirm that the video files have extensions like '.mp4', '.avi', '.mov', etc.")
    exit()

# Process each video file
for video_name in video_files:
    print(f"Processing video: {video_name}")

    
    try:
        
        observations = functions.getObservationsByVideo(video_name)

        # Open the video file for reading
        video_path = os.path.join(input_video_folder, video_name)

        # Open the video
        cap = cv2.VideoCapture(video_path)

        # Check if the video file cannot be opened and report to user
        if not cap.isOpened():
            print(f"Error: Cannot open video file '{video_path}'.")
            continue

        # Get the frame rate and size of the input video
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # Get the total number of frames
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Set up the VideoWriter to save the annotated video
        output_video_path = os.path.join(output_folder, f"annotated_{video_name}")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

        # Create a dictionary to store annotations by frame
        annotations_by_frame = {}

        # Initialize the range finder
        functions.range_finder = DatabaseVideoAnnotationsRangeFinder()

        # Loop through every observation
        for obs in observations:
            # Loop through all the keyframes of this annotation
            if "keyframes" in obs:
                for keyframe in obs["keyframes"]:
                    # Create an AnnotationRectangle instance
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

                    # Add the annotation to the frame's list
                    annotations_by_frame.setdefault(annotation.framenum, []).append(annotation)

        # Reload the data
        functions.range_finder.reload(annotations_by_frame)

        # Process the video frame by frame
        frame_index = 0
        while True:
            ret, frame = cap.read()
            
            if not ret:
                break

            # Provide a progress update every 200 frames
            if frame_index % 1500 == 0:
                functions.printSymbolBasedOnProgress(".", frame_index, total_frames)

            # Track the annotations that should be visible on the canvas for the current frame
            target_annotations = {}

            # Get the annotations for the current frame if available
            if frame_index in annotations_by_frame:
                for db_annotation in annotations_by_frame[frame_index]:
                    key = f"{db_annotation.observation_id}_{db_annotation.subset}"
                    if key not in target_annotations:
                        target_annotations[key] = db_annotation

            surrounding_annotations = functions.range_finder.get_surrounding_annotations(frame_index)

            for key, (previous, next_frame) in surrounding_annotations.items():
                # Skip if this key is already in target_annotations
                if key in target_annotations:
                    continue

                # Perform interpolation logic
                if previous and next_frame:
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
                elif previous and not next_frame:
                    if previous.type != "end":
                        new_annotation = AnnotationRectangle(
                            x_center=previous.x_center,
                            y_center=previous.y_center,
                            width_norm=previous.width_norm,
                            height_norm=previous.height_norm,
                            class_name=previous.class_name,
                            type="pre-interpolated",
                            observation_id=previous.observation_id,
                            subset=previous.subset,
                            framenum=frame_index
                        )
                        target_annotations[key] = new_annotation

            # Draw annotations on the frame
            for key, annotation in target_annotations.items():
                x_center_px = int(annotation.x_center * width)
                y_center_px = int(annotation.y_center * height)
                box_width_px = int(annotation.width_norm * width)
                box_height_px = int(annotation.height_norm * height)
                x1 = int(x_center_px - box_width_px / 2)
                y1 = int(y_center_px - box_height_px / 2)
                x2 = int(x_center_px + box_width_px / 2)
                y2 = int(y_center_px + box_height_px / 2)

                # Determine color based on annotation type
                color = (0, 255, 0)  # Default color
                if annotation.type == "start":
                    color = (13, 22, 158)
                elif annotation.type == "middle":
                    color = (255, 0, 0)
                elif annotation.type == "end":
                    color = (0, 0, 255)
                elif annotation.type == "interpolated":
                    color = (0, 255, 0)
                elif annotation.type == "pre-interpolated":
                    color = (255, 255, 255)


                # Here is where we decide what to do once we have these frames
                # Draw rectangle on the frame
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Add text annotations
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = max(0.35, box_width_px / 325.0)  # Scale font size with box width, with a minimum scale of 0.4
                thickness = int(max(1, box_width_px / 70))  # Adjust text thickness based on box width

                # Split the class name into two parts
                first_part = annotation.class_name
                second_part = f"{annotation.observation_id}_{annotation.subset}"

                # Get size of the first part of the class name
                (first_part_width, first_part_height), _ = cv2.getTextSize(first_part, font, font_scale, thickness)
                # Calculate x-coordinate for centered text at the top of the box
                first_part_x = x1 + (box_width_px - first_part_width) // 2

                # Get size of the second part of the class name
                (second_part_width, second_part_height), _ = cv2.getTextSize(second_part, font, font_scale, thickness)
                # Calculate x-coordinate for centered text at the bottom of the box
                second_part_x = x1 + (box_width_px - second_part_width) // 2

                # Put the first part of the class name at the top of the bounding box, centered
                cv2.putText(frame, first_part, (first_part_x, y1 - 10),
                            font, font_scale, (36, 255, 12), thickness)

                # Put the second part of the class name at the bottom of the bounding box, centered
                cv2.putText(frame, second_part, (second_part_x, y2 + second_part_height + 10),
                            font, font_scale, (36, 255, 12), thickness)


            # Write the annotated frame to the output video
            out.write(frame)
            frame_index += 1

        # Release resources
        cap.release()
        out.release()
        print(f"Annotated video saved to: {output_video_path}")

    except requests.exceptions.RequestException as err:
        print(f"Error occurred for '{video_name}': {err}")
    except Exception as e:
        print(f"An unexpected error occurred for '{video_name}': {e}")

print("All videos have been processed and annotated.")