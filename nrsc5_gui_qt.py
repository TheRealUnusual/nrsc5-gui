#!/usr/bin/env python3
# nrsc5_gui_qt.py
# Requires: PyQt5, pyqtgraph, nrsc5, ffmpeg, ffplay
# Run: python3 nrsc5_gui_qt.py

from PyQt5 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import re
import shutil
import sys
import os
import datetime
import math
import json


class NRSC5Gui(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("nrsc5 GUI — Listen & Record")
        self.resize(900, 600)

        # ---------- Persistent settings ----------
        self.settings = QtCore.QSettings("NRSC5GUI", "NRSC5GUIQt")

        # ---------- State ----------
        self.radio_running = False
        self.recording = False
        self.stopping_radio = False  # true while user is stopping the radio

        # Station and user location (lat, lon in degrees, alt in meters)
        self.station_lat = None
        self.station_lon = None
        self.station_alt = None

        self.user_lat = None
        self.user_lon = None
        self.user_alt = None  # always stored in meters internally

        # Log and history limits
        self.max_log_lines = 10000
        self.max_history_rows = 500

        # BER graph data
        self.ber_history = []
        self.ber_max_points = 300  # keep last N BER samples

        # Summary text fields
        self.status_text = "Status: Idle"
        self.ber_text = "—"
        self.relpos_text = "N/A"
        self.vert_text = "N/A"

        # Recording duration
        self.record_start_time = None
        self.record_duration_text = ""
        self.record_timer = QtCore.QTimer(self)
        self.record_timer.setInterval(1000)
        self.record_timer.timeout.connect(self._update_record_duration)

        # Now-playing history tracking
        self.last_title = None
        self.last_artist = None
        self.last_album = None

        # ---------- Input widgets ----------
        freq_label = QtWidgets.QLabel("Frequency (MHz):")
        self.freq_edit = QtWidgets.QLineEdit("106.9")

        prog_label = QtWidgets.QLabel("Program:")
        self.prog_combo = QtWidgets.QComboBox()
        # Static list: 0–3
        self.prog_combo.addItems(["0", "1", "2", "3"])

        host_label = QtWidgets.QLabel("rtl_tcp host:")
        self.host_edit = QtWidgets.QLineEdit("192.168.0.162")

        port_label = QtWidgets.QLabel("rtl_tcp port:")
        self.port_edit = QtWidgets.QLineEdit("1234")

        # Recording directory (config tab)
        default_record_dir = os.path.expanduser("~/Desktop")
        self.record_dir_edit = QtWidgets.QLineEdit(default_record_dir)
        self.browse_dir_btn = QtWidgets.QPushButton("Browse...")

        # Units selector (metric / imperial)
        self.units_combo = QtWidgets.QComboBox()
        self.units_combo.addItems(["Metric (m, km)", "Imperial (ft, mi)"])

        # User location (config tab)
        self.user_lat_edit = QtWidgets.QLineEdit("")
        self.user_lon_edit = QtWidgets.QLineEdit("")
        self.user_alt_edit = QtWidgets.QLineEdit("")
        self.user_lat_edit.setPlaceholderText("e.g. 35.8833")
        self.user_lon_edit.setPlaceholderText("e.g. -95.7706")
        self.user_alt_edit.setPlaceholderText("e.g. 300")

        # ---------- Buttons ----------
        self.radio_btn = QtWidgets.QPushButton("Start Radio")       # toggle start/stop
        self.record_btn = QtWidgets.QPushButton("Start Recording")  # toggle start/stop
        self.record_btn.setEnabled(False)  # Only enabled when radio is running

        # ---------- Record Time ----------
        self.record_time_label = QtWidgets.QLabel("")

        # ---------- Process Handlers ----------
        self.proc_nrsc5 = None  # Receiver (Producer)
        self.proc_play = None   # Audio Player (Consumer 1)
        self.proc_rec = None    # Recorder (Consumer 2)

        self.current_record_file = None

        # ---------- Now-playing labels (top bar) ----------
        self.title_label = QtWidgets.QLabel("—")
        self.artist_label = QtWidgets.QLabel("—")
        self.album_label = QtWidgets.QLabel("—")

        # ---------- BER plot ----------
        self.ber_plot = pg.PlotWidget()
        self.ber_plot.setBackground('w')
        self.ber_plot.setLabel('left', 'BER (%)')
        self.ber_plot.setLabel('bottom', 'Samples')
        self.ber_plot.showGrid(x=True, y=True, alpha=0.3)
        self.ber_curve = self.ber_plot.plot(
            pen=pg.mkPen(color=(255, 0, 0), width=2)
        )

        # Disable user interaction with the graph
        self.ber_plot.enableAutoRange('xy', False)
        vb = self.ber_plot.getPlotItem().getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        vb.setMenuEnabled(False)

        # Initial fixed ranges: 300-sample window, 0–10% soft bound
        self.ber_plot.setLimits(yMin=0)
        self.ber_plot.setXRange(0, self.ber_max_points - 1)
        self.ber_plot.setYRange(0, 10)

        # ---------- NRSC5 log widgets ----------
        self.log_toggle_btn = QtWidgets.QToolButton()
        self.log_toggle_btn.setText("NRSC5 Log")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.setChecked(False)
        self.log_toggle_btn.setToolButtonStyle(
            QtCore.Qt.ToolButtonTextBesideIcon
        )
        self.log_toggle_btn.setArrowType(QtCore.Qt.RightArrow)

        self.clear_log_btn = QtWidgets.QPushButton("Clear Log")

        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setVisible(False)

        # ---------- Now-playing history widgets ----------
        self.history_toggle_btn = QtWidgets.QToolButton()
        self.history_toggle_btn.setText("Now Playing History")
        self.history_toggle_btn.setCheckable(True)
        self.history_toggle_btn.setChecked(False)
        self.history_toggle_btn.setToolButtonStyle(
            QtCore.Qt.ToolButtonTextBesideIcon
        )
        self.history_toggle_btn.setArrowType(QtCore.Qt.RightArrow)

        self.history_table = QtWidgets.QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(
            ["Time", "Title", "Artist", "Album"]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.history_table.setVisible(False)

        # ---------- Display tab labels ----------
        self.display_title_label = QtWidgets.QLabel("—")
        self.display_title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.display_title_label.setWordWrap(True)
        title_font = self.display_title_label.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        self.display_title_label.setFont(title_font)

        self.display_artist_label = QtWidgets.QLabel("—")
        self.display_artist_label.setAlignment(QtCore.Qt.AlignCenter)
        self.display_artist_label.setWordWrap(True)
        artist_font = self.display_artist_label.font()
        artist_font.setPointSize(16)
        artist_font.setBold(False)
        self.display_artist_label.setFont(artist_font)

        # ---------- Layout: Top controls + Tabs ----------
        main_layout = QtWidgets.QVBoxLayout(self)

        # Top row: tuning controls + radio/record buttons in same row
        tune_layout = QtWidgets.QGridLayout()
        tune_layout.addWidget(freq_label, 0, 0)
        tune_layout.addWidget(self.freq_edit, 0, 1)
        tune_layout.addWidget(prog_label, 0, 2)
        tune_layout.addWidget(self.prog_combo, 0, 3)
        tune_layout.addWidget(self.radio_btn, 0, 4)
        tune_layout.addWidget(self.record_btn, 0, 5)
        tune_layout.addWidget(self.record_time_label, 0, 6)
        main_layout.addLayout(tune_layout)

        # Now Playing (single line) wrapped in a widget so it can be shown/hidden
        self.meta_widget = QtWidgets.QWidget()
        meta_row = QtWidgets.QHBoxLayout(self.meta_widget)
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addWidget(QtWidgets.QLabel("Title:"))
        meta_row.addWidget(self.title_label, 1)
        meta_row.addSpacing(12)
        meta_row.addWidget(QtWidgets.QLabel("Artist:"))
        meta_row.addWidget(self.artist_label, 1)
        meta_row.addSpacing(12)
        meta_row.addWidget(QtWidgets.QLabel("Album:"))
        meta_row.addWidget(self.album_label, 1)
        main_layout.addWidget(self.meta_widget)

        # Tabs: order Info, Presets, Config, Display
        self.tabs = QtWidgets.QTabWidget()
        self.info_tab = QtWidgets.QWidget()
        self.presets_tab = QtWidgets.QWidget()
        self.config_tab = QtWidgets.QWidget()
        self.display_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.info_tab, "Info")
        self.tabs.addTab(self.presets_tab, "Presets")
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.display_tab, "Display")
        # Give the tab area stretch so it scales with the window
        main_layout.addWidget(self.tabs, 1)

        # ---------- Config tab layout ----------
        config_layout = QtWidgets.QFormLayout(self.config_tab)
        config_layout.addRow(host_label, self.host_edit)
        config_layout.addRow(port_label, self.port_edit)

        record_dir_layout = QtWidgets.QHBoxLayout()
        record_dir_layout.addWidget(self.record_dir_edit)
        record_dir_layout.addWidget(self.browse_dir_btn)
        config_layout.addRow("Recording directory:", record_dir_layout)

        config_layout.addRow("Units:", self.units_combo)
        config_layout.addRow("Your latitude (deg):", self.user_lat_edit)
        config_layout.addRow("Your longitude (deg):", self.user_lon_edit)
        config_layout.addRow("Your altitude (m/ft):", self.user_alt_edit)

        # ---------- Info tab layout ----------
        info_layout = QtWidgets.QVBoxLayout(self.info_tab)
        self.info_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        # Top part: summary line, graph, history dropdown
        top_info_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_info_widget)

        self.info_summary_label = QtWidgets.QLabel()
        self.info_summary_label.setWordWrap(True)
        top_layout.addWidget(self.info_summary_label)

        top_layout.addWidget(self.ber_plot)

        top_layout.addWidget(self.history_toggle_btn)
        top_layout.addWidget(self.history_table)

        # Bottom part: log toggle + clear/log text (resizable via splitter)
        bottom_log_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_log_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        log_header_layout = QtWidgets.QHBoxLayout()
        log_header_layout.addWidget(self.log_toggle_btn)
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.clear_log_btn)

        bottom_layout.addLayout(log_header_layout)
        bottom_layout.addWidget(self.log_text)

        self.info_splitter.addWidget(top_info_widget)
        self.info_splitter.addWidget(bottom_log_widget)
        self.info_splitter.setStretchFactor(0, 4)
        self.info_splitter.setStretchFactor(1, 1)
        self.info_splitter.setSizes([400, 120])

        info_layout.addWidget(self.info_splitter)

        # ---------- Display tab layout ----------
        display_layout = QtWidgets.QVBoxLayout(self.display_tab)
        # Keep a small fixed margin from the very top
        display_layout.addSpacing(20)
        display_layout.addWidget(self.display_title_label)
        # This stretch grows/shrinks with window height, separating title and artist
        display_layout.addStretch(1)
        display_layout.addWidget(self.display_artist_label)
        # Extra stretch below so the artist doesn't cling to the bottom
        display_layout.addStretch(2)
        # ---------- Presets tab layout ----------
        self._init_presets_tab()

        # ---------- Regexes ----------
        self.re_title = re.compile(r"Title:\s*(.+)", re.IGNORECASE)
        self.re_artist = re.compile(r"Artist:\s*(.+)", re.IGNORECASE)
        self.re_album = re.compile(r"Album:\s*(.+)", re.IGNORECASE)
        self.re_ber = re.compile(r"BER:\s*([0-9]*\.?[0-9eE+-]+)")
        self.re_station_loc = re.compile(
            r"Station location:\s*([0-9.+-]+),\s*([0-9.+-]+),\s*([0-9.+-]+)m",
            re.IGNORECASE,
        )

        # ---------- Hook signals ----------
        self.radio_btn.clicked.connect(self.toggle_radio)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.browse_dir_btn.clicked.connect(self._choose_record_directory)
        self.log_toggle_btn.toggled.connect(self._toggle_log_visibility)
        self.history_toggle_btn.toggled.connect(self._toggle_history_visibility)
        self.clear_log_btn.clicked.connect(self._clear_log)
        self.units_combo.currentIndexChanged.connect(self._units_changed)

        self.user_lat_edit.editingFinished.connect(self._update_user_location)
        self.user_lon_edit.editingFinished.connect(self._update_user_location)
        self.user_alt_edit.editingFinished.connect(self._update_user_location)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # ---------- Load settings ----------
        self._load_settings()
        self._update_user_location()  # parse user location from loaded text
        self._update_info_summary_line()

        # ---------- Check binaries ----------
        self._check_dependency("nrsc5")
        self._check_dependency("ffmpeg")
        self._check_dependency("ffplay")

    # ---------------- Presets tab setup ----------------
    def _init_presets_tab(self):
        layout = QtWidgets.QVBoxLayout(self.presets_tab)

        form = QtWidgets.QFormLayout()
        self.preset_name_edit = QtWidgets.QLineEdit()
        form.addRow("Preset name:", self.preset_name_edit)
        layout.addLayout(form)

        # Row 1: basic actions
        row1 = QtWidgets.QHBoxLayout()
        self.add_preset_btn = QtWidgets.QPushButton("Add current")
        self.remove_preset_btn = QtWidgets.QPushButton("Remove selected")
        self.tune_preset_btn = QtWidgets.QPushButton("Tune to selected")
        row1.addWidget(self.add_preset_btn)
        row1.addWidget(self.remove_preset_btn)
        row1.addWidget(self.tune_preset_btn)
        layout.addLayout(row1)

        # Row 2: advanced actions
        row2 = QtWidgets.QHBoxLayout()
        self.move_up_btn = QtWidgets.QPushButton("Move Up")
        self.move_down_btn = QtWidgets.QPushButton("Move Down")
        self.import_presets_btn = QtWidgets.QPushButton("Import...")
        self.export_presets_btn = QtWidgets.QPushButton("Export...")
        row2.addWidget(self.move_up_btn)
        row2.addWidget(self.move_down_btn)
        row2.addStretch()
        row2.addWidget(self.import_presets_btn)
        row2.addWidget(self.export_presets_btn)
        layout.addLayout(row2)

        self.preset_list = QtWidgets.QListWidget()
        layout.addWidget(self.preset_list)

        self.add_preset_btn.clicked.connect(self._add_preset)
        self.remove_preset_btn.clicked.connect(self._remove_selected_preset)
        self.tune_preset_btn.clicked.connect(self._tune_selected_preset)
        self.preset_list.itemDoubleClicked.connect(self._tune_preset_item)

        self.move_up_btn.clicked.connect(lambda: self._move_preset(-1))
        self.move_down_btn.clicked.connect(lambda: self._move_preset(1))
        self.import_presets_btn.clicked.connect(self._import_presets)
        self.export_presets_btn.clicked.connect(self._export_presets)

    def _add_preset(self):
        freq = self.freq_edit.text().strip()
        prog_num = self._get_current_program_number()
        prog_str = str(prog_num)
        if not freq:
            return
        name = self.preset_name_edit.text().strip() or f"{freq} MHz P{prog_str}"
        text = f"{name} — {freq} MHz (P{prog_str})"
        item = QtWidgets.QListWidgetItem(text)
        meta = {"name": name, "freq": freq, "prog": prog_str}
        item.setData(QtCore.Qt.UserRole, meta)
        self.preset_list.addItem(item)

    def _remove_selected_preset(self):
        row = self.preset_list.currentRow()
        if row >= 0:
            self.preset_list.takeItem(row)

    def _move_preset(self, direction: int):
        row = self.preset_list.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= self.preset_list.count():
            return
        item = self.preset_list.takeItem(row)
        self.preset_list.insertItem(new_row, item)
        self.preset_list.setCurrentRow(new_row)

    def _tune_selected_preset(self):
        item = self.preset_list.currentItem()
        if item:
            self._tune_preset_item(item)

    def _tune_preset_item(self, item):
        meta = item.data(QtCore.Qt.UserRole)
        if not meta:
            return
        freq = meta.get("freq", "")
        prog = meta.get("prog", "0")
        if freq:
            self.freq_edit.setText(freq)
        self._select_program_by_number(prog)

        # If radio is currently running, stop and restart with new settings
        if self.radio_running:
            self.stopping_radio = True
            self.stop_stream()
            self.stopping_radio = False
            self.start_stream()

    def _import_presets(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Presets", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Import Error", f"Failed to import presets:\n{e}"
            )
            return

        if not isinstance(data, list):
            QtWidgets.QMessageBox.warning(
                self, "Import Error", "Invalid presets file format."
            )
            return

        for meta in data:
            if not isinstance(meta, dict):
                continue
            name = meta.get("name", "")
            freq = meta.get("freq", "")
            prog = meta.get("prog", "0")
            if not freq:
                continue
            text = f"{name or (freq + ' MHz P' + prog)} — {freq} MHz (P{prog})"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, meta)
            self.preset_list.addItem(item)

    def _export_presets(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Presets", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filename:
            return
        presets = []
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            meta = item.data(QtCore.Qt.UserRole)
            if isinstance(meta, dict):
                presets.append(meta)
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=2)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Export Error", f"Failed to export presets:\n{e}"
            )

    # ---------------- Settings persistence ----------------
    def _load_settings(self):
        s = self.settings

        self.host_edit.setText(s.value("host", self.host_edit.text()))
        self.port_edit.setText(s.value("port", self.port_edit.text()))
        self.freq_edit.setText(s.value("freq", self.freq_edit.text()))
        saved_prog = s.value("prog", "0")
        self.record_dir_edit.setText(
            s.value("record_dir", self.record_dir_edit.text())
        )
        units_index = int(s.value("units_index", 0))
        if 0 <= units_index < self.units_combo.count():
            self.units_combo.setCurrentIndex(units_index)

        self.user_lat_edit.setText(s.value("user_lat", self.user_lat_edit.text()))
        self.user_lon_edit.setText(s.value("user_lon", self.user_lon_edit.text()))
        self.user_alt_edit.setText(s.value("user_alt", self.user_alt_edit.text()))

        # Presets
        self._load_presets()

        # Geometry
        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        # Select saved program number if present
        self._select_program_by_number(saved_prog)

    def _save_settings(self):
        s = self.settings
        s.setValue("host", self.host_edit.text())
        s.setValue("port", self.port_edit.text())
        s.setValue("freq", self.freq_edit.text())
        s.setValue("prog", str(self._get_current_program_number()))
        s.setValue("record_dir", self.record_dir_edit.text())
        s.setValue("units_index", self.units_combo.currentIndex())
        s.setValue("user_lat", self.user_lat_edit.text())
        s.setValue("user_lon", self.user_lon_edit.text())
        s.setValue("user_alt", self.user_alt_edit.text())
        s.setValue("geometry", self.saveGeometry())
        self._save_presets()

    def _load_presets(self):
        self.preset_list.clear()
        data = self.settings.value("presets", "[]")
        try:
            presets = json.loads(data)
        except Exception:
            presets = []
        if not isinstance(presets, list):
            presets = []
        for meta in presets:
            name = meta.get("name", "")
            freq = meta.get("freq", "")
            prog = meta.get("prog", "0")
            if not freq:
                continue
            text = f"{name or (freq + ' MHz P' + prog)} — {freq} MHz (P{prog})"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, meta)
            self.preset_list.addItem(item)

    def _save_presets(self):
        presets = []
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            meta = item.data(QtCore.Qt.UserRole)
            if isinstance(meta, dict):
                presets.append(meta)
        self.settings.setValue("presets", json.dumps(presets))

    # ---------------- Dependency check ----------------
    def _check_dependency(self, binary):
        if not shutil.which(binary):
            QtWidgets.QMessageBox.critical(
                self,
                "Missing Dependency",
                f"'{binary}' not found in PATH.\nPlease install it to use this tool.",
            )
            self.radio_btn.setEnabled(False)

    # ---------------- Core Logic: The Data Pump ----------------
    def _distribute_audio_data(self):
        """Reads raw bytes from nrsc5 and sends them to ffplay and ffmpeg."""
        if not self.proc_nrsc5:
            return

        data = self.proc_nrsc5.readAllStandardOutput()
        if not data:
            return

        if self.proc_play and self.proc_play.state() == QtCore.QProcess.Running:
            self.proc_play.write(data)

        if (
            self.recording
            and self.proc_rec
            and self.proc_rec.state() == QtCore.QProcess.Running
        ):
            self.proc_rec.write(data)

    # ---------------- Log handling ----------------
    def _append_log_line(self, line: str):
        self.log_text.appendPlainText(line)
        doc = self.log_text.document()
        # Trim from the top if we exceed max_log_lines
        while doc.blockCount() > self.max_log_lines:
            block = doc.firstBlock()
            cursor = QtGui.QTextCursor(block)
            cursor.select(QtGui.QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _clear_log(self):
        self.log_text.clear()

    # ---------------- Process diagnostics ----------------
    def _on_process_error(self, name: str, error: QtCore.QProcess.ProcessError):
        err_map = {
            QtCore.QProcess.FailedToStart: "Failed to start",
            QtCore.QProcess.Crashed: "Crashed",
            QtCore.QProcess.Timedout: "Timed out",
            QtCore.QProcess.WriteError: "Write error",
            QtCore.QProcess.ReadError: "Read error",
            QtCore.QProcess.UnknownError: "Unknown error",
        }
        msg = err_map.get(error, "Unknown error")

        # If the user (or app close) is intentionally stopping the radio,
        # ignore the "Crashed" error – that's just Qt's name for a killed process.
        if self.stopping_radio and error == QtCore.QProcess.Crashed:
            self._append_log_line(f"{name} terminated (user stop).")
            return

        self._append_log_line(f"{name} error: {msg} ({int(error)})")

        if name == "nrsc5":
            self.status_text = f"Status: nrsc5 error: {msg}"
            self._update_info_summary_line()
            QtWidgets.QMessageBox.warning(
                self, "nrsc5 Error", f"nrsc5 error: {msg}"
            )

    def _on_process_finished(self, name: str, exitCode: int, exitStatus: QtCore.QProcess.ExitStatus):
        # During an intentional stop (button/preset/app close) Qt often reports
        # CrashExit even though we asked the process to die. Avoid scary wording.
        if self.stopping_radio and exitStatus == QtCore.QProcess.CrashExit:
            self._append_log_line(f"{name} terminated (user stop).")
            return

        status_str = "normal" if exitStatus == QtCore.QProcess.NormalExit else "crashed"
        self._append_log_line(
            f"{name} finished with code {exitCode}, status: {status_str}"
        )

    def _on_nrsc5_finished(self, exitCode: int, exitStatus: QtCore.QProcess.ExitStatus):
        self._on_process_finished("nrsc5", exitCode, exitStatus)

        # If nrsc5 died on its own while we thought the radio was running,
        # clean up. But don't do this during an intentional stop to avoid
        # re-entering stop_stream().
        if self.radio_running and not self.stopping_radio:
            self.stop_stream()

    # ---------------- Metadata & BER parsing ----------------
    def _parse_metadata_output(self):
        """
        Reads nrsc5 STDERR to get song titles, BER, station location, and log.
        """
        if not self.proc_nrsc5:
            return

        raw_bytes = self.proc_nrsc5.readAllStandardError()
        text = bytes(raw_bytes).decode(errors="ignore")

        metadata_changed = False

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Append to log with line limit
            self._append_log_line(line)

            # BER
            m = self.re_ber.search(line)
            if m:
                ber_str = m.group(1)
                try:
                    ber_val = float(ber_str)          # raw BER (e.g. 0.00123)
                    ber_percent = ber_val * 100.0     # convert to percent
                    self.ber_text = f"{ber_percent:.3f} %"
                    self._update_ber_graph(ber_percent)
                    self._update_info_summary_line()
                except ValueError:
                    pass

            # Metadata
            m = self.re_title.search(line)
            if m:
                title_text = m.group(1).strip()
                self.title_label.setText(title_text)
                self.display_title_label.setText(title_text)
                metadata_changed = True

            m = self.re_artist.search(line)
            if m:
                artist_text = m.group(1).strip()
                self.artist_label.setText(artist_text)

                # Easter egg: override Display tab only
                if "bieber" in artist_text.lower():
                    self.display_artist_label.setText("[artist choice not endorsed]")
                else:
                    self.display_artist_label.setText(artist_text)
            
                metadata_changed = True


            m = self.re_album.search(line)
            if m:
                self.album_label.setText(m.group(1).strip())
                metadata_changed = True

            # Station location
            m = self.re_station_loc.search(line)
            if m:
                try:
                    lat = float(m.group(1))
                    lon = float(m.group(2))
                    alt = float(m.group(3))
                    self.station_lat = lat
                    self.station_lon = lon
                    self.station_alt = alt
                    self._update_distances()
                except ValueError:
                    pass

        if metadata_changed:
            self._maybe_add_history_entry()

    def _update_ber_graph(self, ber_value: float):
        """Append a BER value (in percent) and refresh the BER plot."""
        self.ber_history.append(ber_value)
        if len(self.ber_history) > self.ber_max_points:
            self.ber_history = self.ber_history[-self.ber_max_points :]

        x = list(range(len(self.ber_history)))
        self.ber_curve.setData(x, self.ber_history)

        # X range: always show a 300-sample window
        if len(self.ber_history) < self.ber_max_points:
            self.ber_plot.setXRange(0, self.ber_max_points - 1)
        else:
            start = len(self.ber_history) - self.ber_max_points
            end = len(self.ber_history) - 1
            self.ber_plot.setXRange(start, end)

        # Y range: soft 0–10% bound, but expand if values go higher
        y_max = max(self.ber_history) if self.ber_history else 0.0
        upper = max(10.0, y_max * 1.1 if y_max > 0 else 10.0)
        self.ber_plot.setYRange(0, upper)

    # ---------------- Now-playing history ----------------
    def _maybe_add_history_entry(self):
        title = self.title_label.text().strip()
        artist = self.artist_label.text().strip()
        album = self.album_label.text().strip()

        if (
            title in ["", "—"]
            and artist in ["", "—"]
            and album in ["", "—"]
        ):
            return

        key = (title, artist, album)
        prev = (self.last_title, self.last_artist, self.last_album)
        if key == prev:
            return

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        self.history_table.setItem(row, 0, QtWidgets.QTableWidgetItem(now_str))
        self.history_table.setItem(row, 1, QtWidgets.QTableWidgetItem(title))
        self.history_table.setItem(row, 2, QtWidgets.QTableWidgetItem(artist))
        self.history_table.setItem(row, 3, QtWidgets.QTableWidgetItem(album))

        # Limit history size
        while self.history_table.rowCount() > self.max_history_rows:
            self.history_table.removeRow(0)

        self.last_title, self.last_artist, self.last_album = key

    # ---------------- Distances ----------------
    def _update_user_location(self):
        def parse(edit):
            text = edit.text().strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None

        self.user_lat = parse(self.user_lat_edit)
        self.user_lon = parse(self.user_lon_edit)
        alt_val = parse(self.user_alt_edit)
        if alt_val is not None:
            # Interpret altitude according to units (m or ft), store internally as meters
            if self.units_combo.currentIndex() == 0:  # metric
                self.user_alt = alt_val
            else:  # imperial: feet
                self.user_alt = alt_val * 0.3048
        else:
            self.user_alt = None

        self._update_distances()

    def _units_changed(self, index):
        # Reinterpret altitude with new units and update distances
        self._update_user_location()

    def _bearing_to_cardinal(self, bearing_deg: float) -> str:
        dirs = [
            "North",
            "Northeast",
            "East",
            "Southeast",
            "South",
            "Southwest",
            "West",
            "Northwest",
        ]
        idx = int((bearing_deg + 22.5) // 45) % 8
        return dirs[idx]

    def _update_distances(self):
        """
        Compute approximate horizontal distance, bearing, and vertical distance
        between user and station, and format them using metric or imperial units.
        Updates the summary line only.
        """
        if any(
            v is None
            for v in (
                self.station_lat,
                self.station_lon,
                self.station_alt,
                self.user_lat,
                self.user_lon,
                self.user_alt,
            )
        ):
            self.relpos_text = "N/A"
            self.vert_text = "N/A"
            self._update_info_summary_line()
            return

        # Earth radius (m)
        R = 6371000.0

        lat1 = math.radians(self.user_lat)
        lon1 = math.radians(self.user_lon)
        lat2 = math.radians(self.station_lat)
        lon2 = math.radians(self.station_lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        lat_mean = 0.5 * (lat1 + lat2)

        # Local coordinates: x east–west (positive east), z north–south (positive north)
        dx = R * math.cos(lat_mean) * dlon
        dz = R * dlat

        # Vertical difference (station - user)
        dv = self.station_alt - self.user_alt

        horizontal_m = math.hypot(dx, dz)
        if horizontal_m == 0:
            bearing_deg = 0.0
            cardinal = "Here"
        else:
            # Bearing from true north, clockwise: atan2(East, North)
            bearing_rad = math.atan2(dx, dz)
            bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
            cardinal = self._bearing_to_cardinal(bearing_deg)

        use_metric = self.units_combo.currentIndex() == 0

        # Summary horizontal distance with cardinal and bearing
        if use_metric:
            dist = horizontal_m / 1000.0
            unit = "km"
        else:
            dist = horizontal_m / 1609.344
            unit = "mi"

        if horizontal_m == 0:
            relpos = "0 (here)"
        else:
            relpos = f"{dist:,.2f} {unit} {cardinal} ({bearing_deg:.0f}°)"

        # Vertical text
        if dv == 0:
            vert = "0"
        else:
            direction = "above" if dv > 0 else "below"
            dist_m = abs(dv)
            if use_metric:
                dist_v = dist_m
                vunit = "m"
            else:
                dist_v = dist_m * 3.28084
                vunit = "ft"
            vert = f"{dist_v:,.1f} {vunit} {direction}"

        self.relpos_text = relpos
        self.vert_text = vert
        self._update_info_summary_line()

    # ---------------- Streaming Controls ----------------
    def toggle_radio(self):
        if not self.radio_btn.isEnabled():
            return

        # Prevent rapid double-click races
        self.radio_btn.setEnabled(False)
        try:
            if self.radio_running:
                self.stopping_radio = True
                self.stop_stream()
                self.stopping_radio = False
            else:
                self.start_stream()
        finally:
            self.radio_btn.setEnabled(True)

    def _get_current_program_number(self) -> int:
        idx = self.prog_combo.currentIndex()
        if idx < 0:
            return 0
        text = self.prog_combo.itemText(idx).strip()
        # Allow "0" or "0 - Something" formats
        try:
            num_str = text.split("-")[0].strip()
            return int(num_str)
        except Exception:
            try:
                return int(text)
            except ValueError:
                return 0

    def _select_program_by_number(self, prog_str: str):
        for i in range(self.prog_combo.count()):
            text = self.prog_combo.itemText(i).strip()
            num_str = text.split("-")[0].strip()
            if num_str == prog_str:
                self.prog_combo.setCurrentIndex(i)
                return

    def _validate_start_inputs(self) -> bool:
        # Frequency
        freq_text = self.freq_edit.text().strip()
        try:
            freq_val = float(freq_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(
                self, "Input Error", "Frequency must be a number (MHz)."
            )
            self.freq_edit.setFocus()
            return False
        if freq_val <= 0:
            QtWidgets.QMessageBox.warning(
                self, "Input Error", "Frequency must be greater than zero."
            )
            self.freq_edit.setFocus()
            return False

        # Host/port
        host = self.host_edit.text().strip()
        port_text = self.port_edit.text().strip()
        if host:
            if not port_text:
                QtWidgets.QMessageBox.warning(
                    self, "Input Error",
                    "Port is required when a remote rtl_tcp host is specified."
                )
                self.port_edit.setFocus()
                return False
            try:
                port_val = int(port_text)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self, "Input Error", "Port must be an integer."
                )
                self.port_edit.setFocus()
                return False
            if not (1 <= port_val <= 65535):
                QtWidgets.QMessageBox.warning(
                    self, "Input Error",
                    "Port must be between 1 and 65535."
                )
                self.port_edit.setFocus()
                return False

        return True

    def start_stream(self):
        if self.radio_running:
            return

        if not self._validate_start_inputs():
            return

        freq = self.freq_edit.text().strip()
        prog = str(self._get_current_program_number()).strip()
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()

        # Start Audio Player (Consumer)
        play_args = [
            "-nodisp",
            "-autoexit",
            "-hide_banner",
            "-loglevel",
            "quiet",
            "-f",
            "s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            "pipe:0",
        ]
        self.proc_play = QtCore.QProcess(self)
        self.proc_play.errorOccurred.connect(
            lambda e: self._on_process_error("ffplay", e)
        )
        self.proc_play.finished.connect(
            lambda code, status: self._on_process_finished(
                "ffplay", code, status
            )
        )
        self.proc_play.start("ffplay", play_args)
        if not self.proc_play.waitForStarted(2000):
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to start ffplay."
            )
            self._kill_process(self.proc_play)
            self.proc_play = None
            return

        # Start Receiver (Producer)
        nrsc_args = []
        if host:
            if port:
                host = f"{host}:{port}"
            nrsc_args += ["-H", host]
        nrsc_args += [freq, prog, "-o", "-"]

        self.proc_nrsc5 = QtCore.QProcess(self)
        self.proc_nrsc5.setProcessChannelMode(QtCore.QProcess.SeparateChannels)
        self.proc_nrsc5.errorOccurred.connect(
            lambda e: self._on_process_error("nrsc5", e)
        )
        self.proc_nrsc5.readyReadStandardOutput.connect(
            self._distribute_audio_data
        )
        self.proc_nrsc5.readyReadStandardError.connect(
            self._parse_metadata_output
        )
        self.proc_nrsc5.finished.connect(self._on_nrsc5_finished)

        self.proc_nrsc5.start("nrsc5", nrsc_args)

        if self.proc_nrsc5.waitForStarted(2000):
            self.radio_running = True
            self.radio_btn.setText("Stop Radio")
            self._update_ui_state(running=True)
            self._reset_labels()
        else:
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to start nrsc5."
            )
            self.stop_stream()

    def stop_stream(self):
        # Stop recording first
        self.stop_recording()

        self._kill_process(self.proc_nrsc5)
        self._kill_process(self.proc_play)

        self.proc_nrsc5 = None
        self.proc_play = None

        self.radio_running = False
        self.radio_btn.setText("Start Radio")
        self._update_ui_state(running=False)

    # ---------------- Recording Controls ----------------
    def toggle_recording(self):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not self.radio_running:
            return

        freq = self.freq_edit.text().strip()
        prog = str(self._get_current_program_number()).strip()
        self.current_record_file = self._make_filename(freq, prog)

        ffmpeg_args = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-i",
            "pipe:0",
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            self.current_record_file,
        ]

        self.proc_rec = QtCore.QProcess(self)
        self.proc_rec.errorOccurred.connect(
            lambda e: self._on_process_error("ffmpeg", e)
        )
        self.proc_rec.finished.connect(
            lambda code, status: self._on_process_finished(
                "ffmpeg", code, status
            )
        )
        self.proc_rec.start("ffmpeg", ffmpeg_args)

        if self.proc_rec.waitForStarted(1000):
            self.recording = True
            self.record_btn.setText("Stop Recording")
            self.status_text = "Status: Listening & Recording"
            # Start recording duration tracking
            self.record_start_time = datetime.datetime.now()
            self.record_duration_text = "00:00:00"
            self.record_timer.start()
            self._update_info_summary_line()
            self.record_time_label.setText(self.record_duration_text)
            self.record_btn.setStyleSheet("background-color: #ffcccc")
        else:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not start ffmpeg recorder."
            )

    def stop_recording(self):
        if not self.recording:
            return

        if self.proc_rec and self.proc_rec.state() == QtCore.QProcess.Running:
            self.proc_rec.closeWriteChannel()
            self.proc_rec.waitForFinished(2000)
            if self.proc_rec.state() == QtCore.QProcess.Running:
                self.proc_rec.terminate()

        self.recording = False
        self.record_btn.setText("Start Recording")
        self.record_btn.setStyleSheet("")
        self.record_timer.stop()
        self.record_start_time = None
        self.record_duration_text = ""

        if self.radio_running:
            self.status_text = "Status: Listening"
        else:
            self.status_text = "Status: Idle"
        self._update_info_summary_line()

        if self.current_record_file and os.path.exists(self.current_record_file):
            print(f"Recording saved: {self.current_record_file}")

        self.proc_rec = None

    def _update_record_duration(self):
        if not self.recording or not self.record_start_time:
            return
        delta = datetime.datetime.now() - self.record_start_time
        total_secs = int(delta.total_seconds())
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        self.record_duration_text = f"{h:02}:{m:02}:{s:02}"
        self._update_info_summary_line()
        self.record_time_label.setText(self.record_duration_text)

    # ---------------- Helpers ----------------
    def _kill_process(self, proc):
        if proc and proc.state() != QtCore.QProcess.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(1000):
                proc.kill()

    def _update_ui_state(self, running):
        # Radio button always enabled (to start/stop)
        self.radio_btn.setEnabled(True)
        self.record_btn.setEnabled(running)

        self.freq_edit.setEnabled(not running)
        self.host_edit.setEnabled(not running)
        self.prog_combo.setEnabled(not running)
        self.port_edit.setEnabled(not running)
        self.record_dir_edit.setEnabled(not running)
        self.browse_dir_btn.setEnabled(not running)
        # Units and user location remain editable while running

        if running:
            if not self.recording:
                self.status_text = "Status: Listening"
        else:
            self.status_text = "Status: Idle"
        self._update_info_summary_line()

    def _update_info_summary_line(self):
        status = self.status_text or "Status: N/A"
        ber = self.ber_text if self.ber_text not in [None, ""] else "N/A"
        pos = self.relpos_text if self.relpos_text not in [None, ""] else "N/A"
        vert = self.vert_text if self.vert_text not in [None, ""] else "N/A"

        parts = [
            status,
            f"BER: {ber}",
            f"Position: {pos}",
            f"Vertical: {vert}",
        ]

        # If we’re recording, also show the elapsed record time in the summary.
        if self.record_duration_text:
            parts.append(f"Rec: {self.record_duration_text}")

        self.info_summary_label.setText(" | ".join(parts))


    def _reset_labels(self):
        self.title_label.setText("—")
        self.artist_label.setText("—")
        self.album_label.setText("—")
        self.display_title_label.setText("—")
        self.display_artist_label.setText("—")

        self.ber_text = "—"
        self.relpos_text = "N/A"
        self.vert_text = "N/A"
        self.record_duration_text = ""
        self.record_timer.stop()
        self.record_start_time = None
        self._update_info_summary_line()
        self.record_time_label.clear()

        self.station_lat = None
        self.station_lon = None
        self.station_alt = None

        self.ber_history = []
        self.ber_curve.clear()

        self.log_text.clear()

        self.last_title = None
        self.last_artist = None
        self.last_album = None
        self.history_table.setRowCount(0)

    def _sanitize_filename(self, text):
        return re.sub(r'[\\/*?:"<>|]', "", text).strip()

    def _make_filename(self, freq, prog):
        artist = self.artist_label.text()
        title = self.title_label.text()

        has_meta = (artist not in ["—", ""]) and (title not in ["—", ""])

        if has_meta:
            safe_artist = self._sanitize_filename(artist)
            safe_title = self._sanitize_filename(title)
            ts = datetime.datetime.now().strftime("%H%M%S")
            filename = f"{safe_title} - {safe_artist}_{ts}.mp3"
        else:
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_freq = freq.replace(".", "_")
            filename = f"Radio_{safe_freq}_P{prog}_{ts}.mp3"

        dir_path = self.record_dir_edit.text().strip()
        if not dir_path or not os.path.isdir(dir_path):
            dir_path = os.path.expanduser("~/Desktop")
        return os.path.join(dir_path, filename)

    def _choose_record_directory(self):
        start_dir = self.record_dir_edit.text().strip() or os.path.expanduser("~")
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Recording Directory", start_dir
        )
        if directory:
            self.record_dir_edit.setText(directory)

    def _toggle_log_visibility(self, checked):
        self.log_text.setVisible(checked)
        self.log_toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        # Adjust splitter sizes a bit when toggling
        sizes = self.info_splitter.sizes()
        total = sum(sizes) if sizes else 1
        if checked:
            self.info_splitter.setSizes([int(total * 0.6), int(total * 0.4)])
        else:
            self.info_splitter.setSizes([int(total * 0.9), int(total * 0.1)])

    def _toggle_history_visibility(self, checked):
        self.history_table.setVisible(checked)
        self.history_toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

        # Optionally adjust splitter sizes a little
        sizes = self.info_splitter.sizes()
        total = sum(sizes) if sizes else 1
        self.info_splitter.setSizes([int(total * 0.7), int(total * 0.3)])

    def _on_tab_changed(self, index: int):
        # Hide top-bar Title/Artist/Album when Display tab is selected
        if self.tabs.widget(index) is self.display_tab:
            self.meta_widget.setVisible(False)
        else:
            self.meta_widget.setVisible(True)

    def closeEvent(self, event):
        # Mark that we’re intentionally shutting the radio down so the
        # QProcess "Crashed" signals are treated as normal.
        self.stopping_radio = True
        self._save_settings()
        self.stop_stream()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = NRSC5Gui()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
