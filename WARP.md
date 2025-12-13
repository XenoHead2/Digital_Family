# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Digital Family is a PyQt6-based desktop application that creates customizable AI chatbot characters with emotional responses, memory systems, and text-to-speech capabilities. Each character has individual profiles, conversation history, and visual emotion displays through images.

## Architecture

### Multi-Window PyQt6 Architecture
- **Launcher Window** (`LauncherWindow`): Main entry point for selecting character profiles
- **Chat Window** (`ChatWindow`): Individual conversation windows for each character  
- **Profile Creator** (`ProfileCreatorWindow`): Character creation/editing interface
- **Emotion Map Editor** (`EmotionMapEditor`): Visual emotion mapping system
- **Memory Window** (`MemoryWindow`): Manual memory management interface

### Core Components
- **start.py**: Main application entry point and GUI implementation
- **gui_windows.py**: Separated GUI window classes (modular approach)
- **llm_workers.py**: Currently contains main() but should contain LLM worker threads
- **elevenlabs_tts.py**: ElevenLabs TTS integration (exclusive TTS solution)

### Data Structure
```
profiles/           # Character JSON profiles
memory/            # Per-character conversation history and core memories
  {character}_history.json        # Recent conversation context
  {character}_core_memories.json  # Persistent important memories
images/            # Character emotion images organized by character name
  {character}/     # Individual character image folders
icons/             # Application UI icons
```

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Alternative quick setup
getready.bat
```

### Running the Application
```bash
# Main application
python start.py

# Quick launcher
go.bat
```

### Development Workflow
```bash
# Install new dependencies
pip install <package_name>
pip freeze > requirements.txt

# Version control
git add .
git commit -m "feat: description"
git push
# OR use: commitall.bat
```

## Character Profile System

Characters are defined in JSON files in the `profiles/` directory with this structure:
- **Basic Info**: name, age, gender, user_name (what they call you)
- **Appearance**: hair, eyes, body_type descriptions
- **Personality**: likes, dislikes, extra_info, behavioral instructions
- **Emotion System**: emotion_map (keyword → image mappings), default_emotion
- **TTS**: tts_voice (ElevenLabs voice ID per character)

## Memory Architecture

### Two-Tier Memory System
1. **Short-term History**: Recent conversation context (max 20 messages)
2. **Core Memories**: Manually saved important memories with timestamps

### Memory Files
- Automatic history saving on window close
- Manual memory saving through GUI "Save Memory" button
- JSON format with role/content structure for LLM context

## Emotion & Visual System

### Dynamic Emotion Display
- 200x200 pixel emotion display in chat window
- Keyword-based emotion triggering from LLM responses
- Fallback to default emotion when no keywords match
- Images organized per character in `images/{character}/` folders

### Text Formatting
- Special formatting for emotive text using regex patterns:
  - `[audio cues]` → Purple italics (Segoe Print)
  - `*actions*` → Red bold (Comic Sans MS)
  - Regular text → Black (Times New Roman)

## LLM Integration

### Current State
The project references `ChatWorker` and `ImageDescriptionWorker` classes that handle:
- Asynchronous LLM API calls
- Image processing and description
- Response threading to prevent GUI blocking

### Integration Points
- System prompt built from character profile data
- Conversation history management
- Image attachment support (PNG, JPG, JPEG)
- Text file attachment support

## TTS Integration

### ElevenLabs (Exclusive TTS Solution)
- API key stored in `.env` file as `ELEVENLABS_API_KEY`
- Voice settings: stability=0.0, similarity_boost=1.0, style=0.0, use_speaker_boost=True
- Automatic speech synthesis on LLM responses
- Each character has configurable `tts_voice` ID in their profile
- Default fallback voice: Adam (pNInz6obpgDQGcFmaJgB)

### Voice Processing
- Strips emotive text markers `[audio]` and `*actions*` before TTS
- Streaming audio generation for real-time playback
- Uses `eleven_multilingual_v2` model for multilingual support
- Error handling for API failures

## Development Phases

The project follows a structured development approach:

### Phase 1: Stable Core ✅ 
- PyQt6 multi-window architecture
- Basic character profiles and chat interface

### Phase 2: Memory System 🔄
- Per-character memory files
- Manual memory control
- Long-term vs key memory distinction

### Phase 3: Visual Features 🔄
- Static emotion images (implemented)
- Planned: Animated GIF support
- File attachment system

### Phase 4: LoRA Integration 📅
- Custom character personality training
- Integration with running application

### Phase 5: Voice Chat 📅
- Microphone input
- Speech-to-text integration
- Full voice conversation capability

## Environment Configuration

### Required Environment Variables
```
ELEVENLABS_API_KEY=your_api_key_here
```

### Python Dependencies
- PyQt6: GUI framework
- elevenlabs: ElevenLabs TTS service (exclusive)
- python-dotenv: Environment management
- requests: HTTP client
- speech_recognition: STT functionality (for future voice input)
- pyaudio, sounddevice, numpy: Audio processing
- pillow: Image processing

## File Attachment System

### Supported File Types
- **Images**: PNG, JPG, JPEG (converted to base64 for LLM)
- **Text Files**: Read and embedded in conversation context
- Asynchronous image description generation
- Visual feedback in chat interface

## Common Issues & Solutions

### Missing Worker Classes
If `ChatWorker` or `ImageDescriptionWorker` are not found, they need to be implemented in `llm_workers.py` or a separate module as QThread subclasses.

### Image Loading Errors
The system includes safety checks for corrupted images and will display error messages instead of crashing.

### Memory File Corruption
JSON decode errors in memory files are handled gracefully with fallback to empty memory structures.

## Testing Character Profiles

Create test profiles in `profiles/` directory following the JSON structure in existing profiles like `Kimmy.json`. Ensure corresponding image directories exist in `images/{character_name}/`.
