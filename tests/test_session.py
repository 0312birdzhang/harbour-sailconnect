"""Exercise the complete app session lifecycle with a simulated receiver."""
import plistlib
import threading
from types import SimpleNamespace
import pytest
from sailconnect import session as module


@pytest.mark.parametrize('disconnect', [False, True])
@pytest.mark.parametrize('control,locked', [(None, False), (False, False), (None, True)])
@pytest.mark.parametrize('automatic_geometry', [False, True])
@pytest.mark.parametrize('bluetooth', [False, True])
def test_negotiation_stream_and_disconnect_cleanup(monkeypatch, tmp_path, disconnect, control, locked, automatic_geometry, bluetooth):
    calls, closed = [], []
    observed_control = []
    links = []
    display = {'uuid': 'screen', 'widthPixels': 1280, 'heightPixels': 720, 'maxFPS': 30}
    class Client:
        def __init__(self):
            self.sock = SimpleNamespace(sock=self, close=lambda: closed.append('control'))
        def request(self, method, path, body=b'', headers=None):
            value = plistlib.loads(body) if body else {}
            calls.append((method, path, value))
            if path == '/info': result = {'displays': [display], 'hidDevices': []}
            elif method == 'SETUP' and 'streams' in value:
                result = {'streams': [{'type': 110, 'dataPort': 7100}]}
            else: result = {'eventPort': 7200}
            return 200, {}, plistlib.dumps(result)
        def shutdown(self, *_): pass
    client = Client()
    monkeypatch.setattr(module, 'connect', lambda *args: client)
    monkeypatch.setattr(module, 'identity', lambda: {'id': 'phone-id', 'private_key': 'aa'*32})
    monkeypatch.setattr(module, 'pair_setup', lambda *args: object())
    monkeypatch.setattr(module, 'pair_verify', lambda *args: SimpleNamespace(shared=b'k'*32))
    class Resource:
        def __init__(self, *args, **kwargs): self.port = 7300; self.stop = threading.Event()
        def close(self): closed.append(type(self).__name__)
    class Events(Resource):
        def __init__(self, *args):
            super().__init__()
            if bluetooth:
                assert args[-1]({'type': 'iAPSendMessage', 'params': {'data': b'network-iap'}}) == {'status': 0}
            if disconnect: self.stop.set()
    class Tunnel(Resource):
        def __init__(self, run_link, send):
            super().__init__()
            self.run_link, self.send = run_link, send
        def feed(self, data):
            assert data == b'network-iap'
            self.run_link('network-socket', self.stop)
            self.send(b'phone-iap-response')
    if bluetooth:
        from carplay_proto import iaptunnel
        monkeypatch.setattr(iaptunnel, 'IAPTunnel', Tunnel)
    class Capture(Resource):
        def __init__(self, *args, **kwargs):
            super().__init__()
            assert args == (1280, 720, 30, 90, 4000000,
                            0 if automatic_geometry else 1080, 0 if automatic_geometry else 1920)
        def start(self, stop): pass
        def request_keyframe(self): pass
        def geometry(self): return 1080, 1920
        def frames(self, seconds):
            assert not s.touch.permitted(), 'Remote input must wait for actual capture geometry'
            assert not s.ready
            yield b'config', [b'frame']
            yield b'config', [b'frame2']
    class Screen(Resource):
        def send(self, config, nals, timestamp):
            calls.append(('frame', config, nals))
            observed_control.append(s.touch.permitted() and s.unlocked())
    monkeypatch.setattr(module, 'TimingServer', Resource)
    monkeypatch.setattr(module, 'DemoEvents', Events)
    monkeypatch.setattr(module, 'PhoneDisplay', Capture)
    monkeypatch.setattr(module, 'ScreenStream', Screen)
    monkeypatch.setattr(module, 'ScreenFeedback', Resource)
    real_open = open
    monkeypatch.setattr(module, 'open', lambda path, mode: real_open(tmp_path/'receiver.plist', mode), raising=False)
    statuses = []
    options = dict(host='192.168.1.2', port=7000, interface='wlan0',
                 quality=0, fps=60, rotation=90, bitrate=4000000,
                 native_width=0 if automatic_geometry else 1080,
                 native_height=0 if automatic_geometry else 1920)
    if control is not None:
        options['control'] = control
    if bluetooth:
        options['device_id'] = 'AA:BB:CC:DD:EE:FF'
    s = module.Session(options, statuses.append, lambda: not locked)
    if bluetooth:
        s.iap_link = lambda sock, stop, transport: links.append((sock, transport))
    if disconnect:
        with pytest.raises(RuntimeError, match='disconnected'): s.run()
    else:
        s.run()
        assert len([c for c in calls if c[0] == 'frame']) == 2
        assert observed_control == [control is not False and not locked] * 2
    assert not s.allow
    assert not s.ready
    assert s.metrics['native_width'] == 1080 and s.metrics['native_height'] == 1920
    assert s.touch.closed
    assert 'Capture' in closed and 'Events' in closed and 'Screen' in closed
    assert calls[-1][:2] == ('TEARDOWN', '/')
    assert [c[0] for c in calls].index('RECORD') < next(i for i,c in enumerate(calls) if c[0] == 'SETUP' and 'streams' in c[2])
    setup = next(c[2] for c in calls if c[0] == 'SETUP' and 'deviceID' in c[2])
    if bluetooth:
        assert setup['deviceID'] == 'AA:BB:CC:DD:EE:FF'
        assert links == [('network-socket', 'airplay')]
        assert 'Tunnel' in closed
        assert ('POST', '/command', {'type': 'iAPSendMessage', 'params': {'data': b'phone-iap-response'}}) in calls
    else:
        assert setup['deviceID'].startswith('02:')
    assert setup['macAddress'] == setup['deviceID']
