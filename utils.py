"""
Utility functions and parsing helpers.
Original file: nrsc5_gui_qt.py (helper methods and standalone logic)
"""

import re
import math
import datetime
import os
from PyQt5 import QtCore, QtGui


# ---------- Filename sanitization ----------
def sanitize_filename(text):
    """Remove invalid filesystem characters from text."""
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()


def make_recording_filename(freq, prog, artist_text, title_text, record_dir):
    """
    Generate a timestamped filename for recording.
    Uses artist/title metadata if available, otherwise falls back to freq/prog.
    
    Original: NRSC5Gui._make_filename()
    """
    has_meta = (artist_text not in ["—", ""]) and (title_text not in ["—", ""])

    if has_meta:
        safe_artist = sanitize_filename(artist_text)
        safe_title = sanitize_filename(title_text)
        ts = datetime.datetime.now().strftime("%H%M%S")
        filename = f"{safe_title} - {safe_artist}_{ts}.mp3"
    else:
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_freq = freq.replace(".", "_")
        filename = f"Radio_{safe_freq}_P{prog}_{ts}.mp3"

    dir_path = record_dir.strip()
    if not dir_path or not os.path.isdir(dir_path):
        dir_path = os.path.expanduser("~/Desktop")
    return os.path.join(dir_path, filename)


# ---------- Distance and bearing calculations ----------
def haversine_distance_and_bearing(user_lat, user_lon, station_lat, station_lon):
    """
    Calculate horizontal distance (meters) and bearing (degrees) between two points.
    
    Original: NRSC5Gui._update_distances() (partial)
    Returns: (distance_m, bearing_deg)
    """
    R = 6371000.0  # Earth radius in meters

    lat1 = math.radians(user_lat)
    lon1 = math.radians(user_lon)
    lat2 = math.radians(station_lat)
    lon2 = math.radians(station_lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    lat_mean = 0.5 * (lat1 + lat2)

    # Local coordinates: x east–west (positive east), z north–south (positive north)
    dx = R * math.cos(lat_mean) * dlon
    dz = R * dlat

    horizontal_m = math.hypot(dx, dz)
    
    if horizontal_m == 0:
        bearing_deg = 0.0
    else:
        bearing_rad = math.atan2(dx, dz)
        bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0

    return horizontal_m, bearing_deg


def bearing_to_cardinal(bearing_deg):
    """
    Convert bearing in degrees to cardinal direction string.
    
    Original: NRSC5Gui._bearing_to_cardinal()
    """
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


def format_distance(distance_m, use_metric):
    """
    Format distance in appropriate units.
    
    Original: NRSC5Gui._update_distances() (partial)
    """
    if use_metric:
        dist = distance_m / 1000.0
        unit = "km"
    else:
        dist = distance_m / 1609.344
        unit = "mi"
    return f"{dist:,.2f} {unit}"


def format_altitude_difference(alt_diff_m, use_metric):
    """
    Format vertical altitude difference with direction.
    
    Original: NRSC5Gui._update_distances() (partial)
    """
    if alt_diff_m == 0:
        return "0"
    
    direction = "above" if alt_diff_m > 0 else "below"
    dist_m = abs(alt_diff_m)
    
    if use_metric:
        dist_v = dist_m
        vunit = "m"
    else:
        dist_v = dist_m * 3.28084
        vunit = "ft"
    
    return f"{dist_v:,.1f} {vunit} {direction}"


# ---------- Font fitting ----------
def fit_font_to_label(label, font, max_height_ratio, tab_height):
    """
    Adjust font size to fit label dimensions with word wrap.
    
    Original: NRSC5Gui._fit_font_to_label()
    """
    metrics = QtGui.QFontMetrics(font)
    text = label.text() or "—"
    padding = 16
    max_width = max(label.width() - padding, 1)
    max_height = max(int(tab_height * max_height_ratio), 1)

    # Shrink if too tall
    while (
        (metrics.boundingRect(0, 0, max_width, 10_000, QtCore.Qt.TextWordWrap, text).height() > max_height)
        and font.pointSize() > 5
    ):
        font.setPointSize(font.pointSize() - 1)
        metrics = QtGui.QFontMetrics(font)

    # Grow if too small
    while (
        metrics.boundingRect(0, 0, max_width, 10_000, QtCore.Qt.TextWordWrap, text).height() < max_height * 0.85
        and font.pointSize() < 120
    ):
        font.setPointSize(font.pointSize() + 1)
        metrics = QtGui.QFontMetrics(font)

    # Final check
    if (
        metrics.boundingRect(0, 0, max_width, 10_000, QtCore.Qt.TextWordWrap, text).height()
        > max_height
    ):
        font.setPointSize(max(font.pointSize() - 1, 12))

    return font


# ---------- Regex patterns (module-level for reuse) ----------
RE_TITLE = re.compile(r"Title:\s*(.+)", re.IGNORECASE)
RE_ARTIST = re.compile(r"Artist:\s*(.+)", re.IGNORECASE)
RE_ALBUM = re.compile(r"Album:\s*(.+)", re.IGNORECASE)
RE_BER = re.compile(r"BER:\s*([0-9]*\.?[0-9eE+-]+)")
RE_STATION_LOC = re.compile(
    r"Station location:\s*([0-9.+-]+),\s*([0-9.+-]+),\s*([0-9.+-]+)m",
    re.IGNORECASE,
)


def parse_metadata_line(line):
    """
    Parse a single NRSC5 stderr line for metadata.
    
    Original: NRSC5Gui._parse_metadata_output() (inline parsing)
    Returns: dict with keys 'title', 'artist', 'album', 'ber', 'station_loc' (or None)
    """
    result = {}
    
    m = RE_TITLE.search(line)
    if m:
        result['title'] = m.group(1).strip()
    
    m = RE_ARTIST.search(line)
    if m:
        result['artist'] = m.group(1).strip()
    
    m = RE_ALBUM.search(line)
    if m:
        result['album'] = m.group(1).strip()
    
    m = RE_BER.search(line)
    if m:
        try:
            ber_val = float(m.group(1))
            result['ber'] = ber_val * 100.0  # convert to percent
        except ValueError:
            pass
    
    m = RE_STATION_LOC.search(line)
    if m:
        try:
            lat = float(m.group(1))
            lon = float(m.group(2))
            alt = float(m.group(3))
            result['station_loc'] = (lat, lon, alt)
        except ValueError:
            pass
    
    return result if result else None
