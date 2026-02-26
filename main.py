#!/usr/bin/env python3
"""
Entry point for NRSC5 GUI application.
Original file: nrsc5_gui_qt.py (main() function)
"""

import sys
import signal
from PyQt5 import QtWidgets
from PyQt5 import QtCore
from gui import NRSC5Gui


def main():
    """Start the QApplication and show the main window."""
    app = QtWidgets.QApplication(sys.argv)

    # Ensure Ctrl+C works cleanly in the terminal while the Qt event loop is running.
    def _handle_sigint(_sig, _frame):
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)

    # Keep the interpreter responsive to signals while Qt runs.
    sigint_timer = QtCore.QTimer(app)
    sigint_timer.setInterval(100)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()
    app._sigint_timer = sigint_timer

    w = NRSC5Gui()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
