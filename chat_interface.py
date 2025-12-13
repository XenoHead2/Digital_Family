import os
import sys
import json
import base64
import re
import speech_recognition as sr
import threading
# Placeholder for local TTS until a full solution is implemented.
def speak_text(text, voice_id=""):
    """Bypasses TTS by printing the text to the console."""
    print(f"--- TTS BYPASSED: Would have spoken: '{text[:100]}...' ---")
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFormLayout,
    QMessageBox,
    QFileDialog, QComboBox, QScrollArea, QListWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent, QPixmap, QIcon, QPainter, QColor
import uuid

from llm_workers import ChatWorker, ImageDescriptionWorker

# Configuration constants
PROFILES_DIR = 'profiles'
ICON_DIR = 'icons'

def colorize_emotive_text(text, character_name):
    """
    Applies HTML styles to the entire response line, including special
    formatting for text within [...] and *...* delimiters.
    """
    default_style = (
        "font-family: 'Times New Roman'; font-size: 15px; "
        "color: #000000;"
    )
    bracket_style = (
        "font-family: 'Segoe Print'; font-size: 11px; font-style: italic;"
        "color: #900CC7"
    )
    asterisk_style = (
        "font-family: 'Comic Sans MS'; font-size: 10px; font-style: bold;"
        "color: #FF0000"
    )
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(
        r'\[(.*?)\]',
        lambda m: f'<span style="{bracket_style}">{m.group(1)}</span>',
        text
    )
    text = re.sub(
        r'\*(.*?)\*',
        lambda m: f'<span style="{asterisk_style}">{m.group(1)}</span>',
        text
    )
    return f'<p style="{default_style}"><b>{character_name}:</b> {text}</p>'


class MemoryWindow(QWidget):
    def __init__(self, core_memory_file):
        super().__init__()
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.core_memory_file = core_memory_file
        self.setWindowTitle("Save a Core Memory")
        self.setGeometry(300, 300, 400, 200)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        label = QLabel("Enter a specific memory:")
        layout.addWidget(label)
        self.memory_input = QTextEdit()
        layout.addWidget(self.memory_input)
        save_button = QPushButton("Save Memory")
        save_button.clicked.connect(self.save_memory)
        layout.addWidget(save_button)
        self.setLayout(layout)

    def save_memory(self):
        memory_to_save = self.memory_input.toPlainText().strip()
        if not memory_to_save:
            return
        memories = []
        if os.path.exists(self.core_memory_file):
            with open(self.core_memory_file, 'r', encoding='utf-8') as f:
                try:
                    memories = json.load(f)
                except json.JSONDecodeError:
                    pass
        new_memory = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "memory": memory_to_save
        }
        memories.append(new_memory)
        with open(self.core_memory_file, 'w', encoding='utf-8') as f:
            json.dump(memories, f, indent=4)
        print(f"SUCCESS: Saved new memory object to {self.core_memory_file}")
        self.close()


class ChatWindow(QWidget):
    def __init__(self, profile_data):
        super().__init__()
        self.profile_data = profile_data
        self.setWindowTitle(
            f"Chat with {self.profile_data.get('name', 'Bot')}"
        )
        self.setGeometry(250, 250, 800, 600)
        self.memory_window = None
        self.attached_file_path = None
        self.description_workers = {}
        self.character_name = self.profile_data.get('name', 'Unknown')
        self.emotion_map = self.profile_data.get('emotion_map', {})
        self.max_history_length = 20
        
        # Corrected paths to be inside the character's profile folder
        character_path = os.path.join(PROFILES_DIR, self.character_name)
        self.core_memory_file = os.path.join(
            character_path,
            f"{self.character_name.lower()}_core_memories.json"
        )
        self.history_file = os.path.join(
            character_path,
            f"{self.character_name.lower()}_history.json"
        )

        self.load_memory()
        self.initUI()
        self.update_emotion_image()

    def start_listening(self):
        """Starts the speech recognition process in a separate thread."""
        self.user_input.setText("Listening...")
        self.user_input.setEnabled(False)
        self.speak_button.setEnabled(False)
        self.listen_thread = threading.Thread(target=self.recognize_speech)
        self.listen_thread.start()

    def recognize_speech(self):
        """Handles the speech-to-text conversion."""
        r = sr.Recognizer()
        with sr.Microphone() as source:
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=5)
                text = r.recognize_google(audio)
                self.user_input.setText(text)
                self.user_input.setEnabled(True)
                self.speak_button.setEnabled(True)
                self.send_message()
            except sr.UnknownValueError:
                self.user_input.setText("Could not understand audio.")
            except sr.RequestError as e:
                self.user_input.setText(
                    f"Could not request results from Google Speech "
                    f"Recognition service; {e}"
                )
            except Exception as e:
                self.user_input.setText(f"An error occurred: {e}")
            finally:
                self.user_input.setEnabled(True)
                self.speak_button.setEnabled(True)

    def update_history_with_description(self, message_id, description):
        """Finds a message in the history by its ID and updates its content
        with the description received from the worker."""
        for message in reversed(self.conversation_history):
            if message.get("message_id") == message_id:
                message["content"] = message["content"].replace(
                    "[Image: Awaiting description...]",
                    f"[Image: {description}]"
                )
                del message["message_id"]
                print(f"History updated for message {message_id}.")
                break
        if message_id in self.description_workers:
            del self.description_workers[message_id]

    def load_memory(self):
        prompt_parts = []
        name = self.profile_data.get('name', 'Unknown')
        user_name = self.profile_data.get('user_name', 'Daddy')
        prompt_parts.append(f"You are a chatbot named {name}.")
        if self.profile_data.get('gender'):
            prompt_parts.append(f"You are {self.profile_data.get('gender')}.")
        if self.profile_data.get('age'):
            prompt_parts.append(
                f"You are {self.profile_data.get('age')}" " years old."
            )
        appearance = self.profile_data.get('appearance', {})
        appearance_parts = []
        if appearance.get('hair'):
            appearance_parts.append(f"hair is {appearance.get('hair')}")
        if appearance.get('eyes'):
            appearance_parts.append(f"eyes are {appearance.get('eyes')}")
        if appearance.get('body_type'):
            appearance_parts.append(
                f"body type is {appearance.get('body_type')}"
            )
        if appearance_parts:
            prompt_parts.append(
                "Your appearance is as follows: your " +
                ", your ".join(appearance_parts) + "."
            )
        personality = self.profile_data.get('personality', {})
        if personality.get('likes'):
            prompt_parts.append(f"You like {personality.get('likes')}.")
        if personality.get('dislikes'):
            prompt_parts.append(f"You dislike {personality.get('dislikes')}.")
        if self.profile_data.get('extra_info'):
            prompt_parts.append(self.profile_data.get('extra_info'))
        default_instructions = self.profile_data.get(
            'default_instructions',
            ""
        ).replace("the user", f"'{user_name}'")
        prompt_parts.append(default_instructions)
        base_prompt = " ".join(part for part in prompt_parts if part)
        core_memory_content = "No core memories saved yet."
        if os.path.exists(self.core_memory_file):
            with open(self.core_memory_file, 'r', encoding='utf-8') as f:
                try:
                    memories = json.load(f)
                except (json.JSONDecodeError, KeyError):
                    core_memory_content = "Could not read core memory file."
                    memories = []
            if memories:
                core_memory_content = "\n".join(
                    [f"- {item['memory']}" for item in memories]
                )
        full_prompt = (
            f"{base_prompt}\n\n--- Core Memories ---\n"
            f"Here are some key things to remember about us:\n"
            f"{core_memory_content}"
        )
        self.conversation_history = (
            [{"role": "system", "content": full_prompt}]
        )
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.conversation_history.extend(json.load(f))
            except Exception as e:
                print(f"Error loading history: {e}")

    def save_history(self):
        history_to_save = [
            msg for msg in self.conversation_history
            if msg.get("role") != "system"
        ]
        if len(history_to_save) > self.max_history_length:
            history_to_save = history_to_save[-self.max_history_length:]
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history_to_save, f, indent=2)
        print(
            f"Saved the last {len(history_to_save)} messages "
            "to short-term history."
        )

    def initUI(self):
        main_layout = QHBoxLayout()
        self.emotion_display = QLabel()
        self.emotion_display.setFixedSize(200, 200)
        self.emotion_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emotion_display.setStyleSheet("border: 1px solid gray;")
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.emotion_display)
        left_layout.addStretch()
        right_layout = QVBoxLayout()
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        right_layout.addWidget(self.chat_display)
        self.chat_display.setStyleSheet(
            "background-color: white; color: black;"
        )
        for msg in self.conversation_history:
            if msg["role"] == "user":
                self.chat_display.append(
                    f"<font color='blue'><b>You:</b> {msg['content']}</font>"
                )
            elif msg["role"] == "assistant":
                self.chat_display.append(
                    f"<font color='purple'><b>"
                    f"{self.profile_data.get('name', 'Bot')}:"
                    f"</b> {msg['content']}</font>"
                )
        input_layout = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Type your message here...")
        self.user_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.user_input)

        # --- NEW: Speak Button ---
        self.speak_button = QPushButton("Speak")
        self.speak_button.clicked.connect(self.start_listening)
        input_layout.addWidget(self.speak_button)
        # --- END NEW ---

        attach_button = QPushButton("Attach File")
        attach_button.clicked.connect(self.attach_file)
        input_layout.addWidget(attach_button)
        
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(send_button)

        memory_button = QPushButton("Save Memory")
        memory_button.clicked.connect(self.open_memory_window)
        input_layout.addWidget(memory_button)
        right_layout.addLayout(input_layout)
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

    def attach_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach File",
            "",
            "All Files (*.png *.jpg *.jpeg *.txt);;"
            "Images (*.png *.jpg *.jpeg);;"
            "Text Files (*.txt)"
        )
        if file_path:
            self.attached_file_path = file_path
            self.user_input.setPlaceholderText(
                f"Attached: {os.path.basename(file_path)}"
            )
            print(f"Attached file: {file_path}")

    def open_memory_window(self):
        self.memory_window = MemoryWindow(self.core_memory_file)
        self.memory_window.show()

    def send_message(self):
        user_text = self.user_input.text().strip()
        if not user_text and not self.attached_file_path:
            return
        api_content_for_llm = None
        history_content_for_log = None
        if self.attached_file_path:
            file_extension = os.path.splitext(
                self.attached_file_path
            )[1].lower()
            if file_extension == '.txt':
                try:
                    with open(
                        self.attached_file_path, 'r', encoding='utf-8'
                    ) as f:
                        file_content = f.read()
                    full_text = (
                        f"Here is the content of the text file "
                        f"'{os.path.basename(self.attached_file_path)}':\n\n"
                        f"{file_content}\n\n{user_text}"
                    )
                    api_content_for_llm = history_content_for_log = full_text
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Could not read text file: {e}"
                    )
                    self.reset_attachment()
                    return
            elif file_extension in ['.png', '.jpg', '.jpeg']:
                try:
                    with open(self.attached_file_path, 'rb') as f:
                        image_data = f.read()
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    message_id = str(uuid.uuid4())
                    api_content_for_llm = []
                    if user_text:
                        api_content_for_llm.append({
                            "type": "text",
                            "text": user_text
                        })
                    api_content_for_llm.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    })
                    history_content_for_log = (
                        f"{user_text} [Image: Awaiting description...]"
                    )
                    desc_worker = ImageDescriptionWorker(
                        base64_image,
                        message_id
                    )
                    desc_worker.description_ready.connect(
                        self.update_history_with_description
                    )
                    desc_worker.start()
                    self.description_workers[message_id] = desc_worker
                    self.conversation_history.append({
                        "role": "user",
                        "content": history_content_for_log,
                        "message_id": message_id
                    })
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Could not process image file: {e}"
                    )
                    self.reset_attachment()
                    return
        else:
            api_content_for_llm = history_content_for_log = user_text
            self.conversation_history.append({
                "role": "user",
                "content": history_content_for_log
            })
        self.user_input.clear()
        history_for_worker = self.conversation_history[:-1] + [{
            "role": "user",
            "content": api_content_for_llm
        }]
        self.worker = ChatWorker(history_for_worker)
        self.worker.response_ready.connect(self.handle_llm_response)
        self.worker.start()
        self.reset_attachment()

    def reset_attachment(self):
        """Clears the attachment state."""
        self.attached_file_path = None
        self.user_input.setPlaceholderText("Type your message here...")

    def handle_llm_response(self, response_text):
        self.conversation_history.append({
            "role": "assistant",
            "content": response_text
        })
        full_html_line = colorize_emotive_text(
            response_text,
            self.profile_data.get('name', 'Bot')
        )
        self.chat_display.append(full_html_line)
        self.update_emotion_image(response_text)
        voice_id = self.profile_data.get("tts_voice", "21m00Tcm4oosq6XlT19c")
        speak_text(response_text, voice_id=voice_id)

    def update_emotion_image(self, text=""):
        default_filename = self.profile_data.get('default_emotion', '')
        found_emotion = default_filename
        for keyword, filename in self.emotion_map.items():
            if keyword in text.lower():
                found_emotion = filename
                break
        if not found_emotion:
            self.emotion_display.setText("No default image set.")
            return
        
        # Corrected: Image path is now relative to the character's profile folder
        character_path = os.path.join(PROFILES_DIR, self.character_name)
        image_path = os.path.join(character_path, found_emotion)

        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                print(
                    f"Warning: Failed to load image at {image_path}. "
                    "It might be corrupted or an unsupported format."
                )
                self.emotion_display.setText(
                    f"Error loading:\n{found_emotion}"
                )
            else:
                self.emotion_display.setPixmap(
                    pixmap.scaled(
                        200, 200,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
        else:
            self.emotion_display.setText(f"Image not found:\n{found_emotion}")

    def closeEvent(self, event: QCloseEvent):
        self.save_history()
        event.accept()


class CharacterWindow(QWidget):
    """A circular, floating, draggable window to represent a character."""
    launch_chat_requested = pyqtSignal()

    def __init__(self, profile_data):
        super().__init__()
        self.profile_data = profile_data
        self.character_name = self.profile_data.get('name', 'Unknown')
        self.offset = None

        # Corrected: Get image path from the character's profile folder
        image_filename = self.profile_data.get('default_emotion', '')
        character_path = os.path.join(PROFILES_DIR, self.character_name)
        image_path = os.path.join(character_path, image_filename)

        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            # Create a default circular placeholder if image is missing
            self.pixmap = QPixmap(150, 150)
            self.pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(self.pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor("#900CC7")) # Purple color
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 150, 150)
            painter.end()
        
        # Set window properties
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.pixmap.size())
        self.setMask(self.pixmap.mask())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.mapToGlobal(event.pos() - self.offset))
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.offset = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.launch_chat_requested.emit()