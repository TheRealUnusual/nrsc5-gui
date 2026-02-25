# NRSC5 GUI

A graphical interface for **nrsc5** that allows tuning, listening, and recording HD Radio broadcasts.

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
## Screenshots
![Screenshots](https://github.com/TheRealUnusual/nrsc5-gui/blob/main/docs/images/collage.png)

---

## Requirements

- [Python 3](https://www.python.org/)
- [PyQt5](https://pypi.org/project/PyQt5/)
- [pyqtgraph](https://pypi.org/project/pyqtgraph/)
- [nrsc5](https://github.com/theori-io/nrsc5)
- [ffmpeg](https://ffmpeg.org/)
- [ffplay](https://ffmpeg.org/)

---

## Installation

1. Clone this repository.

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Ensure nrsc5, ffmpeg, and ffplay are installed and available in your PATH.

5. Set up an RTL-SDR via rtl_tcp.

## Usage

Run the GUI with:

```bash
python3 main.py
```

Steps:

1. Enter the Frequency (MHz) of the station.

2. Select the Program number (0–3).

3. Enter the rtl_tcp host and port.

4. Click Start Radio to begin streaming.

### Presets

- Add a preset with the current frequency and program number.

- Tune to a preset by selecting it and clicking Tune to selected.

- Reorder, import, or export presets using the buttons in the Presets tab.

### Configuration

- rtl_tcp IP address and port

- Recording directory: Select where recorded files are saved.

- Units: Metric or Imperial for distance and altitude calculations.

- User location: Latitude, longitude, and altitude for station distance calculations.

## License

This project is licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later). See the [LICENSE](LICENSE) file for details.
