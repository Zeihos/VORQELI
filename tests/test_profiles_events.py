import pytest
from vorqeli_connect.profiles import validate_profile, save_profiles, load_profiles, Profile
from vorqeli_connect.event_log import record_event, recent_events

def test_profile_roundtrip(tmp_path):
    exe=tmp_path/'safe.exe';exe.write_bytes(b'123')
    profile=validate_profile('My profile',str(exe))
    target=tmp_path/'profiles.json'
    save_profiles([profile],target)
    assert load_profiles(target)==[profile]

def test_profile_bad_file(tmp_path):
    with pytest.raises(FileNotFoundError):validate_profile('X',str(tmp_path/'missing.exe'))

def test_profile_duplicates(tmp_path):
    with pytest.raises(ValueError):save_profiles([Profile('A','x'),Profile('a','y')],tmp_path/'p.json')

def test_event_roundtrip(tmp_path):
    target=tmp_path/'events.jsonl'
    record_event('start','ok',target)
    record_event('stop','done',target)
    assert [x['action'] for x in recent_events(target)]==['stop','start']

def test_event_empty(tmp_path):
    assert recent_events(tmp_path/'missing.jsonl')==[]
