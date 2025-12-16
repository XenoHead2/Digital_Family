import os
import requests
import json
from PyQt6.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv

load_dotenv()


class ChatWorker(QThread):
    """Worker thread for handling LLM API calls asynchronously."""
    response_chunk_ready = pyqtSignal(str)
    response_finished = pyqtSignal()
    
    def __init__(self, conversation_history):
        super().__init__()
        self.conversation_history = conversation_history
    
    def run(self): 
        """Make the API call in the background thread and stream the response."""
        print("--- ChatWorker: Starting streaming API call ---")
        try:
            messages = []
            for msg in self.conversation_history:
                if msg.get('role') in ['system', 'user', 'assistant']:
                    content = msg.get('content', '')
                    # --- NEW: Handle vision-style content for non-vision models ---
                    if isinstance(content, list):
                        # Reconstruct a text-only version of the content
                        text_parts = []
                        for item in content:
                            if item.get('type') == 'text':
                                text_parts.append(item['text'])
                            elif item.get('type') == 'image_url':
                                text_parts.append("[user sent an image]")
                        content = ' '.join(text_parts).strip()
                    messages.append({'role': msg['role'], 'content': content})
            
            data = {
                'model': 'llama3.2:1b',
                'messages': messages,
                'temperature': 0.7,
                'max_tokens': 300,
                'stream': True
            }
            
            print(f"--- ChatWorker: Sending data to http://localhost:11434/api/chat:\n{json.dumps(data, indent=2)} ---")
            print(f"--- ChatWorker: Prompt length: {len(json.dumps(data['messages']))} characters ---")

            
            with requests.post('http://localhost:11434/api/chat', json=data, timeout=600, stream=True) as response:
                print(f"--- ChatWorker: Received status code {response.status_code} ---")
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            try:
                                result = json.loads(line)
                                message_chunk = result.get('message', {})
                                content_chunk = message_chunk.get('content', '')
                                if content_chunk:
                                    self.response_chunk_ready.emit(content_chunk)
                            except json.JSONDecodeError:
                                print(f"--- ChatWorker: Could not decode JSON line: {line} ---")
                else:
                    error_message = f"Sorry, I'm having trouble connecting. (Error {response.status_code})"
                    print(f"--- ChatWorker: Error response body:\n{response.text} ---")
                    self.response_chunk_ready.emit(error_message)

        except Exception as e:
            error_message = f"--- ChatWorker: CRITICAL ERROR: {str(e)} ---"
            print(error_message)
            self.response_chunk_ready.emit(error_message)
        finally:
            print("--- ChatWorker: Stream finished. ---")
            self.response_finished.emit()

class ImageDescriptionWorker(QThread):
    """Worker thread for generating image descriptions asynchronously."""
    description_ready = pyqtSignal(str, str)  # message_id, description
    
    def __init__(self, base64_image, message_id):
        super().__init__()
        self.base64_image = base64_image
        self.message_id = message_id
    
    def run(self):
        """Generate image description in the background thread."""
        try:
            # --- NEW: Implement image description using Ollama ---
            # This uses a vision-capable model like 'llava'
            data = {
                "model": "llava", # Make sure you have a vision model like 'llava' pulled in Ollama
                "prompt": "Describe this image in one brief sentence from the user's point of view, as if they are showing it to someone.",
                "images": [self.base64_image],
                "stream": False # We want the full description at once
            }

            print("--- ImageDescriptionWorker: Sending request to Ollama for image description ---")
            response = requests.post('http://localhost:11434/api/generate', json=data, timeout=600)

            if response.status_code == 200:
                result = response.json()
                description = result.get('response', 'Could not get a description.').strip()
                print(f"--- ImageDescriptionWorker: Received description: {description} ---")
                self.description_ready.emit(self.message_id, description)
            else:
                error_text = response.text
                print(f"--- ImageDescriptionWorker: Error from Ollama API: {response.status_code} - {error_text} ---")
                # Check for a common error: model not found
                if "model" in error_text and "not found" in error_text:
                    description = "Vision model not found. Please run 'ollama pull llava' and try again."
                else:
                    description = f"API Error: {response.status_code}"
                self.description_ready.emit(self.message_id, description)

        except Exception as e:
            error_message = f"Error generating image description: {str(e)}"
            print(f"--- ImageDescriptionWorker: CRITICAL ERROR: {error_message} ---")
            self.description_ready.emit(self.message_id, error_message)
