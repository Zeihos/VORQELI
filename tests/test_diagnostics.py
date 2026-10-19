from unittest.mock import patch
from vorqeli_connect.diagnostics import check_service, SERVICES

def test_known_services():
    expected = {"Discord", "YouTube", "Telegram Web", "ChatGPT",
                "Microsoft (Copilot, Designer, Xbox)"}
    assert set(SERVICES) == expected

def test_unreachable_service():
    from urllib.error import URLError
    with patch("vorqeli_connect.diagnostics.urlopen",side_effect=URLError("offline")):
        assert check_service("test","https://example.invalid")== ("test","Нет ответа")
