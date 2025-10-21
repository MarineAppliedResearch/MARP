import os
import tkinter as tk
from tkinter import filedialog
from pydub import AudioSegment, silence
import whisper
import csv
import re

def select_folder():
    root = tk.Tk()
    root.withdraw()
    folder_selected = filedialog.askdirectory(title="Select Folder with .wav Files")
    return folder_selected

def normalize_text(text):
    # Basic text normalization: lowercasing and removing extra spaces
    text = text.lower().strip()
    
    number_mapping = {
        "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
        "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
    }
    def replace_number(match):
        return " ".join(number_mapping[digit] for digit in match.group())
    
    # Replace percentages and decimal numbers
    text = re.sub(r"(\d+\.\d+)", lambda m: m.group().replace('.', ' point '), text)
    # Replace whole numbers
    text = re.sub(r"\b\d+\b", replace_number, text)
    return text

def process_audio_files(folder):
    # Prepare output directories
    output_folder = os.path.join(folder, "processed")
    wavs_folder = os.path.join(output_folder, "wavs")
    os.makedirs(wavs_folder, exist_ok=True)
    metadata_path = os.path.join(output_folder, "metadata.csv")

    model = whisper.load_model("base")

    with open(metadata_path, mode="w", newline="", encoding="utf-8") as metadata_file:
        csv_writer = csv.writer(metadata_file, delimiter="|")

        for filename in os.listdir(folder):
            if filename.endswith(".wav"):
                file_path = os.path.join(folder, filename)
                print(f"Processing {filename}...")

                # Load audio file
                audio = AudioSegment.from_wav(file_path)

                # Detect silences
                silences = silence.detect_nonsilent(audio, min_silence_len=1000, silence_thresh=-40)

                for i, (start, end) in enumerate(silences):
                    segment = audio[start:end]

                    # Export segment
                    segment_filename = f"{os.path.splitext(filename)[0]}_segment_{i:03d}.wav"
                    segment_path = os.path.join(wavs_folder, segment_filename)
                    segment = segment.set_frame_rate(16000).set_channels(1)  # Resample to 16 kHz mono
                    segment.export(segment_path, format="wav")

                    # Transcribe audio
                    transcription_result = model.transcribe(segment_path)
                    transcription = transcription_result["text"]
                    normalized_transcription = normalize_text(transcription)

                    # Write to metadata (strip '.wav' from the filename)
                    csv_writer.writerow([os.path.splitext(segment_filename)[0], transcription, normalized_transcription])


    print(f"Processing complete. Output saved to {output_folder}")

if __name__ == "__main__":
    folder = select_folder()
    if folder:
        process_audio_files(folder)
    else:
        print("No folder selected. Exiting.")