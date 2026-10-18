import hashlib
import pytest
from vorqeli_connect.integrations import inspect_file, verify_sha256

def test_inspect_file(tmp_path):
    file=tmp_path/"engine.exe"
    file.write_bytes(b"sample")
    item=inspect_file(str(file))
    assert item.sha256 == hashlib.sha256(b"sample").hexdigest()
    assert item.size == 6

def test_verify_hash(tmp_path):
    file=tmp_path/"proxy.py"
    file.write_bytes(b"proxy")
    digest=hashlib.sha256(b"proxy").hexdigest()
    assert verify_sha256(str(file), digest)
    assert not verify_sha256(str(file), "0"*64)

def test_invalid_hash(tmp_path):
    file=tmp_path/"proxy.py"
    file.write_bytes(b"proxy")
    with pytest.raises(ValueError):
        verify_sha256(str(file), "bad")

def test_reject_unknown_extension(tmp_path):
    file=tmp_path/"unknown.dll"
    file.write_bytes(b"abc")
    with pytest.raises(ValueError):
        inspect_file(str(file))
