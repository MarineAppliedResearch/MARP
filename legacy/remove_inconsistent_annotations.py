import os;

output_dataset_folder = "yolo_dataset"
for_human_review_folder = os.path.join(output_dataset_folder, "for_human_review")
train_labels_folder = os.path.join(output_dataset_folder, "train", "labels")
eval_labels_folder = os.path.join(output_dataset_folder, "eval", "labels")

# Get all subfolders (class-specific) in `for_human_review`
human_review_subfolders = [os.path.join(for_human_review_folder, d) for d in os.listdir(for_human_review_folder) if os.path.isdir(os.path.join(for_human_review_folder, d))]

# Collect all valid keys from `for_human_review`
human_review_keys = set()

for subfolder in human_review_subfolders:
    for file_name in os.listdir(subfolder):
        if file_name.endswith(".jpg"):
            parts = file_name.split("_")
            if len(parts) >= 4:  # Example: video1_frame_0005_611869_sub1.jpg
                observation_key = parts[-2] + "_" + parts[-1].replace(".jpg", "")
                human_review_keys.add(observation_key)

print(f"Found {len(human_review_keys)} unique keys in `for_human_review` across all classes.")

# Function to process label files
def process_label_files(labels_folder):
    files_to_remove = []
    for label_file in os.listdir(labels_folder):
        label_path = os.path.join(labels_folder, label_file)
        if not label_file.endswith(".txt"):
            continue

        updated_lines = []
        with open(label_path, "r") as file:
            for line in file:
                # Check if the annotation contains a valid key
                parts = line.strip().split("#")
                if len(parts) == 2:
                    annotation_data, key = parts
                    if key.strip() in human_review_keys:  # Use the stripped version of `key` for comparison
                        #print("\nRetaining Annotation: " + key + " in " + label_file)
                        updated_lines.append(line.strip())  # Retain the original line
                    else:
                        print("\nRemoving Annotation: " + key + " from " + label_file)

        # Overwrite the file if there are valid annotations
        if updated_lines:
            with open(label_path, "w") as file:
                file.write("\n".join(updated_lines) + "\n")
        else:
            # If no valid annotations remain, mark the file for removal
            files_to_remove.append(label_path)

    # Remove files with no valid annotations
    for label_path in files_to_remove:
        os.remove(label_path)
        print("\nRemoving Label: " + label_path)
        # Remove corresponding image file
        image_file = label_path.replace("labels", "images").replace(".txt", ".jpg")
        if os.path.exists(image_file):
            os.remove(image_file)
            print("\nRemoving Image: " + image_file)

# Process `train` and `eval` label files
print("Processing `train` annotations...")
process_label_files(train_labels_folder)
print("Processing `eval` annotations...")
process_label_files(eval_labels_folder)

print("Consistency check completed. Inconsistent annotations removed.")
