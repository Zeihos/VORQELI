"""Basic public repository guardrails; never touch system/network configuration."""
from pathlib import Path
import re
from vorqeli_connect import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_readme_matches_current_version_and_public_status():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{__version__}" in text
    assert "Release Candidate" in text
    assert "not stable" not in text.lower()
    assert "SECURITY.md" in text and "CONTRIBUTING.md" in text
    assert "assets/brand-banner.jpg" in text
    assert "GitHub Actions" in text
    assert "не является VPN" in text


def test_legacy_previews_are_not_at_repository_root():
    legacy = ("UI", "Settings", "Diagnostics", "Keyboard", "Compact", "Update")
    assert not [name for name in legacy if (ROOT / f"{name}-preview.png").exists()]


def test_public_contributor_docs_exist():
    for relative in (
        "CONTRIBUTING.md", "SECURITY.md", ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert len(content) > 100, relative


def test_quick_start_is_not_an_obsolete_version():
    quick = (ROOT / "docs/QUICK_START.md").read_text(encoding="utf-8")
    assert f"v{__version__}" in quick
    assert not re.search(r"v0\.1[0-9]\.0", quick)
