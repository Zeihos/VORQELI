"""Standard-library CI preflight for incomplete GitHub uploads.

This check runs *before* pip, tests, or a potentially expensive Windows build.
It does not install dependencies or touch networking, registry or DNS.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys

REQUIRED_FILES = (
    'tests/test_geohide_recovery_v406.py',
    'tests/test_dns_restore_ui_v406.py',
    'docs/GEOHIDE_RECOVERY_AND_DNS_V406.md',
    'tests/test_native_ui_v405.py',
    'docs/NATIVE_UI_DIAGNOSTICS_V405.md',
    'tests/test_native_ui_v404.py',
    'docs/NATIVE_UI_RELEASE_GUARDS_V404.md',
    'tests/test_native_ui_v403.py',
    'docs/NATIVE_UI_COMPACT_V403.md',
    'tests/test_native_ui_v402.py',
    'docs/NATIVE_UI_HARDENING_V402.md',
    'src/vorqeli_connect/native_ui.py',
    'tests/test_native_ui_v401.py',
    'docs/NATIVE_INTERFACE_V401.md',
    'docs/AUDIT_REPORT_V401.md',
    'assets/VORQELI-wordmark.png',
    'pyproject.toml', 'README.md', 'LICENSE', 'NOTICE.md',
    'BUILD_MANIFEST.json', 'scripts/verify_build_manifest.py',
    'tests/test_build_manifest_v31.py', 'tests/test_update_security_v31.py',
    'build_entry.py', '.github/workflows/windows-build.yml',
    'installer/VORQELI.iss', 'assets/VORQELI.ico',
    'assets/VORQELI-logo.png', 'src/vorqeli_connect/app.py',
    'src/vorqeli_connect/__init__.py',
    'src/vorqeli_connect/unified.py',
    'src/vorqeli_connect/smart_dpi.py', 'tests/test_smart_dpi_v26.py',
    'docs/SMART_DPI_V26.md',
    'src/vorqeli_connect/geohide_doh.py', 'tests/test_geohide_doh_v27.py',
    'docs/GEOHIDE_DOH_V27.md', 'scripts/windows_doh_readonly_smoke.py',
    'src/vorqeli_connect/ui_navigation.py', 'src/vorqeli_connect/windows_chrome.py',
    'src/vorqeli_connect/update_checker.py', 'tests/test_update_checker_v29.py',
    'docs/UPDATES_V29.md', 'docs/RELEASE_CANDIDATE_CHECKLIST_V29.md',
    'tests/test_update_security_v30.py', 'scripts/windows_release_gate.ps1',
    'docs/RELEASE_CANDIDATE_GATE_V30.md',
    'tests/test_ui_navigation_v28.py', 'docs/UI_ACCESSIBILITY_V28.md',
    'src/vorqeli_connect/uninstall_safety.py',
    'tests/test_unified.py', 'tests/test_startup_audit_v24.py',
    'scripts/windows_installer_smoke.ps1',
    'scripts/windows_adapter_identity_smoke.py', 'tests/test_adapter_identity_v34.py',
    'docs/GEOHIDE_ADAPTER_IDENTITY_V34.md',
    'scripts/windows_startup_smoke.py', 'tests/test_startup_registry_v25.py',
    'src/vorqeli_connect/telegram_web_audit.py',
    'tests/test_telegram_web_audit_v36.py',
    'docs/TELEGRAM_WEB_DIAGNOSTICS_V36.md',
    'tests/test_windows_ci_encoding_v361.py',
)


def check_layout(root: Path) -> list[str]:
    problems = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or not path.stat().st_size:
            problems.append('Отсутствует обязательный файл: ' + relative)
    project_path = root / 'pyproject.toml'
    try:
        project_text = project_path.read_text(encoding='utf-8')
        match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$',
                          project_text, re.MULTILINE)
        if not match:
            raise ValueError('Версия отсутствует')
        project_version = match.group(1)
    except (OSError, ValueError, TypeError) as exc:
        problems.append('Неверный pyproject.toml: ' + type(exc).__name__)
        return problems
    try:
        package_source = (root / 'src/vorqeli_connect/__init__.py').read_text(encoding='utf-8')
        found_version = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']',
                                  package_source, re.MULTILINE)
        if not found_version or found_version.group(1) != project_version:
            problems.append('Версия пакета не совпадает с pyproject.toml')
        installer = (root / 'installer/VORQELI.iss').read_text(encoding='utf-8')
        if f'#define MyAppVersion "{project_version}"' not in installer:
            problems.append('Версия установщика не совпадает с pyproject.toml')
        if r'AppMutex=Local\VORQELI-Connect-Instance' not in installer:
            problems.append('Установщик не защищён от обновления работающего приложения')
        workflow = (root / '.github/workflows/windows-build.yml').read_text(encoding='utf-8')
        if f'VORQELI-Connect-v{project_version}-Windows' not in workflow:
            problems.append('Версия артефакта GitHub Actions не совпадает')
        app_source = (root / 'src/vorqeli_connect/app.py').read_text(encoding='utf-8')
        if 'from . import __version__ as VERSION' not in app_source:
            problems.append('Версия интерфейса должна использовать версию пакета')
        # Detect basic damage to the two binary/graphic assets.
        icon = (root / 'assets/VORQELI.ico').read_bytes()
        if not icon.startswith(b'\x00\x00\x01\x00'):
            problems.append('Файл иконки ICO повреждён')
        logo = (root / 'assets/VORQELI-logo.png').read_bytes()
        if not logo.startswith(b'\x89PNG\r\n\x1a\n'):
            problems.append('Логотип PNG повреждён')
    except (OSError, SyntaxError, NameError) as exc:
        problems.append('Не удалось проверить файлы проекта: ' + type(exc).__name__)
    return problems


def main(argv: list[str] | None = None) -> int:
    # Even if invoked outside GitHub Actions on cp1252/legacy terminals, never
    # let an informational Russian message hide the actual preflight result.
    for channel in (sys.stdout, sys.stderr):
        if hasattr(channel, 'reconfigure'):
            channel.reconfigure(errors='backslashreplace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    issues = check_layout(args.root)
    if issues:
        for issue in issues:
            print('ERROR:', issue, file=sys.stderr)
        print('Проверьте загрузку всех файлов в корень репозитория.', file=sys.stderr)
        return 2
    print('VORQELI: структура и версии проекта проверены.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
