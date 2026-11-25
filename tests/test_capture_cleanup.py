import os
import logging
import threading
from types import SimpleNamespace
import pytest
from sailconnect.display import CaptureLog, PhoneDisplay
from sailconnect.session import Session


def prepared(tmp_path):
    directory = tmp_path / 'capture'
    directory.mkdir()
    pipeline = PhoneDisplay(1280, 720, 30)
    pipeline.directory = str(directory)
    pipeline.fifo = str(directory / 'video.h264')
    os.mkfifo(pipeline.fifo, 0o600)
    info = os.lstat(pipeline.fifo)
    pipeline.fifo_identity = info.st_dev, info.st_ino
    return pipeline, directory


def test_cleanup_removes_only_owned_fifo_and_empty_directory(tmp_path):
    pipeline, directory = prepared(tmp_path)
    pipeline.close()
    assert not directory.exists()


def test_cleanup_preserves_replaced_file_and_directory(tmp_path):
    pipeline, directory = prepared(tmp_path)
    os.unlink(pipeline.fifo)
    with open(pipeline.fifo, 'w') as stream:
        stream.write('unexpected user content')
    pipeline.close()
    assert directory.joinpath('video.h264').read_text() == 'unexpected user content'


def test_capture_metadata_detects_native_geometry_and_survives_fps_updates():
    pipeline = PhoneDisplay(1280, 720, 30)
    session = Session({}, lambda _: None, lambda: True)
    log = CaptureLog(session.update_metrics, pipeline.set_geometry)
    log.emit(logging.makeLogRecord(dict(msg='capture native geometry: width=1080 height=2160')))
    log.emit(logging.makeLogRecord(dict(msg='capture stats: fps=29.5 encode_ms=8.2')))
    assert pipeline.geometry() == (1080, 2160)
    assert session.metrics == dict(native_width=1080, native_height=2160, fps=29.5, encode_ms=8.2)


def test_waiting_for_capture_geometry_can_be_cancelled():
    pipeline = PhoneDisplay(1280, 720, 30)
    pipeline.cancel = threading.Event()
    pipeline.cancel.set()
    pipeline.capture = SimpleNamespace(poll=lambda: None)
    with pytest.raises(InterruptedError):
        pipeline.geometry()
