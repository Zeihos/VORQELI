"""Pinned official Flowseal zapret release: download, SHA-256 verify, safe extract."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
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


def find_bundle(root: Path) -> Path:
    candidates = [p.parent.parent for p in root.rglob('winws.exe') if p.parent.name.lower() == 'bin']
    for path in candidates:
        if (path / 'lists/list-general.txt').is_file() and (path / 'LICENSE.txt').is_file():
            return path
    raise ValueError('В официальном архиве не найден ожидаемый комплект winws.exe / lists / LICENSE.txt')


def ensure_zapret(*, progress=None, base_dir: Path | None = None,
                  url: str = ZAPRET_URL, expected_sha: str = ZAPRET_SHA256) -> Path:
    dest = (base_dir or APP_DIR / 'engines') / 'zapret-1.10.3'
    if (dest / 'bin/winws.exe').is_file() and (dest / 'lists/list-general.txt').is_file() and (dest / 'LICENSE.txt').is_file():
        return dest
    if progress:
        progress('Загрузка официального DPI-пакета (1,5 МБ)…')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vorqeli-', dir=str(dest.parent)) as t:
        temp = Path(t)
        archive = temp / 'engine.zip'
        request = urllib.request.Request(url, headers={'User-Agent': 'VORQELI-Connect/0.12.0'})
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
        if dest.exists():
            shutil.rmtree(dest)
        staged.rename(dest)
    return dest
