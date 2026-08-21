# Makes pytest treat .app_internal as the rootdir and add it to sys.path.
# Run pytest from .app_internal.
import pytest


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session (Qt only allows one per
    process). Requires QT_QPA_PLATFORM=offscreen in headless environments."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
