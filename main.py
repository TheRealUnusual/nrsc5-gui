#!/usr/bin/env python3
"""
Entry point for NRSC5 GUI application.
Original file: nrsc5_gui_qt.py (main() function)
"""

import sys
from PyQt5 import QtWidgets
from gui import NRSC5Gui


def main():
    """Start the QApplication and show the main window."""
    app = QtWidgets.QApplication(sys.argv)
    w = NRSC5Gui()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
