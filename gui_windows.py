import os
import sys
import json
import shutil
import base64
import re
import speech_recognition as sr
import threading
from elevenlabs_tts import speak_text
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFormLayout, QMessageBox,
    QFileDialog, QComboBox, QScrollArea, QListWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent, QPixmap, QIcon
import uuid

from llm_workers import ChatWorker, ImageDescriptionWorker


# We need the configuration from start.py
PROFILES_DIR = 'profiles'
MEMORY_DIR = 'memory'
IMAGE_DIR = 'images'
ICON_DIR = 'icons'


# --- Helper Functions (Moved from start.py) ---
def get_profile_list():
    if not os.path.exists(PROFILES_DIR):
        return []
    return [
        os.path.splitext(f)[0]
        for f in os.listdir(PROFILES_DIR)
        if f.endswith('.json')
    ]


def load_profile(profile_name):
    profile_path = os.path.join(PROFILES_DIR, f"{profile_name}.json")
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading profile '{profile_name}': {e}")
        return None


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


# --- GUI Windows (Moved from start.py) ---
class EmotionMapEditor(QWidget):
    map_updated = pyqtSignal(dict, str)

    def __init__(self, current_map, character_name, default_emotion):
        super().__init__()
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.current_map = current_map
        self.character_name = character_name.lower()
        self.default_emotion = default_emotion
        self.setWindowTitle(f"Edit Emotion Map for {character_name}")
        self.setGeometry(300, 300, 500, 400)
        self.rows = []
        self.initUI()
        self.populate_default_selector()

    def initUI(self):
        main_layout = QVBoxLayout()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        for keyword, filename in self.current_map.items():
            self.add_emotion_row(keyword, filename)
        default_layout = QHBoxLayout()
        default_layout.addWidget(QLabel("<b>Default Image:</b>"))
        self.default_selector = QComboBox()
        self.default_selector.currentIndexChanged.connect(
            self.check_save_button_state
        )
        default_layout.addWidget(self.default_selector)
        main_layout.addLayout(default_layout)
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Emotion")
        add_button.clicked.connect(lambda: self.add_emotion_row())
        self.save_button = QPushButton("Save Map")
        self.save_button.clicked.connect(self.save_map)
        button_layout.addWidget(add_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        self.check_save_button_state()

    def add_emotion_row(self, keyword="", filename=""):
        row_layout = QHBoxLayout()
        keyword_input = QLineEdit(keyword)
        keyword_input.setPlaceholderText("Emotion Keyword (e.g., laugh)")
        filepath_input = QLineEdit(filename)
        filepath_input.setReadOnly(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(
            lambda: self.browse_for_image(filepath_input)
        )
        row_layout.addWidget(QLabel("Keyword:"))
        row_layout.addWidget(keyword_input)
        row_layout.addWidget(QLabel("Image File:"))
        row_layout.addWidget(filepath_input)
        row_layout.addWidget(browse_button)
        self.scroll_layout.addLayout(row_layout)
        self.rows.append((keyword_input, filepath_input))

    def browse_for_image(self, filepath_input):
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.gif)"
        )
        if not source_path:
            return
        source_filename = os.path.basename(source_path)
        destination_dir = os.path.join(IMAGE_DIR, self.character_name)
        destination_path = os.path.join(destination_dir, source_filename)
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)
        try:
            shutil.copy(source_path, destination_path)
            filepath_input.setText(source_filename)
            self.populate_default_selector()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not copy file: {e}")

    def populate_default_selector(self):
        self.default_selector.blockSignals(True)
        current_selection = self.default_selector.currentText()
        self.default_selector.clear()
        filenames = set(fi.text() for _, fi in self.rows if fi.text())
        if filenames:
            self.default_selector.addItems(sorted(list(filenames)))
            if current_selection in filenames:
                self.default_selector.setCurrentText(current_selection)
            elif self.default_emotion in filenames:
                self.default_selector.setCurrentText(self.default_emotion)
        self.default_selector.blockSignals(False)
        self.check_save_button_state()

    def check_save_button_state(self):
        if self.default_selector.currentText():
            self.save_button.setEnabled(True)
            self.save_button.setText("Save Map")
        else:
            self.save_button.setEnabled(False)
            self.save_button.setText("Select a Default Image to Save")

    def save_map(self):
        new_map = {
            ki.text().strip().lower(): fi.text().strip()
            for ki, fi in self.rows
            if ki.text().strip() and fi.text().strip()
        }
        self.map_updated.emit(new_map, self.default_selector.currentText())
        self.close()


class ProfileCreatorWindow(QWidget):
    profile_created = pyqtSignal()

    def __init__(self, profile_name=None):
        super().__init__()
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.edit_mode = profile_name is not None
        self.existing_name = profile_name
        self.emotion_map = {}
        self.default_emotion = ""
        title = (
            "Edit Profile" if self.edit_mode
            else "Create a New Family Member"
        )
        self.setWindowTitle(title)
        self.setGeometry(250, 250, 400, 550)
        self.initUI()
        if self.edit_mode:
            self.load_profile_data()

    def initUI(self):
        main_layout = QVBoxLayout()
        form_layout = QFormLayout()
        self.name_input = QLineEdit()
        self.user_name_input = QLineEdit()
        self.user_name_input.setPlaceholderText(
            "e.g., Daddy, Boss, Sir"
        )
        self.gender_input = QLineEdit()
        self.age_input = QLineEdit()
        self.hair_input = QLineEdit()
        self.eyes_input = QLineEdit()
        self.body_type_input = QLineEdit()
        self.likes_input = QLineEdit()
        self.dislikes_input = QLineEdit()
        self.extra_info_input = QTextEdit()
        self.default_instructions_input = QTextEdit()
        form_layout.addRow("Name:", self.name_input)
        form_layout.addRow("What they call you:", self.user_name_input)
        form_layout.addRow("Gender:", self.gender_input)
        form_layout.addRow("Age:", self.age_input)
        form_layout.addRow(QLabel("--- Appearance ---"))
        form_layout.addRow("Hair:", self.hair_input)
        form_layout.addRow("Eyes:", self.eyes_input)
        form_layout.addRow("Body Type:", self.body_type_input)
        form_layout.addRow(QLabel("--- Personality ---"))
        form_layout.addRow("Likes:", self.likes_input)
        form_layout.addRow("Dislikes:", self.dislikes_input)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(QLabel("Extra Info / Backstory:"))
        main_layout.addWidget(self.extra_info_input)
        main_layout.addWidget(QLabel("Default Behavioral Instructions:"))
        main_layout.addWidget(self.default_instructions_input)
        button_layout = QHBoxLayout()
        emotion_button = QPushButton("Emotion Images")
        emotion_button.clicked.connect(self.open_emotion_editor)
        save_button = QPushButton("SAVE")
        save_button.clicked.connect(self.save_profile)
        button_layout.addWidget(emotion_button)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def load_profile_data(self):
        data = load_profile(self.existing_name)
        if not data:
            QMessageBox.critical(
                self,
                "Error",
                "Could not load profile data to edit."
            )
            self.close()
            return
        self.name_input.setText(data.get("name", ""))
        self.user_name_input.setText(data.get("user_name", ""))
        self.gender_input.setText(data.get("gender", ""))
        self.age_input.setText(data.get("age", ""))
        appearance = data.get("appearance", {})
        self.hair_input.setText(appearance.get("hair", ""))
        self.eyes_input.setText(appearance.get("eyes", ""))
        self.body_type_input.setText(appearance.get("body_type", ""))
        personality = data.get("personality", {})
        self.likes_input.setText(personality.get("likes", ""))
        self.dislikes_input.setText(personality.get("dislikes", ""))
        self.extra_info_input.setPlainText(data.get("extra_info", ""))
        self.default_instructions_input.setPlainText(
            data.get("default_instructions", "")
        )
        self.emotion_map = data.get("emotion_map", {})
        self.default_emotion = data.get("default_emotion", "")

    def open_emotion_editor(self):
        character_name = self.name_input.text().strip()
        if not character_name:
            QMessageBox.warning(
                self,
                "Missing Name",
                "Please enter a name before editing emotions."
            )
            return
        self.editor = EmotionMapEditor(
            self.emotion_map,
            character_name,
            self.default_emotion
        )
        self.editor.map_updated.connect(self.update_emotion_map)
        self.editor.show()

    def update_emotion_map(self, new_map, new_default):
        self.emotion_map = new_map
        self.default_emotion = new_default

    def save_profile(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                "Missing Name",
                "The 'Name' field is required."
            )
            return
        if self.emotion_map and not self.default_emotion:
            QMessageBox.warning(
                self,
                "Default Image Missing",
                "Please open 'Emotion Images' and select a default image."
            )
            return
        profile_data = {
            "name": name,
            "user_name": self.user_name_input.text().strip(),
            "age": self.age_input.text().strip(),
            "gender": self.gender_input.text().strip(),
            "appearance": {
                "hair": self.hair_input.text().strip(),
                "eyes": self.eyes_input.text().strip(),
                "body_type": self.body_type_input.text().strip()
            },
            "personality": {
                "likes": self.likes_input.text().strip(),
                "dislikes": self.dislikes_input.text().strip()
            },
            "extra_info": self.extra_info_input.toPlainText().strip(),
            "default_instructions": (
                self.default_instructions_input.toPlainText().strip()
            ),
            "emotion_map": self.emotion_map,
            "default_emotion": self.default_emotion
        }
        profile_filename = os.path.join(PROFILES_DIR, f"{name}.json")
        with open(profile_filename, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=4)
        character_image_dir = os.path.join(IMAGE_DIR, name.lower())
        if not os.path.exists(character_image_dir):
            os.makedirs(character_image_dir)
        QMessageBox.information(
            self,
            "Success",
            f"Profile for {name} has been saved!"
        )
        self.profile_created.emit()
        self.close()


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
        self.core_memory_file = os.path.join(
            MEMORY_DIR,
            f"{self.character_name.lower()}_core_memories.json"
        )
        self.history_file = os.path.join(
            MEMORY_DIR,
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
                f"You are {self.profile_data.get('age')} years old."
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
        image_path = os.path.join(
            IMAGE_DIR, self.character_name, found_emotion
        )
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


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.chat_windows = []
        self.profile_creator_window = None
        self.setWindowTitle("Digital Family Launcher")
        self.setGeometry(200, 200, 300, 300)
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout()
        label = QLabel("Select a Character")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(label)
        self.profile_list = QListWidget()
        self.profile_list.addItems(get_profile_list())
        main_layout.addWidget(self.profile_list)
        button_layout = QHBoxLayout()
        self.launch_button = QPushButton("Launch Chat")
        self.launch_button.setEnabled(False)
        self.edit_button = QPushButton("Edit Profile")
        self.edit_button.setEnabled(False)
        create_button = QPushButton("Create New")
        self.launch_button.clicked.connect(self.launch_chat)
        self.edit_button.clicked.connect(self.open_profile_editor)
        create_button.clicked.connect(self.open_profile_creator)
        button_layout.addWidget(self.launch_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(create_button)
        main_layout.addLayout(button_layout)
        self.profile_list.currentItemChanged.connect(self.update_button_states)
        self.setLayout(main_layout)

    def update_button_states(self):
        is_selected = self.profile_list.currentItem() is not None
        self.launch_button.setEnabled(is_selected)
        self.edit_button.setEnabled(is_selected)

    def launch_chat(self):
        selected_item = self.profile_list.currentItem()
        if not selected_item:
            return
        profile_name = selected_item.text()
        profile_data = load_profile(profile_name)
        if profile_data:
            chat_win = ChatWindow(profile_data)
            self.chat_windows.append(chat_win)
            chat_win.show()

    def open_profile_creator(self):
        self.profile_creator_window = ProfileCreatorWindow()
        self.profile_creator_window.profile_created.connect(
            self.refresh_profile_list
        )
        self.profile_creator_window.show()

    def open_profile_editor(self):
        selected_item = self.profile_list.currentItem()
        if not selected_item:
            return
        profile_name = selected_item.text()
        self.profile_creator_window = ProfileCreatorWindow(
            profile_name=profile_name
        )
        self.profile_creator_window.profile_created.connect(
            self.refresh_profile_list
        )
        self.profile_creator_window.show()

    def refresh_profile_list(self):
        self.profile_list.clear()
        self.profile_list.addItems(get_profile_list())
        self.update_button_states()

    def closeEvent(self, event: QCloseEvent):
        for window in self.chat_windows:
            window.close()
        event.accept()


