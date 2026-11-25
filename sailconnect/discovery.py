"""Bounded, interface-scoped DNS-SD discovery of the three LAN receivers."""
import fcntl
import ipaddress
import select
import socket
import struct
import threading
import time

SERVICE = '_airplay._tcp.local'
TYPES = {'A': 1, 'PTR': 12, 'TXT': 16, 'AAAA': 28, 'SRV': 33}
PROVIDERS = ('WinPlay', 'LinuxPlay', 'MacPlay')


def local_interfaces():
    """Up multicast-capable LAN interfaces, without Bluetooth or network changes."""
    result = []
    ipv6_interfaces = set()
    try:
        with open('/proc/net/if_inet6') as addresses:
            for line in addresses:
                fields = line.split()
                if len(fields) != 6 or int(fields[4], 16) & 0x48:
                    continue
                address = ipaddress.ip_address(bytes.fromhex(fields[0]))
                if not address.is_loopback and not address.is_unspecified and (address.is_private or address.is_link_local):
                    ipv6_interfaces.add(fields[5])
    except (OSError, ValueError):
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for index, name in socket.if_nameindex():
            request = struct.pack('256s', name.encode()[:15])
            try:
                flags = struct.unpack_from('H', fcntl.ioctl(probe, 0x8913, request), 16)[0]
                if not flags & 1 or flags & (8 | 16) or not flags & 0x1000:
                    continue
                address = network = None
                try:
                    candidate = socket.inet_ntoa(fcntl.ioctl(probe, 0x8915, request)[20:24])
                    mask = socket.inet_ntoa(fcntl.ioctl(probe, 0x891b, request)[20:24])
                    ip = ipaddress.ip_address(candidate)
                    if (ip.is_private or ip.is_link_local) and not ip.is_loopback and not ip.is_unspecified:
                        address = candidate
                        network = ipaddress.ip_network(address + '/' + mask, strict=False)
                except OSError:
                    pass
                if not address and name not in ipv6_interfaces:
                    continue
                result.append(dict(name=name, index=index, address=address, network=network))
            except OSError:
                continue
    return result[:8]


def _name(data, offset):
    """Decode a DNS name, bounding compression depth, size and pointer cycles."""
    labels, visited, end = [], set(), None
    for _ in range(128):
        if offset >= len(data) or offset in visited:
            raise ValueError('invalid DNS name')
        visited.add(offset)
        size = data[offset]
        if size & 0xc0 == 0xc0:
            if offset + 1 >= len(data):
                raise ValueError('truncated DNS pointer')
            if end is None:
                end = offset + 2
            offset = ((size & 0x3f) << 8) | data[offset + 1]
            continue
        if size & 0xc0 or size > 63 or offset + 1 + size > len(data):
            raise ValueError('invalid DNS label')
        offset += 1
        if size == 0:
            value = '.'.join(labels)
            if len(value.encode('utf-8')) > 255:
                raise ValueError('DNS name exceeds limit')
            return value, end if end is not None else offset
        labels.append(data[offset:offset + size].decode('utf-8', 'replace'))
        offset += size
    raise ValueError('DNS compression exceeds limit')


def parse_response(data):
    if not 12 <= len(data) <= 9000:
        raise ValueError('invalid DNS packet size')
    _, flags, questions, answers, authorities, additional = struct.unpack_from('!6H', data)
    if not flags & 0x8000:
        return []
    if questions > 64 or answers + authorities + additional > 256:
        raise ValueError('DNS record count exceeds limit')
    offset = 12
    for _ in range(questions):
        _, offset = _name(data, offset)
        offset += 4
        if offset > len(data):
            raise ValueError('truncated DNS question')
    records = []
    for _ in range(answers + authorities + additional):
        name, offset = _name(data, offset)
        if offset + 10 > len(data):
            raise ValueError('truncated DNS record')
        kind, cls, ttl, size = struct.unpack_from('!HHIH', data, offset)
        start, end = offset + 10, offset + 10 + size
        if end > len(data):
            raise ValueError('truncated DNS data')
        offset = end
        if cls & 0x7fff != 1:
            continue
        if kind == 12:
            value, consumed = _name(data, start)
            if consumed != end:
                raise ValueError('invalid PTR data')
            value = value.lower().rstrip('.')
        elif kind == 33:
            if size < 7:
                raise ValueError('truncated SRV data')
            _, _, port = struct.unpack_from('!HHH', data, start)
            target, consumed = _name(data, start + 6)
            if consumed != end or not port:
                raise ValueError('invalid SRV data')
            value = (port, target.lower().rstrip('.'))
        elif kind == 16:
            chunks = []
            position = start
            while position < end:
                length = data[position]
                position += 1
                if position + length > end:
                    raise ValueError('truncated TXT data')
                chunks.append(data[position:position + length].decode('utf-8', 'replace'))
                position += length
            value = tuple(chunks)
        elif kind in (1, 28):
            if size != (4 if kind == 1 else 16):
                raise ValueError('invalid address record')
            value = str(ipaddress.ip_address(data[start:end]))
        else:
            continue
        records.append((name.lower().rstrip('.'), kind, value, ttl, bool(cls & 0x8000)))
    return records


def query(questions):
    packet = bytearray(struct.pack('!6H', 0, 0, len(questions), 0, 0, 0))
    for name, kind in questions:
        encoded = bytearray()
        for label in name.rstrip('.').split('.'):
            label = label.encode('utf-8')
            if not 0 < len(label) <= 63:
                raise ValueError('invalid query name')
            encoded += bytes([len(label)]) + label
        if len(encoded) > 254:
            raise ValueError('query name exceeds limit')
        packet += encoded + b'\0' + struct.pack('!HH', kind, 1)
    return bytes(packet)


class RecordStore:
    def __init__(self):
        # Origin scoping preserves two receivers using the same instance name.
        self.origins = {}

    def feed(self, records, interface, source, now):
        origin = (interface['name'], source.split('%')[0])
        if origin not in self.origins and len(self.origins) >= 64:
            return
        entries = self.origins.setdefault(origin, (interface, {}))[1]
        flushed = set()
        for name, kind, value, ttl, flush in records:
            group = (name, kind)
            if flush and group not in flushed:
                for key in list(entries):
                    if key[:2] == group:
                        del entries[key]
                flushed.add(group)
            key = (name, kind, value)
            if not ttl:
                entries.pop(key, None)
            elif len(entries) < 256 or key in entries:
                entries[key] = now + min(ttl, 120)

    def _groups(self, now):
        for origin, (interface, entries) in list(self.origins.items()):
            for key, expiry in list(entries.items()):
                if expiry <= now:
                    del entries[key]
            if not entries:
                del self.origins[origin]
                continue
            yield interface, list(entries)

    def receivers(self, now):
        found = {}
        for interface, records in self._groups(now):
            for instance, kind, value in records:
                if kind != 33 or not instance.endswith('.' + SERVICE):
                    continue
                port, target = value
                txt = {}
                for name, type_, data in records:
                    if name == instance and type_ == 16:
                        for entry in data:
                            key, _, content = entry.partition('=')
                            txt[key.lower()] = content
                prefix = instance[:-len('.' + SERVICE)]
                advertised = ' '.join((prefix, txt.get('model', ''), target)).lower()
                provider = next((name for name in PROVIDERS if name.lower() in advertised), None)
                if not provider:
                    continue
                for name, type_, host in records:
                    if name != target or type_ not in (1, 28):
                        continue
                    ip = ipaddress.ip_address(host)
                    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or not (ip.is_private or ip.is_link_local):
                        continue
                    if ip.version == 4 and (interface['network'] is None or ip not in interface['network']):
                        continue
                    if ip.version == 6 and ip.is_link_local:
                        host += '%' + interface['name']
                    identity = target + '|' + interface['name']
                    endpoint = dict(id=identity, name=provider, host=host, port=port,
                                    interface=interface['name'])
                    previous = found.get(identity)
                    if previous is None or ':' in previous['host'] and ip.version == 4:
                        found[identity] = endpoint
        return sorted(found.values(), key=lambda item: (item['name'], item['host'], item['port']))[:32]

    def questions(self, now):
        questions = {(SERVICE, 12)}
        for _, records in self._groups(now):
            for name, kind, value in records:
                if kind == 12 and name == SERVICE:
                    questions.update(((value, 33), (value, 16)))
                elif kind == 33 and name.endswith('.' + SERVICE):
                    questions.update(((name, 16), (value[1], 1), (value[1], 28)))
        return sorted(questions)[:64]


class Discovery:
    def __init__(self, update, interfaces=local_interfaces):
        self.update, self.interfaces = update, interfaces
        self.stop = threading.Event()

    def close(self):
        self.stop.set()

    @staticmethod
    def _socket(interface, family):
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                            interface['name'].encode() + b'\0')
            if family == socket.AF_INET:
                address = socket.inet_aton(interface['address'])
                sock.bind(('', 5353))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                socket.inet_aton('224.0.0.251') + address)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, address)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
                destination = ('224.0.0.251', 5353)
            else:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                sock.bind(('::', 5353))
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                                socket.inet_pton(socket.AF_INET6, 'ff02::fb') + struct.pack('@I', interface['index']))
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, interface['index'])
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
                destination = ('ff02::fb', 5353, 0, interface['index'])
            sock.setblocking(False)
            return sock, destination
        except BaseException:
            sock.close()
            raise

    def run(self, seconds=5):
        sockets, store = {}, RecordStore()
        error = ''
        try:
            interfaces = self.interfaces()
            if not interfaces:
                error = 'no local network interface'
            for interface in interfaces:
                for family in (socket.AF_INET, socket.AF_INET6):
                    if family == socket.AF_INET and not interface['address']:
                        continue
                    try:
                        sock, destination = self._socket(interface, family)
                        sockets[sock] = (interface, destination)
                    except OSError:
                        continue
            if interfaces and not sockets:
                error = 'local discovery unavailable'
            deadline, next_query = time.monotonic() + seconds, 0
            previous = None
            while sockets and not self.stop.is_set() and time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_query:
                    request = query(store.questions(now))
                    for sock, (_, destination) in sockets.items():
                        try:
                            sock.sendto(request, destination)
                        except OSError:
                            pass
                    next_query = now + 1
                ready, _, _ = select.select(list(sockets), [], [], .2)
                for sock in ready:
                    try:
                        data, source = sock.recvfrom(9001)
                        interface, _ = sockets[sock]
                        store.feed(parse_response(data), interface, source[0], time.monotonic())
                    except (OSError, ValueError, struct.error):
                        continue
                receivers = store.receivers(time.monotonic())
                if receivers != previous:
                    self.update(dict(scanning=True, receivers=receivers, error=''))
                    previous = receivers
        except Exception:
            error = 'local discovery unavailable'
        finally:
            for sock in sockets:
                sock.close()
            self.update(dict(scanning=False, receivers=store.receivers(time.monotonic()), error=error))
