import socket
from pathlib import Path
from vorqeli_connect.preflight import Check, check_dpi, check_telegram, checks_ok, format_checks


def test_dpi_missing():
    results = check_dpi("")
    assert len(results) == 1 and not checks_ok(results)
    assert "Пакет DPI" in format_checks(results)


def test_dpi_ready(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "lists").mkdir()
    (tmp_path / "bin/winws.exe").write_bytes(b"test")
    (tmp_path / "lists/list-general.txt").write_text("example.org")
    (tmp_path / "LICENSE.txt").write_text("MIT")
    assert checks_ok(check_dpi(str(tmp_path)))


def test_telegram_missing_and_secrets_ignored(tmp_path):
    secret = "a" * 32
    checks = check_telegram(str(tmp_path), 1443, secret)
    assert not checks_ok(checks)
    assert secret not in format_checks(checks)


def test_telegram_checks_port(tmp_path, monkeypatch):
    (tmp_path / "proxy").mkdir()
    (tmp_path / "proxy/tg_ws_proxy.py").write_text("# stub")
    (tmp_path / "LICENSE").write_text("MIT")
    monkeypatch.setattr("vorqeli_connect.engine_adapters.shutil.which", lambda _: "/usr/bin/python")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        checks = check_telegram(str(tmp_path), port, "b"*32, "python")
        assert not checks_ok(checks)
        assert checks_ok(check_telegram(str(tmp_path), port, "b"*32, "python", port_busy_ok=True))


def test_busy_port_claim_is_conservative(tmp_path, monkeypatch):
    (tmp_path / "proxy").mkdir()
    (tmp_path / "proxy/tg_ws_proxy.py").write_text("# stub")
    (tmp_path / "LICENSE").write_text("MIT")
    monkeypatch.setattr("vorqeli_connect.engine_adapters.shutil.which", lambda _: "/usr/bin/python")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        checks = check_telegram(str(tmp_path), port, "b" * 32, "python", port_busy_ok=True)
        assert checks_ok(checks)
        assert "не подтверждена" in format_checks(checks)
