"""Windows CI: exercise OFF persistence without touching actual user settings.

Creates isolated files in a temporary directory only. Never changes DPI,
network adapter configuration, tasks, startup registry entries or DNS.
"""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from vorqeli_connect.config import Settings, load_settings, off_intent_path, save_settings


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='vorqeli-off-intent-ci-') as folder:
        path = Path(folder) / 'settings.json'
        save_settings(Settings(desired_enabled=True), path)
        assert load_settings(path).desired_enabled is True
        save_settings(Settings(desired_enabled=False), path)
        assert off_intent_path(path).is_file()
        # Simulate a stale ON preference in the primary file after power loss.
        source = json.loads(path.read_text(encoding='utf-8'))
        source['desired_enabled'] = True
        path.write_text(json.dumps(source), encoding='utf-8')
        assert load_settings(path).desired_enabled is False
        save_settings(Settings(desired_enabled=True), path)
        assert not off_intent_path(path).exists()
        assert load_settings(path).desired_enabled is True
    print('VORQELI explicit OFF persistence smoke passed.')


if __name__ == '__main__':
    main()
