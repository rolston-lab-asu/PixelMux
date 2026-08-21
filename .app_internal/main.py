"""
Entry point.

Two-stage startup so a slow lab laptop shows something alive within ~1
second

  1. Create the QApplication and a lightweight QSplashScreen (gui.splash)
     built only from PySide6 + gui.style, both cheap/already-needed
     imports (no numpy/scipy/pyqtgraph yet).
  2. Show the splash and flush the event loop so it actually paints.
  3. Then import the heavy modules (pyqtgraph, gui.main_window, which
     pulls in the controllers/core/instruments stack) and build the real
     window.
  4. Swap the splash for the main window.

Progress bars and pip errors are visible in a real terminal b/f this GUI process
(run windowed, via pythonw) ever starts.
"""
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from core.paths import get_icon_path
    from core.app_info import APP_USER_MODEL_ID
    from gui.splash import build_splash, splash_progress

    mock = "--mock" in sys.argv

    # Windows groups windows in the taskbar by their host process (python.exe)
    # unless the process claims its own "App User Model ID"
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass  # cosmetic only, never worth failing startup over

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(get_icon_path()))

    # --- Stage 1: splash appears before any heavy imports ---
    splash = build_splash(app)
    splash_progress(splash, "Starting up...", 8)
    splash.show()
    app.processEvents()

    # --- Stage 2: heavy imports happen only now ---
    splash_progress(splash, "Loading numerical libraries...", 45)
    app.processEvents()
    import pyqtgraph as pg

    splash_progress(splash, "Building interface...", 80)
    app.processEvents()
    from gui.main_window import MainWindow

    pg.setConfigOptions(antialias=True)
    window = MainWindow(mock=mock)
    window.setWindowIcon(app.windowIcon())

    splash_progress(splash, "Ready", 100)
    app.processEvents()
    splash.finish(window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
