"""Run on a Windows GitHub Actions worker; avoids touching real user settings."""
import json
import os
import tempfile
from pathlib import Path

if os.name != 'nt':
    raise SystemExit('This smoke test only runs on Windows')

from vorqeli_connect.config import Settings, load_settings, save_settings
from vorqeli_connect.secret_storage import protect, unprotect

secret = 'ea' * 16
assert unprotect(protect(secret)) == secret
with tempfile.TemporaryDirectory(prefix='vorqeli-dpapi-') as directory:
    path = Path(directory) / 'settings.json'
    save_settings(Settings(telegram_secret=secret, desired_enabled=True), path)
    source = path.read_text(encoding='utf-8')
    payload = json.loads(source)
    assert secret not in source, 'Telegram secret must not appear in Windows settings JSON'
    assert payload.get('telegram_secret_dpapi'), 'Missing DPAPI ciphertext'
    restored = load_settings(path)
    assert restored.desired_enabled and restored.telegram_secret == secret
print('Windows DPAPI roundtrip: OK; saved secrets encrypted')
