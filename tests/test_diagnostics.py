from unittest.mock import patch
from vorqeli_connect.diagnostics import check_service, SERVICES

def test_known_services():
    assert {"Discord", "YouTube", "Telegram", "GitHub"} <= set(SERVICES)

def test_unreachable_service():
    from urllib.error import URLError
    with patch("vorqeli_connect.diagnostics.urlopen",side_effect=URLError("offline")):
        assert check_service("test","https://example.invalid")== ("test","Нет ответа")
