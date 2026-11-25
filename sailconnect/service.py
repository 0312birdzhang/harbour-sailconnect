"""Small privileged D-Bus boundary. No shell commands or caller-selected paths."""
import ipaddress
import json
import re
import subprocess
import threading
from .controller import Controller
from .discovery import Discovery


def stop_sailplay():
    """Release Sailplay's Bluetooth/network resources before preparing our profile."""
    result = subprocess.run(
        ['/usr/bin/systemctl', 'show', 'sailplay.service', '--property=LoadState', '--value'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        timeout=5)
    if result.stdout.strip() == 'not-found':
        return
    if result.returncode or not result.stdout.strip():
        raise RuntimeError('Cannot check Sailplay service: ' + result.stderr.strip())
    # A synchronous stop waits for Sailplay's ExecStopPost cleanup as well.
    result = subprocess.run(
        ['/usr/bin/systemctl', 'stop', 'sailplay.service'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        timeout=60)
    if result.returncode:
        raise RuntimeError('Cannot stop Sailplay service: ' + result.stderr.strip())


def validate(host, port, interface, nw, nh, rotation, quality, fps, bitrate):
    address = ipaddress.ip_address(str(host).split('%')[0])
    if not (address.is_private or address.is_link_local) or address.is_loopback or address.is_multicast or address.is_unspecified:
        raise ValueError('receiver must have a LAN address')
    if interface and not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,15}', str(interface)):
        raise ValueError('invalid network interface')
    if not 1 <= port <= 65535 or not ((nw == 0 and nh == 0) or (240 <= nw <= 7680 and 240 <= nh <= 7680)):
        raise ValueError('invalid port or native screen size')
    if rotation not in (0, 90, 180, 270) or quality not in (0, 1, 2, 3):
        raise ValueError('invalid rotation or quality')
    if fps not in (15, 30, 60) or not 500000 <= bitrate <= 20000000:
        raise ValueError('invalid frame rate or bitrate')
    return dict(host=str(host), port=int(port), interface=str(interface),
                native_width=int(nw), native_height=int(nh), rotation=int(rotation),
                quality=int(quality), fps=int(fps), bitrate=int(bitrate))


def main():
    import logging
    logging.basicConfig(level=logging.INFO, format='%(threadName)s: %(message)s')
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    name = dbus.service.BusName('org.sailconnect.Control', bus)

    class Control(dbus.service.Object):
        def __init__(self):
            super().__init__(name, '/org/sailconnect/Control')
            self.controller = self.worker = None
            self.state = 'stopped'
            self.screen_locked = True
            self.owner = None
            self.bootstrap = None
            self.discovery = self.discovery_worker = None
            self.discovery_lock = threading.RLock()
            self.discovery_state = dict(scanning=False, receivers=[], error='')
            bus.add_signal_receiver(self.owner_changed, signal_name='NameOwnerChanged',
                    dbus_interface='org.freedesktop.DBus', bus_name='org.freedesktop.DBus')
            bus.add_signal_receiver(self.lock_changed, signal_name='tklock_mode_ind',
                    dbus_interface='com.nokia.mce.signal', bus_name='com.nokia.mce',
                    path='/com/nokia/mce/signal')

        @property
        def session(self):
            return self.controller.current if self.controller else None

        def lock_changed(self, mode):
            self.screen_locked = str(mode) != 'unlocked'
            if self.screen_locked and self.session:
                self.session.control(False)

        def owner_changed(self, name, old, new):
            if name == self.owner and not new:
                self.Stop()
                self.owner = None

        def unlocked(self):
            return not self.screen_locked

        def check_lock(self):
            try:
                mce = dbus.Interface(bus.get_object('com.nokia.mce', '/com/nokia/mce/request'), 'com.nokia.mce.request')
                mode = str(mce.get_tklock_mode(timeout=1))
                self.screen_locked = mode != 'unlocked'
            except Exception:
                self.screen_locked = True
            if self.screen_locked and self.session:
                # Revoke consent on lock: local unlock does not restore control.
                self.session.control(False)
            if self.session and self.session.events and self.session.events.stop.is_set():
                self.session.control(False)
            return True

        def status(self, value):
            self.state = value
            print(value, flush=True)

        def discovery_update(self, value):
            with self.discovery_lock:
                self.discovery_state = value

        def prepare_bluetooth(self):
            stop_sailplay()
            if self.bootstrap is None:
                from .bluetooth import Bootstrap
                self.bootstrap = Bootstrap(bus)
            return self.bootstrap

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='s', sender_keyword='sender')
        def PrepareBluetooth(self, sender=None):
            bootstrap = self.prepare_bluetooth()
            if not self.worker or not self.worker.is_alive():
                self.owner = sender
            return bootstrap.address

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='')
        def ScanReceivers(self):
            if self.discovery_worker and self.discovery_worker.is_alive():
                return
            self.discovery_update(dict(scanning=True, receivers=[], error=''))
            self.discovery = Discovery(self.discovery_update)
            self.discovery_worker = threading.Thread(target=self.discovery.run, daemon=True)
            self.discovery_worker.start()

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='s')
        def DiscoveryStatus(self):
            with self.discovery_lock:
                return json.dumps(self.discovery_state)

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='s')
        def SetupStatus(self):
            from .setup import setup_state
            value = setup_state(bus)
            value['bluetooth_ready'] = (self.bootstrap is not None
                                       and value['bluetooth_powered']
                                       and not value['bluetooth_error'])
            return json.dumps(value)

        @dbus.service.method('org.sailconnect.Control', in_signature='sisiuiiii', out_signature='', sender_keyword='sender')
        def Start(self, host, port, interface, nw, nh, rotation, quality, fps, bitrate, sender=None):
            self.start(host, port, interface, nw, nh, rotation, quality, fps, bitrate, True, sender)

        @dbus.service.method('org.sailconnect.Control', in_signature='sisiuiiiib', out_signature='', sender_keyword='sender')
        def StartWithControl(self, host, port, interface, nw, nh, rotation, quality, fps, bitrate, control, sender=None):
            self.start(host, port, interface, nw, nh, rotation, quality, fps, bitrate, control, sender)

        def start(self, host, port, interface, nw, nh, rotation, quality, fps, bitrate, control, sender):
            if self.worker and self.worker.is_alive():
                raise dbus.exceptions.DBusException('session already active')
            options = validate(host, port, interface, nw, nh, rotation, quality, fps, bitrate)
            options['control'] = bool(control)
            self.check_lock()
            bootstrap = self.prepare_bluetooth()
            options['device_id'] = bootstrap.address
            self.controller = Controller(options, self.status, self.unlocked, bootstrap.link)
            self.owner = sender
            controller = self.controller
            def run():
                try:
                    controller.run()
                finally:
                    self.status('stopped')
                    GLib.idle_add(self.finish, controller)
            self.worker = threading.Thread(target=run, daemon=True)
            self.worker.start()

        def finish(self, controller):
            if self.controller is controller and self.bootstrap:
                self.bootstrap.close()
                self.bootstrap = None
            return False

        @dbus.service.method('org.sailconnect.Control', in_signature='b', out_signature='', sender_keyword='sender')
        def AllowControl(self, allow, sender=None):
            if allow and sender != self.owner:
                raise dbus.exceptions.DBusException('control belongs to the session owner')
            if not self.session or not self.worker or not self.worker.is_alive():
                raise dbus.exceptions.DBusException('no active session')
            if allow and (self.screen_locked or not self.state.startswith('streaming')):
                raise dbus.exceptions.DBusException('unlock phone and wait for video first')
            self.session.control(allow)

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='')
        def Stop(self):
            if self.discovery:
                self.discovery.close()
            if self.controller and self.worker and self.worker.is_alive():
                self.state = 'stopping'
                self.controller.stop()
            else:
                if self.bootstrap:
                    self.bootstrap.close()
                    self.bootstrap = None
                self.state = 'stopped'

        @dbus.service.method('org.sailconnect.Control', in_signature='', out_signature='s')
        def Status(self):
            return json.dumps(dict(state=self.state, locked=self.screen_locked,
                                   active=bool(self.worker and self.worker.is_alive()),
                                   control=bool(self.session and self.session.allow),
                                   bluetooth_ready=self.bootstrap is not None,
                                   native_width=self.session.metrics.get('native_width', 0) if self.session else 0,
                                   native_height=self.session.metrics.get('native_height', 0) if self.session else 0,
                                   fps=self.session.metrics.get('fps', 0) if self.session else 0))

    control = Control()
    GLib.timeout_add(250, control.check_lock)
    loop = GLib.MainLoop()
    import signal
    def terminate(*_):
        control.Stop()
        loop.quit()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        loop.run()
    finally:
        control.Stop()
        if control.worker:
            control.worker.join(12)
        if control.discovery_worker:
            control.discovery_worker.join(2)
        if control.bootstrap:
            control.bootstrap.close()
            control.bootstrap = None


if __name__ == '__main__':
    main()
