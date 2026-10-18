"""Experimental, consent-based DPI strategy selection using bounded HTTPS reachability.

IMPORTANT: A reachable HTTPS endpoint is not proof of censorship bypass. The
network's state and service availability may change between probes; selectors
report their observations only. The user must opt into the ``auto`` DPI mode.
No third-party telemetry or shell invocations are performed here.
"""
from __future__ import annotations
from dataclasses import dataclass
import ssl
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

PROFILES = ('fake', 'multisplit')
# HTTPS destinations also checked in the ordinary Diagnostics page.
TARGETS = ('https://discord.com/', 'https://www.youtube.com/')


@dataclass(frozen=True)
class Trial:
    mode: str
    reachable: int
    checked: int
    launched: bool


@dataclass(frozen=True)
class Selection:
    active_mode: str
    trials: tuple[Trial, ...]
    all_targets_reachable: bool
    warning: str


class SelectionCancelled(RuntimeError):
    """Manual OFF wins over an automatic strategy probe."""


def https_reachable(url: str, *, timeout: float = 2.5) -> bool:
    """Check a fixed HTTPS endpoint without using environment HTTP proxies.

    A 4xx/5xx *HTTP response* still proves the TLS connection reached a web
    server; an HTTP error does not automatically mean a site is blocked.
    Disabling proxy discovery makes the measurement about this host's direct
    HTTPS reachability instead of an unrelated browser/system proxy.
    """
    if url not in TARGETS:
        raise ValueError('Проверка разрешена только для известных HTTPS-адресов')
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(Request(url, method='HEAD',
                   headers={'User-Agent': 'VORQELI-Connect/0.26'}), timeout=timeout) as response:
            return 100 <= response.status <= 599
    except HTTPError:
        return True
    except (URLError, OSError, TimeoutError, ValueError):
        return False


def probe_targets(cancelled: Callable[[], bool],
                  request: Callable[[str], bool] = https_reachable) -> tuple[bool, ...]:
    """Make no request after manual OFF; bounded to two direct HTTPS checks."""
    results = []
    for url in TARGETS:
        if cancelled():
            raise SelectionCancelled('Подключение отменено')
        try:
            results.append(bool(request(url)))
        except (OSError, ValueError, RuntimeError):
            results.append(False)
    return tuple(results)


def select_strategy(*, start: Callable[[str], None], stop: Callable[[], None],
                    running: Callable[[], bool],
                    cancelled: Callable[[], bool],
                    progress: Callable[[str], None] = lambda msg: None,
                    probe: Callable[[Callable[[], bool]], tuple[bool, ...]] = probe_targets
                    ) -> Selection:
    """Try FAKE then MULTISPLIT and keep the best observed strategy.

    Tests are limited to two profiles and two HTTPS endpoints per profile.
    Fully reachable first profile ends search early. Otherwise score both
    profiles; ties prefer FAKE (the original default). If neither reaches
    anything, leave FAKE running with an explicit *unverified* warning.
    Process callbacks only manage the application's own child process.
    """
    trials: list[Trial] = []
    active: str | None = None
    for mode in PROFILES:
        if cancelled():
            raise SelectionCancelled('Подключение отменено')
        if active is not None:
            stop()
            active = None
        progress(f'Smart DPI: пробуем {mode.upper()}…')
        try:
            start(mode)
            active = mode
            if not running():
                raise RuntimeError('DPI-процесс остановился после запуска')
        except Exception:
            # Never leave an unknown process running when the launch failed.
            stop()
            active = None
            trials.append(Trial(mode, 0, len(TARGETS), False))
            continue
        if cancelled():
            raise SelectionCancelled('Подключение отменено')
        try:
            statuses = tuple(bool(v) for v in probe(cancelled))
        except SelectionCancelled:
            raise
        except Exception:
            statuses = ()
        if len(statuses) != len(TARGETS):
            statuses = (False,) * len(TARGETS)
        trial = Trial(mode, sum(statuses), len(statuses), True)
        trials.append(trial)
        progress(f'Smart DPI: {mode.upper()} — HTTPS отвечает {trial.reachable}/{trial.checked}')
        if all(statuses):
            break

    eligible = [t for t in trials if t.launched]
    if not eligible:
        raise RuntimeError('Ни одна DPI-стратегия не запустилась')
    # Stable tie breaker follows profile order even if last process is active.
    best = max(eligible, key=lambda trial: trial.reachable)
    if cancelled():
        raise SelectionCancelled('Подключение отменено')
    if active != best.mode:
        if active is not None:
            stop()
        active = None
        start(best.mode)
        active = best.mode
        if not running():
            stop()
            raise RuntimeError('Выбранная DPI-стратегия не запустилась повторно')
    all_targets_reachable = best.reachable == len(TARGETS)
    warning = ('' if all_targets_reachable else
               f'Smart DPI: HTTPS отвечает {best.reachable}/{best.checked}. '
               'Работа обхода не подтверждена; проверьте доступность сервисов вручную.')
    return Selection(active, tuple(trials), all_targets_reachable, warning)
