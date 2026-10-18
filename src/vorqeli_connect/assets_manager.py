"""Pinned official Flowseal zapret release: download, SHA-256 verify, safe extract."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from .config import APP_DIR

ZAPRET_TAG = '1.10.3'
ZAPRET_URL = ('https://github.com/Flowseal/zapret-discord-youtube/releases/download/'
              '1.10.3/zapret-discord-youtube-1.10.3.zip')
ZAPRET_SHA256 = '244314ae1c24538a0d751601da8e0c925c843371eec4456eb15f14c4fd6b7058'
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
MAX_EXTRACT_BYTES = 140 * 1024 * 1024
ENGINE_MANIFEST = '.vorqeli-engine-manifest.json'
FLOWSEAL_LICENSE_RESOURCE = 'Flowseal-zapret-1.10.3-LICENSE.txt'
FLOWSEAL_LICENSE_SHA256 = 'fe3983a1e91206ad1a530bcfae01fad207020cb61882edd62c1e3cb5f8d5d430'
# Restrict verification to executable binaries: user-provided host lists need not
# be overwritten during validation. Manifest is generated only after ZIP SHA
# validation, then stored in the protected installation directory.
EXECUTABLE_SUFFIXES = frozenset({'.exe', '.dll', '.sys'})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(256 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_extract_zip(archive: Path, target: Path) -> None:
    """Reject traversal, symlinks, oversized archives; no extraction outside target."""
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(archive) as z:
        files = z.infolist()
        if len(files) > 5000:
            raise ValueError('Слишком много файлов в архиве')
        for info in files:
            name = info.filename.replace('\\', '/')
            parts = name.split('/')
            if (name.startswith('/') or '..' in parts or
                    any(':' in p for p in parts) or not name or
                    (info.external_attr >> 16) & stat.S_IFMT(0o170000) == stat.S_IFLNK):
                raise ValueError('Небезопасное содержимое архива')
            total += info.file_size
            if total > MAX_EXTRACT_BYTES:
                raise ValueError('Архив превышает лимит распаковки')
        for info in files:
            out = target.joinpath(*info.filename.replace('\\', '/').split('/'))
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as reader, out.open('wb') as writer:
                shutil.copyfileobj(reader, writer, length=256 * 1024)


def _engine_binaries(root: Path) -> dict[str, str]:
    """Hash binary files without following symlinks or traversing outside root."""
    binary_dir = root / 'bin'
    if not binary_dir.is_dir() or binary_dir.is_symlink():
        raise ValueError('Папка bin отсутствует или является ссылкой')
    result = {}
    for entry in sorted(binary_dir.iterdir()):
        if entry.is_symlink():
            raise ValueError('Символьные ссылки в пакете DPI запрещены')
        if entry.is_file() and entry.suffix.lower() in EXECUTABLE_SUFFIXES:
            result[f'bin/{entry.name}'] = sha256_file(entry)
    if 'bin/winws.exe' not in result:
        raise ValueError('В пакете DPI отсутствует winws.exe')
    return result


def write_engine_manifest(root: Path, *, release_sha: str = ZAPRET_SHA256) -> None:
    """Call only on unpacked contents of a SHA-verified official release."""
    payload = {'schema': 1, 'source': 'Flowseal/zapret-discord-youtube',
               'archive_sha256': release_sha.lower(),
               'binaries': _engine_binaries(root)}
    path = root / ENGINE_MANIFEST
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def engine_integrity(root: Path, *, release_sha: str = ZAPRET_SHA256) -> str:
    """Offline status: verified, missing, legacy, tampered. Never downloads.

    Manifest originates in a known-good ZIP, but is only tamper-resistant if
    the containing directory is protected by OS ACLs (installed Program Files).
    """
    if not root.is_dir():
        return 'missing'
    path = root / ENGINE_MANIFEST
    if not path.is_file() or path.is_symlink():
        return 'legacy'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.get('schema') != 1 or
                data.get('source') != 'Flowseal/zapret-discord-youtube' or
                data.get('archive_sha256') != release_sha.lower()):
            return 'tampered'
        hashes = data.get('binaries')
        if not isinstance(hashes, dict) or not hashes or 'bin/winws.exe' not in hashes:
            return 'tampered'
        # Exact equality catches extra executables/drivers inserted into bin.
        present = _engine_binaries(root)
        if any(not isinstance(h, str) or len(h) != 64 for h in hashes.values()):
            return 'tampered'
        return 'verified' if present == hashes else 'tampered'
    except (OSError, ValueError, UnicodeError, TypeError):
        return 'tampered'


def find_bundle(root: Path) -> Path:
    candidates = [p.parent.parent for p in root.rglob('winws.exe') if p.parent.name.lower() == 'bin']
    for path in candidates:
        if (path / 'lists/list-general.txt').is_file():
            return path
    raise ValueError('В официальном архиве не найдены bin/winws.exe и lists/list-general.txt')


def engine_cache_root() -> Path:
    """Use an administrator-protected location for privileged scheduled launches.

    The installer places the EXE under Program Files with Windows' standard
    restrictive ACLs. Never run a user-writable cached EXE from that scheduled
    task. Portable/source development retains per-user caching; production
    installer is the supported unattended-start mode.
    """
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        from .startup import trusted_install_path
        if trusted_install_path():
            return Path(sys.executable).resolve().parent / 'engines'
    return APP_DIR / 'engines'


def ensure_zapret(*, progress=None, base_dir: Path | None = None,
                  url: str = ZAPRET_URL, expected_sha: str = ZAPRET_SHA256) -> Path:
    dest = (base_dir if base_dir is not None else engine_cache_root()) / 'zapret-1.10.3'
    cache_status = engine_integrity(dest, release_sha=expected_sha)
    if (cache_status == 'verified' and
            (dest / 'lists/list-general.txt').is_file() and
            (dest / 'LICENSE.txt').is_file()):
        return dest
    if progress and cache_status in ('legacy', 'tampered'):
        progress('DPI-кеш не подтверждён: повторная загрузка официального пакета…')
    if progress:
        progress('Загрузка официального DPI-пакета (1,5 МБ)…')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vorqeli-', dir=str(dest.parent)) as t:
        temp = Path(t)
        archive = temp / 'engine.zip'
        request = urllib.request.Request(url, headers={'User-Agent': 'VORQELI-Connect/0.27.0'})
        size = 0
        with urllib.request.urlopen(request, timeout=25) as response, archive.open('wb') as stream:
            while block := response.read(64 * 1024):
                size += len(block)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError('Превышен лимит размера загрузки')
                stream.write(block)
        if sha256_file(archive) != expected_sha.lower():
            raise ValueError('Не совпадает контрольная сумма архива Flowseal. Загрузка отклонена.')
        if progress:
            progress('Проверка и распаковка DPI-пакета…')
        unpack = temp / 'unpacked'
        safe_extract_zip(archive, unpack)
        found = find_bundle(unpack)
        staged = dest.parent / '.zapret-installing'
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(found, staged)
        # Flowseal's release ZIP may omit LICENSE.txt despite the tagged source
        # including it. Never fabricate a license or weaken SHA validation:
        # bundle the exact, SHA-pinned official 1.10.3 LICENSE.txt in the app.
        license_path = staged / 'LICENSE.txt'
        if not license_path.exists():
            # Package resources are installed with pip and collected into the
            # frozen app. Do not derive paths from site-packages/../../.
            resource = Path(__file__).resolve().parent / FLOWSEAL_LICENSE_RESOURCE
            if not resource.is_file() or sha256_file(resource) != FLOWSEAL_LICENSE_SHA256:
                raise RuntimeError('Лицензия Flowseal отсутствует или повреждена; установка DPI отменена')
            shutil.copyfile(resource, license_path)
        write_engine_manifest(staged, release_sha=expected_sha)
        if engine_integrity(staged, release_sha=expected_sha) != 'verified':
            raise RuntimeError('Не удалось проверить распакованный DPI-движок')
        # Only replace a previous cache AFTER the new release was fully
        # validated. Keep the old cache if download/verification fails.
        if dest.exists():
            retired = dest.parent / '.zapret-retired'
            if retired.exists():
                shutil.rmtree(retired)
            dest.rename(retired)
            try:
                staged.rename(dest)
            except Exception:
                retired.rename(dest)
                raise
            try:
                shutil.rmtree(retired)
            except OSError:
                pass  # A loaded driver or antivirus can temporarily lock files.
        else:
            staged.rename(dest)
    return dest
