"""Non-invasive HTTPS checks, without changing DNS, firewall or routing."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SERVICES = {
    "Discord": "https://discord.com",
    "YouTube": "https://www.youtube.com",
    "Telegram Web": "https://web.telegram.org/k/",
    "GitHub": "https://github.com",
}


def check_service(name: str, url: str, timeout: float = 4.0) -> tuple[str, str]:
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "VorqeliConnect/0.1"})
        with urlopen(req, timeout=timeout) as response:
            status = response.status
        return name, "Доступен" if 200 <= status < 400 else f"HTTP {status}"
    except HTTPError as exc:
        return name, f"HTTP {exc.code}"
    except (URLError, OSError, TimeoutError):
        return name, "Нет ответа"


def check_all() -> list[tuple[str, str]]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(check_service, name, url) for name, url in SERVICES.items()]
        return [future.result() for future in futures]
