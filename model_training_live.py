import os
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import functions
import yaml
import random
import cv2
from database_video_annotations import AnnotationRectangle, DatabaseVideoAnnotationsRangeFinder
from ultralytics import YOLO
import shutil
import matplotlib.pyplot as plt
import pandas as pd
import os
from datetime import datetime
from pathlib import Path
import time
import numpy as np

# Try importing the plotting utilities from the correct place
try:
    from ultralytics.utils.plotting import Annotator as _  # quick test import
    import ultralytics.utils.plotting as plots
except ImportError:
    plots = None  # plotting module not available in this version

import torch
try:
    from torch.profiler import profile, record_function, ProfilerActivity, schedule
    use_profiler = True
except ImportError:
    use_profiler = False


# ==========================================================
# DATASET BUILDER POPUP WINDOW
# ==========================================================
def open_dataset_builder(parent):
    """
    Opens a popup Dataset Builder window (GUI placeholder for now).
    """
    popup = ctk.CTkToplevel(parent)
    popup.title("Dataset Builder")
    popup.geometry("700x700")
    popup.grab_set()  # lock focus to popup until closed

    # Layout
    popup.grid_columnconfigure(0, weight=1)
    popup.grid_rowconfigure(0, weight=1)

    frame = ctk.CTkFrame(popup)
    frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

    title = ctk.CTkLabel(frame, text="Build a New Dataset", font=("TkDefaultFont", 14, "bold"))
    title.pack(pady=(10, 10))


    # -----------------------------
    # Video Folder Selection
    # -----------------------------
    video_folder_var = ctk.StringVar(value="No folder selected")

    def choose_video_folder():
        folder = filedialog.askdirectory(title="Select Video Folder")
        if folder:
            video_folder_var.set(folder)
        else:
            video_folder_var.set("No folder selected")

    # -----------------------------
    # Video Folder + Dataset Name
    # -----------------------------
    folder_frame = ctk.CTkFrame(frame)
    folder_frame.pack(fill="x", pady=(0, 15))
    folder_frame.grid_columnconfigure((0, 1), weight=1)

    # --- Video Folder ---
    video_folder = ctk.StringVar(value="No folder selected")

    def choose_video_folder():
        folder = filedialog.askdirectory(title="Select Video Folder")
        if folder:
            video_folder.set(folder)
        else:
            video_folder.set("No folder selected")

    folder_label = ctk.CTkLabel(folder_frame, text="Video Folder:", font=("TkDefaultFont", 11, "bold"))
    folder_label.grid(row=0, column=0, sticky="w", padx=10, pady=(5, 2))

    browse_btn = ctk.CTkButton(folder_frame, text="Browse...", command=choose_video_folder, width=100)
    browse_btn.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 5))

    folder_path_label = ctk.CTkLabel(folder_frame, textvariable=video_folder, text_color="gray", wraplength=300)
    folder_path_label.grid(row=2, column=0, sticky="w", padx=10)

    browse_btn = ctk.CTkButton(folder_frame, text="Browse...", command=choose_video_folder, width=100)
    browse_btn.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 5))

    folder_path_label = ctk.CTkLabel(folder_frame, textvariable=video_folder_var, text_color="gray", wraplength=300)
    folder_path_label.grid(row=2, column=0, sticky="w", padx=10)


    # --- Dataset Name ---
    dataset_name_var = ctk.StringVar()

    name_label = ctk.CTkLabel(folder_frame, text="Dataset Name:", font=("TkDefaultFont", 11, "bold"))
    name_label.grid(row=0, column=1, sticky="w", padx=10, pady=(5, 2))

    name_entry = ctk.CTkEntry(folder_frame, textvariable=dataset_name_var, placeholder_text="Enter dataset name")
    name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 5))

    ctk.CTkLabel(folder_frame, text="", text_color="gray").grid(row=2, column=1)  # spacing placeholder


        # -----------------------------
    # Scrollable species list (demo)
    # -----------------------------
    scrollable = ctk.CTkScrollableFrame(frame, label_text="Select Species")
    scrollable.pack(fill="both", expand=True, pady=(0, 15))

    # Example demo data (replace with API data later)
    """ demo_species = [
        "Lingcod", "Rockfish", "Cabezon", "Greenling", "Sea Star", "Sea Cucumber",
        "Sponge", "Anemone", "Octopus", "Crab", "Shrimp", "Urchin", "Abalone",
        "Squid", "Sea Pen", "Sea Fan", "Sea Whip", "Hydroid", "Tunicate", "Bryozoan"
    ] """

    species_data = functions.getSpecies()
    demo_species = [sp["comname"] for sp in species_data if sp["comname"]]

    species_vars = {}

      # Configure the scrollable frame to use 3 columns
    num_cols = 3
    for c in range(num_cols):
        scrollable.grid_columnconfigure(c, weight=1)

    # Evenly split the species list into 3 columns
    n = len(demo_species)
    chunk_size = (n + num_cols - 1) // num_cols  # divide evenly
    species_vars = {}

    for col in range(num_cols):
        start = col * chunk_size
        end = min(start + chunk_size, n)
        for row, sp in enumerate(demo_species[start:end]):
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(scrollable, text=sp, variable=var)
            cb.grid(row=row, column=col, sticky="w", padx=10, pady=2)
            species_vars[sp] = var

    # For testing: show which species are selected
    def build_dataset():
        input_video_folder = video_folder.get() 
        selected_comnames = [sp for sp, var in species_vars.items() if var.get()]
        messagebox.showinfo("Selected Species", "\n".join(selected_comnames) if selected_comnames else "None selected")

        output_dataset_folder = "datasets/"+name_entry.get()

        classnames_file = os.path.join(output_dataset_folder, "classnames.yaml")

        # Subfolders for training and evaluation data
        train_images_folder = os.path.join(output_dataset_folder, "train", "images")
        train_labels_folder = os.path.join(output_dataset_folder, "train", "labels")
        eval_images_folder = os.path.join(output_dataset_folder, "eval", "images")
        eval_labels_folder = os.path.join(output_dataset_folder, "eval", "labels")
        human_review_folder = os.path.join(output_dataset_folder, "for_human_review")

        # Create necessary folders
        os.makedirs(train_images_folder, exist_ok=True)
        os.makedirs(train_labels_folder, exist_ok=True)
        os.makedirs(eval_images_folder, exist_ok=True)
        os.makedirs(eval_labels_folder, exist_ok=True)
        os.makedirs(human_review_folder, exist_ok=True)

        # ---------------------------------------------------------
        # Register the dataset in the (fake) MARP API
        # ---------------------------------------------------------
        """ datasetRecord = functions.createDatabaseDataset(
            name=name_entry.get(),
            location=output_dataset_folder,
            description=f"Dataset built from {len(selected_comnames)} species",
            numSamples=0,  # we’ll update this later if needed
            numClasses=len(selected_comnames),
            source="manual",
            notes=""
        ) """

        

        # get observations from the database that have the selected comnames
        observations = functions.getObservationsWithKeyframesByComnames(selected_comnames)

        num_samples = 0

        # Step 4: Rebuild `annotations_by_video` dictionary from observations
        annotations_by_video = {}
        for obs in observations:

            ## only use observations with a note of R
            if obs["note"] != 'R': 
                continue

            # Extract frame numbers from the observation's keyframes
            frame_numbers = [kf["framenum"] for kf in obs["keyframes"] if "framenum" in kf]

            # If there are valid frames, compute the range
            if frame_numbers:
                min_frame = min(frame_numbers)
                max_frame = max(frame_numbers)
                frame_count = (max_frame - min_frame) + 1  # inclusive range
                num_samples += frame_count
            else:
                print(f"[WARN] Observation {obs.get('observation_id')} has no valid keyframes")
            video_name = obs["video_source"]  # Assuming `video_name` is part of each observation
            annotations_by_video.setdefault(video_name, []).append(obs)

        new_dataset = {
            "name": name_entry.get(),
            "description": f"Dataset built from {len(selected_comnames)} species",
            "location": output_dataset_folder,
            "num_samples": num_samples,
            "num_classes": len(selected_comnames),
            "source": "model_training_live.py",
            "notes": "test"
        }

        result = functions.createDatabaseDataset(new_dataset)

        if result:
            print("Created dataset ID:", result.get("id"))
        else:
            print("Failed to create dataset.")


        datasetId = result["id"]
        print(f"[INFO] Created dataset record with ID {datasetId}")

        classnames_list = sorted(selected_comnames)
        classnames_to_ids = {classname: idx for idx, classname in enumerate(classnames_list)}

        classnames_data = {
            "names": classnames_list,
            "nc": len(classnames_list),
            "train": os.path.abspath(train_images_folder),
            "val": os.path.abspath(eval_images_folder)
        }

        with open(classnames_file, "w") as yaml_file:
            yaml.dump(classnames_data, yaml_file)

        print(f"Class names and dataset paths saved to {classnames_file}")

        observation_ids = list({obs["observation_id"] for obs in observations})
        random.shuffle(observation_ids)
        split_idx = int(len(observation_ids) * 0.8)
        train_ids = set(observation_ids[:split_idx])
        eval_ids = set(observation_ids[split_idx:])

        # Prepare all dataset_observation records
        dataset_observations_payload = []
        for obs in observations:
            dataset_observations_payload.append({
                "dataset_id": datasetId,
                "observation_id": obs["observation_id"],
                "inclusion_type": "train" if obs["observation_id"] in train_ids else "val",
                "selection_method": "automatic",
                "weight": 1,
                "notes" : "initial tests"
            })

        # Send all in one call
        result = functions.createDatabaseDatasetObservationsBulk(dataset_observations_payload)
        if result:
            print(f"Successfully inserted {result.get('inserted')} dataset_observations.")
        else:
            print("Bulk insert failed.")

        # Process videos
        for video_name, observations in annotations_by_video.items():
            video_path = os.path.join(input_video_folder, video_name)
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                print(f"Error: Cannot open video file '{video_path}'. Skipping.")
                continue

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # The remaining frame processing and annotation logic continues unchanged.
            # Prepare annotations
            annotations_by_frame = {}
            range_finder = DatabaseVideoAnnotationsRangeFinder()

            for obs in observations:
                for keyframe in obs["keyframes"]:
                    annotation = AnnotationRectangle(
                        x_center=keyframe["x"],
                        y_center=keyframe["y"],
                        width_norm=keyframe["width"],
                        height_norm=keyframe["height"],
                        class_name=obs["comname"],
                        type=keyframe["type"],
                        observation_id=keyframe["observation_id"],
                        subset=keyframe["subset"],
                        framenum=keyframe["framenum"]
                    )
                    annotations_by_frame.setdefault(annotation.framenum, []).append(annotation)

            # Reload range finder
            range_finder.reload(annotations_by_frame)

            # Process each frame
            frame_index = 0
            while frame_index < total_frames:
                ret, frame = cap.read()

                if not ret:
                    break

                # Provide a progress update every 200 frames
                if frame_index % 1500 == 0:
                    functions.printSymbolBasedOnProgress(".", frame_index, total_frames)

                # Track annotations for the current frame
                target_annotations = {}

                # Get annotations for the current frame if available
                if frame_index in annotations_by_frame:
                    for annotation in annotations_by_frame[frame_index]:
                        key = f"{annotation.observation_id}_{annotation.subset}"
                        target_annotations[key] = annotation

                # Add interpolated annotations for the current frame
                surrounding_annotations = range_finder.get_surrounding_annotations(frame_index)
                for key, (previous, next_frame) in surrounding_annotations.items():
                    if key in target_annotations:
                        continue

                    if previous and next_frame:
                        # Perform interpolation
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

                # Only save the frame and labels if annotations exist for this frame
                if target_annotations:
                    dataset_type = "train" if any(annotation.observation_id in train_ids for annotation in target_annotations.values()) else "eval"
                    images_folder = train_images_folder if dataset_type == "train" else eval_images_folder
                    labels_folder = train_labels_folder if dataset_type == "train" else eval_labels_folder

                    # Save the image
                    image_filename = f"{video_name}_frame_{frame_index:04d}.jpg"
                    image_path = os.path.join(images_folder, image_filename)
                    cv2.imwrite(image_path, frame)

                    # Save the YOLO label
                    label_filename = f"{video_name}_frame_{frame_index:04d}.txt"
                    label_path = os.path.join(labels_folder, label_filename)
                    with open(label_path, "w") as label_file:
                        for annotation in target_annotations.values():
                            class_id = classnames_to_ids[annotation.class_name]
                            label_file.write(f"{class_id} {annotation.x_center} {annotation.y_center} {annotation.width_norm} {annotation.height_norm} \n")

                            x_center_px = int(annotation.x_center * width)
                            y_center_px = int(annotation.y_center * height)
                            box_width_px = int(annotation.width_norm * width)
                            box_height_px = int(annotation.height_norm * height)

                            # Calculate bounding box coordinates
                            x1 = max(0, int(x_center_px - box_width_px / 2))
                            y1 = max(0, int(y_center_px - box_height_px / 2))
                            x2 = min(width, int(x_center_px + box_width_px / 2))
                            y2 = min(height, int(y_center_px + box_height_px / 2))

                            # Debug log for bounding box values
                            #print(f"Cropping region: x1={x1}, y1={y1}, x2={x2}, y2={y2}, width={x2 - x1}, height={y2 - y1}")

                            # Crop the annotation region from the frame
                            cropped_annotation = frame[y1:y2, x1:x2]

                            # Validate the cropped region
                            if cropped_annotation is None or cropped_annotation.size == 0:
                                print(f"Invalid cropped region for frame {frame_index}: {x1}, {y1}, {x2}, {y2}. Skipping...")
                                continue  # Skip this annotation if the region is invalid

                            # Create class-specific subfolder in `for_human_review`
                            class_folder = os.path.join(human_review_folder, annotation.class_name)
                            os.makedirs(class_folder, exist_ok=True)

                            # Save the cropped annotation
                            #human_review_filename = f"{video_name}_frame_{frame_index:04d}_{annotation.observation_id}_{annotation.subset}.jpg"
                            human_review_filename = f"_{annotation.observation_id}_{annotation.subset}_frame_{frame_index:04d}_{video_name}_.jpg"
                            human_review_path = os.path.join(class_folder, human_review_filename)

                            # Validate frame before saving
                            if cropped_annotation.size > 0:
                                cv2.imwrite(human_review_path, cropped_annotation)
                                p = 1
                            else:
                                print(f"Empty cropped annotation for {human_review_filename}. Skipping save.")

                frame_index += 1

            cap.release()

        print("\nYOLO dataset and human review images have been created successfully!")

    ctk.CTkButton(frame, text="Build Dataset", command=build_dataset).pack(pady=(5, 10))



    ctk.CTkButton(frame, text="Close", command=popup.destroy).pack(pady=10)


# ------------------------------------------------------------
# startMlTraining
# ------------------------------------------------------------
# Starts the machine learning training pipeline for the given dataset.
# Parameters:
#   dataset_info (dict) – full dataset record from the API
# ------------------------------------------------------------
def startMlTraining(dataset_info, config):
    print("[ML] Starting training process...")
    print(f"[ML] Dataset: {dataset_info['name']}")
    print(f"[ML] Location: {dataset_info['location']}")


    print("CUDA AVAILABLE: " + str(torch.cuda.is_available()))  # Should return True if CUDA is available
    print("Device Count: " + str(torch.cuda.device_count()))  # Number of GPUs available

    compute_device = torch.cuda.get_device_name(0)

    try:
        print(torch.cuda.get_device_name(0))  # Name of the first GPU (if available)
    except Exception as e:
        print(str(e))


    # Paths to dataset and model
    yolo_dataset_folder = os.path.abspath(dataset_info["location"])
    classnames_file = os.path.join(yolo_dataset_folder, "classnames.yaml")
    train_images_folder = os.path.join(yolo_dataset_folder, "train", "images")
    eval_images_folder = os.path.join(yolo_dataset_folder, "eval", "images")

    # Ensure the dataset and classnames file exist
    if not os.path.exists(yolo_dataset_folder) or not os.path.exists(classnames_file):
        print("Error: `yolo_dataset` or `classnames.yaml` not found. Ensure the dataset is prepared.")
        exit()

    # Model configuration
    new_model_name = config.get("new_model_name", "").strip()
    pretrained_model_name = config["transfer_model_path"] + config["transfer_model_name"]
    pretrained_weights = pretrained_model_name  # Pre-trained weights
    epochs = config["epochs"]  # Number of epochs for training
    batch_size = config["batch_size"]  # Batch size

    # Load the model
    print(f"Loading pre-trained YOLO model: {pretrained_weights}")

    model = YOLO(pretrained_weights)

    # --- place this immediately after: model = YOLO(pretrained_weights) ---
    try:
        if plots and hasattr(plots, 'clean_label'):
            original_clean_label = plots.clean_label

            def clean_label_preserve_period(label: str):
                # Keep periods intact in class labels when YOLO generates plots
                sanitized = original_clean_label(label)
                if isinstance(label, str) and "." in label:
                    sanitized = sanitized.replace(" ", ".").replace("_", ".")
                    while ".." in sanitized:
                        sanitized = sanitized.replace("..", ".")
                    if "." not in sanitized:
                        sanitized = label
                return sanitized

            plots.clean_label = clean_label_preserve_period  # apply patch

        elif hasattr(model, 'names'):  # fallback if plotting helper missing
            if isinstance(model.names, dict):
                model.names = {i: (n.replace(".", "․") if isinstance(n, str) else n)
                            for i, n in model.names.items()}
            elif isinstance(model.names, list):
                model.names = [(n.replace(".", "․") if isinstance(n, str) else n)
                            for n in model.names]

    except Exception:
        pass

    device = "0" if torch.cuda.is_available() else "cpu"



    # Train the model
    print("Starting training...")

    try:
        # Attempt to import profiler
        try:
            from torch.profiler import profile, ProfilerActivity, schedule
            use_profiler = True
        except ImportError:
            use_profiler = False

        # Make sure the models/ folder exists
        models_root = "models"
        os.makedirs(models_root, exist_ok=True)

        # Define output_folder if you haven’t already
        output_folder = models_root  # This is the "project" folder

        # Full expected path
        expected_output_path = os.path.join(output_folder, new_model_name)

        print(f"[INFO] YOLO training output will be saved in: {expected_output_path}")

        # Create ML model entry
        new_model_record = {
            "name": config["new_model_name"]+".pt",
            "parent_model_id": config.get("transfer_model_id"),  # link if transfer training
            "model_type": "YOLOv8",
            "architecture_version": "custom-2025a",
            "storage_path": expected_output_path + f"\\weights\\",          # filled later
            "status": "training",
            "notes": f"Started training on dataset {dataset_info['name']} "
                    f"from parent model {config.get('transfer_model_name', 'None')}"
        }

        # Create the model in the database
        model_record = functions.createDatabaseModel(new_model_record)
        model_id = model_record["id"]


        # ------------------------------------------------------------
        # Safely extract YOLO model arguments as a dictionary
        # ------------------------------------------------------------
        if hasattr(model, "args"):
            if isinstance(model.args, dict):
                yolo_args = model.args
            else:
                try:
                    yolo_args = vars(model.args)
                except TypeError:
                    yolo_args = dict(model.args.__dict__) if hasattr(model.args, "__dict__") else {}
        else:
            yolo_args = {}

        learning_rate = yolo_args.get("lr0", 0.001)
        optimizer = yolo_args.get("optimizer", "Adam")
        loss_function = "Auto"  # YOLO doesn’t expose loss name directly
        augmentation = {
            "mosaic": yolo_args.get("mosaic", True),
            "flipud": yolo_args.get("flipud", 0.5),
            "fliplr": yolo_args.get("fliplr", 0.5),
            "hsv_h": yolo_args.get("hsv_h", 0.015),
            "hsv_s": yolo_args.get("hsv_s", 0.7),
            "hsv_v": yolo_args.get("hsv_v", 0.4)
        }

        # ------------------------------------------------------------
        # Create a training run record before training starts
        # ------------------------------------------------------------
        training_run_record = {
            "model_id": model_id,
            "dataset_id": dataset_info["id"],
            "start_time": datetime.now().isoformat(),
            "total_epochs": config["epochs"],
            "batch_size": config["batch_size"],

            # Pulled dynamically from YOLO model
            "learning_rate": learning_rate,
            "optimizer": optimizer,
            "loss_function": loss_function,
            "augmentation": augmentation,

            # Environment and script info
            "compute_device": compute_device,
            "train_script_commit": Path(__file__).name,
            "notes": f"Transfer training from {config['transfer_model_name']}",
}

        training_run = functions.createDatabaseTrainingRun(training_run_record)
        training_run_id = training_run.get("id", None)

        #print(f"[DB] Created training_run id={training_run_id}")

        #print(f"[DB] Created ml_model entry: id={model_id}")

        # Keep track of epoch timing in a dict (in memory)
        epoch_start_times = {}

        def on_epoch_start(trainer):
            """Called at the start of each epoch."""
            epoch_num = trainer.epoch + 1
            epoch_start_times[epoch_num] = time.time()

        def on_epoch_end(trainer):
            """
            Callback: runs after every epoch.
            Keeps user-named weights file updated with the latest best.pt.
            """
            
            weights_folder = os.path.join(output_folder, config["new_model_name"], "weights")
            best_weights = os.path.join(weights_folder, "best.pt")
            user_named_weights = os.path.join(weights_folder, f"{config['new_model_name']}.pt")

            # Only act if best.pt exists
            if os.path.exists(best_weights):
                try:
                    shutil.copy2(best_weights, user_named_weights)
                    #print(f"[EPOCH {trainer.epoch}] Updated {user_named_weights}")
                except Exception as e:
                    print(f"[WARNING] Failed to update model weights for epoch {trainer.epoch}: {e}")

            epoch_num = trainer.epoch + 1
            metrics = trainer.metrics
            end_time = time.time()
            start_time = epoch_start_times.get(epoch_num, end_time)
            duration = round(end_time - start_time, 3)

            epoch_record = {
                "training_run_id": training_run_id,
                "epoch_number": epoch_num,
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.fromtimestamp(end_time).isoformat(),
                "duration_seconds": duration,
                "precision": metrics.get("metrics/precision(B)", None),
                "recall": metrics.get("metrics/recall(B)", None),
                "map50": metrics.get("metrics/mAP50(B)", None),
                "map5095": metrics.get("metrics/mAP50-95(B)", None),
                "box_loss": metrics.get("val/box_loss", None),
                "cls_loss": metrics.get("val/cls_loss", None),
                "dfl_loss": metrics.get("val/dfl_loss", None),
                "timestamp": datetime.now().isoformat(),
            }

            functions.createDatabaseEpoch(epoch_record)

            # After saving metrics and weights
            if epoch_num % 5 == 0:  # only every 5 epochs
               # --- NEW live plot generation ---
                try:
                    # Option 1: modern YOLO API
                    if hasattr(trainer, "plot_results"):
                        trainer.plot_results()
                    # Option 2: fallback for older versions
                    else:
                        from ultralytics.utils.plotting import plot_results
                        results_csv = os.path.join(trainer.save_dir, 'results.csv')
                        if os.path.exists(results_csv):
                            plot_results(file=results_csv, dir=trainer.save_dir)
                except Exception as e:
                    print(f"[WARNING] Failed to generate epoch plots: {e}")


        model.add_callback("on_train_epoch_end", on_epoch_end)
        model.add_callback("on_train_epoch_start", on_epoch_start)

        if use_profiler:
            print("[INFO] Using PyTorch profiler for this run.")
            with profile(
                activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA] if torch.cuda.is_available() else [ProfilerActivity.CPU],
                on_trace_ready=torch.profiler.tensorboard_trace_handler('./logs'),
                schedule=schedule(wait=1, warmup=1, active=3, repeat=2),
                with_stack=True
            ) as prof:
                results = model.train(
                    data=classnames_file,
                    epochs=epochs,
                    imgsz=640,
                    workers=16,
                    patience=config["patience"],
                    project=output_folder,
                    name=new_model_name,
                    device=device,
                    exist_ok=True,  # stops yolo from creating folder2 everytime
                    batch=batch_size
                )
        else:
            print("[INFO] Profiler not available. Running standard training.")
            results = model.train(
                data=classnames_file,
                epochs=epochs,
                imgsz=640,
                workers=16,
                patience=config["patience"],
                project=output_folder,
                name=new_model_name,
                device=device,
                batch=batch_size
            )

        # Evaluate the model
        print("Evaluating model...")
        metrics = model.val()

        prec = metrics.results_dict.get("metrics/precision(B)", None)
        rec  = metrics.results_dict.get("metrics/recall(B)", None)
        f1_score = (2 * prec * rec / (prec + rec)) if (prec and rec and (prec + rec) > 0) else None

        summary_record = {
            "training_run_id": training_run_id,
            "dataset_split": "val",
            "precision": prec,  # or metrics.results_dict["metrics/precision(B)"]
            "recall": rec,
            "map50": metrics.results_dict.get("metrics/mAP50(B)", None),
            "map5095": metrics.results_dict.get("metrics/mAP50-95(B)", None),
            "f1_score": f1_score,
            "fitness": metrics.results_dict.get("fitness", None),
            "confusion_matrix_path": os.path.join(output_folder, new_model_name, "confusion_matrix.png"),
            "result_plot_path": os.path.join(output_folder, new_model_name, "results.png"),
            "confusion_matrix_norm_path": os.path.join(output_folder, new_model_name, "confusion_matrix_normalized.png"),
            "box_f1_curve_path": os.path.join(output_folder, new_model_name, "BoxF1_curve.png"),
            "box_p_curve_path": os.path.join(output_folder, new_model_name, "BoxP_curve.png"),
            "box_pr_curve_path": os.path.join(output_folder, new_model_name, "BoxPR_curve.png"),
            "box_r_curve_path": os.path.join(output_folder, new_model_name, "BoxR_curve.png"),
            "labels_plot_path": os.path.join(output_folder, new_model_name, "labels.png"),
            "timestamp": datetime.now().isoformat(),
        }

        summary_result = functions.createDatabaseMetricsSummary(summary_record)
        summary_id = summary_result.get("id")

        # Now generate and save both aggregate + per-species curves
        saveAllMetricsCurves(metrics, summary_id)

        


        # ------------------------------------------------------------
        # Per-species summaries
        # ------------------------------------------------------------
        try:
            class_indices = metrics.box.ap_class_index
            names = metrics.names  # {0: 'rockfish', 1: 'crab', ...}

            # Global fitness value (YOLO's overall score)
            fitness_value = getattr(metrics, "fitness", None)

            # Per-class arrays
            prec_values = metrics.box.p.tolist() if hasattr(metrics.box.p, "tolist") else list(metrics.box.p)
            rec_values  = metrics.box.r.tolist() if hasattr(metrics.box.r, "tolist") else list(metrics.box.r)
            map5095_values = metrics.box.maps.tolist() if hasattr(metrics.box.maps, "tolist") else list(metrics.box.maps)

            # Handle optional per-class mAP50
            map50_values = getattr(metrics.box, "ap50", None)
            if map50_values is not None:
                map50_values = map50_values.tolist() if hasattr(map50_values, "tolist") else list(map50_values)

            for idx, class_idx in enumerate(class_indices):
                species_name = names.get(class_idx, f"class_{class_idx}")

                # Look up species_id in your DB, if available
                species_record = functions.getSpeciesByComname(species_name)
                species_id = species_record["id"] if species_record else None

                prec = float(prec_values[idx]) if idx < len(prec_values) else None
                rec  = float(rec_values[idx]) if idx < len(rec_values) else None
                map5095 = float(map5095_values[idx]) if idx < len(map5095_values) else None
                map50 = (
                    float(map50_values[idx])
                    if map50_values is not None and idx < len(map50_values)
                    else None
                )
                f1 = (2 * prec * rec / (prec + rec)) if (prec and rec and (prec + rec) > 0) else None

                species_summary = {
                    "training_run_id": training_run_id,
                    "species_id": species_id,
                    "dataset_split": "val",
                    "precision": prec,
                    "recall": rec,
                    "map50": map50,         # per-class if available
                    "map5095": map5095,
                    "f1_score": f1,
                    "fitness": fitness_value,  # same global fitness applied to each species
                    "timestamp": datetime.now().isoformat(),
                }

                functions.createDatabaseMetricsSummary(species_summary)
                print(f"[DB] Saved metrics summary for species '{species_name}' (id={species_id})")

                functions.createDatabaseModelSpecies({
                    "model_id": model_id,
                    "species_id": species_id,
                    "precision_mean": prec,
                    "recall_mean": rec,
                    "f1_mean": f1,
                    "notes": f"Auto-linked after training run {training_run_id}"
                })
                print(f"[DB] Linked model {model_id} ↔ species '{species_name}' in model_species")

        except Exception as e:
            print(f"[WARNING] Failed saving per-species summaries: {e}")

        # Generate evaluation charts
        print("Generating evaluation charts...")

        # Path to results
        training_results_file = os.path.join(output_folder, new_model_name, "results.csv")

        # ------------------------------------------------------------
        # Update ml_model record after training completes
        # ------------------------------------------------------------
        weights_folder = os.path.join(output_folder, new_model_name, "weights")

        # This folder should contain best.pt, last.pt, etc.
        trained_weights_file = os.path.join(weights_folder, "best.pt")

        update_training_run_data = {
            "end_time": datetime.now().isoformat()
        }

        functions.updateDatabaseTrainingRun(training_run_id, update_training_run_data)
        print(f"[DB] Updated training_run id={training_run_id} with end_time and status.")

        print(f"[DB] Updated ml_model {model_id}: "
            f"storage_path='{weights_folder}', name='{config['new_model_name']}.pt', status='trained'")
        

        # ------------------------------------------------------------
        # Final weight renaming (keep last.pt, rename best.pt → modelname.pt)
        # ------------------------------------------------------------
        weights_folder = os.path.join(output_folder, new_model_name, "weights")
        best_path = os.path.join(weights_folder, "best.pt")
        named_path = os.path.join(weights_folder, f"{config['new_model_name']}.pt")

        try:
            # Remove any stale copy from previous epochs
            if os.path.exists(named_path):
                os.remove(named_path)

            # Copy the final stripped best.pt to modelname.pt
            if os.path.exists(best_path):
                shutil.copy2(best_path, named_path)
                print(f"[INFO] Final model saved as {named_path}")
            else:
                print("[WARNING] best.pt not found at end of training.")

        except Exception as e:
            print(f"[WARNING] Failed to finalize model weights: {e}")


        update_data = {
            "status": "trained",
            "storage_path": weights_folder +"\\",
            "updated_at": datetime.now().isoformat()
        }

        functions.updateDatabaseModel(model_id, update_data)

        

        # Generate training charts
        if os.path.exists(training_results_file):
            plot_training_results(training_results_file, os.path.join(output_folder, "transfer_training"))

        # Print final metrics
        print("\nFinal Metrics:")

        print(metrics)  # Inspect the object
        print(dir(metrics))  # List available attributes or methods


        print(f"Precision: {metrics.results_dict.get('metrics/precision(B)', 0):.3f}")
        print(f"Recall: {metrics.results_dict.get('metrics/recall(B)', 0):.3f}")
        print(f"mAP@50: {metrics.results_dict.get('metrics/mAP50(B)', 0):.3f}")
        print(f"mAP@50-95: {metrics.results_dict.get('metrics/mAP50-95(B)', 0):.3f}")


        print("Training and evaluation complete. Results saved in:", output_folder)
    except Exception as e:

         print("There was an exception" + str(e))
    


def saveAllMetricsCurves(metrics, summary_id):
    try:
        conf_thresholds = metrics.box.px
        now = datetime.now().isoformat()

        # ---------------- Aggregate curves ----------------
        agg_prec = np.mean(metrics.box.p_curve, axis=0)
        agg_rec  = np.mean(metrics.box.r_curve, axis=0)
        agg_f1   = np.mean(metrics.box.f1_curve, axis=0)

        agg_records = [{
            "metrics_summary_id": summary_id,
            "species_id": None,
            "confidence_threshold": float(conf),
            "precision": float(agg_prec[i]),
            "recall": float(agg_rec[i]),
            "f1_score": float(agg_f1[i]),
            "support": None,
            "created_at": now,
            "updated_at": now,
        } for i, conf in enumerate(conf_thresholds)]

        # ---------------- Per-species curves ----------------
        species_records = []
        for class_idx, class_name in metrics.names.items():
            species_record = functions.getSpeciesByComname(class_name)
            species_id = species_record["id"] if species_record else None

            p_curve = metrics.box.p_curve[class_idx]
            r_curve = metrics.box.r_curve[class_idx]
            f1_curve = metrics.box.f1_curve[class_idx]

            for i, conf in enumerate(conf_thresholds):
                species_records.append({
                    "metrics_summary_id": summary_id,
                    "species_id": species_id,
                    "confidence_threshold": float(conf),
                    "precision": float(p_curve[i]),
                    "recall": float(r_curve[i]),
                    "f1_score": float(f1_curve[i]),
                    "support": None,
                    "created_at": now,
                    "updated_at": now,
                })

        # ---------------- Send both in bulk ----------------
        print(f"[DB] Inserting {len(agg_records)} aggregate + {len(species_records)} per-species curve points…")
        functions.createDatabaseMetricsCurvesBulk(agg_records + species_records)

    except Exception as e:
        print(f"[WARNING] Failed saving all metrics_curves: {e}")


# Ensure Matplotlib charts are saved
def plot_training_results(results_file, output_folder):


    try:
        # Read results file
        df = pd.read_csv(results_file)

        # Plot metrics
        plt.figure(figsize=(10, 6))
        plt.plot(df["epoch"], df["metrics/precision(B)"], label="Precision")
        plt.plot(df["epoch"], df["metrics/recall(B)"], label="Recall")
        plt.plot(df["epoch"], df["metrics/mAP50(B)"], label="mAP@50")
        plt.plot(df["epoch"], df["metrics/mAP50-95(B)"], label="mAP@50-95")
        plt.xlabel("Epoch")
        plt.ylabel("Metric Value")
        plt.title("Training Metrics Over Epochs")
        plt.legend()
        plt.grid()
        chart_path = os.path.join(output_folder, "training_metrics.png")
        plt.savefig(chart_path)
        plt.close()
        print(f"Training metrics chart saved to {chart_path}")

        # Plot losses
        plt.figure(figsize=(10, 6))
        plt.plot(df["epoch"], df["loss/box"], label="Box Loss")
        plt.plot(df["epoch"], df["loss/obj"], label="Objectness Loss")
        plt.plot(df["epoch"], df["loss/cls"], label="Class Loss")
        plt.xlabel("Epoch")
        plt.ylabel("Loss Value")
        plt.title("Loss Metrics Over Epochs")
        plt.legend()
        plt.grid()
        chart_path = os.path.join(output_folder, "loss_metrics.png")
        plt.savefig(chart_path)
        plt.close()
        print(f"Loss metrics chart saved to {chart_path}")

    except Exception as e:
        print(f"An error occurred while plotting training results: {e}")

# ------------------------------------------------------------
# onSelectDataset
# ------------------------------------------------------------
# Handles user selection of a dataset.
# Fetches dataset details from the backend and launches ML training.
# ------------------------------------------------------------
def onSelectDataset(dataset_id, parent):
    print(f"[INFO] Dataset selected (ID={dataset_id})")
    dataset_info = functions.getDatabaseDatasetById(dataset_id)

    if not dataset_info:
        messagebox.showerror("Error", "Failed to retrieve dataset info.")
        return

    messagebox.showinfo("Dataset Selected", f"Launching ML Training for:\n{dataset_info['name']}")
    #startMlTraining(dataset_info)
    open_training_config_window(parent, dataset_info)


# ==========================================================
# MAIN DATASET SELECTION WINDOW
# ==========================================================
def dataset_selection_window():
    """
    GUI window for selecting or creating a training dataset.
    (GUI only — includes placeholder for 'Build New Dataset')
    """

    # --- Window setup ---
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Select Training Dataset")
    root.geometry("950x550")

    # --- Layout configuration ---
    root.grid_columnconfigure(0, weight=2)
    root.grid_columnconfigure(1, weight=3)
    root.grid_rowconfigure(0, weight=1)

    bold_font = ("TkDefaultFont", 11, "bold")

    # ------------------------------------------------------
    # LEFT COLUMN: Dataset source + actions
    # ------------------------------------------------------
    left_frame = ctk.CTkFrame(root)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
    left_frame.grid_columnconfigure((0, 1), weight=1)

    # --- Source selection ---
    ctk.CTkLabel(left_frame, text="Dataset Source:", font=bold_font).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5)
    )

    source_var = ctk.StringVar(value="database")

    # --- Frame toggle logic ---
    def on_source_change():
        selected = source_var.get()
        db_frame.grid_remove()
        fs_frame.grid_remove()
        new_frame.grid_remove()

        if selected == "database":
            db_frame.grid()
        elif selected == "filesystem":
            fs_frame.grid()
        elif selected == "new":
            new_frame.grid()

    # Radio buttons
    ctk.CTkRadioButton(left_frame, text="From Database",
                       variable=source_var, value="database",
                       command=on_source_change).grid(row=1, column=0, sticky="w", padx=10)

    ctk.CTkRadioButton(left_frame, text="From Filesystem",
                       variable=source_var, value="filesystem",
                       command=on_source_change).grid(row=1, column=1, sticky="w", padx=10)

    ctk.CTkRadioButton(left_frame, text="Build New Dataset",
                       variable=source_var, value="new",
                       command=on_source_change).grid(row=2, column=0, sticky="w", padx=10, pady=(5, 0))

    # --- Database frame ---
    db_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
    db_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(15, 10))
    ctk.CTkLabel(db_frame, text="(Database datasets will be listed on the right)", text_color="gray").pack(pady=20)

    # --- Filesystem frame ---
    fs_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
    fs_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(15, 10))
    fs_frame.grid_remove()

    def browse_dataset_folder():
        folder = filedialog.askdirectory(title="Select Dataset Folder")
        if not folder:
            return
        messagebox.showinfo("Selected Folder", f"You selected:\n{folder}")

    ctk.CTkButton(fs_frame, text="Browse Dataset Folder",
                  command=browse_dataset_folder).pack(pady=20)

    # --- New Dataset frame ---
    new_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
    new_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(15, 10))
    new_frame.grid_remove()

    ctk.CTkLabel(new_frame, text="Create a New Dataset", font=bold_font).pack(pady=(5, 10))
    ctk.CTkLabel(new_frame, text="(This will open a dataset builder window)", text_color="gray").pack()
    ctk.CTkButton(new_frame, text="Open Dataset Builder",
                  width=160, command=lambda: open_dataset_builder(root)).pack(pady=20)

    # ------------------------------------------------------
    # RIGHT COLUMN: Dataset table / info viewer
    # ------------------------------------------------------
    right_frame = ctk.CTkFrame(root)
    right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
    right_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

    # Header row
    headers = ["Name", "Samples", "Classes", "Created"]
    for col, h in enumerate(headers):
        ctk.CTkLabel(right_frame, text=h, font=bold_font).grid(row=0, column=col, padx=5, pady=5)

    # Dummy dataset rows
    """ example_datasets = [
        ("Fish2025", "48,320", "57", "2025-10-01"),
        ("InvertSetB", "12,008", "22", "2025-09-15"),
        ("GulfMix", "31,245", "40", "2025-07-10")
    ] """

    database_datasets = functions.getDatabaseDatasets();

    headers = ["Name", "Samples", "Classes", "Created", "Action"]
    for col, header in enumerate(headers):
        ctk.CTkLabel(right_frame, text=header, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=col, padx=5, pady=(0,5))

    for i, dataset in enumerate(database_datasets, start=1):
        dataset_id = dataset.get("id")
        name = dataset.get("name", "N/A")
        samples = dataset.get("num_samples", "N/A")
        classes = dataset.get("num_classes", "N/A")
        created = dataset.get("created_at", "N/A")

        ctk.CTkLabel(right_frame, text=name).grid(row=i, column=0, sticky="w", padx=5)
        ctk.CTkLabel(right_frame, text=samples).grid(row=i, column=1)
        ctk.CTkLabel(right_frame, text=classes).grid(row=i, column=2)
        ctk.CTkLabel(right_frame, text=created[:10] if created else "N/A").grid(row=i, column=3)  # trim to date only

        # Button now calls the dataset selection function
        ctk.CTkButton(
            right_frame,
            text="Select",
            width=70,
            command=lambda d_id=dataset_id: onSelectDataset(d_id, root)
        ).grid(row=i, column=4, padx=5)


    # ------------------------------------------------------
    # Bottom buttons
    # ------------------------------------------------------
    ctk.CTkButton(root, text="Continue", width=120).grid(
        row=1, column=0, columnspan=2, pady=(0, 20)
    )

    root.mainloop()


# ==========================================================
# MODEL TRAINING CONFIGURATION WINDOW
# ==========================================================
def open_training_config_window(parent, dataset_info):
    """
    Opens a popup window to configure model training parameters.
    Allows selecting transfer model, epochs, batch size, and patience.
    """
    # --- Window setup ---
    popup = ctk.CTkToplevel(parent)
    popup.title("Model Training Configuration")
    popup.geometry("600x400")
    popup.grab_set()  # Lock focus to popup until closed

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    bold_font = ("TkDefaultFont", 11, "bold")

    # --- Layout ---
    popup.grid_columnconfigure(0, weight=1)
    popup.grid_rowconfigure(0, weight=1)

    frame = ctk.CTkFrame(popup)
    frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

    ctk.CTkLabel(frame, text=f"Training Configuration for: {dataset_info['name']}", font=("TkDefaultFont", 14, "bold")).pack(pady=(5, 20))

    # ------------------------------------------------------
    # Helper for tooltips
    # ------------------------------------------------------
    class HoverTip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text = text
            self.tip_window = None
            widget.bind("<Enter>", self.show_tip)
            widget.bind("<Leave>", self.hide_tip)

        def show_tip(self, event=None):
            if self.tip_window or not self.text:
                return
            x, y, cx, cy = self.widget.bbox("insert")
            x = x + self.widget.winfo_rootx() + 25
            y = y + cy + self.widget.winfo_rooty() + 20
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                tw,
                text=self.text,
                justify="left",
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=("TkDefaultFont", 9)
            )
            label.pack(ipadx=1)

        def hide_tip(self, event=None):
            if self.tip_window:
                self.tip_window.destroy()
                self.tip_window = None


    # ------------------------------------------------------
    # 0. New Model Name
    # ------------------------------------------------------
    ctk.CTkLabel(frame, text="New Model Name:", font=bold_font).pack(anchor="w")
    model_name_var = ctk.StringVar(value="")  # User-defined model name
    name_entry = ctk.CTkEntry(frame, textvariable=model_name_var, placeholder_text="Enter new model name")
    name_entry.pack(pady=(0, 15), fill="x")
    HoverTip(name_entry, "Give a unique name to the new model that will be created after training.")


    # ------------------------------------------------------
    # 1. Model Selection
    # ------------------------------------------------------
    ctk.CTkLabel(frame, text="Transfer Model:", font=bold_font).pack(anchor="w")

    # Retrieve full model records
    models_list = functions.getDatabaseModels()

    # Build dropdown values and mapping for quick lookup
    model_names = ["None"] + [m.get("name", "Unnamed") for m in models_list]
    model_lookup = {m.get("name"): m for m in models_list}

    model_var = ctk.StringVar(value=model_names[0])
    model_dropdown = ctk.CTkComboBox(frame, variable=model_var, values=model_names, width=300)
    model_dropdown.pack(pady=(0, 15))
    HoverTip(model_dropdown, "Select a base model to transfer weights from (or None for fresh training).")

    # ------------------------------------------------------
    # 2. Epochs
    # ------------------------------------------------------
    ctk.CTkLabel(frame, text="Epochs:", font=bold_font).pack(anchor="w")
    epochs_var = ctk.IntVar(value=200)
    epochs_entry = ctk.CTkEntry(frame, textvariable=epochs_var, width=100)
    epochs_entry.pack(pady=(0, 15))
    HoverTip(epochs_entry, "Number of complete passes through the training dataset.")

    # ------------------------------------------------------
    # 3. Batch Size
    # ------------------------------------------------------
    ctk.CTkLabel(frame, text="Batch Size:", font=bold_font).pack(anchor="w")
    batch_var = ctk.IntVar(value=16)
    batch_entry = ctk.CTkEntry(frame, textvariable=batch_var, width=100)
    batch_entry.pack(pady=(0, 15))
    HoverTip(batch_entry, "Number of samples processed before the model’s internal parameters are updated.")

    # ------------------------------------------------------
    # 4. Patience
    # ------------------------------------------------------
    ctk.CTkLabel(frame, text="Patience:", font=bold_font).pack(anchor="w")
    patience_var = ctk.IntVar(value=50)
    patience_entry = ctk.CTkEntry(frame, textvariable=patience_var, width=100)
    patience_entry.pack(pady=(0, 15))
    HoverTip(patience_entry, "Number of epochs with no improvement before early stopping.")

    # ------------------------------------------------------
    # 5. Start Button
    # ------------------------------------------------------
    def start_training():
        selected_model_name = model_var.get()
        selected_model = model_lookup.get(selected_model_name) if selected_model_name != "None" else None

        config = {
            "new_model_name": model_name_var.get().strip(),  # <-- NEW FIELD
            "transfer_model_name": selected_model_name if selected_model_name != "None" else None,
            "transfer_model_id": selected_model.get("id") if selected_model else None,
            "transfer_model_path": selected_model.get("storage_path") if selected_model else None,
            "epochs": epochs_var.get(),
            "batch_size": batch_var.get(),
            "patience": patience_var.get()
        }

        print("[TRAINING CONFIG]", config)
        popup.destroy()
        startMlTraining(dataset_info, config)

    ctk.CTkButton(frame, text="Start Training", command=start_training, width=160).pack(pady=(20, 5))

    ctk.CTkButton(frame, text="Cancel", command=popup.destroy, width=100).pack(pady=(5, 10))


# ==========================================================
# STANDALONE TEST HARNESS
# ==========================================================
if __name__ == "__main__":
    print("Launching Model Training GUI...")
    dataset_selection_window()