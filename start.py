import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from dotenv import load_dotenv

from gui_windows import LauncherWindow

load_dotenv()


# --- Main Configuration ---
PROFILES_DIR = 'profiles'
MEMORY_DIR = 'memory'
IMAGE_DIR = 'images'
ICON_DIR = 'icons'


def main():
    """Main entry point for the Digital Family application."""
    # Create necessary directories
    for dir_path in [PROFILES_DIR, MEMORY_DIR, IMAGE_DIR, ICON_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # Initialize the PyQt6 application
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(ICON_DIR, 'app_icon.png')))
    
    # Create and show the main launcher window
    launcher = LauncherWindow()
    launcher.show()
    
    # Start the application event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
