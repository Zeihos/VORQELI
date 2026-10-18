"""Read-only DNS and TCP diagnostics. No system settings are modified."""
import socket
from concurrent.futures import ThreadPoolExecutor

TARGETS = {"Discord": ("discord.com", 443), "YouTube": ("www.youtube.com", 443),
           "Telegram Web": ("web.telegram.org", 443), "GitHub": ("github.com", 443)}


def check_endpoint(name: str, host: str, port: int = 443, timeout: float = 3.0) -> tuple[str, str]:
    """Return a user-facing result without leaking full system exception messages."""
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return name, "Ошибка DNS"
    if not addresses:
        return name, "Ошибка DNS"
    for family, socktype, proto, _, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as connection:
                connection.settimeout(timeout)
                connection.connect(sockaddr)
                return name, "TCP доступен"
        except (OSError, TimeoutError):
            continue
    return name, "TCP недоступен"


def check_network() -> list[tuple[str, str]]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(check_endpoint, name, host, port) for name, (host, port) in TARGETS.items()]
        return [job.result() for job in jobs]
