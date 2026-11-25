"""Exercise early iAP2 preparation, session identity, and owner cleanup."""
import json
import signal
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from sailconnect import service
from sailconnect.session import Session


@pytest.mark.parametrize('requested_control', [None, False])
@pytest.mark.parametrize('prepare_first', [False, True])
def test_start_and_owner_cleanup_with_bootstrap(monkeypatch, requested_control, prepare_first):
    objects, controllers, destinations, bootstraps = [], [], [], []
    stops = []
    monkeypatch.setattr(service, 'stop_sailplay', lambda: stops.append(True))

    class Bootstrap:
        address = 'AA:BB:CC:DD:EE:FF'

        def __init__(self, bus):
            assert stops, 'Sailplay must stop before Bluetooth registration'
            self.closed = False
            bootstraps.append(self)

        def link(self, *args, **kwargs):
            pass

        def close(self):
            self.closed = True

    class Bus:
        def add_signal_receiver(self, *args, **kwargs):
            pass

        def get_object(self, destination, path):
            destinations.append(destination)
            if destination != 'com.nokia.mce':
                raise RuntimeError('No such bus service: ' + destination)
            return SimpleNamespace(get_tklock_mode=lambda **kwargs: 'unlocked')

    class Object:
        def __init__(self, *args):
            objects.append(self)

    class Controller:
        def __init__(self, options, status, unlocked, iap_link):
            self.options, self.status = options, status
            self.current = Session(options, status, unlocked)
            self.current.iap_link = iap_link
            self.streaming = threading.Event()
            self.finished = threading.Event()
            controllers.append(self)

        def run(self):
            self.current.ready = True
            self.status('streaming 1280x720 target 30fps')
            self.streaming.set()
            self.finished.wait(5)

        def stop(self):
            self.current.close()
            self.finished.set()

    class Loop:
        def run(self):
            control = objects[0]
            args = ('192.168.1.2', 17000, 'wlan0', 1080, 2160, 0, 3, 30, 4000000)
            if prepare_first:
                assert control.PrepareBluetooth(sender=':1.lan-client') == Bootstrap.address
                assert json.loads(control.Status())['bluetooth_ready']
                assert not json.loads(control.Status())['active']
            if requested_control is None:
                control.Start(*args, sender=':1.lan-client')
            else:
                control.StartWithControl(*args, requested_control, sender=':1.lan-client')
            controller = controllers[0]
            assert controller.streaming.wait(1)
            assert controller.options['host'] == '192.168.1.2'
            assert controller.options['device_id'] == Bootstrap.address
            assert controller.current.iap_link == bootstraps[0].link
            assert len(bootstraps) == 1, 'Starting must reuse the profile prepared before WinPlay starts'
            state = json.loads(control.Status())
            assert state['active'] and state['state'].startswith('streaming')
            assert state['control'] is (requested_control is not False)
            control.owner_changed(':1.lan-client', ':1.lan-client', '')

        def quit(self):
            pass

    dbus = ModuleType('dbus')
    dbus_service = ModuleType('dbus.service')
    dbus_service.Object = Object
    dbus_service.BusName = lambda *args: object()
    dbus_service.method = lambda *args, **kwargs: lambda function: function
    dbus.service = dbus_service
    dbus.SystemBus = Bus
    dbus.Interface = lambda value, *args: value
    dbus.exceptions = SimpleNamespace(DBusException=RuntimeError)
    mainloop = ModuleType('dbus.mainloop')
    dbus_glib = ModuleType('dbus.mainloop.glib')
    dbus_glib.DBusGMainLoop = lambda **kwargs: None
    mainloop.glib = dbus_glib
    gi = ModuleType('gi')
    repository = ModuleType('gi.repository')
    repository.GLib = SimpleNamespace(timeout_add=lambda *args: None, MainLoop=Loop,
                                     idle_add=lambda function, *args: function(*args))
    gi.repository = repository
    for name, module in [('dbus', dbus), ('dbus.service', dbus_service),
                         ('dbus.mainloop', mainloop), ('dbus.mainloop.glib', dbus_glib),
                         ('gi', gi), ('gi.repository', repository)]:
        monkeypatch.setitem(sys.modules, name, module)
    bluetooth = ModuleType('sailconnect.bluetooth')
    bluetooth.Bootstrap = Bootstrap
    monkeypatch.setitem(sys.modules, 'sailconnect.bluetooth', bluetooth)
    monkeypatch.setattr(service, 'Controller', Controller)
    monkeypatch.setattr(signal, 'signal', lambda *args: None)

    service.main()

    assert destinations == ['com.nokia.mce']
    assert controllers[0].finished.is_set()
    assert controllers[0].current.stop.is_set()
    assert not controllers[0].current.allow
    assert not objects[0].worker.is_alive()
    assert bootstraps[0].closed
    assert len(stops) == (2 if prepare_first else 1)
