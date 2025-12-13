import os
import re
import io
import pygame
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load your Eleven Labs API key from the environment variable
client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Initialize pygame mixer for audio playback
pygame.mixer.init()

def play_audio_stream(audio_generator):
    """Play audio using pygame from a generator of audio chunks."""
    try:
        # Collect all audio data
        audio_data = b''.join(audio_generator)
        
        # Create a BytesIO object to treat bytes as a file
        audio_file = io.BytesIO(audio_data)
        
        # Load and play the audio
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        
        # Wait for playback to finish
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
            
    except Exception as e:
        print(f"Pygame audio error: {e}")
        raise

def speak_text(text, voice_id=None):
    """
    Synthesizes speech from the input text and plays it using ElevenLabs TTS.
    
    Args:
        text (str): The text to be synthesized.
        voice_id (str): The unique ID of the voice to use.
    """
    if not text or not text.strip():
        return
        
    # Strip out emotive text before speaking
    cleaned_text = re.sub(r'\[.*?\]|\*.*?\*', '', text).strip()
    
    if not cleaned_text:
        return

    # Use the selected voice or a default one
    if voice_id:
        voice_to_use = voice_id
    else:
        # Use Adam voice as default
        voice_to_use = "pNInz6obpgDQGcFmaJgB"
    
    try:
        # Generate the audio from the text using the newer API
        audio = client.text_to_speech.convert(
            voice_id=voice_to_use,
            text=cleaned_text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
            ),
        )
        
        # Use pygame to play the audio stream
        play_audio_stream(audio)
        
    except Exception as e:
        print(f"TTS Error: {e}")
