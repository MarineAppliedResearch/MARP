from TTS.api import TTS

# Get the TTS model manager
model_manager = TTS().list_models()

# List the available models
available_models = model_manager.models_dict["tts_models"]["en"]["ljspeech"]
print("Available models:")
for model in available_models:
    print(f"- {model}")
