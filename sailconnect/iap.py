"""Sailplay iAP2 phone-role link, without vehicle/navigation or network changes."""
import hashlib
import logging
import os
import socket
import struct
import time
import uuid
from carplay_proto.runtime_logging import socket_endpoint
from carplay_proto.iap2link import ACK, DETECT, EAK, RST, SYN, Decoder, Packet, encode, parse_synchronization
from carplay_proto.wire import Frame, Framer, encode_param, parse_params
from carplay_proto.accessoryauth import PinnedAccessory, paired_accessory
from carplay_proto.wireless import parse_wifi_configuration, peer_supports_wifi_configuration_request, request_wifi_configuration, parse_start_session
INITIAL_UPDATES = {0xae00: 0xae01, 0x4157: 0x4158, 0x5000: 0x5001, 0x4c00: 0x4c01}
PHONE_UUID = '00000000-deca-fade-deca-deafdecacafe'
IAP_V2_UUID = '02030302-1d19-415f-86f2-22a2106a0a77'

def text_value(payload):
    return payload.split(b'\x00', 1)[0].decode('utf-8', 'replace')

def payload_hex(payload, limit=512):
    suffix = '...' if len(payload) > limit else ''
    return payload[:limit].hex() + suffix

def parse_ea_protocols(frame):
    protocols = []
    for parameter in frame.parameters():
        if parameter.id != 10:
            continue
        try:
            nested = {item.id: item.payload for item in parse_params(parameter.payload)}
        except ValueError:
            logging.warning('invalid EA protocol group=%d payload=%s',
                            parameter.id, payload_hex(parameter.payload))
            continue
        identifier = nested.get(0, b'')[:1]
        if not identifier:
            continue
        name = text_value(nested.get(1, b''))
        protocols.append((identifier[0], name))
        logging.info('EA protocol id=%d name=%r', identifier[0], name)
    return protocols

def parse_component_ids(frame):
    identifiers = []
    for parameter in frame.parameters():
        if parameter.id != 0:
            continue
        if len(parameter.payload) != 2:
            logging.warning('invalid Bluetooth component identifier payload=%s',
                            payload_hex(parameter.payload))
            continue
        identifiers.append(struct.unpack('>H', parameter.payload)[0])
    return identifiers

def service_record(channel):
    if not 1 <= channel <= 30:
        raise ValueError('invalid RFCOMM channel')
    return '''<?xml version="1.0"?>
<record>
 <attribute id="0x0001"><sequence><uuid value="%s"/><uuid value="%s"/></sequence></attribute>
 <attribute id="0x0004"><sequence>
  <sequence><uuid value="0x0100"/></sequence>
  <sequence><uuid value="0x0003"/><uint8 value="%d"/></sequence>
 </sequence></attribute>
 <attribute id="0x0005"><sequence><uuid value="0x1002"/></sequence></attribute>
 <attribute id="0x0009"><sequence><sequence>
  <uuid value="0x1101"/><uint16 value="0x0102"/>
 </sequence></sequence></attribute>
 <attribute id="0x0100"><text value="Wireless iAP v2"/></attribute>
</record>''' % (PHONE_UUID, IAP_V2_UUID, channel)

def probe(sock, stop, duration, certificate_out=None, accessory_key=None,
          announce_wireless=False, local_address=None, session_out=None, wifi_handover=False,sustained=False,
          local_name='SailfishOS', paired_pin_path=None, on_authenticated=None,
          transport='bluetooth', connection_role='unknown', bluetooth_device=None, on_start=None):
    started = time.monotonic()
    phase = 'detection'
    received_bytes = 0
    exit_reason = 'duration'
    decoder, csm = Decoder(), Framer()
    deadline = time.monotonic() + duration if duration else float('inf')
    sync_at = 0
    peer_syn = False
    local_syn_acked = False
    last_rx = None
    session = None
    negotiated = False
    outgoing = []
    pending = None
    sequence = 0
    retry_at = 0
    retries = 0
    detection_deadline = time.monotonic() + 15
    authenticator = None
    authenticated = False
    peer_received_messages = set()
    wifi_config = None
    sock.settimeout(0.2)
    try:
        authenticator = PinnedAccessory(accessory_key) if accessory_key else None
        while not stop.is_set() and time.monotonic() < deadline:
            now = time.monotonic()
            if not negotiated and now >= detection_deadline:
                raise ValueError('iAP2 handshake timeout; release RFCOMM for retry')
            if sync_at and not local_syn_acked and now >= sync_at:
                sock.sendall(encode(Packet(SYN | ACK, 0, last_rx, 0, sync_payload)))
                sync_at = now + 1
            if negotiated and pending is None and outgoing:
                sequence = (sequence + 1) & 255
                frame = outgoing.pop(0)
                logging.info('CSM tx message=0x%04x body_bytes=%d', frame.message_id, len(frame.body))
                pending = Packet(ACK, sequence, last_rx, session, frame.encoded())
                retries = 0
                retry_at = 0
            if pending is not None and now >= retry_at:
                if retries >= 5:
                    raise ValueError('control packet acknowledgement timeout')
                sock.sendall(encode(pending._replace(acknowledgement=last_rx)))
                retries += 1
                retry_at = now + 1
            try:
                raw = sock.recv(4096)
            except socket.timeout:
                continue
            if not raw:
                exit_reason = 'peer EOF'
                break
            received_bytes += len(raw)
            for packet in decoder.feed(raw):
                if transport == 'airplay':
                    if packet == DETECT:
                        logging.info('link rx DETECT')
                    else:
                        logging.info('link rx control=0x%02x seq=%d ack=%d session=%s bytes=%d',
                                     packet.control, packet.sequence, packet.acknowledgement,
                                     packet.session, len(packet.payload or b''))
                if packet == DETECT:
                    if not sync_at:
                        logging.info('peer iAP2 detection confirmed')
                        # Phone is the iAP2 host: echo DETECT and wait for accessory SYN.
                        sock.sendall(DETECT)
                    elif transport == 'airplay':
                        # The head unit dropped this link and is starting over;
                        # end it so the tunnel answers the next DETECT afresh.
                        raise ValueError('peer restarted the iAP2 link (DETECT after sync)')
                    continue
                if packet.control & RST:
                    raise ValueError('peer reset link')
                if packet.control & SYN:
                    phase = 'synchronization'
                    limits, sessions = parse_synchronization(packet.payload or b'')
                    logging.info('peer SYN limits=%s sessions=%s', limits, sessions)
                    controls = [s[0] for s in sessions if s[1] == 0 and s[2] in (1, 2)]
                    if not controls:
                        raise ValueError('peer has no compatible control session')
                    session = controls[0]
                    peer_syn = True
                    last_rx = packet.sequence
                    sync_payload = packet.payload
                    sock.sendall(encode(Packet(SYN | ACK, 0, last_rx, 0, sync_payload)))
                    sync_at = time.monotonic() + 1
                if sync_at and packet.control & ACK and packet.acknowledgement == 0:
                    local_syn_acked = True
                if pending is not None and packet.control & ACK and packet.acknowledgement == pending.sequence:
                    pending = None
                if peer_syn and local_syn_acked and not negotiated:
                    negotiated = True
                    phase = 'identification'
                    outgoing.append(Frame(0x1d00, b''))
                    logging.info('iAP2 link negotiated; requesting accessory identification elapsedMs=%.1f',
                                 (time.monotonic() - started) * 1000)
                if packet.control & EAK:
                    logging.warning('peer extended ACK; probe has no queued control packets')
                if packet.control & ~(ACK) == 0 and packet.payload is not None:
                    if not negotiated:
                        raise ValueError('data before synchronization completed')
                    if packet.sequence == ((last_rx + 1) & 255):
                        last_rx = packet.sequence
                        if packet.session == session:
                            for frame in csm.offer(packet.payload):
                                # Never log Wi-Fi credentials or authentication bodies.
                                logging.info('CSM rx message=0x%04x body_bytes=%d',
                                             frame.message_id, len(frame.body))
                                if transport == 'airplay' and frame.message_id not in (
                                        0xaa01, 0xaa03, 0x5703, 0x4301):
                                    # Bodies identify what the head unit expects
                                    # next; credentials and auth are never logged.
                                    logging.info('CSM rx body=%s', payload_hex(frame.body, 4096))
                                if frame.message_id == 0x1d01:
                                    identity = {}
                                    for parameter in frame.parameters():
                                        if parameter.id in (0, 1, 2):
                                            identity[parameter.id] = text_value(parameter.payload)
                                        elif parameter.id in (6, 7):
                                            if len(parameter.payload) % 2:
                                                raise ValueError('invalid supported-message list')
                                            ids = list(struct.unpack('>' + 'H' * (len(parameter.payload) // 2), parameter.payload))
                                            logging.info('accessory %s message IDs=%s',
                                                         'sent' if parameter.id == 6 else 'received',
                                                         ','.join('0x%04x' % value for value in ids))
                                            if parameter.id == 7:
                                                peer_received_messages = set(ids)
                                    logging.info('accessory identity name=%r model=%r manufacturer=%r',
                                                 identity.get(0, ''), identity.get(1, ''), identity.get(2, ''))
                                    logging.info('identification parameter ids=%s',
                                                 [(parameter.id, len(parameter.payload))
                                                  for parameter in frame.parameters()])
                                    parse_ea_protocols(frame)
                                    outgoing.extend([Frame(0x1d02, b''), Frame(0xaa00, b'')])
                                elif frame.message_id == 0xaa01:
                                    phase = 'authentication'
                                    parameters = frame.parameters()
                                    certificates = [p.payload for p in parameters if p.id == 0]
                                    if len(certificates) != 1 or not certificates[0]:
                                        raise ValueError('invalid accessory certificate message')
                                    certificate = certificates[0]
                                    logging.info('accessory certificate sha256=%s bytes=%d',
                                                 hashlib.sha256(certificate).hexdigest(), len(certificate))
                                    if certificate_out:
                                        descriptor = os.open(certificate_out, os.O_WRONLY | os.O_CREAT |
                                                             os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                                        with os.fdopen(descriptor, 'wb') as output:
                                            output.write(certificate)
                                    if paired_pin_path:
                                        authenticator = paired_accessory(certificate, paired_pin_path, authenticator)
                                    if authenticator:
                                        logging.info('accessory authentication algorithm=%s key_bits=%d public_key_bytes=%d challenge_bytes=%d',
                                                     authenticator.algorithm, authenticator.key_info['key_bits'],
                                                     len(authenticator.public_key), authenticator.key_info['challenge_bytes'])
                                        challenge = authenticator.begin(certificate)
                                        outgoing.append(Frame(0xaa02, encode_param(0, challenge)))
                                        logging.info('accessory certificate selected; random challenge queued')
                                    else:
                                        logging.info('accessory certificate received; challenge verification disabled')
                                elif frame.message_id == 0xaa03:
                                    if not authenticator or authenticated:
                                        raise ValueError('unexpected authentication response')
                                    signatures = [p.payload for p in frame.parameters() if p.id == 0]
                                    if len(signatures) != 1:
                                        raise ValueError('invalid authentication response')
                                    logging.info('accessory challenge response algorithm=%s signature_bytes=%d',
                                                 authenticator.algorithm, len(signatures[0]))
                                    authenticator.verify(signatures[0])
                                    authenticated = True
                                    phase = 'authenticated'
                                    logging.info('iAP2 accessory authenticated elapsedMs=%.1f',
                                                 (time.monotonic() - started) * 1000)
                                    if on_authenticated:
                                        on_authenticated()
                                    outgoing.append(Frame(0xaa05, b''))
                                    if transport != 'airplay':
                                        # EA sessions require a matching accessory application.
                                        if peer_supports_wifi_configuration_request(peer_received_messages):
                                            outgoing.append(request_wifi_configuration())
                                            logging.info('pinned accessory challenge signature VERIFIED; '
                                                         'Wi-Fi configuration request queued after authentication')
                                        else:
                                            logging.info('pinned accessory challenge signature VERIFIED; '
                                                         'waiting for notification-driven Wi-Fi handover '
                                                         '(peer does not advertise 0x5702)')
                                    if announce_wireless:
                                        if not local_address:
                                            raise ValueError('missing local Bluetooth transport identity')
                                        device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'org.sailconnect:' + local_address)).upper()
                                        outgoing.extend([
                                            Frame(0x4e0c, encode_param(0, device_id.encode('ascii') + b'\x00')),
                                            Frame(0x4e09, encode_param(0, local_name.encode('utf-8') + b'\x00')),
                                            Frame(0x4e0e, encode_param(0, local_address.encode('ascii') + b'\x00')),
                                            Frame(0x4e0d, encode_param(0, b'\x01')),
                                        ])
                                        if 0x4300 in peer_received_messages:
                                            # Existing xcertplay receiver's grouped availability layout.
                                            wired = encode_param(0, b'\x00')
                                            wireless = (encode_param(0, b'\x01') +
                                                        encode_param(1, local_address.encode('ascii') + b'\x00'))
                                            outgoing.append(Frame(0x4300, encode_param(0, wired) +
                                                                   encode_param(1, wireless)))
                                            logging.info('HU advertises 4300; diagnostic grouped CarPlayAvailability queued')
                                        logging.info('DIAGNOSTIC wireless capability notification queued; no media sender yet')
                                    if transport == 'airplay':
                                        # Wi-Fi is already up; only the link and
                                        # authentication are needed here.
                                        logging.info('iAP2 over AirPlay: accessory authenticated')
                                        for frame in device_notifications(local_name, local_address,
                                                                          peer_received_messages):
                                            outgoing.append(frame)
                                            logging.info('device notification queued message=0x%04x',
                                                         frame.message_id)
                                        # A CarPlay accessory's wireless control sequence
                                        # expects the device to request the Wi-Fi
                                        # configuration on this link too (it lists 0x5702
                                        # as received and answers with 0x5703).
                                        if peer_supports_wifi_configuration_request(peer_received_messages):
                                            outgoing.append(request_wifi_configuration())
                                            logging.info('Wi-Fi configuration requested over AirPlay link')
                                elif authenticated and frame.message_id in INITIAL_UPDATES:
                                    reply = initial_update(frame, peer_received_messages)
                                    if reply is not None:
                                        outgoing.append(reply)
                                        logging.info('initial update queued message=0x%04x for request=0x%04x body=%s',
                                                     reply.message_id, frame.message_id, payload_hex(reply.body))
                                    else:
                                        logging.info('no initial update for request=0x%04x', frame.message_id)
                                elif frame.message_id == 0x4e01:
                                    logging.info('Bluetooth component information body=%s', payload_hex(frame.body))
                                elif frame.message_id == 0x4e03:
                                    component_ids = parse_component_ids(frame)
                                    logging.info('Bluetooth connection updates requested components=%s body=%s',
                                                 component_ids, payload_hex(frame.body))
                                    for component_id in component_ids:
                                        profiles = encode_param(7, b'')
                                        outgoing.append(Frame(0x4e04,
                                                              encode_param(0, struct.pack('>H', component_id)) +
                                                              encode_param(1, profiles)))
                                        logging.info('Bluetooth connection update queued component=%d profiles=iAP2Link',
                                                     component_id)
                                elif frame.message_id == 0x4e05:
                                    logging.info('Bluetooth connection updates stopped body=%s', payload_hex(frame.body))
                                elif frame.message_id == 0xea02:
                                    bundle = ''
                                    for parameter in frame.parameters():
                                        if parameter.id == 0:
                                            bundle = text_value(parameter.payload)
                                    logging.info('accessory app launch requested bundle=%r body=%s',
                                                 bundle, payload_hex(frame.body))
                                elif frame.message_id == 0xea03:
                                    logging.info('EA session status body=%s', payload_hex(frame.body))
                                elif frame.message_id == 0x5703:
                                    if not authenticated:
                                        raise ValueError('Wi-Fi credentials arrived before authentication')
                                    config = parse_wifi_configuration(frame)
                                    wifi_config = config
                                    logging.info('accessory Wi-Fi configuration received: %r', config)
                                    # Some head units (Honda) never send
                                    # CarPlayStartSession over Bluetooth; they
                                    # expect the phone to join their access point
                                    # and find AirPlay on the default port.

                                elif frame.message_id == 0x4301:
                                    if not authenticated:
                                        raise ValueError('StartSession before authentication')
                                    start = parse_start_session(frame, wifi_config)
                                    logging.info('parsed CarPlay StartSession: %r', start)
                                    if on_start:
                                        on_start(start)
                    elif packet.sequence != last_rx:
                        # A stale window means this RFCOMM link is poisoned;
                        # exit and let the advertiser relaunch a clean probe.
                        raise ValueError('out-of-order packet; restarting probe')
                    # An ACK-only packet carries our last sent sequence number;
                    # head units ignore one numbered 0 and keep retransmitting.
                    sock.sendall(encode(Packet(ACK, sequence, last_rx, 0, None)))
        logging.info('probe ended; checksum errors=%d', decoder.errors)
    except (OSError, ValueError):
        exit_reason = 'failure'
        logging.exception('probe failed transport=%s role=%s phase=%s elapsedMs=%.1f receivedBytes=%d',
                          transport, connection_role, phase, (time.monotonic() - started) * 1000, received_bytes)
    finally:
        logging.info('iAP2 connection ended transport=%s role=%s phase=%s reason=%s elapsedMs=%.1f receivedBytes=%d negotiated=%s authenticated=%s',
                     transport, connection_role, phase, 'stopped' if stop.is_set() else exit_reason,
                     (time.monotonic() - started) * 1000, received_bytes, negotiated, authenticated)
        if transport == 'bluetooth':
            # BlueZ retains a duplicate of the handed-over RFCOMM descriptor.
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        sock.close()

def battery_charge_level(path='/sys/class/power_supply/battery/capacity'):
    """Battery level scaled to iAP2's 0..65535 range, or None."""
    try:
        with open(path) as source:
            percent = max(0, min(100, int(source.read().strip())))
    except (OSError, ValueError):
        return None
    return percent * 65535 // 100

def initial_update(request, received_message_ids):
    """Minimal first update for a Start... request, or None.

    Only the battery level is filled in (PowerUpdate parameter 6, the only
    one the Honda asks for). The other updates are sent empty, meaning
    nothing to report: no call data, nothing playing, no media library.
    """
    reply_id = INITIAL_UPDATES.get(request.message_id)
    if reply_id is None or (received_message_ids and reply_id not in received_message_ids):
        return None
    if reply_id == 0xae01:
        requested = {parameter.id for parameter in request.parameters()}
        level = battery_charge_level()
        body = encode_param(6, struct.pack('>H', level)) if 6 in requested and level is not None else b''
        return Frame(0xae01, body)
    return Frame(reply_id, b'')

def device_language():
    language = (os.environ.get('LANG') or 'en').split('_')[0].split('.')[0].lower()
    return language if language.isalpha() and 2 <= len(language) <= 3 else 'en'

def device_notifications(local_name, local_address, received_message_ids):
    """Device updates an iPhone sends once the accessory is authenticated.

    Only messages the accessory lists as received are sent; an empty list
    (no identification parameters) sends all of them.
    """
    frames = [Frame(0x4e09, encode_param(0, local_name.encode('utf-8') + b'\x00'))]
    if local_address:
        device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'org.sailconnect:' + local_address)).upper()
        frames[:0] = [Frame(0x4e0c, encode_param(0, device_id.encode('ascii') + b'\x00'))]
        frames.append(Frame(0x4e0e, encode_param(0, local_address.encode('ascii') + b'\x00')))
    frames.append(Frame(0x4e0a, encode_param(0, device_language().encode('ascii') + b'\x00')))
    frames.append(Frame(0x4e0d, encode_param(0, b'\x01')))
    if received_message_ids:
        frames = [frame for frame in frames if frame.message_id in received_message_ids]
    return frames
