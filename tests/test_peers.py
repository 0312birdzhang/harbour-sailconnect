import pytest
from sailconnect.peers import paired_peer

ADAPTER = '/org/bluez/hci0'


def objects(*devices):
    return {ADAPTER + '/dev_' + name: {'org.bluez.Device1': properties}
            for name, properties in devices}


def test_only_paired_computer_does_not_need_an_existing_connection():
    assert paired_peer(objects(('PC', {'Paired': True, 'Connected': False})), ADAPTER).endswith('/dev_PC')


def test_one_connected_paired_computer_wins():
    assert paired_peer(objects(('PC', {'Paired': True, 'Connected': True}),
                               ('OTHER', {'Paired': True})), ADAPTER).endswith('/dev_PC')


@pytest.mark.parametrize('devices', [
    (), (('PC', {'Paired': False, 'Connected': True}),),
    (('PC', {'Paired': True}), ('OTHER', {'Paired': True})),
    (('PC', {'Paired': True, 'Connected': True}), ('OTHER', {'Paired': True, 'Connected': True})),
])
def test_missing_or_ambiguous_pairing_is_not_guessed(devices):
    with pytest.raises(ValueError, match='exactly one paired'):
        paired_peer(objects(*devices), ADAPTER)
