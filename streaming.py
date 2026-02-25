"""
Audio streaming and recording process management.
Original file: nrsc5_gui_qt.py (streaming/recording methods)
"""

from PyQt5 import QtCore


# ---------- Process management ----------
def kill_process(proc):
    """
    Terminate a QProcess gracefully, then forcefully if needed.
    
    Original: NRSC5Gui._kill_process()
    """
    if proc and proc.state() != QtCore.QProcess.NotRunning:
        proc.terminate()
        if not proc.waitForFinished(1000):
            proc.kill()


# ---------- Audio data distribution ----------
def distribute_audio_data(proc_nrsc5, proc_play, proc_rec, is_recording):
    """
    Read raw audio bytes from nrsc5 and send to ffplay and/or ffmpeg.
    
    Original: NRSC5Gui._distribute_audio_data()
    """
    if not proc_nrsc5:
        return

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
    """
    Start the nrsc5 receiver process.
    
    Original: NRSC5Gui.start_stream() (partial - nrsc5 setup)
    Returns: QProcess instance or None on failure
    """
    nrsc_args = []
    if host:
        if port:
            host = f"{host}:{port}"
        nrsc_args += ["-H", host]
    nrsc_args += [freq, prog, "-o", "-"]

    proc = QtCore.QProcess()
    proc.setProcessChannelMode(QtCore.QProcess.SeparateChannels)
    proc.errorOccurred.connect(error_callback)
    proc.readyReadStandardOutput.connect(stdout_callback)
    proc.readyReadStandardError.connect(stderr_callback)
    proc.finished.connect(finished_callback)

    proc.start("nrsc5", nrsc_args)

    if proc.waitForStarted(2000):
        return proc
    else:
        kill_process(proc)
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
