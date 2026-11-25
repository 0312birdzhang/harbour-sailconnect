"""Read the prerequisites for the connection guide without changing settings."""
from .discovery import local_interfaces
from .peers import paired_peer


def bluetooth_state(objects):
    result = dict(bluetooth_available=False, bluetooth_powered=False,
                  paired_devices=[], peer_name='', bluetooth_error='')
    adapters = [(str(path), value['org.bluez.Adapter1'])
                for path, value in objects.items() if 'org.bluez.Adapter1' in value]
    result['bluetooth_available'] = bool(adapters)
    powered = [(path, props) for path, props in adapters if props.get('Powered')]
    result['bluetooth_powered'] = bool(powered)
    for path, value in objects.items():
        device = value.get('org.bluez.Device1', {})
        if device.get('Paired'):
            result['paired_devices'].append(dict(name=str(device.get('Alias') or device.get('Name') or 'Bluetooth device'),
                                                  connected=bool(device.get('Connected'))))
    if len(powered) != 1:
        result['bluetooth_error'] = 'one powered Bluetooth adapter required for wireless CarPlay'
        return result
    try:
        peer = paired_peer(objects, powered[0][0])
        props = objects[peer]['org.bluez.Device1']
        result['peer_name'] = str(props.get('Alias') or props.get('Name') or 'Bluetooth device')
    except ValueError as error:
        result['bluetooth_error'] = str(error)
    return result


def setup_state(bus, interface_query=local_interfaces):
    import dbus
    try:
        objects = dbus.Interface(bus.get_object('org.bluez', '/'),
                                 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=1)
        result = bluetooth_state(objects)
    except Exception:
        result = bluetooth_state({})
        result['bluetooth_error'] = 'org.bluez unavailable'
    interfaces = interface_query()
    result['network_connected'] = bool(interfaces)
    result['network_addresses'] = [item['address'] for item in interfaces if item['address']]
    return result
