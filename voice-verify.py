from TTS.tts.datasets import load_tts_samples
from TTS.tts.configs.shared_configs import BaseDatasetConfig

dataset_config = BaseDatasetConfig(
    formatter="ljspeech",
    meta_file_train="metadata.csv",
    path = r"C:\Users\MARE\Documents\workspace\Mare_Video_Annotations\voice_samples\processed"

)
# Load all samples
samples = load_tts_samples(dataset_config, eval_split=False)

# Set the split ratio (e.g., 90% training, 10% evaluation)
split_ratio = 0.9
split_index = int(len(samples[0]) * split_ratio)

# Split the samples into training and evaluation sets
train_samples = samples[0][:split_index]
eval_samples = samples[0][split_index:]

print(f"Loaded {len(train_samples)} training samples and {len(eval_samples)} evaluation samples.")
