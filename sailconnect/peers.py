"""Choose a paired Bluetooth peer without requiring an existing RFCOMM link."""
def paired_peer(objects, adapter):
    paired = [str(path) for path, interfaces in objects.items()
              if str(path).startswith(adapter + '/')
              and interfaces.get('org.bluez.Device1', {}).get('Paired')]
    connected = [path for path in paired if objects[path]['org.bluez.Device1'].get('Connected')]
    if len(connected) == 1:
        return connected[0]
    if not connected and len(paired) == 1:
        return paired[0]
    raise ValueError('connect Bluetooth to exactly one paired WinPlay computer first')
