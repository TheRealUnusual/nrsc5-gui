"""
Audio streaming and recording process management.
Original file: nrsc5_gui_qt.py (streaming/recording methods)
"""

from PyQt5 import QtCore
from lib.nrsc5 import NRSC5, EventType, Mode
import time
from lib.nrsc5 import NRSC5, NRSC5Error, ctypes  # make sure ctypes is imported too

class ExtendedNRSC5(NRSC5):
    """Our own version with the missing set_program method added."""
    def set_program(self, program):
        """Change the active audio program (0-3) at runtime."""
        self._check_session()
        result = self.libnrsc5.nrsc5_set_program(self.radio, ctypes.c_uint(program))
        if result != 0:
            raise NRSC5Error(f"nrsc5_set_program failed with code {result}")

class NRSC5Wrapper(QtCore.QObject):
    readyReadStandardOutput = QtCore.pyqtSignal()
    readyReadStandardError = QtCore.pyqtSignal()
    errorOccurred = QtCore.pyqtSignal(QtCore.QProcess.ProcessError)
    finished = QtCore.pyqtSignal(int, QtCore.QProcess.ExitStatus)

    def __init__(self):
        super().__init__()
        self.stdout_buffer = bytearray()
        self.stderr_buffer = bytearray()
        self.nrsc5 = None
        self.running = False
        self.program = 0

    def start(self, freq, prog, host, port):
        try:
            self.program = int(prog)
            self.nrsc5 = ExtendedNRSC5(self._api_callback)
            if host:
                p = int(port) if port else 1234
                self.nrsc5.open_rtltcp(host, p)
            else:
                self.nrsc5.open(0)  # Assume device index 0; customize if needed
            self.nrsc5.set_frequency(float(freq) * 1e6)  # Convert MHz to Hz
            self.nrsc5.set_mode(Mode.FM)  # Assume FM; add config if AM needed
            self.nrsc5.start()
            self.running = True
            self._add_stderr("NRSC5 started via API.")
            return True
        except Exception as e:
            print(f"Error starting NRSC5: {e}")
            self.errorOccurred.emit(QtCore.QProcess.FailedToStart)
            return False

    def state(self):
        return QtCore.QProcess.Running if self.running else QtCore.QProcess.NotRunning

    def waitForStarted(self, ms=2000):
        return self.running  # Starts synchronously

    def waitForFinished(self, ms=2000):
        return True  # Stops synchronously

    def readAllStandardOutput(self):
        data = QtCore.QByteArray(self.stdout_buffer)
        self.stdout_buffer.clear()
        return data

    def readAllStandardError(self):
        data = QtCore.QByteArray(self.stderr_buffer)
        self.stderr_buffer.clear()
        return data

    def terminate(self):
        if self.nrsc5:
            self.nrsc5.stop()
            time.sleep(0.1)  # Minimal wait for cleanup
            self.nrsc5.close()
        self.running = False
        self.finished.emit(0, QtCore.QProcess.NormalExit)

    def kill(self):
        self.terminate()  # Same as terminate for sync API

    def _add_stdout(self, data):
        self.stdout_buffer.extend(data)
        self.readyReadStandardOutput.emit()

    def _add_stderr(self, text):
        self.stderr_buffer.extend((text + "\n").encode())
        self.readyReadStandardError.emit()

    def set_program(self, prog):
       """Live program change via API (no restart). Returns True on success."""
       if not self.nrsc5 or not self.running:
           return False
       try:
           self.program = int(prog)
           self.nrsc5.set_program(self.program)
           self._add_stderr(f"Switched to program {self.program}")
           return True
       except Exception as e:
           self._add_stderr(f"Program switch failed: {e}")
           return False

    def _api_callback(self, evt_type, evt):

            if evt_type == EventType.AUDIO:
                if evt.program == self.program:
                    self._add_stdout(evt.data)
            elif evt_type == EventType.ID3:
                if evt.program == self.program:
                    if evt.title:
                        self._add_stderr(f"Title: {evt.title}")
                    if evt.artist:
                        self._add_stderr(f"Artist: {evt.artist}")
                    if evt.album:
                        self._add_stderr(f"Album: {evt.album}")
            elif evt_type == EventType.BER:
                self._add_stderr(f"BER: {evt.cber:.6f}")
            elif evt_type == EventType.STATION_LOCATION:
                self._add_stderr(f"Station location: {evt.latitude}, {evt.longitude}, {evt.altitude}m")
            elif evt_type == EventType.SYNC:
                self._add_stderr("Got sync!")
            elif evt_type == EventType.LOST_SYNC:
                self._add_stderr("Lost sync!")
            elif evt_type == EventType.LOST_DEVICE:
                self._add_stderr("Lost device!")
                self.errorOccurred.emit(QtCore.QProcess.Crashed)
                self.finished.emit(1, QtCore.QProcess.CrashExit)
                self.running = False

# ---------- Process management ----------
def kill_process(proc):
    if proc:
        if isinstance(proc, NRSC5Wrapper):
            if proc.state() != QtCore.QProcess.NotRunning:
                proc.terminate()
                time.sleep(1)  # Mimic waitForFinished(1000)
                if proc.state() != QtCore.QProcess.NotRunning:
                    proc.kill()
        elif proc.state() != QtCore.QProcess.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(1000):
                proc.kill()


# ---------- Audio data distribution ----------
def distribute_audio_data(proc_nrsc5, proc_play, proc_rec, is_recording):
    if not proc_nrsc5:
        return

    if isinstance(proc_nrsc5, NRSC5Wrapper):
        data = proc_nrsc5.readAllStandardOutput().data()  # Get bytes
    else:
        data = proc_nrsc5.readAllStandardOutput()

    if not data:
        return

    if proc_play and proc_play.state() == QtCore.QProcess.Running:
        proc_play.write(data)

    if (
        is_recording
        and proc_rec
        and proc_rec.state() == QtCore.QProcess.Running
    ):
        proc_rec.write(data)


# ---------- Stream start/stop ----------
def start_nrsc5_process(freq, prog, host, port, error_callback, stdout_callback, stderr_callback, finished_callback):
    proc = NRSC5Wrapper()
    proc.errorOccurred.connect(error_callback)
    proc.readyReadStandardOutput.connect(stdout_callback)
    proc.readyReadStandardError.connect(stderr_callback)
    proc.finished.connect(finished_callback)
    if proc.start(freq, prog, host, port):
        return proc
    else:
        return None


def start_ffplay_process(error_callback, finished_callback):
    """
    Start the ffplay audio player process.
    
    Original: NRSC5Gui.start_stream() (partial - ffplay setup)
    Returns: QProcess instance or None on failure
    """
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
    
    proc = QtCore.QProcess()
    proc.errorOccurred.connect(error_callback)
    proc.finished.connect(finished_callback)
    proc.start("ffplay", play_args)
    
    if proc.waitForStarted(2000):
        return proc
    else:
        kill_process(proc)
        return None


def start_ffmpeg_recorder(output_file, error_callback, finished_callback):
    """
    Start the ffmpeg recording process.
    
    Original: NRSC5Gui.start_recording() (partial)
    Returns: QProcess instance or None on failure
    """
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
        output_file,
    ]

    proc = QtCore.QProcess()
    proc.errorOccurred.connect(error_callback)
    proc.finished.connect(finished_callback)
    proc.start("ffmpeg", ffmpeg_args)

    if proc.waitForStarted(1000):
        return proc
    else:
        kill_process(proc)
        return None


def stop_ffmpeg_recorder(proc_rec):
    """
    Gracefully stop the ffmpeg recording process.
    
    Original: NRSC5Gui.stop_recording() (partial)
    """
    if proc_rec and proc_rec.state() == QtCore.QProcess.Running:
        proc_rec.closeWriteChannel()
        proc_rec.waitForFinished(2000)
        if proc_rec.state() == QtCore.QProcess.Running:
            proc_rec.terminate()
