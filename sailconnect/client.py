"""CLI session controller, also useful for repeatable device validation."""
import argparse
import json
import signal
import threading
import time


def main():
    import dbus
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host')
    parser.add_argument('--scan', action='store_true', help='discover WinPlay, LinuxPlay and MacPlay LAN receivers')
    parser.add_argument('--port', type=int, default=17000)
    parser.add_argument('--interface', default='')
    parser.add_argument('--native-width', type=int, default=0)
    parser.add_argument('--native-height', type=int, default=0)
    parser.add_argument('--rotation', type=int, default=0)
    parser.add_argument('--quality', type=int, choices=(0, 1, 2, 3), default=3, help='3=automatic, 0=full, 1=5/6, 2=2/3')
    parser.add_argument('--fps', type=int, choices=(15, 30, 60), default=30)
    parser.add_argument('--bitrate', type=int, default=4000000)
    parser.add_argument('--seconds', type=int, default=1800)
    control = parser.add_mutually_exclusive_group()
    control.add_argument('--view-only', action='store_true', help='disable remote control for this connection and its reconnects')
    control.add_argument('--control', action='store_true', help='enable remote control (the default; kept for compatibility)')
    args = parser.parse_args()
    if not args.scan and not args.host:
        parser.error('--host is required unless --scan is used')
    bus = dbus.SystemBus()
    api = dbus.Interface(bus.get_object('org.sailconnect.Control', '/org/sailconnect/Control'), 'org.sailconnect.Control')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    if args.scan:
        api.ScanReceivers()
        deadline = time.monotonic() + 10
        while not stop.is_set() and time.monotonic() < deadline:
            result = json.loads(str(api.DiscoveryStatus()))
            if not result['scanning']:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            stop.wait(.2)
        raise RuntimeError('receiver discovery timed out')
    api.StartWithControl(args.host, dbus.Int32(args.port), args.interface, dbus.Int32(args.native_width),
              dbus.UInt32(args.native_height), dbus.Int32(args.rotation), dbus.Int32(args.quality),
              dbus.Int32(args.fps), dbus.Int32(args.bitrate), dbus.Boolean(not args.view_only))
    previous = None
    deadline = time.monotonic() + 120
    video_started = False
    try:
        while not stop.is_set() and time.monotonic() < deadline:
            raw = str(api.Status())
            status = json.loads(raw)
            if raw != previous:
                print(time.strftime('%Y-%m-%d %H:%M:%S'), raw, flush=True)
                previous = raw
            if status['state'].startswith('failed') or status['state'] == 'stopped':
                break
            if not video_started and status['state'].startswith('streaming'):
                video_started = True
                deadline = time.monotonic() + args.seconds
            stop.wait(.5)
    finally:
        api.Stop()


if __name__ == '__main__':
    main()
