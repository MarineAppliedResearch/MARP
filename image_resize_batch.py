from PIL import Image
import os
from tkinter import Tk, filedialog

# --- Configuration ---
target_w, target_h = 244, 176
output_folder_name = "output_images"
# ----------------------

# Hide the main tkinter window
Tk().withdraw()

# Ask the user for the top-level input folder
input_root = filedialog.askdirectory(title="Select the top-level folder containing PNG images")
if not input_root:
    print("❌ No folder selected. Exiting.")
    exit()

# Define output root next to the input folder
parent_dir = os.path.dirname(input_root)
output_root = os.path.join(parent_dir, output_folder_name)
os.makedirs(output_root, exist_ok=True)

# Walk through all subdirectories
for dirpath, _, filenames in os.walk(input_root):
    # Figure out the corresponding output directory path
    rel_path = os.path.relpath(dirpath, input_root)
    output_dir = os.path.join(output_root, rel_path)
    os.makedirs(output_dir, exist_ok=True)

    for filename in filenames:
        if not filename.lower().endswith(".png"):
            continue

        input_path = os.path.join(dirpath, filename)
        output_path = os.path.join(output_dir, filename)

        with Image.open(input_path) as img:
            w, h = img.size
            scale = max(target_w / w, target_h / h)

            new_w = int(w * scale)
            new_h = int(h * scale)

            # Resize with aspect preserved
            img = img.resize((new_w, new_h), Image.LANCZOS)

            # Center crop
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            right = left + target_w
            bottom = top + target_h
            img = img.crop((left, top, right, bottom))

            # Save result
            img.save(output_path)

print(f"✅ Done! All PNGs resized to {target_w}x{target_h} and saved under '{output_root}'")