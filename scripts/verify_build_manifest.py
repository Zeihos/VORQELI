"""Fail-closed check of source inventory and SHA-256 before any Windows build.

The source manifest detects missing, unexpectedly added, or modified files
across important project directories. It is an integrity/completeness guard,
NOT a cryptographic publisher signature: a malicious party who edits the
manifest can rewrite the hashes too. Windows releases require Authenticode.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import sys

TRACKED_DIRS = ('src', 'scripts', 'tests', 'installer', 'assets', 'docs', '.github')
TRACKED_ROOT_FILES = frozenset({
    'pyproject.toml', 'build_entry.py', 'README.md', 'LICENSE',
    'NOTICE.md', '.gitignore', 'CHANGELOG.md',
})
EXCLUDED_PARTS = frozenset({
    '__pycache__', '.pytest_cache', '.git', '.venv', 'venv',
    '.mypy_cache', '.ruff_cache',
})
SKIPPED_SUFFIXES = frozenset({'.pyc', '.pyo', '.tmp', '.log'})
HASH = re.compile(r'[a-f0-9]{64}\Z')


def _source_inventory(root: Path) -> set[str]:
    """List all project files that must appear in a reproducible source zip."""
    names: set[str] = set()
    for file in root.iterdir():
        if file.is_file() and file.name in TRACKED_ROOT_FILES:
            names.add(file.name)
    for directory in TRACKED_DIRS:
        base = root / directory
        if not base.is_dir() or base.is_symlink():
            continue  # A missing required file is detected separately.
        for file in base.rglob('*'):
            relative = file.relative_to(root)
            if any(part in EXCLUDED_PARTS or part.endswith('.egg-info') for part in relative.parts):
                continue
            if file.suffix.lower() in SKIPPED_SUFFIXES:
                continue
            if file.is_file() or file.is_symlink():
                names.add(relative.as_posix())
    return names


def _safe_name(value: object) -> bool:
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        return False
    posix = PurePosixPath(value)
    if (posix.is_absolute() or value != posix.as_posix()
            or any(part in ('', '.', '..') or ':' in part for part in posix.parts)):
        return False
    return True


def verify(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads((root / 'BUILD_MANIFEST.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict) or type(data.get('file_count')) is not int:
            return ['Manifest invalid: schema']
        entries = data.get('files')
        if not isinstance(entries, dict) or not entries or len(entries) != data['file_count']:
            return ['Manifest has inconsistent file counts']
        names = set(entries)
        if any(not _safe_name(name) for name in names):
            return ['Unsafe filename in manifest: ' + str(next(n for n in names if not _safe_name(n)))]
        folded = [name.casefold() for name in names]
        if len(folded) != len(set(folded)):
            errors.append('Manifest contains case-conflicting Windows filenames')
        for name, info in entries.items():
            if not isinstance(info, dict) or (type(info.get('bytes')) is not int or info['bytes'] < 0 or
                    not isinstance(info.get('sha256'), str) or not HASH.fullmatch(info['sha256'])):
                errors.append(f'Invalid file metadata: {name}')
                continue
            path = root.joinpath(*PurePosixPath(name).parts)
            # It is possible for only a parent directory (not the final file)
            # to be a symlink. Never trust any such path in a privileged build.
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root.parent):
                errors.append(f'Linked file or directory: {name}')
            elif not path.is_file():
                errors.append(f'Missing file: {name}')
            elif path.stat().st_size != info['bytes'] or _digest(path) != info['sha256']:
                errors.append(f'File mismatch: {name}')
        expected = _source_inventory(root)
        # New Python/installer/workflow files must be reviewed and signed into
        # the manifest instead of being silently admitted to Windows artifacts.
        for missing in sorted(expected - names):
            errors.append(f'Unmanifested project file: {missing}')
        if (root / 'pyproject.toml').exists() or (root / '.github').exists():
            for missing in sorted(TRACKED_ROOT_FILES - names):
                errors.append(f'Unmanifested critical file: {missing}')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'Manifest invalid: {type(exc).__name__}')
    return errors


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    errors = verify(Path(__file__).resolve().parents[1])
    if errors:
        for error in errors:
            print('ERROR:', error, file=sys.stderr)
        return 1
    print('Source manifest and critical file inventory verified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
