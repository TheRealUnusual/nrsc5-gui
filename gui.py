"""
Main GUI class and all widgets, layouts, and signal connections.
Original file: nrsc5_gui_qt.py (NRSC5Gui class)
"""

from PyQt5 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import shutil
import sys
import os
import datetime
import json

# Import from our modules
from utils import (
    sanitize_filename,
    make_recording_filename,
    haversine_distance_and_bearing,
    bearing_to_cardinal,
    format_distance,
    format_altitude_difference,
    fit_font_to_label,
    parse_metadata_line,
)

from streaming import (
    kill_process,
    distribute_audio_data,
    start_nrsc5_process,
    start_ffplay_process,
    start_ffmpeg_recorder,
    stop_ffmpeg_recorder,
)


class NRSC5Gui(QtWidgets.QWidget):
    """
    Main window for NRSC5 GUI application.
    
    Original: NRSC5Gui class from nrsc5_gui_qt.py
    """
    
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
        self.radio_btn = QtWidgets.QPushButton("Start Radio")
        self.record_btn = QtWidgets.QPushButton("Start Recording")
        self.record_btn.setEnabled(False)

        # ---------- Record Time ----------
        self.record_time_label = QtWidgets.QLabel("")

        # ---------- Process Handlers ----------
        self.proc_nrsc5 = None
        self.proc_play = None
        self.proc_rec = None

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
        self.display_title_base_size = 24
        title_font = self.display_title_label.font()
        title_font.setPointSize(self.display_title_base_size)
        title_font.setBold(True)
        self.display_title_label.setFont(title_font)
        self.display_title_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred,
        )

        self.display_artist_label = QtWidgets.QLabel("—")
        self.display_artist_label.setAlignment(QtCore.Qt.AlignCenter)
        self.display_artist_label.setWordWrap(True)
        self.display_artist_base_size = 16
        artist_font = self.display_artist_label.font()
        artist_font.setPointSize(self.display_artist_base_size)
        artist_font.setBold(False)
        self.display_artist_label.setFont(artist_font)
        self.display_artist_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred,
        )

        # ---------- Layout: Top controls + Tabs ----------
        main_layout = QtWidgets.QVBoxLayout(self)

        # Top row
        tune_layout = QtWidgets.QGridLayout()
        tune_layout.addWidget(freq_label, 0, 0)
        tune_layout.addWidget(self.freq_edit, 0, 1)
        tune_layout.addWidget(prog_label, 0, 2)
        tune_layout.addWidget(self.prog_combo, 0, 3)
        tune_layout.addWidget(self.radio_btn, 0, 4)
        tune_layout.addWidget(self.record_btn, 0, 5)
        tune_layout.addWidget(self.record_time_label, 0, 6)
        main_layout.addLayout(tune_layout)

        # Now Playing
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

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.info_tab = QtWidgets.QWidget()
        self.presets_tab = QtWidgets.QWidget()
        self.config_tab = QtWidgets.QWidget()
        self.display_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.info_tab, "Info")
        self.tabs.addTab(self.presets_tab, "Presets")
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.display_tab, "Display")
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

        top_info_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_info_widget)

        self.info_summary_label = QtWidgets.QLabel()
        self.info_summary_label.setWordWrap(True)
        top_layout.addWidget(self.info_summary_label)

        top_layout.addWidget(self.ber_plot)

        top_layout.addWidget(self.history_toggle_btn)
        top_layout.addWidget(self.history_table)

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
        display_layout.setContentsMargins(24, 24, 24, 24)
        display_layout.addStretch(1)
        display_layout.addWidget(self.display_title_label, alignment=QtCore.Qt.AlignCenter)
        display_layout.addSpacing(16)
        display_layout.addWidget(self.display_artist_label, alignment=QtCore.Qt.AlignCenter)
        display_layout.addStretch(1)

        # ---------- Presets tab layout ----------
        self._init_presets_tab()

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
        self._update_user_location()
        self._update_info_summary_line()
        self._update_display_fonts()

        # ---------- Check binaries ----------
        self._check_dependency("nrsc5")
        self._check_dependency("ffmpeg")
        self._check_dependency("ffplay")

    # ================ Presets Tab ================
    # Original: NRSC5Gui._init_presets_tab() and related methods
    
    def _init_presets_tab(self):
        layout = QtWidgets.QVBoxLayout(self.presets_tab)

        form = QtWidgets.QFormLayout()
        self.preset_name_edit = QtWidgets.QLineEdit()
        form.addRow("Preset name:", self.preset_name_edit)
        layout.addLayout(form)

        row1 = QtWidgets.QHBoxLayout()
        self.add_preset_btn = QtWidgets.QPushButton("Add current")
        self.remove_preset_btn = QtWidgets.QPushButton("Remove selected")
        self.tune_preset_btn = QtWidgets.QPushButton("Tune to selected")
        row1.addWidget(self.add_preset_btn)
        row1.addWidget(self.remove_preset_btn)
        row1.addWidget(self.tune_preset_btn)
        layout.addLayout(row1)

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

    def _move_preset(self, direction):
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

    # ================ Settings Persistence ================
    # Original: NRSC5Gui._load_settings(), _save_settings(), etc.
    
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

        self._load_presets()

        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

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

    # ================ Dependency Check ================
    # Original: NRSC5Gui._check_dependency()
    
    def _check_dependency(self, binary):
        if not shutil.which(binary):
            QtWidgets.QMessageBox.critical(
                self,
                "Missing Dependency",
                f"'{binary}' not found in PATH.\nPlease install it to use this tool.",
            )
            self.radio_btn.setEnabled(False)

    # ================ Audio Data Distribution ================
    # Original: NRSC5Gui._distribute_audio_data()
    # Now delegated to streaming.py
    
    def _distribute_audio_data(self):
        distribute_audio_data(
            self.proc_nrsc5,
            self.proc_play,
            self.proc_rec,
            self.recording
        )

    # ================ Log Handling ================
    # Original: NRSC5Gui._append_log_line(), _clear_log()
    
    def _append_log_line(self, line):
        self.log_text.appendPlainText(line)
        doc = self.log_text.document()
        while doc.blockCount() > self.max_log_lines:
            block = doc.firstBlock()
            cursor = QtGui.QTextCursor(block)
            cursor.select(QtGui.QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _clear_log(self):
        self.log_text.clear()

    # ================ Process Diagnostics ================
    # Original: NRSC5Gui._on_process_error(), _on_process_finished(), etc.
    
    def _on_process_error(self, name, error):
        err_map = {
            QtCore.QProcess.FailedToStart: "Failed to start",
            QtCore.QProcess.Crashed: "Crashed",
            QtCore.QProcess.Timedout: "Timed out",
            QtCore.QProcess.WriteError: "Write error",
            QtCore.QProcess.ReadError: "Read error",
            QtCore.QProcess.UnknownError: "Unknown error",
        }
        msg = err_map.get(error, "Unknown error")

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

    def _on_process_finished(self, name, exitCode, exitStatus):
        if self.stopping_radio and exitStatus == QtCore.QProcess.CrashExit:
            self._append_log_line(f"{name} terminated (user stop).")
            return

        status_str = "normal" if exitStatus == QtCore.QProcess.NormalExit else "crashed"
        self._append_log_line(
            f"{name} finished with code {exitCode}, status: {status_str}"
        )

    def _on_nrsc5_finished(self, exitCode, exitStatus):
        self._on_process_finished("nrsc5", exitCode, exitStatus)

        if self.radio_running and not self.stopping_radio:
            self.stop_stream()

    # ================ Metadata & BER Parsing ================
    # Original: NRSC5Gui._parse_metadata_output(), _update_ber_graph()
    # Now using utils.parse_metadata_line()
    
    def _parse_metadata_output(self):
        if not self.proc_nrsc5:
            return

        raw_bytes = self.proc_nrsc5.readAllStandardError()
        text = bytes(raw_bytes).decode(errors="ignore")

        metadata_changed = False

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            self._append_log_line(line)

            parsed = parse_metadata_line(line)
            if not parsed:
                continue

            if 'ber' in parsed:
                self.ber_text = f"{parsed['ber']:.3f} %"
                self._update_ber_graph(parsed['ber'])
                self._update_info_summary_line()

            if 'title' in parsed:
                title_text = parsed['title']
                self.title_label.setText(title_text)
                self.display_title_label.setText(title_text)
                metadata_changed = True

            if 'artist' in parsed:
                artist_text = parsed['artist']
                self.artist_label.setText(artist_text)

                # Easter egg
                if "bieber" in artist_text.lower():
                    self.display_artist_label.setText("[artist choice not endorsed]")
                else:
                    self.display_artist_label.setText(artist_text)

                metadata_changed = True

            if 'album' in parsed:
                self.album_label.setText(parsed['album'])
                metadata_changed = True

            if 'station_loc' in parsed:
                lat, lon, alt = parsed['station_loc']
                self.station_lat = lat
                self.station_lon = lon
                self.station_alt = alt
                self._update_distances()

        if metadata_changed:
            self._maybe_add_history_entry()
            self._update_display_fonts()

    def _update_ber_graph(self, ber_value):
        self.ber_history.append(ber_value)
        if len(self.ber_history) > self.ber_max_points:
            self.ber_history = self.ber_history[-self.ber_max_points :]

        x = list(range(len(self.ber_history)))
        self.ber_curve.setData(x, self.ber_history)

        if len(self.ber_history) < self.ber_max_points:
            self.ber_plot.setXRange(0, self.ber_max_points - 1)
        else:
            start = len(self.ber_history) - self.ber_max_points
            end = len(self.ber_history) - 1
            self.ber_plot.setXRange(start, end)

        y_max = max(self.ber_history) if self.ber_history else 0.0
        upper = max(10.0, y_max * 1.1 if y_max > 0 else 10.0)
        self.ber_plot.setYRange(0, upper)

    # ================ Now-Playing History ================
    # Original: NRSC5Gui._maybe_add_history_entry()
    
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

        while self.history_table.rowCount() > self.max_history_rows:
            self.history_table.removeRow(0)

        self.last_title, self.last_artist, self.last_album = key

    # ================ Distance Calculations ================
    # Original: NRSC5Gui._update_user_location(), _update_distances()
    # Now using utils functions
    
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
            if self.units_combo.currentIndex() == 0:  # metric
                self.user_alt = alt_val
            else:  # imperial: feet
                self.user_alt = alt_val * 0.3048
        else:
            self.user_alt = None

        self._update_distances()

    def _units_changed(self, index):
        self._update_user_location()

    def _update_distances(self):
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

        use_metric = self.units_combo.currentIndex() == 0

        # Horizontal distance and bearing
        horizontal_m, bearing_deg = haversine_distance_and_bearing(
            self.user_lat, self.user_lon,
            self.station_lat, self.station_lon
        )

        if horizontal_m == 0:
            relpos = "0 (here)"
        else:
            cardinal = bearing_to_cardinal(bearing_deg)
            dist_str = format_distance(horizontal_m, use_metric)
            relpos = f"{dist_str} {cardinal} ({bearing_deg:.0f}°)"

        # Vertical difference
        dv = self.station_alt - self.user_alt
        vert = format_altitude_difference(dv, use_metric)

        self.relpos_text = relpos
        self.vert_text = vert
        self._update_info_summary_line()

    # ================ Streaming Controls ================
    # Original: NRSC5Gui.toggle_radio(), start_stream(), stop_stream()
    # Now using streaming.py functions
    
    def toggle_radio(self):
        if not self.radio_btn.isEnabled():
            return

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

    def _get_current_program_number(self):
        idx = self.prog_combo.currentIndex()
        if idx < 0:
            return 0
        text = self.prog_combo.itemText(idx).strip()
        try:
            num_str = text.split("-")[0].strip()
            return int(num_str)
        except Exception:
            try:
                return int(text)
            except ValueError:
                return 0

    def _select_program_by_number(self, prog_str):
        for i in range(self.prog_combo.count()):
            text = self.prog_combo.itemText(i).strip()
            num_str = text.split("-")[0].strip()
            if num_str == prog_str:
                self.prog_combo.setCurrentIndex(i)
                return

    def _validate_start_inputs(self):
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

        # Start ffplay (audio player)
        self.proc_play = start_ffplay_process(
            error_callback=lambda e: self._on_process_error("ffplay", e),
            finished_callback=lambda code, status: self._on_process_finished(
                "ffplay", code, status
            )
        )
        if not self.proc_play:
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to start ffplay."
            )
            return

        # Start nrsc5 (receiver)
        self.proc_nrsc5 = start_nrsc5_process(
            freq, prog, host, port,
            error_callback=lambda e: self._on_process_error("nrsc5", e),
            stdout_callback=self._distribute_audio_data,
            stderr_callback=self._parse_metadata_output,
            finished_callback=self._on_nrsc5_finished
        )

        if self.proc_nrsc5:
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
        self.stop_recording()

        kill_process(self.proc_nrsc5)
        kill_process(self.proc_play)

        self.proc_nrsc5 = None
        self.proc_play = None

        self.radio_running = False
        self.radio_btn.setText("Start Radio")
        self._update_ui_state(running=False)

    # ================ Recording Controls ================
    # Original: NRSC5Gui.toggle_recording(), start_recording(), stop_recording()
    # Now using streaming.py functions
    
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
        
        self.current_record_file = make_recording_filename(
            freq, prog,
            self.artist_label.text(),
            self.title_label.text(),
            self.record_dir_edit.text()
        )

        self.proc_rec = start_ffmpeg_recorder(
            self.current_record_file,
            error_callback=lambda e: self._on_process_error("ffmpeg", e),
            finished_callback=lambda code, status: self._on_process_finished(
                "ffmpeg", code, status
            )
        )

        if self.proc_rec:
            self.recording = True
            self.record_btn.setText("Stop Recording")
            self.status_text = "Status: Listening & Recording"
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

        stop_ffmpeg_recorder(self.proc_rec)

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

    # ================ UI Helpers ================
    # Original: NRSC5Gui._update_ui_state(), _update_info_summary_line(), etc.
    
    def _update_ui_state(self, running):
        self.radio_btn.setEnabled(True)
        self.record_btn.setEnabled(running)

        self.freq_edit.setEnabled(not running)
        self.host_edit.setEnabled(not running)
        self.prog_combo.setEnabled(not running)
        self.port_edit.setEnabled(not running)
        self.record_dir_edit.setEnabled(not running)
        self.browse_dir_btn.setEnabled(not running)

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

        if self.record_duration_text:
            parts.append(f"Rec: {self.record_duration_text}")

        self.info_summary_label.setText(" | ".join(parts))

    def _update_display_fonts(self):
        available_height = max(self.display_tab.height(), 1)
        available_width = max(self.display_tab.width(), 1)
        height_scale = available_height / 600.0
        width_scale = available_width / 800.0
        scale = min(max(min(height_scale, width_scale), 0.7), 3.0)

        title_font = self.display_title_label.font()
        title_font.setPointSize(int(self.display_title_base_size * scale))
        title_font = fit_font_to_label(
            self.display_title_label, title_font,
            max_height_ratio=0.42,
            tab_height=self.display_tab.height()
        )
        self.display_title_label.setFont(title_font)

        artist_font = self.display_artist_label.font()
        artist_font.setPointSize(int(self.display_artist_base_size * scale))
        artist_font = fit_font_to_label(
            self.display_artist_label, artist_font,
            max_height_ratio=0.24,
            tab_height=self.display_tab.height()
        )
        self.display_artist_label.setFont(artist_font)

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

    def resizeEvent(self, event):
        self._update_display_fonts()
        super().resizeEvent(event)

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

        sizes = self.info_splitter.sizes()
        total = sum(sizes) if sizes else 1
        self.info_splitter.setSizes([int(total * 0.7), int(total * 0.3)])

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.display_tab:
            self.meta_widget.setVisible(False)
        else:
            self.meta_widget.setVisible(True)

    def closeEvent(self, event):
        self.stopping_radio = True
        self._save_settings()
        self.stop_stream()
        event.accept()
