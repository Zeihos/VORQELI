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


def test_redact_credentials_without_known_secret():
    samples = (
        "token=tok_TEST_abc-123",
        "api_key: API_abc123-xyz",
        "access_token=oauth.abcd.efgh",
        'password = "a complex passphrase"',
        "--secret short-but-sensitive",
        "Generated secret: A1B2C3D4",
    )
    for sample in samples:
        result = redact_secrets(sample + "\nstatus=healthy")
        assert "[СКРЫТО]" in result
        assert "status=healthy" in result
        assert sample.split()[-1] not in result
