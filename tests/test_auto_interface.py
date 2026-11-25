import pytest

from carplay_proto import rtspclient


@pytest.mark.parametrize('address,interface,expected', [
    ('fe80::1%wlan0', '', ('fe80::1', 17000, 0, 12)),
    ('fe80::1', 'wlan0', ('fe80::1', 17000, 0, 12)),
    ('fd00::1', '', ('fd00::1', 17000, 0, 0)),
    ('192.168.1.20', '', ('192.168.1.20', 17000)),
])
def test_automatic_route_and_ipv6_scope(monkeypatch, address, interface, expected):
    destinations = []

    class Socket:
        def settimeout(self, timeout):
            pass

        def connect(self, destination):
            destinations.append(destination)

        def close(self):
            pass

    monkeypatch.setattr(rtspclient.socket, 'socket', lambda *args: Socket())
    monkeypatch.setattr(rtspclient.socket, 'if_nametoindex', lambda name: 12)
    rtspclient.connect(address, 17000, interface)
    assert destinations == [expected]
