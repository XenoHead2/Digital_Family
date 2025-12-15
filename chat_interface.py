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

# Placeholder for local TTS until a full solution is implemented.
def speak_text(text, voice_id=""):
    """Bypasses TTS by printing the text to the console."""
    print(f"--- TTS BYPASSED: Would have spoken: '{text[:100]}...' ---")
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFormLayout,
    QMessageBox,
    QFileDialog, QComboBox, QScrollArea, QListWidget, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent, QPixmap, QIcon, QPainter, QColor, QPainterPath, QAction
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


class CoreMemoryEditor(QWidget):
    """A window for editing a character's core memories."""
    def __init__(self, core_memory_file, character_name):
        super().__init__()
        self.core_memory_file = core_memory_file
        self.character_name = character_name
        self.rows = [] # This will store tuples of (QLineEdit, QWidget)

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
        # add_button.clicked.connect(self.add_memory_row) # Will implement next
        # save_button.clicked.connect(self.save_memories) # Will implement next
    
    def load_memories(self):
        """Loads memories from the JSON file and populates the UI."""
        if not os.path.exists(self.core_memory_file):
            return
        
        with open(self.core_memory_file, 'r', encoding='utf-8') as f:
            try:
                memories = json.load(f)
                # self.scroll_layout will be populated by add_memory_row, which we'll call here
                # for memory in memories:
                #     self.add_memory_row(memory.get("memory", ""))
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Error", "Could not decode the core memory file. It may be corrupted.")


class ChatWindow(QWidget):
    def __init__(self, profile_data, character_window):
        super().__init__()
        self.profile_data = profile_data
        self.character_window = character_window
        self.setWindowTitle(
            f"Chat with {self.profile_data.get('name', 'Bot')}"
        )
        self.setGeometry(250, 250, 800, 600)
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
        log_to_file(f"--- ChatWindow.load_memory: Base prompt length: {len(base_prompt)} chars ---")

        core_memory_content = "No core memories saved yet."
        if os.path.exists(self.core_memory_file):
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
        
        log_to_file(f"--- ChatWindow.load_memory: Core memory content length: {len(core_memory_content)} chars ---")
        full_prompt = (
            f"{base_prompt}\n\n--- Core Memories ---\n"
            f"Here are some key things to remember about us:\n"
            f"{core_memory_content}"
        )
        system_message = {"role": "system", "content": full_prompt}

        # Load and truncate chat history from the file
        chat_history_from_file = []
        if os.path.exists(self.history_file):
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
        
        # --- New, definitive truncation logic ---
        system_prompt = self.conversation_history[0]
        chat_messages = [msg for msg in self.conversation_history if msg['role'] != 'system']
        if len(chat_messages) > self.max_history_length:
            chat_messages = chat_messages[-self.max_history_length:]
        
        # Persist the truncated history for the current session
        self.conversation_history = [system_prompt] + chat_messages

        # The worker gets the final, correctly formatted history
        history_for_worker = self.conversation_history[:-1] + [{"role": "user", "content": api_content_for_llm}]
        
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
        
        # Update emotion on the character window and speak the full response
        if self.character_window:
            self.character_window.update_emotion(self.current_response)
        voice_id = self.profile_data.get("tts_voice", "21m00Tcm4oosq6XlT19c")
        speak_text(self.current_response, voice_id=voice_id)
        
        # Reset for the next message
        self.current_response = ""
        
        # Add a newline to separate the next user message
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

    def edit_core_memories(self):
        """Placeholder for opening the core memory editor."""
        print(f"TODO: Open core memory editor for {self.character_name}")

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