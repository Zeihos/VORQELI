from pathlib import Path
import hashlib
import socket
import pytest

from vorqeli_connect.engine_adapters import (
    build_dpi_spec, build_telegram_spec, validate_proxy_settings,
    proxy_link, port_is_free, port_is_listening,
)


def dpi_bundle(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "lists").mkdir()
    (tmp_path / "bin" / "winws.exe").write_bytes(b"TEST_ONLY")
    (tmp_path / "lists" / "list-general.txt").write_text("example.org\n")
    (tmp_path / "LICENSE.txt").write_text("MIT License")
    return tmp_path


def tg_bundle(tmp_path):
    (tmp_path / "proxy").mkdir()
    (tmp_path / "proxy" / "tg_ws_proxy.py").write_text("# test\n")
    (tmp_path / "LICENSE").write_text("MIT License")
    return tmp_path


def test_dpi_fake_builds_direct_exe(tmp_path):
    root = dpi_bundle(tmp_path)
    spec = build_dpi_spec(root, "fake")
    assert spec.argv[0] == str(root / "bin" / "winws.exe")
    assert "--dpi-desync=fake" in spec.argv
    assert "--wf-tcp=80,443" in spec.argv
    assert str(root / "lists" / "list-general.txt") in spec.argv[3]
    assert spec.cwd == root / "bin"
    assert not any(arg.lower().endswith(".bat") for arg in spec.argv)


def test_dpi_multisplit(tmp_path):
    root = dpi_bundle(tmp_path)
    args = build_dpi_spec(root, "multisplit").argv
    assert "--dpi-desync=multisplit" in args
    assert "--dpi-desync-split-pos=1" in args
    assert "--dpi-desync-repeats=6" not in args


def test_dpi_rejects_unknown_mode_and_missing_files(tmp_path):
    with pytest.raises(ValueError):
        build_dpi_spec(dpi_bundle(tmp_path), "injected")
    (tmp_path / "LICENSE.txt").unlink()
    with pytest.raises(ValueError):
        build_dpi_spec(tmp_path, "fake")


def test_dpi_empty_folder():
    with pytest.raises(ValueError):
        build_dpi_spec("")


def test_telegram_spec_uses_console_module_with_args(tmp_path, monkeypatch):
    root = tg_bundle(tmp_path)
    monkeypatch.setattr("vorqeli_connect.engine_adapters.shutil.which", lambda x: "C:\\Python\\python.exe")
    secret = "a" * 32
    spec = build_telegram_spec(root, 1443, secret, "python")
    assert spec.argv[:3] == ("C:\\Python\\python.exe", "-m", "proxy.tg_ws_proxy")
    assert "--host" in spec.argv and "127.0.0.1" in spec.argv
    assert "--port" in spec.argv and "1443" in spec.argv
    assert "--secret" in spec.argv and secret in spec.argv
    assert spec.cwd == root


def test_telegram_rejects_missing_source(tmp_path):
    with pytest.raises(ValueError):
        build_telegram_spec(tmp_path, 1443, "a"*32, "python")


@pytest.mark.parametrize("port, secret", [
    (1023, "a"*32), (65536, "a"*32), (True, "a"*32),
    (1443, "x"*32), (1443, "b"*31), ("1443", "a"*32),
])
def test_reject_bad_proxy_settings(port, secret):
    with pytest.raises(ValueError):
        validate_proxy_settings(port, secret)


def test_link_is_local_and_contains_secret():
    link=proxy_link(1443, "ABCDEF0123456789ABCDEF0123456789")
    assert link.startswith("tg://proxy?server=127.0.0.1&port=1443&secret=")
    assert link.endswith("abcdef0123456789abcdef0123456789")


def test_refuses_arbitrary_python_binary(monkeypatch):
    monkeypatch.setattr("vorqeli_connect.engine_adapters.shutil.which", lambda x:"/a")
    from vorqeli_connect.engine_adapters import _python_command
    with pytest.raises(ValueError): _python_command("something-malicious")


def test_port_free_check():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port=listener.getsockname()[1]
        assert not port_is_free(port)
    assert port_is_free(port)


def test_port_listening_probe():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port=listener.getsockname()[1]
        assert port_is_listening(port)
    assert not port_is_listening(port)
    assert not port_is_listening(-1)
