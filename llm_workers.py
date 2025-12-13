import os
import requests
import json
from PyQt6.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv

load_dotenv()


class ChatWorker(QThread):
    """Worker thread for handling LLM API calls asynchronously."""
    response_ready = pyqtSignal(str)
    
    def __init__(self, conversation_history):
        super().__init__()
        self.conversation_history = conversation_history
    
    def run(self):
        """Make the API call in the background thread, targeting Ollama."""
        # --- Ollama Configuration (LLAMA 3 8B) ---
        OLLAMA_API_URL = "http://localhost:11434/api/chat"
        OLLAMA_MODEL = "artifish/llama3.2-uncensored:latest"
        
        try:
            # Convert conversation history to Ollama-compatible messages format
            messages = []
            for msg in self.conversation_history:
                if msg.get('role') in ['system', 'user', 'assistant']:
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        # Handle multimodal content (only extracting text for Llama3 8B)
                        text_parts = [
                            item.get('text', '')
                            for item in content
                            if isinstance(item, dict) and item.get('type') == 'text'
                        ]
                        content = ' '.join(text_parts)
                    
                    messages.append({
                        'role': msg['role'],
                        'content': content
                    })
            
            # --- Ollama API Call ---
            data = {
                'model': OLLAMA_MODEL,
                'messages': messages,
                'stream': False
            }
            
            print(f"DEBUG: Sending {len(messages)} messages to Ollama")
            print(f"DEBUG: Last message: {messages[-1] if messages else 'None'}")
            
            response = requests.post(OLLAMA_API_URL, json=data, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('message', {}).get('content', 'No response received from Ollama model.')
            else:
                print(f"DEBUG: HTTP {response.status_code} error from Ollama")
                print(f"DEBUG: Response text: {response.text[:500]}...")
                ai_response = f"Sorry, I'm having trouble connecting to Ollama. (Error {response.status_code})"
            
            self.response_ready.emit(ai_response)
        except requests.exceptions.RequestException:
            self.response_ready.emit(f"Connection Error: Could not connect to Ollama at {OLLAMA_API_URL}. Is Ollama running?")
        except Exception as e:
            self.response_ready.emit(f"An unexpected error occurred: {str(e)}")


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
            # Placeholder for actual image description API call
            # You'll need to implement your preferred vision API here
            description = "Image description unavailable. Please configure your vision API in llm_workers.py"
            
            # Example API call structure (you'll need to adapt this to your vision API provider):
            # api_key = os.getenv('OPENAI_API_KEY')  # or whatever your API key env var is
            # headers = {
            #     'Authorization': f'Bearer {api_key}',
            #     'Content-Type': 'application/json'
            # }
            # data = {
            #     'model': 'gpt-4-vision-preview',
            #     'messages': [{
            #         'role': 'user',
            #         'content': [{
            #             'type': 'text',
            #             'text': 'Describe this image in detail.'
            #         }, {
            #             'type': 'image_url',
            #             'image_url': {
            #                 'url': f'data:image/jpeg;base64,{self.base64_image}'
            #             }
            #         }]
            #     }],
            #     'max_tokens': 200
            # }
            # response = requests.post('https://api.openai.com/v1/chat/completions',
            #                         headers=headers, json=data)
            # if response.status_code == 200:
            #     result = response.json()
            #     description = result['choices'][0]['message']['content']
            # else:
            #     description = f"API Error: {response.status_code}"
            
            self.description_ready.emit(self.message_id, description)
        except Exception as e:
            self.description_ready.emit(self.message_id, f"Error: {str(e)}")
