#!/usr/bin/env python3
"""
NRSC5-GUI, a graphical interface for NRSC5
Copyright (C) 2026  TheRealUnusual

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
