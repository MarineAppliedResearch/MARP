# trims the first x seconds of a given video, meant to make it easy to remove MARE slides.

import cv2
import tkinter as tk
from tkinter import filedialog, messagebox
import os


def trim_first_seconds(input_path, output_path, seconds_to_remove=4):
    cap = cv2.VideoCapture(input_path)

    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open input video.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        messagebox.showerror("Error", "Invalid FPS detected.")
        cap.release()
        return

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    frames_to_skip = int(fps * seconds_to_remove)

    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))

    # Skip first N frames
    skipped = 0
    while skipped < frames_to_skip:
        ret, _ = cap.read()
        if not ret:
            break
        skipped += 1

    # Write remaining frames
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)

    cap.release()
    out.release()


def main():
    root = tk.Tk()
    root.withdraw()  # Hide main window

    input_path = filedialog.askopenfilename(
        title="Select Video to Trim",
        filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv"), ("All Files", "*.*")]
    )

    if not input_path:
        return

    default_output = os.path.splitext(input_path)[0] + "_trimmed.mp4"

    output_path = filedialog.asksaveasfilename(
        title="Save Trimmed Video As",
        initialfile=os.path.basename(default_output),
        defaultextension=".mp4",
        filetypes=[("MP4 Video", "*.mp4")]
    )

    if not output_path:
        return

    trim_first_seconds(input_path, output_path, seconds_to_remove=4)

    messagebox.showinfo("Done", "Trimmed video saved successfully.")


if __name__ == "__main__":
    main()