import os
import sys
import json
import shutil
import base64
import re
import speech_recognition as sr
import threading
from piper_tts import speak_text
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
from chat_interface import CharacterWindow, ChatWindow


# We need the configuration from start.py
PROFILES_DIR = 'profiles'
MEMORY_DIR = 'memory'
IMAGE_DIR = 'images'
ICON_DIR = 'icons'


# --- Helper Functions (Moved from start.py) ---
def get_profile_list():
    """Scans the profiles directory for character subdirectories."""
    if not os.path.exists(PROFILES_DIR):
        return []
    return [
        d for d in os.listdir(PROFILES_DIR)
        if os.path.isdir(os.path.join(PROFILES_DIR, d))
    ]


def load_profile(profile_name):
    """Loads a character's profile JSON from their specific folder."""
    # Assumes the JSON file is named after the character and is inside their folder.
    profile_path = os.path.join(PROFILES_DIR, profile_name, f"{profile_name}.json")
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Profile JSON not found at {profile_path}")
        return None
    except Exception as e:
        print(f"Error loading profile '{profile_name}': {e}")
        return None

# --- GUI Windows for Profile Management ---
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

        # Initial population of rows
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
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        keyword_input = QLineEdit(keyword)
        keyword_input.setPlaceholderText("Emotion Keyword (e.g., laugh)")
        filepath_input = QLineEdit(filename)
        filepath_input.setReadOnly(True)
        browse_button = QPushButton("Browse...")
        delete_button = QPushButton("Delete")

        row_layout.addWidget(QLabel("Keyword:"))
        row_layout.addWidget(keyword_input)
        row_layout.addWidget(QLabel("Image File:"))
        row_layout.addWidget(filepath_input)
        row_layout.addWidget(browse_button)
        row_layout.addWidget(delete_button)

        item_tuple = (keyword_input, filepath_input)
        self.rows.append(item_tuple)
        
        browse_button.clicked.connect(
            lambda: self.browse_for_image(filepath_input)
        )
        delete_button.clicked.connect(
            lambda: self.delete_row(row_widget, item_tuple)
        )

        self.scroll_layout.addWidget(row_widget)

    def delete_row(self, row_widget, item_tuple):
        """Removes a row from the UI and the internal list."""
        if item_tuple in self.rows:
            self.rows.remove(item_tuple)
        row_widget.deleteLater()
        self.populate_default_selector()

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
        # Corrected: Destination is now the character's folder inside PROFILES_DIR
        destination_dir = os.path.join(PROFILES_DIR, self.character_name)
        destination_path = os.path.join(destination_dir, source_filename)
        # The save_profile method is now responsible for creating the main folder.
        # We can still ensure it exists here for robustness when editing.
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)
        try:
            shutil.copy(source_path, destination_path)
        except shutil.SameFileError:
            # This is not an error, the user selected the file that's already in the profile folder.
            pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not copy file: {e}")
            return # Stop if the copy fails for other reasons

        filepath_input.setText(source_filename)
        self.populate_default_selector()

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
        self.tts_voice_model_input = QLineEdit()
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
        form_layout.addRow(QLabel("--- Voice ---"))
        form_layout.addRow("TTS Voice Model:", self.tts_voice_model_input)
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
        self.tts_voice_model_input.setText(
            data.get("tts_voice_model", "en_US-ljspeech-high.onnx")
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
        
        # Corrected: Create the character's dedicated folder
        character_profile_dir = os.path.join(PROFILES_DIR, name)
        if not os.path.exists(character_profile_dir):
            os.makedirs(character_profile_dir)

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
            "default_emotion": self.default_emotion,
            "tts_voice_model": self.tts_voice_model_input.text().strip()
        }
        
        # Corrected: Save the JSON inside the character's folder
        profile_filename = os.path.join(character_profile_dir, f"{name}.json")
        with open(profile_filename, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=4)

        QMessageBox.information(
            self,
            "Success",
            f"Profile for {name} has been saved!"
        )
        self.profile_created.emit()
        self.close()


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
        self.character_instances = {}
        self.chat_instances = {}
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
        self.launch_button = QPushButton("Launch Character")
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
        
        # If character window already exists, just show it
        if profile_name in self.character_instances:
            self.character_instances[profile_name].show()
            self.character_instances[profile_name].activateWindow()
            return
            
        profile_data = load_profile(profile_name)
        if profile_data:
            char_win = CharacterWindow(profile_data)
            # Use a lambda to pass the profile data to the slot
            char_win.launch_chat_requested.connect(lambda p=profile_data: self.open_full_chat(p))
            self.character_instances[profile_name] = char_win
            char_win.show()

    def open_full_chat(self, profile_data):
        profile_name = profile_data['name']
        
        # If chat window already exists, just show it
        if profile_name in self.chat_instances:
            self.chat_instances[profile_name].show()
            self.chat_instances[profile_name].activateWindow()
            return
        
        # Get the character window to pass it to the chat window
        character_window = self.character_instances.get(profile_name)
        
        chat_win = ChatWindow(profile_data, character_window)
        self.chat_instances[profile_name] = chat_win
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
        # Close all character and chat windows
        for window in list(self.character_instances.values()):
            window.close()
        for window in list(self.chat_instances.values()):
            window.close()
        event.accept()
