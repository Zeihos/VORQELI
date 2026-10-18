from unittest.mock import patch
from vorqeli_connect.network_tools import check_endpoint, check_network, TARGETS


def test_dns_failure():
    with patch("socket.getaddrinfo", side_effect=OSError("dns")):
        assert check_endpoint("Example", "example.invalid")[1] == "Ошибка DNS"


def test_tcp_success():
    class Socket:
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def settimeout(self, value):pass
        def connect(self, address):pass
    with patch("socket.getaddrinfo", return_value=[(2,1,6,"",("127.0.0.1",443))]), patch("socket.socket",return_value=Socket()):
        assert check_endpoint("Example", "example.org")[1] == "TCP доступен"


def test_tcp_failure():
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def settimeout(self,value):pass
        def connect(self,address):raise ConnectionRefusedError
    with patch("socket.getaddrinfo", return_value=[(2,1,6,"",("127.0.0.1",443))]), patch("socket.socket",return_value=Socket()):
        assert check_endpoint("Example", "example.org")[1] == "TCP недоступен"


def test_targets_defined():
    assert all(port == 443 for _,port in TARGETS.values())
