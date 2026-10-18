# Windows CI UTF-8 (v0.36.1)

GitHub Actions Windows Python 3.12 can default `sys.stdout.encoding` to cp1252. The layout checker emits Cyrillic text after successful verification, triggering `UnicodeEncodeError` **before** tests or EXE packaging. A previous repair was lost in v0.36.0.

The workflow now defines `PYTHONUTF8: '1'` and `PYTHONIOENCODING: 'utf-8'` at the top level (not in a later step). `scripts/check_repo_layout.py` independently uses `errors='backslashreplace'` so manual invocation on legacy terminals reports validation errors without masking them by encoding exceptions.

`tests/test_windows_ci_encoding_v361.py` guards these invariants, exercising the validator with forced `cp1252:strict` in a subprocess. The manifest now inventories `.gitattributes` to preserve the line-ending contract. Do **not** weaken `scripts/verify_build_manifest.py`; update its SHA-256 manifest for any source changes. The checks validate source integrity, not publisher authenticity. Signed releases require the separate Authenticode release gate.

The application launch and network engines were intentionally not changed by this hotfix. Passing GitHub CI is not evidence that bypass succeeds in a particular network.
