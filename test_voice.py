# test_voice.py
import os
import sys
import traceback

# This is the only way to be 100% sure we catch every error.
try:
    # We import here to ensure a clean slate.
    from piper_tts import speak_text, log_to_file
    import pygame

    print("--- Starting TTS Test ---")
    log_to_file("--- Starting standalone TTS test. ---")

    # --- Step 1: Check for models folder ---
    if not os.path.exists("tts_models"):
        raise FileNotFoundError("FATAL: 'tts_models' directory not found.")
    print("[PASS] Found 'tts_models' directory.")

    # --- Step 2: Define model and phrase ---
    voice_model = "en_US-ljspeech-high.onnx"
    test_phrase = "Hello, can you hear me now? This is a direct test of the Piper text-to-speech system."
    print(f"Attempting to speak: '{test_phrase}'")
    print(f"Using voice model: {voice_model}")

    # --- Step 3: Force-quit pygame to resolve any conflicts ---
    if pygame.mixer.get_init():
        print("Pygame mixer was already initialized. Forcing quit to ensure clean state.")
        pygame.mixer.quit()

    # --- Step 4: Call the speak function ---
    print("Calling speak_text()...")
    speak_text(test_phrase, voice_model_name=voice_model)
    print("--- Test finished successfully. You should have heard audio. ---")
    log_to_file("--- Standalone TTS test completed successfully. ---")

except Exception:
    # This will catch EVERYTHING and print it.
    print("\n--- !!! TEST FAILED !!! ---")
    print("A critical error occurred. See details below:")
    exc_type, exc_value, exc_traceback = sys.exc_info()
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stdout)
    log_to_file(f"CRITICAL ERROR in standalone test: {traceback.format_exc()}")


