"""
transfer_train_yolo.py

Description:
This script performs transfer training on a YOLO model using the `yolo_dataset` dataset. It:
1. Fine-tunes a pre-trained YOLO model on the provided dataset.
2. Outputs evaluation metrics, including precision, recall, mAP, and loss.
3. Generates training logs and evaluation charts.

Usage:
1. Install dependencies: 'pip install ultralytics matplotlib'.
2. Ensure `yolo_dataset` is prepared with `classnames.yaml`, `train`, and `eval` folders.
3. Run the script: 'python transfer_train_yolo.py'.

Dependencies:
- Python 3.x
- Ultralytics YOLO library
- Matplotliby
"""

import os
from ultralytics import YOLO
import shutil
import matplotlib.pyplot as plt

import torch

# Ensure Matplotlib charts are saved
def plot_training_results(results_file, output_folder):
    import pandas as pd

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
if __name__ == "__main__":

    print("CUDA AVAILABLE: " + str(torch.cuda.is_available()))  # Should return True if CUDA is available
    print("Device Count: " + str(torch.cuda.device_count()))  # Number of GPUs available

    try:
        print(torch.cuda.get_device_name(0))  # Name of the first GPU (if available)
    except Exception as e:
        print(str(e))




    # Paths to dataset and model
    yolo_dataset_folder = "yolo_dataset"
    classnames_file = os.path.join(yolo_dataset_folder, "classnames.yaml")
    train_images_folder = os.path.join(yolo_dataset_folder, "train", "images")
    eval_images_folder = os.path.join(yolo_dataset_folder, "eval", "images")

    # Ensure the dataset and classnames file exist
    if not os.path.exists(yolo_dataset_folder) or not os.path.exists(classnames_file):
        print("Error: `yolo_dataset` or `classnames.yaml` not found. Ensure the dataset is prepared.")
        exit()

    # Model configuration
    model_name = "mare-cucumber"  # Example: yolov8n, yolov8s, yolov8m, yolov8l, yolov8x
    pretrained_weights = f"{model_name}.pt"  # Pre-trained weights
    epochs = 300  # Number of epochs for training
    batch_size = 16  # Batch size

    # Output paths
    output_folder = "yolo_training_output"
    os.makedirs(output_folder, exist_ok=True)

    # Load the model
    print(f"Loading pre-trained YOLO model: {model_name}")



    model = YOLO(pretrained_weights)

    device = "0" if torch.cuda.is_available() else "cpu"

    # Train the model
    print("Starting training...")

    results = model.train(
        data=classnames_file,
        epochs=epochs,
        imgsz=640,
        project=output_folder,
        name="transfer_training",
        device=device,  # Automatically use GPU if available, else fallback to CPU
        batch=batch_size
    )

    # Evaluate the model
    print("Evaluating model...")
    metrics = model.val()

    # Generate evaluation charts
    print("Generating evaluation charts...")

    # Path to results
    training_results_file = os.path.join(output_folder, "transfer_training", "results.csv")



    # Generate training charts
    if os.path.exists(training_results_file):
        plot_training_results(training_results_file, os.path.join(output_folder, "transfer_training"))

    # Print final metrics
    print("\nFinal Metrics:")

    print(metrics)  # Inspect the object
    print(dir(metrics))  # List available attributes or methods


    print(f"Precision: {metrics.precision:.3f}")
    print(f"Recall: {metrics.recall:.3f}")
    print(f"mAP@50: {metrics.mAP50:.3f}")
    print(f"mAP@50-95: {metrics.mAP50_95:.3f}")


    print("Training and evaluation complete. Results saved in:", output_folder)
