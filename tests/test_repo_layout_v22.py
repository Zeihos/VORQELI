from pathlib import Path
import shutil
import importlib.util
import re

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check_repo_layout.py'
spec = importlib.util.spec_from_file_location('vorqeli_repo_layout', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_actual_project_layout_is_complete():
    assert module.check_layout(SCRIPT.parent.parent) == []


def test_incomplete_checkout_fails_fast(tmp_path):
    assert any('pyproject.toml' in problem for problem in module.check_layout(tmp_path))


def test_detect_missing_icon(tmp_path):
    source = SCRIPT.parent.parent
    shutil.copytree(source, tmp_path / 'repo', ignore=shutil.ignore_patterns('.pytest_cache','__pycache__'))
    (tmp_path / 'repo/assets/VORQELI.ico').unlink()
    issues = module.check_layout(tmp_path / 'repo')
    assert any('assets/VORQELI.ico' in problem for problem in issues)


def test_detect_version_mismatch(tmp_path):
    source = SCRIPT.parent.parent
    shutil.copytree(source, tmp_path / 'repo', ignore=shutil.ignore_patterns('.pytest_cache','__pycache__'))
    p = tmp_path / 'repo/installer/VORQELI.iss'
    p.write_text(re.sub(r'MyAppVersion "[0-9]+\.[0-9]+\.[0-9]+"', 'MyAppVersion "0.99.0"', p.read_text(encoding='utf-8')))
    issues = module.check_layout(tmp_path / 'repo')
    assert any('установщика' in problem for problem in issues)
