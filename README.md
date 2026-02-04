# NRSC5 GUI — Listen & Record

A graphical interface for **nrsc5** that allows tuning, listening, and recording HD Radio broadcasts. Built with **PyQt5** and **pyqtgraph**, it provides real-time metadata display, BER visualization, and station distance calculations.

---

## Features

- Tune to HD Radio stations by frequency and program number
- Start/stop live radio streaming
- Record audio to files using `ffmpeg`
- Display "Now Playing" metadata (Title, Artist, Album)
- Maintain a history of recently played tracks
- Show Bit Error Rate (BER) graph in real time
- Display relative distance and bearing to the station
- Manage station presets (add, remove, reorder, import/export)
- Configurable recording directory, units (metric/imperial), and user location
- Real-time NRSC5 log with optional display

---

## Requirements

- Python 3
- [PyQt5](https://pypi.org/project/PyQt5/)
- [pyqtgraph](https://pypi.org/project/pyqtgraph/)
- [nrsc5](https://github.com/theori-io/nrsc5)
- [ffmpeg](https://ffmpeg.org/)
- [ffplay](https://ffmpeg.org/)

---

## Installation

1. Clone this repository or download `nrsc5_gui_qt.py`.
2. Install Python dependencies:

```bash
pip install PyQt5 pyqtgraph
```

3. Ensure nrsc5, ffmpeg, and ffplay are installed and available in your PATH.

4. Optionally, set up a remote RTL-SDR via rtl_tcp.

## Usage

Run the GUI with:

```bash
python3 nrsc5_gui_qt.py
```

Steps:

1. Enter the Frequency (MHz) of the station.

2. Select the Program number (0–3).

3. If using a remote RTL-SDR, enter the host and port.

4. Click Start Radio to begin streaming.

5. Click Start Recording to save audio to the configured directory.

6. Monitor metadata, BER, and history in the GUI.

### Presets

- Add a preset with the current frequency and program number.

- Tune to a preset by selecting it and clicking Tune to selected.

- Reorder, import, or export presets using the buttons in the Presets tab.

### Configuration

- Recording directory: Select where recorded files are saved.

- Units: Metric or Imperial for distance and altitude calculations.

- User location: Latitude, longitude, and altitude for station distance calculations.

## License

This project is provided under the MIT License. See LICENSE for details.

## Notes

- The BER graph updates in real time and expands the Y-axis if the error rate exceeds 10%.

- Metadata parsing supports song title, artist, album, and station location.

- The Display tab can override artist display for fun (e.g., Easter egg for specific artists).
