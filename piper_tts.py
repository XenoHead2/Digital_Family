import os
import re
import io
import pygame
import time
import wave
from datetime import datetime
from piper.voice import PiperVoice 

# --- Configuration ---
# NOTE: TTS_MODEL_DIR is relative to the location of this file
TTS_MODEL_DIR = os.path.join(os.path.dirname(__file__), "tts_models") 

# Initialize without a fixed frequency; we will set it per-voice
if not pygame.mixer.get_init():
    pygame.mixer.init()

# Cache for loaded voices
VOICE_CACHE = {}

def log_to_file(message):
    """Simple logging function (you can replace this with your project's main log_to_file)."""
    # This function should already exist in your main app, but we define it here
    # for completeness in case this module is run standalone.
    with open("debug_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] [TTS] {message}\n")

def load_piper_voice(model_file_path):
    """Loads a Piper voice model and caches it."""
    if model_file_path in VOICE_CACHE:
        return VOICE_CACHE[model_file_path]
    try:
        # Ensure the file actually exists before loading
        if not os.path.exists(model_file_path):
            log_to_file(f"MISSING MODEL FILE: {model_file_path}")
            return None
        
        # --- NEW: Check if the associated JSON config file is empty ---
        config_path = f"{model_file_path}.json"
        if not os.path.exists(config_path) or os.path.getsize(config_path) == 0:
            log_to_file(f"CRITICAL: Model config file is missing or empty: {config_path}")
            log_to_file("Please re-download the voice model, ensuring you have both the .onnx and the .onnx.json files.")
            return None
        # --- END NEW ---

        voice = PiperVoice.load(model_file_path)
        VOICE_CACHE[model_file_path] = voice
        return voice
    except Exception as e:
        log_to_file(f"Error loading Piper voice: {e}")
        return None

def speak_text(text, voice_model_name=None):
    """
    Synthesizes speech using a local Piper model and plays it using pygame.
    """
    # 1. Clean text
    cleaned_text = re.sub(r'\[.*?\]|\*.*?\*', '', text).strip()
    if not cleaned_text:
        return
    if not voice_model_name:
        voice_model_name = "en_US-ljspeech-high.onnx"
    model_path = os.path.join(TTS_MODEL_DIR, voice_model_name)
    voice = load_piper_voice(model_path)
    if not voice:
        return
    try:
        # --- CRITICAL FIX: RE-INIT MIXER TO MATCH MODEL ---
        # Piper models are picky. If the mixer is 44100Hz and model is 22050Hz, 
        # it might play at 2x speed or just fail silently.
        pygame.mixer.quit()
        pygame.mixer.init(frequency=voice.config.sample_rate, channels=1, size=-16)
        audio_io = io.BytesIO()
        with wave.open(audio_io, 'wb') as wav_file:
            voice.synthesize_wav(cleaned_text, wav_file)
        audio_io.seek(0)

        # Load and Play
        pygame.mixer.music.load(audio_io, 'wav') 
        pygame.mixer.music.play()
        # --- CRITICAL FIX: THE PLAYBACK LOOP ---
        # Without this, the function returns, audio_io is destroyed, and sound stops.
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        log_to_file(f"Synthesis/Playback Error: {e}")