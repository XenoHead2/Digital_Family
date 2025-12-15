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
                    if isinstance(content, list):
                        text_parts = [item['text'] for item in content if isinstance(item, dict) and item.get('type') == 'text']
                        content = ' '.join(text_parts)
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

            
            with requests.post('http://localhost:11434/api/chat', json=data, timeout=120, stream=True) as response:
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
