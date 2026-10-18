# Windows GUI assets hotfix (v0.36.1)

Root cause: the `asset()` function used `Path(__file__).parents[2]` for every
non-PyInstaller invocation. After `pip install .[dev]` on Windows the imported
module lives under `site-packages`, where no adjacent `assets/` directory exists.
The UI smoke tests then searched under the Python installation directory.

Fixed by providing three scoped resource locations:

- **PyInstaller executable:** only `_MEIPASS/assets/`, which is shipped by CI.
- **Source checkout:** `assets/` next to `pyproject.toml`.
- **Installed wheel:** `vorqeli_connect/ui_assets/`, populated by package-data.
  Development checkout tests may also fall back to a working-directory `assets/`.

UI assets (PNG, ICO and optional HOSTS reference list) are copied byte-for-byte
from this checkout into package data. No hosts file or DNS settings are changed.

Check on Windows after pushing:

```powershell
python -m pip install --upgrade ".[dev]"
python -m pytest -q
python scripts/verify_build_manifest.py
```

The GitHub Actions pipeline must pass wheel-import testing, PyInstaller tests,
and installer smoke checks. This fix does not claim network functionality.
