"""Session-scoped, single-contact Linux uinput touchscreen; never chmod devices."""
import ctypes
import fcntl
import os
import struct
import threading
from carplay_proto.touch import touch_layout, decode_touch


class UInput:
    def __init__(self, width, height, path='/dev/uinput'):
        self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.down = False
        try:
            # Linux uinput.h: UI_SET_EVBIT/KEYBIT/ABSBIT/PROPBIT.
            for ev in (1, 3):
                fcntl.ioctl(self.fd, 0x40045564, ev)
            fcntl.ioctl(self.fd, 0x40045565, 330)  # BTN_TOUCH
            fcntl.ioctl(self.fd, 0x4004556e, 1)    # INPUT_PROP_DIRECT
            axes = {0: width-1, 1: height-1, 47: 0, 53: width-1,
                    54: height-1, 57: 65535}
            for axis in axes:
                fcntl.ioctl(self.fd, 0x40045567, axis)
            maxima, minima, fuzz, flat = ([0] * 64 for _ in range(4))
            for axis, maximum in axes.items():
                maxima[axis] = maximum
            descriptor = struct.pack('80sHHHHI', b'Sailconnect remote touchscreen',
                                     6, 0x1, 0x1, 1, 0)
            descriptor += struct.pack('256i', *(maxima + minima + fuzz + flat))
            self._write(descriptor)
            fcntl.ioctl(self.fd, 0x5501)  # UI_DEV_CREATE
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def _write(self, data):
        if os.write(self.fd, data) != len(data):
            raise OSError('short uinput write')

    def event(self, kind, code, value):
        # Native struct timeval: long is 32 bits on armv7, 64 on aarch64.
        self._write(struct.pack('@llHHi', 0, 0, kind, code, value))

    def send(self, down, x, y):
        self.event(3, 47, 0)
        if down and not self.down:
            self.event(3, 57, 1)
        if down:
            for code, value in ((0, x), (1, y), (53, x), (54, y)):
                self.event(3, code, value)
        elif self.down:
            self.event(3, 57, -1)
        self.event(1, 330, int(down))
        self.event(0, 0, 0)
        self.down = down

    def close(self):
        if self.fd is None:
            return
        try:
            if self.down:
                self.send(False, 0, 0)
        finally:
            try:
                fcntl.ioctl(self.fd, 0x5502)
            finally:
                os.close(self.fd)
                self.fd = None


class PhoneInput:
    def __init__(self, devices, display_uuid, viewport, permitted, unlocked,
                 backend=UInput):
        self.layouts = {str(d['uuid']): touch_layout(bytes(d['hidDescriptor']))
                        for d in devices if d.get('displayUUID') == display_uuid
                        and 'hidDescriptor' in d}
        self.viewport, self.permitted, self.unlocked = viewport, permitted, unlocked
        self.backend_factory = backend
        self.backend = None
        self.lock = threading.RLock()
        self.closed = False
        self.active = False
        self.blocked = False
        self.last = (0, 0)

    def release(self):
        with self.lock:
            if self.active:
                self.blocked = True
            self.active = False
            if self.backend is not None:
                try:
                    self.backend.close()
                finally:
                    self.backend = None

    def command(self, value):
        if value.get('type') != 'hidSendReport':
            return
        with self.lock:
            if self.closed:
                return
            layout = self.layouts.get(str(value.get('uuid')))
            if not layout:
                return
            down, x, y = decode_touch(layout, bytes(value['hidReport']),
                                      self.viewport.width, self.viewport.height)
            if not self.permitted() or not self.unlocked():
                self.blocked = bool(down)
                self.release()
                return
            if self.blocked:
                self.blocked = bool(down)
                return
            point = self.viewport.map(x, y, clamp=self.active)
            if not self.active and (not down or point is None):
                return
            try:
                if self.backend is None:
                    self.backend = self.backend_factory(self.viewport.nw, self.viewport.nh)
                self.last = point or self.last
                self.backend.send(down, *self.last)
                self.active = down
            except BaseException:
                self.release()
                raise

    def close(self):
        with self.lock:
            self.closed = True
            self.release()
