"""Keep a user-requested connection available across receiver restarts."""
import threading
import traceback
from .session import Session


class Controller:
    def __init__(self, options, status, unlocked, iap_link=None, factory=Session, retry_delay=1):
        self.options, self.status, self.unlocked = options, status, unlocked
        self.iap_link = iap_link
        self.factory, self.retry_delay = factory, retry_delay
        self.current = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()

    def report(self, value):
        if value.startswith('failed at '):
            value = 'reconnecting after ' + value[len('failed at '):]
        self.status(value)

    def run(self):
        while not self.stop_event.is_set():
            with self.lock:
                if self.stop_event.is_set():
                    break
                # Each reconnect gets the requested control default and fresh input/capture.
                self.current = self.factory(self.options, self.report, self.unlocked)
                self.current.iap_link = self.iap_link
                session = self.current
            try:
                session.run()
            except Exception:
                traceback.print_exc()
            if self.stop_event.is_set():
                break
            self.status('waiting to reconnect')
            if self.stop_event.wait(self.retry_delay):
                break

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.current:
                self.current.close()
