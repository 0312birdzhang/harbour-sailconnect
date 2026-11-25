"""Owned H.264 capture lifecycle helpers, forked from Sailplay."""
import os

import fcntl

import re

import select

import signal

import subprocess

import time
import stat

def child_pids(parent, proc='/proc'):
    """Direct children of parent.

    Uses /proc/PID/task/PID/children when the kernel provides it
    (CONFIG_PROC_CHILDREN); otherwise scans the PPid field of every
    /proc/*/stat, which works on any kernel.
    """
    try:
        with open('{0}/{1}/task/{1}/children'.format(proc, parent)) as source:
            return [int(pid) for pid in source.read().split()]
    except FileNotFoundError:
        pass
    children = []
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open('{}/{}/stat'.format(proc, name)) as source:
                stat = source.read()
        except OSError:
            continue
        # The command name may contain spaces or parentheses; PPid is the
        # second field after its closing parenthesis.
        fields = stat.rsplit(')', 1)[-1].split()
        if len(fields) > 1 and fields[1] == str(parent):
            children.append(int(name))
    return sorted(children)

class AnnexBFrames:
    def __init__(self):
        self.buffer = b''
        self.sps = self.pps = None
        self.current = []
        self.started = False

    def feed(self,data):
        import re
        self.buffer += data
        if len(self.buffer)>8*1024*1024:
            raise ValueError('capture NAL exceeds limit')
        matches=list(re.finditer(b'\x00\x00\x00?\x01',self.buffer))
        frames=[]
        for left,right in zip(matches,matches[1:]):
            nal=self.buffer[left.end():right.start()]
            if not nal:
                continue
            kind=nal[0]&31
            if kind in (7,8):
                if kind==7:
                    self.sps=nal
                else:
                    self.pps=nal
            elif kind in (1,5):
                if len(nal)<2:
                    raise ValueError('truncated slice')
                if nal[1]&128 and self.current:
                    frames.append(self.current)
                    self.current=[]
                if kind==5 and self.sps and self.pps:
                    self.started=True
                if self.started:
                    self.current.append(nal)
        if matches:
            self.buffer=self.buffer[matches[-1].start():]
        return frames

    def config(self):
        import struct
        if not self.sps or not self.pps:
            raise ValueError('capture configuration missing')
        s,p=self.sps,self.pps
        return bytes([1,s[1],s[2],s[3],255,225])+struct.pack('>H',len(s))+s+b'\x01'+struct.pack('>H',len(p))+p

class DisplayPipeline:
    def __init__(self,width=1920,height=720,fps=30,encoded_width=None,encoded_height=None):
        self.width,self.height,self.fps=width,height,fps
        self.encoded_width = encoded_width or width
        self.encoded_height = encoded_height or height
        self.processes=[]
        self.logs=[]
        self.ui=None
        self.comp=None
        self.fd=None
        self.lock_fd=None
        self.fifo=None
        self.fifo_identity=None

    def request_keyframe(self):
        # su remains as a parent; never signal the entire group, which would
        # also terminate su. Validate the executable and this pipeline's FIFO.
        parent = self.capture.pid
        if not os.path.exists('/proc/{}'.format(parent)):
            raise RuntimeError('capture process exited before keyframe request')
        candidates = [parent] + child_pids(parent)
        for pid in candidates:
            try:
                executable = os.readlink('/proc/{}/exe'.format(pid))
                if executable != '/opt/sailconnect/carlife-capture':
                    continue
                with open('/proc/{}/cmdline'.format(pid), 'rb') as source:
                    arguments = source.read().split(b'\0')
                if self.fifo.encode() in arguments:
                    os.kill(pid, signal.SIGUSR1)
                    return
            except FileNotFoundError:
                continue
        raise RuntimeError('owned capture process not found for keyframe request')

    def frames(self,seconds):
        parser=AnnexBFrames()
        deadline=time.monotonic()+seconds if seconds else float('inf')
        last_data=time.monotonic()
        while time.monotonic()<deadline:
            self.check_health()
            if self.capture.poll() is not None:
                raise RuntimeError('capture exited')
            ready,_,_=select.select([self.fd],[],[],.2)
            if ready:
                data=os.read(self.fd,65536)
                if not data:
                    time.sleep(.02)
                    continue
                last_data=time.monotonic()
                for frame in parser.feed(data):
                    yield parser.config(),frame
            if time.monotonic()-last_data>8:
                raise TimeoutError('capture produced no frames')

    def close(self):
        for process in reversed(self.processes):
            try:
                os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(.3)
        for process in reversed(self.processes):
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        self.processes = []
        self.comp = self.ui = self.capture = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        for log in self.logs:
            log.close()
        self.logs = []
        if self.fifo is not None and os.path.lexists(self.fifo):
            info = os.lstat(self.fifo)
            if stat.S_ISFIFO(info.st_mode) and self.fifo_identity == (info.st_dev, info.st_ino):
                os.unlink(self.fifo)
            else:
                print('Preserving replaced capture path: {}'.format(self.fifo), flush=True)
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd=None
