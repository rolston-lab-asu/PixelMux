"""Paths for the data folder, logs folder, and app icon."""
import os
import sys

_THIS_FILE = os.path.abspath(__file__)
_APP_INTERNAL_DIR = os.path.dirname(os.path.dirname(_THIS_FILE))
_PROJECT_ROOT = os.path.dirname(_APP_INTERNAL_DIR)


def get_project_root():
    return _PROJECT_ROOT


def get_data_dir():
    path = os.path.join(_PROJECT_ROOT, "data")
    os.makedirs(path, exist_ok=True)
    return path


def get_logs_dir():
    path = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def get_icon_path():
    filename = "app_icon.ico" if sys.platform == "win32" else "app_icon.png"
    return os.path.join(_APP_INTERNAL_DIR, "assets", "icons", filename)
