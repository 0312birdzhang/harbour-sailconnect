"""LAN CarPlay session using the Sailplay authentication and screen transport."""
import json
import os
import plistlib
import threading
import time
import uuid
import hashlib
import socket
from types import SimpleNamespace
from carplay_proto.airplaypair import pair_setup, pair_verify
from carplay_proto.airplaytiming import TimingServer
from carplay_proto.rtspclient import connect
from carplay_proto.screenstream import ScreenStream
from carplay_proto.videodemo import DemoEvents, ScreenFeedback, screen_packet_profile
from .display import PhoneDisplay
from .geometry import Viewport, stream_size
from .input import PhoneInput

HEADERS = {'Content-Type': 'application/x-apple-binary-plist', 'User-Agent': 'AirPlay/566.25.21'}


def identity(path='/var/lib/sailconnect/identity.json'):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        data = {'id': str(uuid.uuid4()), 'private_key': os.urandom(32).hex()}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
        return data
    with os.fdopen(fd) as stream:
        return json.load(stream)


class Session:
    def __init__(self, options, status, unlocked):
        self.options, self.status, self.unlocked = options, status, unlocked
        self.stop = threading.Event()
        self.allow = bool(options.get('control', True)) and unlocked()
        self.ready = False
        self.touch = None
        self.screen = None
        self.client = None
        self.events = None
        self.iap_link = None
        self.metrics = {}

    def update_metrics(self, values):
        self.metrics.update(values)

    def control(self, allow):
        self.allow = bool(allow)
        if not self.allow and self.touch:
            self.touch.release()

    def close(self, abort=True):
        self.stop.set()
        self.ready = False
        self.control(False)
        if abort and self.client:
            sock = self.client.sock
            sock = getattr(sock, 'sock', sock)
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def run(self):
        o = self.options
        events = timing = feedback = pipeline = video = tunnel = None
        self.status('waiting for WinPlay; start receiving on computer')
        phase = 'connect'
        try:
            deadline = time.monotonic() + 120
            while not self.stop.is_set():
                try:
                    self.client = client = connect(o['host'], o['port'], o['interface'])
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    self.stop.wait(1)
            if self.stop.is_set():
                return
            phase = 'public-info'
            status, _, _ = client.request('GET', '/info', plistlib.dumps({}, fmt=plistlib.FMT_BINARY), HEADERS)
            if status not in (200, 455):
                raise RuntimeError('public info rejected: {}'.format(status))
            data = identity()
            phase = 'pair-setup'
            paired = pair_setup(client, data['id'], bytes.fromhex(data['private_key']))
            phase = 'pair-verify'
            verified = pair_verify(client, data['id'], bytes.fromhex(data['private_key']), paired)
            timing = TimingServer(client.sock.sock)
            # Receiver selection checks the phone's Bluetooth identity after bootstrap.
            device_id = o.get('device_id') or '02:' + ':'.join('{:02X}'.format(b) for b in
                                        hashlib.sha256(data['id'].encode()).digest()[:5])
            setup = dict(deviceID=device_id, macAddress=device_id, model='Sailconnect1,1',
                         name='Sailconnect', osName='SailfishOS', osBuildVersion='18F72',
                         sourceVersion='566.25.21', sessionUUID=str(uuid.uuid4()),
                         timingPort=timing.port, features=[], statsCollectionEnabled=False)
            phase = 'initial-setup'
            status, _, body = client.request('SETUP', '/setup', plistlib.dumps(setup, fmt=plistlib.FMT_BINARY), HEADERS)
            if status != 200:
                raise RuntimeError('initial SETUP rejected: {}'.format(status))
            setup_info = plistlib.loads(body)
            phase = 'encrypted-info'
            status, _, body = client.request('GET', '/info', plistlib.dumps({}, fmt=plistlib.FMT_BINARY), HEADERS)
            if status != 200:
                raise RuntimeError('encrypted info rejected: {}'.format(status))
            info = plistlib.loads(body)
            # Persist only receiver capabilities, never shared keys or pairing proofs.
            with open('/run/sailconnect/receiver.plist', 'wb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(body)
            display = info['displays'][0]
            fps = min(o['fps'], max(1, int(display.get('maxFPS', 30))))
            width, height = stream_size(display, o['quality'], fps)
            # Decode and suppress pre-video presses until actual geometry is known.
            self.touch = PhoneInput(info.get('hidDevices', []), display['uuid'],
                                    SimpleNamespace(width=width, height=height),
                                    lambda: self.allow and self.ready and not self.stop.is_set(), self.unlocked)
            modes = {'appStates': [{'appStateID': 1, 'entity': 0, 'speechMode': -1},
                                  {'appStateID': 2, 'entity': 0}, {'appStateID': 3, 'entity': 0}],
                     'resources': [{'resourceID': r, 'entity': 1, 'permanentEntity': 1} for r in (1, 2)]}
            resume, changed = threading.Event(), threading.Event()
            mode_lock, revision = threading.RLock(), [0]
            if self.iap_link:
                from carplay_proto.iaptunnel import IAPTunnel
                def send_iap(data):
                    request = {'type': 'iAPSendMessage', 'params': {'data': data}}
                    status, _, _ = client.request('POST', '/command', plistlib.dumps(request, fmt=plistlib.FMT_BINARY), HEADERS)
                    if status != 200:
                        raise RuntimeError('iAP tunnel message rejected')
                tunnel = IAPTunnel(lambda sock, stop: self.iap_link(sock, stop, transport='airplay'), send_iap)
            def command(value):
                kind = value.get('type')
                if kind == 'iAPSendMessage' and tunnel:
                    from carplay_proto.iaptunnel import tunnel_payload
                    data = tunnel_payload(value)
                    if data:
                        tunnel.feed(data)
                    return {'status': 0}
                if kind == 'hidSendReport':
                    try:
                        if self.touch:
                            self.touch.command(value)
                    except Exception:
                        self.control(False)
                        raise
                    return {'status': 0}
                if kind == 'forceKeyFrame' and pipeline:
                    pipeline.request_keyframe()
                    return {'status': 0}
                if kind == 'requestUI':
                    resume.set()
                    return {'status': 0}
                if kind == 'changeModes':
                    with mode_lock:
                        for request in value.get('params', {}).get('resources', []):
                            resource = next((r for r in modes['resources'] if r['resourceID'] == request.get('resourceID')), None)
                            if resource:
                                transfer = request.get('transferType')
                                owner = {1: 2, 2: 1, 3: 2, 4: resource['permanentEntity']}.get(transfer, resource['entity'])
                                resource['entity'] = owner
                                if transfer in (1, 2):
                                    resource['permanentEntity'] = owner
                        revision[0] += 1
                        owner = modes['resources'][0]['entity']
                        if owner != 1:
                            self.control(False)
                        if self.screen:
                            self.screen.expect_owner(owner)
                        changed.set()
                    return {'status': 0, 'params': modes}

            phase = 'event-connect'
            events = self.events = DemoEvents(o['host'], int(setup_info['eventPort']), o['interface'], verified.shared, command)
            phase = 'capture'
            pipeline = PhoneDisplay(width, height, fps, o['rotation'], o['bitrate'], o['native_width'], o['native_height'], metrics=self.update_metrics)
            pipeline.start(self.stop)
            source = pipeline.frames(0)
            config, nals = next(source)
            if self.stop.is_set():
                return
            native_width, native_height = pipeline.geometry()
            self.update_metrics(dict(native_width=native_width, native_height=native_height))
            viewport = Viewport(width, height, native_width, native_height, o['rotation'])
            with self.touch.lock:
                self.touch.viewport = viewport
            phase = 'record'
            status, _, _ = client.request('RECORD', '/')
            if status != 200:
                raise RuntimeError('RECORD rejected: {}'.format(status))
            stream_id = int.from_bytes(os.urandom(7), 'big') or 1
            phase = 'screen-setup'
            payload = {'streams': [{'type': 110, 'streamConnectionID': stream_id,
                                    'latencyMs': 100, 'uuid': display['uuid']}]}
            status, _, body = client.request('SETUP', '/setup', plistlib.dumps(payload, fmt=plistlib.FMT_BINARY), HEADERS)
            if status != 200:
                raise RuntimeError('screen SETUP rejected: {}'.format(status))
            stream = next(s for s in plistlib.loads(body)['streams'] if s['type'] == 110)
            video = connect(o['host'], int(stream['dataPort']), o['interface']).sock
            self.screen = ScreenStream(client, o['host'], o['interface'], verified.shared,
                         display, video, stream_id, width, height,
                         request_keyframe=pipeline.request_keyframe,
                         packet_profile=screen_packet_profile(info))
            feedback = ScreenFeedback(client, None, modes, resume, self.screen, changed,
                                      mode_lock=mode_lock, mode_revision=revision)
            phase = 'streaming'
            self.ready = True
            self.status('streaming {}x{} target {}fps'.format(width, height, fps))
            import itertools
            for config, nals in itertools.chain([(config, nals)], source):
                if self.stop.is_set():
                    break
                if events.stop.is_set() or feedback.stop.is_set():
                    raise RuntimeError('receiver control channel disconnected')
                self.screen.send(config, nals, time.monotonic_ns())
        except Exception as error:
            if not self.stop.is_set():
                self.status('failed at {}: {}'.format(phase, error))
                raise
        finally:
            self.close(abort=False)
            # Stop event dispatch before destroying its input target.
            for resource in (events, tunnel, feedback, self.touch, self.screen, pipeline, timing):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as error:
                        print('cleanup: {}'.format(error), flush=True)
            if self.screen is None and video is not None:
                video.close()
            if self.client:
                try:
                    self.client.request('TEARDOWN', '/')
                except Exception:
                    pass
                self.client.sock.close()
