"""Opt-in release checks and SHA256-gated downloads.

Security constraints:
- Contact only the official GitHub Releases API with standard TLS verification.
- Never accept arbitrary asset destinations or release download origins.
- Require GitHub's digest field; reject missing or malformed digests.
- Download into a user-profile directory, enforce a size cap, verify *before*
  atomic publication. Never execute an installer, change DNS, or elevate.
- SHA256 authenticates bytes against GitHub's metadata, NOT the publisher.
  Authenticode/signatures remain an outstanding release requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import hashlib
import json
import os
import re
import tempfile
import stat

OWNER = 'Zeihos'
REPOSITORY = 'VORQELI'
API_URL = f'https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases/latest'
INSTALLER_ASSET = 'VORQELI-Connect-Setup.exe'
MAX_METADATA = 256 * 1024
MAX_DOWNLOAD = 250 * 1024 * 1024
VERSION_PATTERN = re.compile(r'^v?(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$')
SHA256_PATTERN = re.compile(r'^sha256:([0-9a-fA-F]{64})$')
ASSET_CDN_HOSTS = frozenset({'release-assets.githubusercontent.com', 'objects.githubusercontent.com'})


class UpdateError(RuntimeError):
    """A remote release is unsafe, inaccessible, or inconsistent."""


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    html_url: str
    installer_url: str
    sha256: str
    size: int


def parse_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise UpdateError('Некорректная версия релиза')
    found = VERSION_PATTERN.fullmatch(value)
    if not found:
        raise UpdateError('Некорректная версия релиза')
    return tuple(map(int, found.groups()))


def _release_page(tag: str) -> str:
    # Use the official release UI rather than trusting metadata-provided URLs.
    from urllib.parse import quote
    return f'https://github.com/{OWNER}/{REPOSITORY}/releases/tag/{quote(tag, safe="")}'


def _is_official_download(url: str, tag: str) -> bool:
    if not isinstance(url, str) or any(c in url for c in ('\n', '\r', '\x00')):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != 'https' or parts.netloc.lower() != 'github.com' or parts.query or parts.fragment:
        return False
    from urllib.parse import quote
    # Exact pathname allows no alternative host, directory traversal, or assets.
    expected = f'/{OWNER}/{REPOSITORY}/releases/download/{quote(tag, safe="")}/{INSTALLER_ASSET}'
    return parts.path == expected



def _redirect_allowed(url: str, *, purpose: str, original_asset_url: str = '') -> bool:
    """Reject cross-origin metadata redirects and untrusted asset CDN hops."""
    if not isinstance(url, str) or any(c in url for c in ('\r', '\n', '\x00')):
        return False
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.username or parts.password or parts.port is not None:
            return False
        if not parts.hostname or parts.fragment or any(seg in ('.', '..') for seg in parts.path.split('/')):
            return False
    except ValueError:  # malformed IPv6 host / invalid port
        return False
    if purpose == 'metadata':
        return False  # The releases API must not redirect, even to another GitHub URL.
    if parts.hostname == 'github.com':
        return url == original_asset_url
    return parts.hostname in ASSET_CDN_HOSTS and bool(parts.path.strip('/'))


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    """GitHub's asset CDN is allowed; arbitrary redirects are refused BEFORE fetch."""
    def __init__(self, purpose: str, original_asset_url: str = ''):
        self.purpose = purpose
        self.original_asset_url = original_asset_url
        self.hops = 0

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > 3 or not _redirect_allowed(
                newurl, purpose=self.purpose, original_asset_url=self.original_asset_url):
            raise UpdateError('Отклонено небезопасное перенаправление загрузки')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _trusted_open(request, timeout: int, *, purpose: str = 'metadata',
                  original_asset_url: str = ''):
    # urllib's default opener follows redirects to any website. Never use it
    # for downloadable executable files or privileged release metadata.
    opener = build_opener(_RestrictedRedirectHandler(purpose, original_asset_url))
    return opener.open(request, timeout=timeout)


def _response_url_allowed(response, *, purpose: str, original_url: str) -> bool:
    # Redirect handler runs before fetching redirect target. This extra check
    # also covers custom transports returning a response with a changed URL.
    geturl = getattr(response, 'geturl', None)
    if geturl is None:
        return True  # Test fakes may have no geturl; real urllib responses do.
    actual = geturl()
    if actual == original_url:
        return True
    return _redirect_allowed(actual, purpose=purpose, original_asset_url=original_url)

def _read_release(open_url=None, *, timeout: int = 12) -> dict:
    request = Request(API_URL, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'VORQELI-Connect-Updater/1.0',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    try:
        transport = open_url or (lambda req, timeout: _trusted_open(req, timeout, purpose='metadata'))
        with transport(request, timeout=timeout) as response:
            if not _response_url_allowed(response, purpose='metadata', original_url=API_URL):
                raise UpdateError('Неожиданное перенаправление GitHub API')
            content = response.read(MAX_METADATA + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('На GitHub пока нет опубликованных релизов VORQELI') from exc
        raise UpdateError('Сервер GitHub не ответил на запрос обновлений') from exc
    except (OSError, TimeoutError) as exc:
        raise UpdateError('Не удалось получить информацию об обновлении') from exc
    if len(content) > MAX_METADATA:
        raise UpdateError('Слишком большой ответ сервера обновлений')
    try:
        parsed = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError('Некорректные данные обновления') from exc
    if not isinstance(parsed, dict):
        raise UpdateError('Некорректный ответ GitHub Releases')
    return parsed


def check_for_update(current_version: str, *, open_url=None) -> Release | None:
    """Return newer verified-metadata release, or None when already current.

    Latest API may 404 when no published release exists. In that situation
    the UI shows a clear informational message rather than manufacturing a
    release URL or triggering any download.
    """
    current = parse_version(current_version)
    data = _read_release(open_url)
    if data.get('draft') is not False or data.get('prerelease') is not False:
        raise UpdateError('GitHub вернул неопубликованный или тестовый релиз')
    tag = data.get('tag_name')
    next_version = parse_version(tag)
    if next_version <= current:
        return None
    assets = data.get('assets')
    if not isinstance(assets, list):
        raise UpdateError('В релизе нет корректного списка файлов')
    installers = [x for x in assets if isinstance(x, dict) and x.get('name') == INSTALLER_ASSET]
    if len(installers) != 1:
        raise UpdateError('В релизе отсутствует единственный установщик VORQELI')
    installer = installers[0]
    digest = installer.get('digest')
    verified_hash = SHA256_PATTERN.fullmatch(digest) if isinstance(digest, str) else None
    if not verified_hash:
        raise UpdateError('GitHub не предоставил SHA-256 установщика: загрузка запрещена')
    size = installer.get('size')
    if type(size) is not int or not 1 <= size <= MAX_DOWNLOAD:
        raise UpdateError('Недопустимый размер установщика')
    download_url = installer.get('browser_download_url')
    if not _is_official_download(download_url, tag):
        raise UpdateError('Неофициальная ссылка на установщик: загрузка запрещена')
    return Release(version='.'.join(map(str,next_version)), tag=tag, html_url=_release_page(tag),
                   installer_url=download_url, sha256=verified_hash.group(1).lower(), size=size)


def _reject_symlinked_directory(directory: Path) -> None:
    """Refuse a redirecting directory at any existing ancestor, not just leaf.

    This is deliberately conservative: downloaded executables should remain in
    the expected local user-profile folder, not an arbitrary symlink target.
    """
    for part in (directory, *directory.parents):
        if part.is_symlink():
            raise UpdateError('Папка обновлений не должна быть символической ссылкой (включая родительские каталоги)')
        if part.exists() and not part.is_dir():
            raise UpdateError('Путь обновлений содержит обычный файл вместо папки')


def download_verified(release: Release, directory: Path, *, open_url=None,
                      timeout: int = 30) -> Path:
    """Download without execution; only publish a file after exact SHA256/size.

    A dedicated versioned destination prevents replacing installed application
    binaries or clobbering a previous update. Partial downloads are removed.
    """
    version = parse_version(release.version)
    if parse_version(release.tag) != version:
        raise UpdateError('Тег релиза не соответствует его версии')
    if not _is_official_download(release.installer_url, release.tag):
        raise UpdateError('Небезопасная ссылка для загрузки')
    if not re.fullmatch(r'[a-f0-9]{64}', release.sha256):
        raise UpdateError('Неправильная контрольная сумма')
    if type(release.size) is not int or not 1 <= release.size <= MAX_DOWNLOAD:
        raise UpdateError('Неправильный размер')
    directory = Path(directory).absolute()
    _reject_symlinked_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    _reject_symlinked_directory(directory)
    destination = directory / f'VORQELI-Connect-Setup-v{release.version}.exe'
    if destination.exists():
        if _matches(destination, release.size, release.sha256):
            return destination
        # An existing unexpected file must not be silently replaced.
        raise UpdateError('В папке уже есть непроверенный установщик с таким именем')
    temporary = None
    try:
        # O_EXCL via mkstemp; no user-controlled filenames in temporary path.
        fd, filename = tempfile.mkstemp(prefix='.vorqeli-download-', suffix='.part', dir=directory)
        temporary = Path(filename)
        hasher = hashlib.sha256()
        written = 0
        request = Request(release.installer_url, headers={'User-Agent':'VORQELI-Connect-Updater/1.0'})
        transport = open_url or (lambda req, timeout: _trusted_open(
            req, timeout, purpose='asset', original_asset_url=release.installer_url))
        with os.fdopen(fd, 'wb') as target:
            try:
                with transport(request, timeout=timeout) as source:
                    if not _response_url_allowed(source, purpose='asset', original_url=release.installer_url):
                        raise UpdateError('Файл пришёл с неподтверждённого сервера')
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        written += len(block)
                        if written > release.size or written > MAX_DOWNLOAD:
                            raise UpdateError('Размер загрузки превысил разрешённый')
                        target.write(block)
                        hasher.update(block)
            finally:
                target.flush()
                os.fsync(target.fileno())
        if written != release.size or hasher.hexdigest() != release.sha256:
            raise UpdateError('Проверка SHA-256/размера не пройдена: загрузка удалена')
        # Atomically publish only if absent. os.replace() silently overwrites
        # another installer's file created between the earlier existence check
        # and this point. Linking the verified temporary file prevents that.
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise UpdateError('Установщик появился во время загрузки; повторите проверку') from exc
        # The separate link now owns the verified bytes; remove temp afterwards.
        temporary.unlink()
        temporary = None
        return destination
    except (OSError, TimeoutError) as exc:
        raise UpdateError('Не удалось скачать установщик обновления') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _matches(file: Path, size: int, expected: str) -> bool:
    try:
        mode = file.lstat().st_mode
        if not stat.S_ISREG(mode) or file.stat().st_size != size:
            return False
        digest = hashlib.sha256()
        with file.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest() == expected
    except OSError:
        return False
