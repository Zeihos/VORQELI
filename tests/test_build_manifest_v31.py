"""Manifest validation fails closed on missing and tampered source files."""
import hashlib
import json
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('verify_build_manifest', Path(__file__).resolve().parents[1] / 'scripts/verify_build_manifest.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
verify = module.verify


def test_manifest_matches_fixture(tmp_path):
    f = tmp_path / 'src' / 'file.py'
    f.parent.mkdir()
    f.write_bytes(b'example')
    data = {'file_count': 1, 'files': {'src/file.py': {'bytes': 7, 'sha256': hashlib.sha256(b'example').hexdigest()}}}
    (tmp_path/'BUILD_MANIFEST.json').write_text(json.dumps(data))
    assert verify(tmp_path) == []
    f.write_bytes(b'altered')
    assert 'File mismatch' in verify(tmp_path)[0]


def test_manifest_rejects_escape(tmp_path):
    data = {'file_count': 1, 'files': {'../escape': {'bytes': 1, 'sha256': '0'*64}}}
    (tmp_path/'BUILD_MANIFEST.json').write_text(json.dumps(data))
    assert 'Unsafe filename' in verify(tmp_path)[0]


def test_manifest_rejects_missing_entries(tmp_path):
    data = {'file_count': 2, 'files': {}}
    (tmp_path/'BUILD_MANIFEST.json').write_text(json.dumps(data))
    assert verify(tmp_path)
