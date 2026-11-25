import subprocess
from types import SimpleNamespace

import pytest

from sailconnect.service import stop_sailplay


@pytest.mark.parametrize('load', ['loaded', 'not-found'])
def test_optional_service_stop(monkeypatch, load):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=load + '\n', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    stop_sailplay()
    assert len(calls) == (1 if load == 'not-found' else 2)
    if load == 'loaded':
        assert calls[1] == ['/usr/bin/systemctl', 'stop', 'sailplay.service']


@pytest.mark.parametrize('failure', ['check', 'stop', 'timeout'])
def test_service_errors_block_preparation(monkeypatch, failure):
    def run(args, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        failed = args[1] == ('show' if failure == 'check' else 'stop')
        return SimpleNamespace(returncode=int(failed), stdout='loaded\n', stderr='denied')

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        stop_sailplay()
