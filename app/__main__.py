"""NetPulse entry point.

Run from a source checkout with:

    python -m app

The same module is the entry script of the PyInstaller build.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from app import APP_DISPLAY_NAME, APP_NAME, APP_VERSION, ORG_NAME
from app.core.settings import AppSettings


def main(argv: Sequence[str] | None = None) -> int:
    """Start the NetPulse application and return the Qt exit code."""
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    arguments = list(sys.argv if argv is None else argv)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_DISPLAY_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationVersion(APP_VERSION)

    application = QApplication(arguments)
    application.setQuitOnLastWindowClosed(True)

    settings = AppSettings().load()
    window = MainWindow(settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
