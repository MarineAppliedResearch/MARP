import torch
from TTS.api import TTS

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"

# List available 🐸TTS models
print("Available models:", TTS().list_models())

# Init TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Debug tokenizer configuration
try:
    tokenizer = tts.tokenizer  # If the tokenizer is accessible
    print(f"PAD Token ID: {tokenizer.pad_token_id}")
    print(f"EOS Token ID: {tokenizer.eos_token_id}")
    if tokenizer.pad_token_id == tokenizer.eos_token_id:
        tokenizer.pad_token = "<pad>"
        tokenizer.add_special_tokens({"pad_token": "<pad>"})
        tts.model.resize_token_embeddings(len(tokenizer))
except AttributeError:
    print("Tokenizer configuration could not be accessed.")

# Run TTS
# Save speech to file
tts.tts_to_file(
    text="Soo, this is my best try at cloning my own voice that i've been able to do so far. But as you can tell, it doesn't sound much like me yet.",
    speaker_wav="voice_samples/Isaac6.wav",
    language="en",
    file_path="voice_output/speech12.wav"
)