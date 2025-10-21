import os
import tkinter as tk
from tkinter import filedialog
import torch
from trainer import Trainer, TrainerArgs
from TTS.tts.configs.glow_tts_config import GlowTTSConfig
from TTS.tts.configs.shared_configs import BaseDatasetConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.models.glow_tts import GlowTTS
from TTS.tts.utils.text.tokenizer import TTSTokenizer
from TTS.utils.audio import AudioProcessor
from multiprocessing import freeze_support
import re
#import logging

#logging.basicConfig(level=logging.DEBUG)

def select_folder(title="Select Folder"):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title=title)

def select_file(title="Select File"):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(title=title, filetypes=[("Model Checkpoints", "*.pth")])



def main():
    checkpoint_path = select_file("Select Model Checkpoint (or Cancel to train from scratch)")
    if checkpoint_path:
        print(f"Using checkpoint: {checkpoint_path}")
    else:
        print("No checkpoint selected. Training from scratch.")

    dataset_folder = select_folder("Select Dataset Folder")
    if not dataset_folder:
        raise FileNotFoundError("No dataset folder selected.")

    wavs_folder = os.path.join(dataset_folder, "wavs")
    metadata_path = os.path.join(dataset_folder, "metadata.csv")

    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"metadata.csv not found in {dataset_folder}")
    if not os.path.exists(wavs_folder):
        raise FileNotFoundError(f"'wavs' folder not found in {dataset_folder}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    output_path = os.path.dirname(os.path.abspath(__file__))
    dataset_config = BaseDatasetConfig(
        formatter="ljspeech",
        meta_file_train="metadata.csv",
        path=dataset_folder,
    )

    config = GlowTTSConfig(
        batch_size=32,
        eval_batch_size=16,
        num_loader_workers=0,  # Disable multiprocessing for simplicity
        num_eval_loader_workers=0,
        run_eval=True,
        test_delay_epochs=-1,
        epochs=1000,
        text_cleaner="phoneme_cleaners",
        use_phonemes=True,
        phoneme_language="en-us",
        phoneme_cache_path=os.path.join(output_path, "phoneme_cache"),
        print_step=25,
        print_eval=False,
        mixed_precision=True,
        output_path=output_path,
        datasets=[dataset_config],
    )

    ap = AudioProcessor.init_from_config(config)
    tokenizer, config = TTSTokenizer.init_from_config(config)
    samples = load_tts_samples(dataset_config, eval_split=False)

    samples = load_tts_samples(dataset_config, eval_split=False)

    # Set the split ratio (e.g., 90% training, 10% evaluation)
    split_ratio = 0.9
    split_index = int(len(samples[0]) * split_ratio)

    # Split the samples into training and evaluation sets
    train_samples = samples[0][:split_index]
    eval_samples = samples[0][split_index:]

    model = GlowTTS(config, ap, tokenizer, speaker_manager=None)
    model.to(device)

    if checkpoint_path:
        print(f"Loading checkpoint from {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model"])

    trainer = Trainer(
        TrainerArgs(), config, output_path, model=model, train_samples=train_samples, eval_samples=eval_samples
    )

    # Disable log file handling
    try:
        if __name__ == "__main__":
            freeze_support()
            trainer.fit()
    except PermissionError as e:
        print(f"Ignoring log file error: {e}")


if __name__ == "__main__":
    main()
