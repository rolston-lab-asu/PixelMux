"""Entry point: shows the splash screen, then loads and opens the main window."""
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from core.paths import get_icon_path
    from core.app_info import APP_USER_MODEL_ID
    from gui.splash import build_splash, splash_progress

    mock = "--mock" in sys.argv

    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(get_icon_path()))

    splash = build_splash(app)
    splash_progress(splash, "Starting up...", 8)
    splash.show()
    app.processEvents()

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
