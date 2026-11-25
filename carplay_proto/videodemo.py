"""CarPlay screen framing, event channel and feedback (from Sailplay)."""
import re

import socket

import struct

import threading

import time

import plistlib

import os

import stat

import copy

from . import crypto

from .controlcipher import ControlCipher

from .rtspclient import EncryptedSocket, connect

def describe_params(value, limit=64):
    """Summarise a command plist for the log, shortening binary payloads."""
    if isinstance(value, dict):
        return {key: describe_params(item, limit) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [describe_params(item, limit) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return 'bytes[{}]:{}{}'.format(len(value), bytes(value[:limit]).hex(),
                                       '...' if len(value) > limit else '')
    return value

def screen_packet_profile(info):
    identity = str(info.get('manufacturer', '')).lower()
    model = str(info.get('model', '')).upper()
    return 'legacy' if 'desay' in identity or model == 'WILDLANDER' else 'ios'

class ScreenEncoder:
    def __init__(self, shared, stream_id, packet_profile='ios'):
        if packet_profile not in ('ios', 'legacy'):
            raise ValueError('unknown screen packet profile')
        self.packet_profile = packet_profile
        self.key = crypto.hkdf_sha512(shared, ('DataStream-Salt'+str(stream_id)).encode(),
                                     b'DataStream-Output-Encryption-Key',32)
        self.counter = 0
        from .nativecrypto import NativeChaCha
        self.native = NativeChaCha(self.key)

    @staticmethod
    def _timestamp(timestamp_ns):
        seconds, fraction = divmod(timestamp_ns,1000000000)
        return (seconds << 32) | ((fraction << 32)//1000000000)

    def _header(self,size,payload_type,timestamp_ns,width,height,idr=False):
        # AirPlay screen packets: little-endian size, 2-byte type, 2-byte
        # option, then a fixed-point NTP timestamp. IDR slices are flagged in
        # the second type byte; receivers that ignore the flag still parse the
        # VCL NAL type, but strict head units need it.
        header = bytearray(128)
        struct.pack_into('<I',header,0,size)
        header[4] = payload_type
        if self.packet_profile == 'legacy':
            if payload_type == 1:
                header[6] = 4
                struct.pack_into('<ff',header,16,width,height)
            else:
                struct.pack_into('<Q',header,8,self._timestamp(timestamp_ns))
            return header
        header[5] = 0x10 if idr else 0
        struct.pack_into('<H',header,6,6)
        struct.pack_into('<Q',header,8,self._timestamp(timestamp_ns))
        if payload_type == 1:
            struct.pack_into('<ff',header,16,width,height)
        struct.pack_into('<ff',header,40,width,height)
        struct.pack_into('<ff',header,56,max(0,width-1),max(0,height-1))
        return header

    def config(self, avcc, width, height, timestamp_ns=None):
        if timestamp_ns is None:
            timestamp_ns = time.monotonic_ns()
        header = self._header(len(avcc),1,timestamp_ns,width,height)
        # Unencrypted H.264 SPS/PPS packet option used by iOS senders.
        if self.packet_profile == 'ios':
            header[6:8] = b'\x16\x01'
        return bytes(header)+avcc

    def frame(self, nals, timestamp_ns, width, height):
        body = b''.join(struct.pack('>I',len(n))+n for n in nals)
        idr = any(n and (n[0] & 31) == 5 for n in nals)
        header = self._header(len(body)+16,0,timestamp_ns,width,height,idr)
        encrypted = self.native.seal(crypto.nonce64(self.counter),body,bytes(header))
        self.counter += 1
        return bytes(header)+encrypted

class DemoEvents:
    def __init__(self,address,port,interface,shared,handler=None):
        self.handler=handler
        self.received = 0
        self.last_received = None
        transport = connect(address,port,interface)
        # The touch channel can be idle for minutes while video stays busy.
        transport.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        transport.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)
        transport.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        transport.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        transport.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Events is an inbound request channel: phone acts as RTSP server.
        read = crypto.hkdf_sha512(shared,b'Events-Salt',b'Events-Write-Encryption-Key',32)
        write = crypto.hkdf_sha512(shared,b'Events-Salt',b'Events-Read-Encryption-Key',32)
        self.sock = EncryptedSocket(transport.sock,ControlCipher(read,write))
        self.sock.sock.settimeout(None)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        buf = b''
        try:
            while not self.stop.is_set():
                while b'\r\n\r\n' not in buf:
                    block = self.sock.recv(16384)
                    if not block:
                        print('Demo event channel closed by head unit (received={})'.format(self.received),flush=True)
                        return
                    buf += block
                    if len(buf)>65536:
                        raise ValueError('event header too large')
                head,buf = buf.split(b'\r\n\r\n',1)
                lines = head.decode('ascii').split('\r\n')
                headers = dict(line.lower().split(':',1) for line in lines[1:])
                size = int(headers.get('content-length','0'))
                if not 0<=size<=1048576:
                    raise ValueError('event body too large')
                while len(buf)<size:
                    block = self.sock.recv(16384)
                    if not block:
                        print('Demo event channel closed by head unit (received={})'.format(self.received),flush=True)
                        return
                    buf += block
                body,buf = buf[:size],buf[size:]
                self.received += 1
                self.last_received = time.monotonic()
                print('Demo event: {} bytes={}'.format(lines[0],size),flush=True)
                code=200
                reply=b''
                if body:
                    try:
                        value = plistlib.loads(body)
                        print('Demo event keys={}'.format(sorted(value)),flush=True)
                        print('Event command type={}'.format(value.get('type')),flush=True)
                        if value.get('type') not in ('hidSendReport','forceKeyFrame'):
                            print('Event command detail={}'.format(describe_params(value)),flush=True)
                        if self.handler and lines[0].split()[1]=='/command':
                            result=self.handler(value)
                            if result is not None:
                                reply=plistlib.dumps(result,fmt=plistlib.FMT_BINARY)
                    except Exception as error:
                        print('Event handler failed: {}: {}'.format(type(error).__name__,error),flush=True)
                        code=400
                self.sock.sendall(('RTSP/1.0 {} {}\r\nCSeq: {}\r\nContent-Type: application/x-apple-binary-plist\r\nContent-Length: {}\r\n\r\n'.format(
                    code,'OK' if code==200 else 'Bad Request',headers.get('cseq','0').strip(),len(reply))).encode()+reply)
        except Exception as error:
            if not self.stop.is_set():
                print('Demo event channel: {}: {}'.format(type(error).__name__,error),flush=True)
        finally:
            self.stop.set()

    def close(self):
        self.stop.set()
        try:
            self.sock.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self.thread.join(1)

class ScreenFeedback:
    """Keep control requests away from the video producer's critical path."""
    def __init__(self,client,commands=None,modes=None,resume=None,screen=None,resource_changed=None,audio=None,duck=None,mode_lock=None,mode_revision=None):
        self.client=client
        self.commands=commands
        self.modes=modes
        self.resume=resume
        self.screen=screen
        self.resource_changed=resource_changed
        self.audio=audio
        self.duck=duck if duck is not None else [1.0]
        self.mode_lock=mode_lock or threading.RLock()
        self.mode_revision=mode_revision if mode_revision is not None else [0]
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        next_feedback=time.monotonic()+2
        while not self.stop.wait(0.1):
            try:
                returning=self.commands and self.commands.return_requested()
                resuming=(self.resume is not None and self.resume.is_set()) or (self.commands and self.commands.resume.is_set())
                changed=self.resource_changed is not None and self.resource_changed.is_set()
                if returning or resuming or changed:
                    if changed:self.resource_changed.clear()
                    if resuming:
                        if self.resume is not None:
                            self.resume.clear()
                        if self.commands:
                            self.commands.resume.clear()
                    reason='CarPlay' if resuming else 'OEM' if returning else 'HU resource transfer'
                    print('Screen ownership command: '+reason,flush=True)
                    with self.mode_lock:
                        revision=self.mode_revision[0]
                        proposed=copy.deepcopy(self.modes)
                    if resuming:
                        # Native MODE switches deliver Play + requestUI after
                        # taking BOTH resources for FM. Reclaim both together.
                        for resource in proposed['resources']:
                            if resource['resourceID'] in (1,2):resource.update(entity=1,permanentEntity=1)
                    elif returning:
                        next(r for r in proposed['resources'] if r['resourceID']==1).update(entity=2,permanentEntity=2)
                    owner=next(r['entity'] for r in proposed['resources'] if r['resourceID']==1)
                    payload=plistlib.dumps({'type':'modesChanged','params':proposed},fmt=plistlib.FMT_BINARY)
                    status,_,body=self.client.request('POST','/command',payload,
                        {'Content-Type':'application/x-apple-binary-plist'})
                    command_status=plistlib.loads(body).get('status',0) if body else 0
                    accepted=status==200 and command_status==0
                    if accepted:
                        with self.mode_lock:
                            current=self.mode_revision[0]==revision
                            if current:
                                self.modes.update(proposed)
                                self.mode_revision[0]+=1
                                if self.audio:
                                    entity=next(r['entity'] for r in self.modes['resources'] if r['resourceID']==2)
                                    self.audio.gain=self.duck[0] if entity==1 else 0.0
                                    print('Audio resource reconciled entity={} senderGain={}'.format(entity,self.audio.gain),flush=True)
                        if current and self.screen:self.screen.ownership(owner)
                        elif not current and self.resource_changed is not None:self.resource_changed.set()
                    elif changed:
                        raise RuntimeError('HU resource notification rejected')
                    print('Screen ownership response owner={} status={} command_status={} accepted={}'.format(owner,status,command_status,accepted),flush=True)
                if time.monotonic()<next_feedback:
                    continue
                status,_,body=self.client.request('POST','/feedback',headers={'User-Agent':'AirPlay/566.25.21'})
                next_feedback=time.monotonic()+2
                print('Screen feedback status={} bytes={}'.format(status,len(body)),flush=True)
            except Exception as error:
                print('Screen feedback failed: {}: {}'.format(type(error).__name__,error),flush=True)
                self.stop.set()
                return

    def close(self):
        self.stop.set()
        self.thread.join(6)
