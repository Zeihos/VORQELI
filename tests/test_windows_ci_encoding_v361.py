"""Prevent Windows CI from silently losing pre-Python UTF-8 protection."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_actions_sets_utf8_before_any_python_step():
    workflow = (ROOT / '.github/workflows/windows-build.yml').read_text(encoding='utf-8')
    header, sep, jobs = workflow.partition('\njobs:\n')
    assert sep and jobs
    assert "  PYTHONUTF8: '1'" in header
    assert "  PYTHONIOENCODING: 'utf-8'" in header
    assert 'python scripts/check_repo_layout.py' in jobs
    assert 'python scripts/verify_build_manifest.py' in jobs
    from scripts.verify_build_manifest import _source_inventory
    assert '.gitattributes' in _source_inventory(ROOT)


def test_layout_preflight_handles_cp1252_console():
    env = dict(os.environ, PYTHONIOENCODING='cp1252:strict', PYTHONUTF8='0')
    result = subprocess.run(
        [sys.executable, 'scripts/check_repo_layout.py'],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='cp1252',
        errors='replace', timeout=20,
    )
    assert result.returncode == 0, result.stderr[-1200:]
    assert 'UnicodeEncodeError' not in result.stderr


def test_layout_failure_handles_cp1252_console(tmp_path):
    env = dict(os.environ, PYTHONIOENCODING='cp1252:strict', PYTHONUTF8='0')
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/check_repo_layout.py'), '--root', str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='cp1252',
        errors='replace', timeout=20,
    )
    assert result.returncode != 0
    assert 'UnicodeEncodeError' not in result.stderr
    assert 'ERROR' in result.stderr
