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
        """Make the API call in the background thread."""
        try:
            # Use luna-ai-llama2-uncensored via LM Studio for faster responses
            # Convert conversation history to OpenAI-compatible format
            messages = []
            for msg in self.conversation_history:
                if msg.get('role') in ['system', 'user', 'assistant']:
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        # Handle multimodal content
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))
                        content = ' '.join(text_parts)
                    
                    messages.append({
                        'role': msg['role'],
                        'content': content
                    })
            
            # Call luna-ai-llama2-uncensored via LM Studio
            data = {
                'model': 'luna-ai-llama2-uncensored',
                'messages': messages,
                'temperature': 0.7,
                'max_tokens': 300,
                'stream': False
            }
            
            print(f"DEBUG: Sending {len(messages)} messages to LM Studio")
            print(f"DEBUG: Last message: {messages[-1] if messages else 'None'}")
            
            response = requests.post('http://localhost:1234/v1/chat/completions', json=data)
            
            if response.status_code == 200:
                result = response.json()
                # LM Studio uses OpenAI-compatible format
                choices = result.get('choices', [])
                if choices:
                    ai_response = choices[0].get('message', {}).get('content', 'No response received')
                else:
                    ai_response = 'No response received from model'
            else:
                print(f"DEBUG: HTTP {response.status_code} error")
                print(f"DEBUG: Response text: {response.text[:200]}...")
                ai_response = f"Sorry, I'm having trouble connecting. (Error {response.status_code})"
            
            self.response_ready.emit(ai_response)
        except Exception as e:
            self.response_ready.emit(f"Error: {str(e)}")


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
