import os
import sys
import json
import base64
import re
import speech_recognition as sr
import threading
from datetime import datetime

LOG_FILE = "debug_log.txt"

def log_to_file(message):
    """Appends a message to the log file with a timestamp."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

from piper_tts import speak_text
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFormLayout,
    QMessageBox,
    QFileDialog, QComboBox, QScrollArea, QListWidget, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent, QPixmap, QIcon, QPainter, QColor, QPainterPath, QAction
import uuid

# --- NEW: Dedicated Audio Player Worker ---
class AudioPlayerWorker(QThread):
    """A dedicated worker to play audio without blocking the UI or other workers."""
    finished = pyqtSignal()

    def __init__(self, text, voice_model_name):
        super().__init__()
        self.text = text
        self.voice_model_name = voice_model_name

    def run(self):
        """Calls the TTS function in a separate thread."""
        speak_text(self.text, voice_model_name=self.voice_model_name)
        self.finished.emit()

# --- NEW: Dedicated Speech Recognition Worker ---
class SpeechRecognitionWorker(QThread):
    """A worker to handle speech recognition without blocking the UI."""
    text_recognized = pyqtSignal(str)
    recognition_error = pyqtSignal(str)
    listening_finished = pyqtSignal()

    def run(self):
        r = sr.Recognizer()
        with sr.Microphone() as source:
            try:
                # Adjust for ambient noise once before listening
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=10)
                text = r.recognize_google(audio)
                self.text_recognized.emit(text)
            except sr.WaitTimeoutError:
                self.recognition_error.emit("Listening timed out. Please try again.")
            except sr.UnknownValueError:
                self.recognition_error.emit("Sorry, I could not understand the audio.")
            except sr.RequestError as e:
                self.recognition_error.emit(f"Could not request results from Google; {e}")
        self.listening_finished.emit()

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


class CoreMemoryEditor(QWidget):
    """A window for editing a character's core memories."""
    def __init__(self, core_memory_file, character_name):
        super().__init__()
        self.core_memory_file = core_memory_file
        self.character_name = character_name
        self.rows = [] # This will store tuples of (QLineEdit, QWidget)
        self.is_dirty = False # To track if changes have been made

        self.setWindowTitle(f"Edit Core Memories for {character_name}")
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.setGeometry(300, 300, 600, 400)
        self.initUI()

    def initUI(self):
        """Initializes the user interface for the memory editor."""
        main_layout = QVBoxLayout()

        # --- Scroll Area for Memories ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add New Memory")
        save_button = QPushButton("Save & Close")
        
        button_layout.addWidget(add_button)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

        # --- Load existing data and connect signals ---
        self.load_memories()
        add_button.clicked.connect(self.add_memory_row)
        save_button.clicked.connect(self.save_memories)
    
    def load_memories(self):
        """Loads memories from the JSON file and populates the UI."""
        if not os.path.exists(self.core_memory_file):
            return
        with open(self.core_memory_file, 'r', encoding='utf-8') as f:
            try:
                memories = json.load(f)
                for memory in memories:
                    self.add_memory_row(memory.get("memory", ""))
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Error", "Could not decode the core memory file. It may be corrupted.")
        self.is_dirty = False # Reset dirty flag after initial load

    def add_memory_row(self, text=""):
        """Adds a new row for a memory entry to the UI."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        memory_input = QLineEdit(text)
        memory_input.setPlaceholderText("Enter a core memory...")
        memory_input.textChanged.connect(self.mark_as_dirty)

        delete_button = QPushButton("Delete")

        row_layout.addWidget(memory_input)
        row_layout.addWidget(delete_button)

        item_tuple = (memory_input, row_widget)
        self.rows.append(item_tuple)

        delete_button.clicked.connect(lambda: self.delete_row(item_tuple))

        self.scroll_layout.addWidget(row_widget)
        self.mark_as_dirty()

    def delete_row(self, item_tuple):
        """Removes a memory row from the UI and the internal list."""
        if item_tuple in self.rows:
            self.rows.remove(item_tuple)
        
        memory_input, row_widget = item_tuple
        row_widget.deleteLater()
        self.mark_as_dirty()

    def mark_as_dirty(self):
        """Flags that changes have been made."""
        self.is_dirty = True

    def save_memories(self):
        """Saves all current memories from the UI to the JSON file."""
        memories_to_save = []
        for memory_input, _ in self.rows:
            memory_text = memory_input.text().strip()
            if memory_text:
                memories_to_save.append({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "memory": memory_text
                })
        
        try:
            with open(self.core_memory_file, 'w', encoding='utf-8') as f:
                json.dump(memories_to_save, f, indent=4)
            QMessageBox.information(self, "Success", "Core memories have been saved.")
            self.is_dirty = False
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save memories: {e}")

    def closeEvent(self, event: QCloseEvent):
        """Warns the user if there are unsaved changes."""
        if self.is_dirty:
            reply = QMessageBox.question(self, 'Unsaved Changes', "You have unsaved changes. Are you sure you want to close?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


class ChatWindow(QWidget):
    def __init__(self, profile_data, character_window):
        super().__init__()
        self.profile_data = profile_data
        self.character_window = character_window
        self.setWindowTitle(
            f"Chat with {self.profile_data.get('name', 'Bot')}"
        )
        # --- NEW: Set a smaller default window size ---
        self.setGeometry(250, 250, 550, 450)
        self.memory_window = None
        self.attached_file_path = None
        self.active_workers = []
        self.character_name = self.profile_data.get('name', 'Unknown')
        self.emotion_map = self.profile_data.get('emotion_map', {})
        self.max_history_length = 20
        self.max_core_memories = 10 # Max number of recent core memories to load
        self.current_response = ""
        self.is_first_chunk = True
        
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
        if self.character_window:
            self.character_window.update_emotion()


    def start_listening(self):
        """Starts the speech recognition process in a separate thread."""
        self.user_input.setPlaceholderText("Listening...")
        self.speak_button.setEnabled(False)
        
        self.speech_worker = SpeechRecognitionWorker()
        self.speech_worker.text_recognized.connect(self.handle_recognized_text)
        self.speech_worker.recognition_error.connect(self.handle_recognition_error)
        self.speech_worker.listening_finished.connect(self.on_listening_finished)
        self.speech_worker.start()

    def handle_recognized_text(self, text):
        """Called when the speech worker successfully recognizes text."""
        self.user_input.setText(text)
        self.send_message()

    def handle_recognition_error(self, error_message):
        """Called when the speech worker encounters an error."""
        # Briefly show the error in the placeholder text
        self.user_input.setPlaceholderText(error_message)
        # We can use a QTimer to reset it after a couple of seconds if desired,
        # but for now, it will reset on the next action.

    def on_listening_finished(self):
        """Re-enables the UI after the listening process is complete."""
        self.speak_button.setEnabled(True)
        if not self.user_input.text(): # If no text was set
            self.reset_attachment() # Resets placeholder text

    def update_history_with_description(self, message_id, description):
        """Finds a message in the history by its ID and updates its content
        with the description received from the worker."""
        # When a description worker finishes, remove it from the active list.
        if self.sender() in self.active_workers:
            self.active_workers.remove(self.sender())

        for message in reversed(self.conversation_history):
            if message.get("message_id") == message_id:
                message["content"] = message["content"].replace(
                    "[Image: Awaiting description...]",
                    f"[Image: {description}]"
                )
                del message["message_id"]
                print(f"History updated for message {message_id}.")
                break

    def load_memory(self):
        log_to_file("--- ChatWindow.load_memory: Building system prompt... ---")
        name = self.profile_data.get('name', 'Unknown')
        user_name = self.profile_data.get('user_name', 'Daddy')

        # --- CONCISE SYSTEM PROMPT ---
        # This creates a much shorter, summary-style prompt.
        persona_summary = (
            f"You are {name}. Your personality is defined by these traits: "
            f"Likes: {self.profile_data.get('personality', {}).get('likes', 'N/A')}. "
            f"Dislikes: {self.profile_data.get('personality', {}).get('dislikes', 'N/A')}. "
            f"Your core instructions are: '{self.profile_data.get('default_instructions', '')}'. "
            f"You are speaking to '{user_name}'. "
            "Always include spoken text in your response, even when performing an action."
        )
        log_to_file(f"--- ChatWindow.load_memory: Persona summary length: {len(persona_summary)} chars ---")

        core_memory_content = "No core memories saved yet."
        # --- NEW: Check if long-term memory is enabled ---
        if self.character_window and self.character_window.long_term_memory_enabled and os.path.exists(self.core_memory_file):
            with open(self.core_memory_file, 'r', encoding='utf-8') as f:
                try:
                    memories = json.load(f)
                    log_to_file(f"--- ChatWindow.load_memory: Loaded {len(memories)} core memories from file. ---")
                except (json.JSONDecodeError, KeyError):
                    core_memory_content = "Could not read core memory file."
                    memories = []
            if memories:
                # Truncate to only the most recent core memories
                if len(memories) > self.max_core_memories:
                    log_to_file(f"--- ChatWindow.load_memory: Truncating core memories from {len(memories)} to {self.max_core_memories}. ---")
                    memories = memories[-self.max_core_memories:]
                core_memory_content = "\n".join(
                    [f"- {item['memory']}" for item in memories]
                )
        else:
            log_to_file("--- ChatWindow.load_memory: Long-term memory is disabled or file not found. Skipping. ---")
        
        log_to_file(f"--- ChatWindow.load_memory: Core memory content length: {len(core_memory_content)} chars ---")
        full_prompt = (
            f"{persona_summary}\n\n--- Core Memories ---\n"
            f"Here are some key things to remember about us:\n"
            f"{core_memory_content}"
        )
        system_message = {"role": "system", "content": full_prompt}

        # Load and truncate chat history from the file
        chat_history_from_file = []
        # --- NEW: Check if short-term memory is enabled ---
        if self.character_window and self.character_window.short_term_memory_enabled and os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    loaded_history = json.load(f)
                    log_to_file(f"--- ChatWindow.load_memory: Loaded {len(loaded_history)} chat messages from file. ---")
                # Ensure we only take the last `max_history_length` messages
                if len(loaded_history) > self.max_history_length:
                    log_to_file(f"--- ChatWindow.load_memory: Truncating chat history from {len(loaded_history)} to {self.max_history_length}. ---")
                    chat_history_from_file = loaded_history[-self.max_history_length:]
                else:
                    chat_history_from_file = loaded_history
            except Exception as e:
                log_to_file(f"Error loading history: {e}")
        else:
            log_to_file("--- ChatWindow.load_memory: Short-term memory is disabled or file not found. Skipping. ---")

        # The conversation history starts with the system prompt plus the truncated chat history
        self.conversation_history = [system_message] + chat_history_from_file
        log_to_file(f"--- ChatWindow.load_memory: Final initial history length: {len(self.conversation_history)} messages. ---")

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
        main_layout = QVBoxLayout()
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        main_layout.addWidget(self.chat_display)
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
        main_layout.addLayout(input_layout)
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

        # --- Display user message immediately ---
        self.chat_display.append(f"<font color='blue'><b>You:</b> {user_text}</font>")
        
        api_content_for_llm = None
        history_content_for_log = None

        if self.attached_file_path:
            # (The existing logic for handling attachments remains the same)
            file_extension = os.path.splitext(self.attached_file_path)[1].lower()
            if file_extension == '.txt':
                try:
                    with open(self.attached_file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    full_text = f"Here is the content of the text file '{os.path.basename(self.attached_file_path)}':\n\n{file_content}\n\n{user_text}"
                    api_content_for_llm = history_content_for_log = full_text
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not read text file: {e}")
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
                        api_content_for_llm.append({"type": "text", "text": user_text})
                    api_content_for_llm.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
                    history_content_for_log = f"{user_text} [Image: Awaiting description...]"
                    desc_worker = ImageDescriptionWorker(base64_image, message_id)
                    desc_worker.description_ready.connect(self.update_history_with_description)
                    desc_worker.start()
                    self.active_workers.append(desc_worker)
                    self.conversation_history.append({"role": "user", "content": history_content_for_log, "message_id": message_id})
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not process image file: {e}")
                    self.reset_attachment()
                    return
        else:
            api_content_for_llm = history_content_for_log = user_text
            self.conversation_history.append({"role": "user", "content": history_content_for_log})
        
        self.user_input.clear()
        
        # --- Definitive truncation logic ---
        system_prompt = self.conversation_history[0]
        # --- NEW: Only include chat history if short-term memory is enabled ---
        if self.character_window and self.character_window.short_term_memory_enabled:
            chat_messages = [msg for msg in self.conversation_history if msg['role'] != 'system']
            # Truncate if we are AT or OVER the max length
            if len(chat_messages) >= self.max_history_length:
                chat_messages = chat_messages[-self.max_history_length:]
        else:
            chat_messages = [] # No history if disabled
        
        # The worker gets the final, correctly formatted and truncated history
        self.conversation_history = [system_prompt] + chat_messages
        # --- FIX: Ensure the current user message is always sent, even if history is off ---
        # If chat_messages is empty (history disabled), self.conversation_history only has the system prompt.
        # We need to add the new user message to what the worker receives.
        history_for_worker = self.conversation_history + [{"role": "user", "content": api_content_for_llm}]
        
        # --- MORE LOGGING ---
        log_to_file(f"--- ChatWindow.send_message: History for worker has {len(history_for_worker)} messages. ---")
        # To avoid spamming the console, let's just print the role and content length of each message
        for i, msg in enumerate(history_for_worker):
            role = msg.get('role', 'no_role')
            content_len = len(str(msg.get('content', '')))
            log_to_file(f"    Message {i}: role={role}, content_len={content_len}")
        # --- END LOGGING ---

        # --- Connect to streaming signals ---
        self.is_first_chunk = True
        self.worker = ChatWorker(history_for_worker)
        self.worker.response_chunk_ready.connect(self.handle_llm_chunk)
        self.worker.response_finished.connect(self.handle_llm_finished)
        self.active_workers.append(self.worker)
        self.worker.start()
        self.reset_attachment()

    def reset_attachment(self):
        """Clears the attachment state."""
        self.attached_file_path = None
        self.user_input.setPlaceholderText("Type your message here...")

    def handle_llm_chunk(self, chunk):
        """Handles incoming chunks of text from the streaming response."""
        if self.is_first_chunk:
            self.chat_display.append(f"<font color='purple'><b>{self.character_name}:</b> </font>")
            self.is_first_chunk = False
        
        # Append the plain text chunk to the display
        self.chat_display.insertPlainText(chunk)
        self.current_response += chunk
        # --- NEW: Ensure the chat display automatically scrolls to the bottom ---
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def handle_llm_finished(self):
        """Handles the end of the streaming response."""
        # Remove the worker from the active list once it's done
        if self.sender() in self.active_workers:
            self.active_workers.remove(self.sender())

        # Save the complete response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": self.current_response
        })
        
        # --- Truncate history right after adding assistant message ---
        system_prompt = self.conversation_history[0]
        chat_messages = [msg for msg in self.conversation_history if msg['role'] != 'system']
        if len(chat_messages) > self.max_history_length:
            chat_messages = chat_messages[-self.max_history_length:]
        self.conversation_history = [system_prompt] + chat_messages
        
        # --- NEW: Check for silent, action-only responses ---
        cleaned_response = re.sub(r'\[.*?\]|\*.*?\*', '', self.current_response).strip()
        if not cleaned_response:
            log_to_file("--- handle_llm_finished: Detected action-only response. Requesting elaboration. ---")
            # The response was only an action. Ask the AI to elaborate.
            # We add the silent action to history so it has context.
            # Then we create a new user message asking it to speak.
            follow_up_prompt = "You just performed an action. Now, add some spoken words to it."
            self.conversation_history.append({"role": "user", "content": follow_up_prompt})
            
            # Use the existing send_message infrastructure, but don't add to display
            history_for_worker = self.conversation_history
            self.is_first_chunk = True
            self.worker = ChatWorker(history_for_worker)
            self.worker.response_chunk_ready.connect(self.handle_llm_chunk)
            self.worker.response_finished.connect(self.handle_llm_finished)
            self.active_workers.append(self.worker)
            self.worker.start()
            # --- FIX: Do not proceed to the speech part for silent responses ---
            return
        else:
            # This is a normal response with speech, so proceed as usual.
            if self.character_window:
                self.character_window.update_emotion(self.current_response)
            voice_model = self.profile_data.get("tts_voice_model", "en_US-ljspeech-high.onnx")
            
            # --- NEW: Use the dedicated audio worker ---
            self.audio_worker = AudioPlayerWorker(self.current_response, voice_model)
            # Clean up the worker once it's done to prevent resource leaks
            self.audio_worker.finished.connect(self.audio_worker.deleteLater)
            self.active_workers.append(self.audio_worker) # Track it for clean shutdown
            self.audio_worker.start()

        # Reset for the next message and add a newline to the display
        self.current_response = ""
        self.chat_display.append("")

    def closeEvent(self, event: QCloseEvent):
        """
        Ensures all worker threads are gracefully shut down before the window closes,
        preventing the QThread: Destroyed while thread is still running error.
        """
        print("--- ChatWindow: Closing window and terminating active workers. ---")
        self.save_history()
        # 1. Stop and wait for all active workers (ChatWorker, ImageDescriptionWorker)
        for worker in self.active_workers:
            if worker.isRunning():
                print(f"--- ChatWindow: Terminating worker {type(worker).__name__} ---")
                worker.terminate() # Forcefully stop the thread
                worker.wait() # Wait for termination to complete
                
        # 2. Call the base implementation to actually close the window
        print("--- ChatWindow: All workers terminated. Closing now. ---")
        super().closeEvent(event)


class CharacterWindow(QWidget):
    """A circular, floating, draggable window to represent a character."""
    launch_chat_requested = pyqtSignal()

    def __init__(self, profile_data):
        super().__init__()
        self.profile_data = profile_data
        self.character_name = self.profile_data.get('name', 'Unknown')
        self.emotion_map = self.profile_data.get('emotion_map', {})
        self.offset = None

        # --- NEW: Memory Toggles ---
        self.long_term_memory_enabled = True
        self.short_term_memory_enabled = True
        # --- END NEW ---
        
        # Set window properties for a frameless, circular, floating window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(150, 150)

        # --- NEW: Context Menu for closing ---
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        # --- END NEW ---

        self.update_emotion() # Set initial image

    def show_context_menu(self, pos):
        """Shows a context menu with options for the character window."""
        context_menu = QMenu(self)
        
        # --- NEW: Open Chat Action ---
        open_chat_action = QAction("Open Chat", self)
        open_chat_action.triggered.connect(self.launch_chat_requested.emit)
        context_menu.addAction(open_chat_action)
        
        context_menu.addSeparator()
        
        # --- NEW: Memory Toggle Actions ---
        long_term_action = QAction("Enable Core Memories", self)
        long_term_action.setCheckable(True)
        long_term_action.setChecked(self.long_term_memory_enabled)
        long_term_action.toggled.connect(self.toggle_long_term_memory)
        context_menu.addAction(long_term_action)

        short_term_action = QAction("Enable Chat History", self)
        short_term_action.setCheckable(True)
        short_term_action.setChecked(self.short_term_memory_enabled)
        short_term_action.toggled.connect(self.toggle_short_term_memory)
        context_menu.addAction(short_term_action)

        context_menu.addSeparator()
        # --- END NEW ---

        edit_core_action = QAction("Edit Core Memories", self)
        edit_core_action.triggered.connect(self.edit_core_memories)
        context_menu.addAction(edit_core_action)

        view_history_action = QAction("View Chat History", self)
        view_history_action.triggered.connect(self.view_chat_history)
        context_menu.addAction(view_history_action)

        context_menu.addSeparator()

        close_action = QAction("Close", self)
        close_action.triggered.connect(self.close)
        context_menu.addAction(close_action)
        
        context_menu.exec(self.mapToGlobal(pos))

    # --- NEW: Toggle Handlers ---
    def toggle_long_term_memory(self, checked):
        self.long_term_memory_enabled = checked
        print(f"Core Memories {'Enabled' if checked else 'Disabled'}")

    def toggle_short_term_memory(self, checked):
        self.short_term_memory_enabled = checked
        print(f"Chat History {'Enabled' if checked else 'Disabled'}")
    # --- END NEW ---

    def edit_core_memories(self):
        """Placeholder for opening the core memory editor."""
        core_memory_file = os.path.join(
            PROFILES_DIR, 
            self.character_name.lower(), 
            f"{self.character_name.lower()}_core_memories.json"
        )
        self.editor = CoreMemoryEditor(core_memory_file, self.character_name)
        self.editor.show()

    def view_chat_history(self):
        """Opens the character's history JSON file in the default text editor."""
        history_file_path = os.path.join(
            PROFILES_DIR, 
            self.character_name.lower(), 
            f"{self.character_name.lower()}_history.json"
        )
        if os.path.exists(history_file_path):
            try:
                os.startfile(history_file_path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open history file: {e}")
        else:
            QMessageBox.information(self, "Not Found", "No chat history file exists for this character yet.")

    def update_emotion(self, text=""):
        """Finds the correct emotion image based on keywords in the text and updates the window's pixmap."""
        default_filename = self.profile_data.get('default_emotion', '')
        found_emotion_filename = default_filename
        
        # Find the emotion keyword in the text
        if text:
            for keyword, filename in self.emotion_map.items():
                if keyword in text.lower():
                    found_emotion_filename = filename
                    break

        # --- Create a fixed-size, circular pixmap for the character icon ---
        character_path = os.path.join(PROFILES_DIR, self.character_name.lower())
        
        # Load the source image into a temporary pixmap
        image_path = os.path.join(character_path, found_emotion_filename)
        temp_pixmap = QPixmap(image_path)

        # Create the final 150x150 pixmap with a transparent background
        pixmap = QPixmap(150, 150)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Use QPainter to draw the scaled image inside a circular clip
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, 150, 150)
        painter.setClipPath(path)

        if not temp_pixmap.isNull():
            # Scale the source image to fill the 150x150 circle
            source_scaled = temp_pixmap.scaled(
                150, 150, 
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(0, 0, source_scaled)
        else:
            # If no image is found, draw the purple placeholder circle
            painter.setBrush(QColor("#900CC7"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 150, 150)
        
        painter.end()
        self.pixmap = pixmap
        self.update() # Trigger a repaint

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