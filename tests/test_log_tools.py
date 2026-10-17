import pytest
from vorqeli_connect.log_tools import tail_log, redact_secrets, failure_hint


def test_tail_log_missing(tmp_path):
    assert "не создан" in tail_log(tmp_path / "none.log")


def test_tail_log_bounded(tmp_path):
    path=tmp_path / "engine.log"
    path.write_bytes(b"old"+b"Z"*1000)
    result=tail_log(path,max_bytes=16)
    assert "old" not in result and "Z"*16 in result
    with pytest.raises(ValueError):
        tail_log(path,max_bytes=0)


def test_secret_redaction():
    secret="abcdef"*5+"12"
    text="--secret " + secret.upper() + " URL="+secret
    result=redact_secrets(text,secret)
    assert secret.lower() not in result.lower()
    assert "[СКРЫТО]" in result


def test_failure_hints():
    assert "Python" in failure_hint("ModuleNotFoundError: No module named httpx",1)
    assert "порт" in failure_hint("Address already in use",1)
    assert "прав" in failure_hint("Access is denied",1)
    assert "кодом 1" in failure_hint("unknown",1)


def test_secret_redaction_without_known_secret():
    secret = "0123456789abcdef" * 2
    lines = [
        "--secret=" + secret,
        "--secret " + secret,
        "Generated secret: " + secret.upper(),
        "secret = " + secret,
    ]
    for line in lines:
        result = redact_secrets(line)
        assert secret.lower() not in result.lower()
        assert "[СКРЫТО]" in result
