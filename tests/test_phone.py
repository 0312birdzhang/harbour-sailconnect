import threading
from types import SimpleNamespace
import pytest
from sailconnect.geometry import Viewport
from sailconnect.input import PhoneInput
from sailconnect.service import validate


@pytest.mark.parametrize('rotation,top_left,bottom_right', [
    (0, (0, 0), (1079, 1919)),
    (90, (0, 1919), (1079, 0)),
    (180, (1079, 1919), (0, 0)),
    (270, (1079, 0), (0, 1919)),
])
def test_letterbox_inverse_reaches_native_edges(rotation, top_left, bottom_right):
    v = Viewport(1920, 720, 1080, 1920, rotation)
    assert v.map(v.bx, v.by) == top_left
    assert v.map(v.bx+v.bw-1, v.by+v.bh-1) == bottom_right
    assert v.map(-1, -1) is None
    assert v.map(-1, -1, clamp=True) == top_left


class Device:
    def __init__(self, width, height):
        self.events = []
        self.closed = False
    def send(self, down, x, y):
        self.events.append((down, x, y))
    def close(self):
        self.closed = True


def phone():
    consent = [False]
    unlocked = [True]
    devices = []
    def factory(w, h):
        d = Device(w, h)
        devices.append(d)
        return d
    p = PhoneInput([], 'screen', Viewport(1920, 720, 1080, 1920),
                   lambda: consent[0], lambda: unlocked[0], factory)
    p.layouts = {'hid': {0: {'down': (0, 1, 1), 'x': (8, 16, 1919), 'y': (24, 16, 719)}}}
    return p, consent, unlocked, devices


def report(p, down, x=960, y=360):
    p.command(dict(type='hidSendReport', uuid='hid',
                   hidReport=bytes([int(down)])+x.to_bytes(2, 'little')+y.to_bytes(2, 'little')))


def test_readonly_never_creates_device_and_no_midgesture_enable():
    p, consent, _, devices = phone()
    report(p, True)
    assert not devices
    consent[0] = True
    report(p, True)
    assert not devices
    report(p, False)
    report(p, True)
    assert len(devices) == 1
    p.close()
    assert devices[0].closed
    report(p, True)
    assert len(devices) == 1


def test_installing_detected_geometry_keeps_a_pre_video_press_blocked():
    p, consent, _, devices = phone()
    p.viewport = SimpleNamespace(width=1920, height=720)
    report(p, True)
    p.viewport = Viewport(1920, 720, 1080, 1920)
    consent[0] = True
    report(p, True)
    assert not devices
    report(p, False)
    report(p, True)
    assert len(devices) == 1
    p.close()


def test_blackbar_start_ignored_but_drag_can_reach_edge():
    p, consent, _, devices = phone()
    consent[0] = True
    report(p, True, x=0)
    assert not devices
    report(p, False)
    report(p, True)
    report(p, True, x=0)
    assert devices[0].events[-1][1] == 0
    report(p, False, x=0)
    assert devices[0].events[-1][0] is False
    p.close()


def test_lock_destroys_device_and_requires_lift():
    p, consent, unlocked, devices = phone()
    consent[0] = True
    report(p, True)
    unlocked[0] = False
    report(p, True)
    assert devices[0].closed
    unlocked[0] = True
    report(p, True)
    assert len(devices) == 1
    report(p, False)
    report(p, True)
    assert len(devices) == 2
    p.close()


@pytest.mark.parametrize('host', ['8.8.8.8', '127.0.0.1', '224.0.0.1', '0.0.0.0', '::1', '::'])
def test_reject_nonlan_receiver(host):
    with pytest.raises(ValueError):
        validate(host, 7000, 'wlan0', 1080, 1920, 0, 0, 30, 4000000)


def test_validate_lan_and_reject_shell_interface():
    assert validate('192.168.1.2', 7000, 'wlan0', 1080, 1920, 0, 0, 30, 4000000)['fps'] == 30
    with pytest.raises(ValueError):
        validate('192.168.1.2', 7000, 'wlan0;id', 1080, 1920, 0, 0, 30, 4000000)


def test_automatic_routing_and_geometry_are_valid_but_partial_geometry_is_not():
    options = validate('192.168.1.2', 17000, '', 0, 0, 0, 3, 30, 4000000)
    assert options['interface'] == '' and options['native_width'] == options['native_height'] == 0
    for width, height in [(0, 2160), (1080, 0)]:
        with pytest.raises(ValueError):
            validate('192.168.1.2', 17000, '', width, height, 0, 3, 30, 4000000)
