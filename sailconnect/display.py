"""Capture the existing lipstick display without starting a compositor or UI."""
import os
import pwd
import signal
import subprocess
import tempfile
import logging
import sys
import re
import errno
import threading
import time
from carplay_proto.display import DisplayPipeline as LegacyPipeline
from carplay_proto.runtime_logging import ProcessOutput


class CaptureLog(logging.StreamHandler):
    component = 'phone-capture'

    def __init__(self, metrics=None, geometry=None):
        super().__init__(sys.stdout)
        self.metrics = metrics
        self.geometry = geometry

    def is_enabled(self):
        return True

    def emit(self, record):
        super().emit(record)
        match = re.search(r'capture stats: fps=([0-9.]+) encode_ms=([0-9.]+)', record.getMessage())
        if match and self.metrics:
            self.metrics(dict(fps=float(match.group(1)), encode_ms=float(match.group(2))))
        native = re.search(r'capture native geometry: width=(\d+) height=(\d+)', record.getMessage())
        if native:
            width, height = int(native.group(1)), int(native.group(2))
            if self.geometry:
                self.geometry(width, height)
            if self.metrics:
                self.metrics(dict(native_width=width, native_height=height))


class PhoneDisplay(LegacyPipeline):
    def __init__(self, width, height, fps, rotation=0, bitrate=4000000, native_width=0, native_height=0, metrics=None):
        super().__init__(width, height, fps)
        self.rotation, self.bitrate = rotation, bitrate
        self.native_width, self.native_height = native_width, native_height
        self.metrics = metrics
        self.directory = None
        self.geometry_ready = threading.Event()

    def set_geometry(self, width, height):
        if not (240 <= width <= 7680 and 240 <= height <= 7680):
            return
        self.native_width, self.native_height = width, height
        self.geometry_ready.set()

    def geometry(self):
        deadline = time.monotonic() + 3
        while not self.geometry_ready.wait(.1):
            self.check_health()
            if time.monotonic() >= deadline:
                raise RuntimeError('capture did not report native geometry')
        return self.native_width, self.native_height

    def start(self, stop=None):
        self.cancel = stop
        if stop is not None and stop.is_set():
            raise InterruptedError('session stopped')
        account = pwd.getpwnam('defaultuser')
        self.directory = tempfile.mkdtemp(prefix='capture-', dir='/run/sailconnect')
        os.chown(self.directory, account.pw_uid, account.pw_gid)
        self.fifo = self.directory + '/video.h264'
        os.mkfifo(self.fifo, 0o600)
        info = os.lstat(self.fifo)
        self.fifo_identity = (info.st_dev, info.st_ino)
        os.chown(self.fifo, account.pw_uid, account.pw_gid)
        self.fd = os.open(self.fifo, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        command = ('exec env XDG_RUNTIME_DIR=/run/user/{uid} '
                   'WAYLAND_DISPLAY=/run/display/wayland-0 '
                   '/opt/sailconnect/carlife-capture --input screen --out {fifo} '
                   '--width {w} --height {h} --fps {fps} --bitrate {bitrate} '
                   '--rotation {rot} --native-width {nw} --native-height {nh}').format(uid=account.pw_uid, fifo=self.fifo,
                    w=self.width, h=self.height, fps=self.fps,
                    bitrate=self.bitrate, rot=self.rotation, nw=self.native_width, nh=self.native_height)
        self.capture = subprocess.Popen(['su', 'defaultuser', '-s', '/bin/sh',
                    '--session-command', command], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append(self.capture)
        self.logs.append(ProcessOutput('phone-capture', self.capture.stdout, self.capture.pid, CaptureLog(self.metrics, self.set_geometry)))
        return self

    def check_health(self):
        if self.cancel is not None and self.cancel.is_set():
            raise InterruptedError('session stopped')
        if self.capture.poll() is not None:
            raise RuntimeError('phone capture exited')

    def close(self):
        try:
            super().close()
        finally:
            if self.directory is not None:
                try:
                    os.rmdir(self.directory)
                except OSError as error:
                    if error.errno != errno.ENOTEMPTY:
                        raise
                    print('Preserving modified capture directory: {}'.format(self.directory), flush=True)
                self.directory = None
