"""Prerequisite reporting must use current device state and tolerate missing services."""
import sys
from types import SimpleNamespace
import pytest
from sailconnect.setup import bluetooth_state, setup_state

ADAPTER = '/org/bluez/hci0'


def objects(powered=True, devices=()):
    value = {ADAPTER: {'org.bluez.Adapter1': {'Powered': powered}}}
    for name, paired, connected in devices:
        value[ADAPTER + '/dev_' + name] = {'org.bluez.Device1': {
            'Alias': name, 'Paired': paired, 'Connected': connected}}
    return value


@pytest.mark.parametrize('powered', [False, True])
def test_pairing_survives_bluetooth_power_off_but_is_not_reported_ready(powered):
    state = bluetooth_state(objects(powered, [('PC', True, False)]))
    assert state['bluetooth_powered'] is powered
    assert state['paired_devices'] == [dict(name='PC', connected=False)]
    assert state['peer_name'] == ('PC' if powered else '')


def test_multiple_pairs_need_an_unambiguous_connected_peer():
    state = bluetooth_state(objects(devices=[('PC', True, False), ('HEADSET', True, False)]))
    assert not state['peer_name'] and state['bluetooth_error']
    state = bluetooth_state(objects(devices=[('PC', True, True), ('HEADSET', True, False)]))
    assert state['peer_name'] == 'PC' and not state['bluetooth_error']


def test_unpaired_devices_are_not_reported_as_paired():
    state = bluetooth_state(objects(devices=[('PC', False, True)]))
    assert not state['paired_devices'] and not state['peer_name']


@pytest.mark.parametrize('interfaces', [
    [], [dict(address='192.168.3.217')], [dict(address=None)]])
def test_network_status_supports_ipv6_only_and_no_network(monkeypatch, interfaces):
    monkeypatch.setitem(sys.modules, 'dbus', SimpleNamespace(Interface=lambda value, _: value))
    bus = SimpleNamespace(get_object=lambda *_: SimpleNamespace(
        GetManagedObjects=lambda **_: objects(devices=[('PC', True, False)])))
    state = setup_state(bus, lambda: interfaces)
    assert state['network_connected'] is bool(interfaces)
    assert state['network_addresses'] == [item['address'] for item in interfaces if item['address']]
    assert state['peer_name'] == 'PC'


def test_unavailable_bluez_does_not_hide_the_network_state(monkeypatch):
    monkeypatch.setitem(sys.modules, 'dbus', SimpleNamespace(Interface=lambda value, _: value))
    def unavailable(*_):
        raise RuntimeError('service not found')
    state = setup_state(SimpleNamespace(get_object=unavailable), lambda: [dict(address='192.168.3.217')])
    assert not state['bluetooth_available']
    assert state['bluetooth_error'] == 'org.bluez unavailable'
    assert state['network_connected']
