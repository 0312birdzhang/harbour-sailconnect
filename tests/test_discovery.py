import ipaddress
import struct

import pytest

from sailconnect.discovery import Discovery, RecordStore, SERVICE, parse_response, query

INTERFACE = dict(name='wlan0', index=3, address='192.168.1.10',
                 network=ipaddress.ip_network('192.168.1.0/24'))


def name(value):
    return b''.join(bytes([len(part)]) + part.encode() for part in value.split('.')) + b'\0'


def record(owner, kind, data, ttl=120, flush=False):
    return name(owner) + struct.pack('!HHIH', kind, 0x8001 if flush else 1, ttl, len(data)) + data


def announcement(provider, port=17000, address='192.168.1.20', target=None, ttl=120):
    target = target or provider.lower() + '-uuid.local'
    instance = provider + '.' + SERVICE
    txt = ('model=' + provider).encode()
    ip = ipaddress.ip_address(address)
    records = [record(SERVICE, 12, name(instance), ttl),
               record(instance, 33, struct.pack('!HHH', 0, 0, port) + name(target), ttl, True),
               record(instance, 16, bytes([len(txt)]) + txt, ttl, True),
               record(target, 1 if ip.version == 4 else 28, ip.packed, ttl, True)]
    return struct.pack('!6H', 0, 0x8400, 0, 1, 0, 3) + b''.join(records)


@pytest.mark.parametrize('provider', ['WinPlay', 'LinuxPlay', 'MacPlay'])
@pytest.mark.parametrize('port', [17000, 7777, 54321])
def test_receiver_advertisement_supplies_the_actual_port(provider, port):
    store = RecordStore()
    store.feed(parse_response(announcement(provider, port)), INTERFACE, '192.168.1.20', 0)
    receiver, = store.receivers(1)
    assert receiver['name'] == provider
    assert receiver['port'] == port
    assert receiver['host'] == '192.168.1.20'
    assert receiver['interface'] == 'wlan0'


def test_dns_compression_in_owner_and_srv_target():
    question = name(SERVICE) + struct.pack('!HH', 12, 1)
    instance_offset = 12 + len(question) + 12
    ptr = b'\xc0\x0c' + struct.pack('!HHIH', 12, 1, 120, 10) + b'\x07WinPlay\xc0\x0c'
    owner = struct.pack('!H', 0xc000 | instance_offset)
    target_offset = 12 + len(question) + len(ptr) + len(owner) + 10 + 6
    srv_data = struct.pack('!HHH', 0, 0, 23456) + name('winplay.local')
    srv = owner + struct.pack('!HHIH', 33, 0x8001, 120, len(srv_data)) + srv_data
    address = struct.pack('!H', 0xc000 | target_offset) + struct.pack('!HHIH', 1, 0x8001, 120, 4) + b'\xc0\xa8\x01\x14'
    packet = struct.pack('!6H', 0, 0x8400, 1, 3, 0, 0) + question + ptr + srv + address
    parsed = parse_response(packet)
    assert parsed[1][2] == (23456, 'winplay.local')
    store = RecordStore()
    store.feed(parsed, INTERFACE, '192.168.1.20', 0)
    assert store.receivers(0)[0]['port'] == 23456


def test_split_records_trigger_resolution_queries():
    records = parse_response(announcement('MacPlay'))
    store = RecordStore()
    store.feed(records[:1], INTERFACE, '192.168.1.20', 0)
    assert ('macplay.' + SERVICE, 33) in store.questions(0)
    assert not store.receivers(0)
    store.feed(records[1:3], INTERFACE, '192.168.1.20', 0)
    assert ('macplay-uuid.local', 1) in store.questions(0)
    store.feed(records[3:], INTERFACE, '192.168.1.20', 0)
    assert len(store.receivers(0)) == 1


def test_two_receivers_with_the_same_service_name_are_preserved():
    store = RecordStore()
    for host, target in [('192.168.1.20', 'winplay-one.local'), ('192.168.1.21', 'winplay-two.local')]:
        store.feed(parse_response(announcement('WinPlay', address=host, target=target)), INTERFACE, host, 0)
    assert [r['host'] for r in store.receivers(0)] == ['192.168.1.20', '192.168.1.21']


def test_ipv6_link_local_address_has_the_phone_interface_scope():
    store = RecordStore()
    store.feed(parse_response(announcement('MacPlay', address='fe80::123')), INTERFACE, 'fe80::123', 0)
    assert store.receivers(0)[0]['host'] == 'fe80::123%wlan0'


def test_dual_stack_advertisements_are_one_receiver_with_ipv4_preferred():
    store = RecordStore()
    store.feed(parse_response(announcement('MacPlay', address='fe80::123')), INTERFACE, 'fe80::123', 0)
    store.feed(parse_response(announcement('MacPlay')), INTERFACE, '192.168.1.20', 0)
    receiver, = store.receivers(0)
    assert receiver['host'] == '192.168.1.20'


@pytest.mark.parametrize('address', ['8.8.8.8', '127.0.0.1', '0.0.0.0', '239.1.1.1', '192.168.2.20'])
def test_addresses_outside_the_local_interface_are_not_listed(address):
    store = RecordStore()
    store.feed(parse_response(announcement('WinPlay', address=address)), INTERFACE, '192.168.1.20', 0)
    assert not store.receivers(0)


def test_an_ordinary_airplay_receiver_is_not_misidentified():
    store = RecordStore()
    store.feed(parse_response(announcement('AppleTV')), INTERFACE, '192.168.1.20', 0)
    assert not store.receivers(0)


@pytest.mark.parametrize('goodbye', [False, True])
def test_expired_or_withdrawn_services_disappear(goodbye):
    store = RecordStore()
    store.feed(parse_response(announcement('LinuxPlay', ttl=1)), INTERFACE, '192.168.1.20', 0)
    assert store.receivers(.5)
    if goodbye:
        store.feed(parse_response(announcement('LinuxPlay', ttl=0)), INTERFACE, '192.168.1.20', .5)
        assert not store.receivers(.5)
    else:
        assert not store.receivers(1)


def test_pointer_cycles_and_truncated_records_are_rejected():
    header = struct.pack('!6H', 0, 0x8400, 0, 1, 0, 0)
    for malformed in [header + b'\xc0\x0c', header + name('test.local'),
                      header + record('test.local', 16, b'\x10x')]:
        with pytest.raises(ValueError):
            parse_response(malformed)


def test_query_is_a_ptr_question_for_the_receiver_service():
    packet = query([(SERVICE, 12)])
    assert struct.unpack_from('!6H', packet) == (0, 0, 1, 0, 0, 0)
    assert packet[12:] == name(SERVICE) + struct.pack('!HH', 12, 1)


def test_no_lan_reports_a_finished_scan_without_opening_sockets():
    updates = []
    Discovery(updates.append, interfaces=lambda: []).run()
    assert updates == [dict(scanning=False, receivers=[], error='no local network interface')]
