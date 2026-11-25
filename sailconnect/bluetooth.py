"""Temporary paired-device RFCOMM profile for WinPlay's wireless bootstrap."""
import os
import socket
import threading
import dbus
import dbus.service
from .iap import probe, service_record
from .peers import paired_peer

PHONE_UUID = '00000000-deca-fade-deca-deafdecacafe'


class Bootstrap:
    def __init__(self, bus):
        self.bus = bus
        objects = dbus.Interface(bus.get_object('org.bluez', '/'),
                        'org.freedesktop.DBus.ObjectManager').GetManagedObjects()
        adapters = [(str(p), v['org.bluez.Adapter1']) for p, v in objects.items()
                    if v.get('org.bluez.Adapter1', {}).get('Powered')]
        if len(adapters) != 1:
            raise ValueError('one powered Bluetooth adapter required for wireless CarPlay')
        adapter, props = adapters[0]
        self.address = str(props['Address'])
        self.peer = paired_peer(objects, adapter)
        self.path = '/org/sailconnect/phone'
        self.manager = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.ProfileManager1')
        self.workers = []
        outer = self

        class Profile(dbus.service.Object):
            @dbus.service.method('org.bluez.Profile1', in_signature='', out_signature='')
            def Release(self):
                outer.retire()

            @dbus.service.method('org.bluez.Profile1', in_signature='oha{sv}', out_signature='')
            def NewConnection(self, device, descriptor, properties):
                sock = socket.socket(fileno=descriptor.take())
                if str(device) != outer.peer:
                    sock.close()
                    raise dbus.exceptions.DBusException('unexpected Bluetooth peer')
                outer.retire()
                stop = threading.Event()
                thread = threading.Thread(target=outer.link, args=(sock, stop), daemon=True)
                outer.workers.append((sock, stop, thread))
                thread.start()

            @dbus.service.method('org.bluez.Profile1', in_signature='o', out_signature='')
            def RequestDisconnection(self, device):
                outer.retire()

        self.profile = Profile(bus, self.path)
        try:
            self.manager.RegisterProfile(self.path, PHONE_UUID,
                    {'Name': 'Sailconnect wireless phone', 'Role': 'server',
                     'Channel': dbus.UInt16(19), 'RequireAuthentication': True,
                     'RequireAuthorization': False, 'ServiceRecord': service_record(19)})
        except BaseException:
            self.profile.remove_from_connection()
            raise

    @property
    def pin(self):
        directory = '/var/lib/sailconnect/accessories'
        os.makedirs(directory, mode=0o700, exist_ok=True)
        return directory + '/' + self.peer.rsplit('/', 1)[1] + '.json'

    def link(self, sock, stop, transport='bluetooth'):
        probe(sock, stop, 0, announce_wireless=True, local_address=self.address,
              local_name='Sailconnect', paired_pin_path=self.pin, transport=transport)

    def retire(self):
        workers, self.workers = self.workers, []
        for sock, stop, thread in workers:
            stop.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            thread.join(1)

    def close(self):
        self.retire()
        try:
            self.manager.UnregisterProfile(self.path)
        finally:
            self.profile.remove_from_connection()
