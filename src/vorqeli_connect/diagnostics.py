"""Bounded on-demand HTTPS checks; not proof of full app functionality.

These tests deliberately do not change DNS, HOSTS, proxy settings or routing.
A 2xx/3xx response to HEAD is a positive HTTPS signal, not a login test.
Microsoft's three services are tested separately and summarized honestly.
"""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SERVICES = {
    "Discord": "https://discord.com/",
    "YouTube": "https://www.youtube.com/",
    "Telegram Web": "https://web.telegram.org/k/",
    "ChatGPT": "https://chatgpt.com/",
    "Microsoft (Copilot, Designer, Xbox)": (
        "https://copilot.microsoft.com/",
        "https://designer.microsoft.com/",
        "https://www.xbox.com/",
    ),
}


def check_service(name: str, url: str, timeout: float = 4.0) -> tuple[str, str]:
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "VORQELI-Connect/0.36"})
        with urlopen(req, timeout=timeout) as response:
            status = response.status
        return name, "Доступен" if 200 <= status < 400 else f"HTTP {status}"
    except HTTPError as exc:
        return name, f"HTTP {exc.code}"
    except (URLError, OSError, TimeoutError, ValueError):
        return name, "Нет ответа"


def check_group(name: str, urls: tuple[str, ...]) -> tuple[str, str]:
    if not urls:
        return name, "Нет адресов"
    # Calls are bounded, on-demand only. The separate statuses remain visible.
    outcomes = [check_service(name, url)[1] for url in urls]
    short = ('Copilot', 'Designer', 'Xbox')
    def compact(value):
        return 'OK' if value == 'Доступен' else 'нет' if value == 'Нет ответа' else value.replace('HTTP ', 'HTTP')
    parts = [f'{short[i] if i < len(short) else i+1}: {compact(outcome)}'
             for i, outcome in enumerate(outcomes)]
    return name, ' | '.join(parts)


def check_all() -> list[tuple[str, str]]:
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(check_group, name, url) if isinstance(url, tuple)
                   else pool.submit(check_service, name, url)
                   for name, url in SERVICES.items()]
        return [future.result() for future in futures]
