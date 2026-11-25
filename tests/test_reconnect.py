import pytest
from sailconnect.controller import Controller
from sailconnect.geometry import stream_size
from sailconnect.session import Session as RealSession


def test_auto_resolution_tracks_receiver_without_double_downscale():
    assert stream_size(dict(widthPixels=1920, heightPixels=1080), 3, 60) == (1280, 720)
    assert stream_size(dict(widthPixels=1280, heightPixels=720), 3, 60) == (1280, 720)
    assert stream_size(dict(widthPixels=1920, heightPixels=1080), 3, 30) == (1920, 1080)


@pytest.mark.parametrize('control', [True, False])
def test_reconnect_applies_control_default_after_old_session_cleanup(control):
    created, states = [], []
    class Session(RealSession):
        def __init__(self, options, status, unlocked):
            super().__init__(options, status, unlocked)
            self.closed = False
            created.append(self)
        def close(self):
            super().close()
            self.closed = True
            self.allow = False
        def run(self):
            assert self.allow is control
            assert not self.ready
            if len(created) == 1:
                self.control(False)
                try:
                    raise RuntimeError('receiver restarted')
                finally:
                    self.close()
            assert created[0].closed and not created[0].allow
            assert self.allow is control
            controller.stop()
    options = {} if control else {'control': False}
    link = lambda *args: None
    controller = Controller(options, states.append, lambda: True, iap_link=link, factory=Session, retry_delay=0)
    controller.run()
    assert len(created) == 2
    assert all(s.closed and not s.allow for s in created)
    assert all(s.iap_link is link for s in created)
    assert 'waiting to reconnect' in states


def test_stop_before_start_does_not_create_session():
    created = []
    controller = Controller({}, lambda _: None, lambda: True, factory=lambda *a: created.append(a))
    controller.stop()
    controller.run()
    assert not created
