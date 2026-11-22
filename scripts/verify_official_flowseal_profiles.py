"""Read-only WinWS argument compatibility smoke for pinned official Flowseal ZIP.

Executed on isolated Windows CI. Downloads only the SHA-256-pinned release into
a temporary directory; never launches winws.exe, installs drivers or edits HOSTS.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from vorqeli_connect.assets_manager import (
    ZAPRET_SHA256, ZAPRET_TAG, ensure_zapret, engine_integrity,
)
from vorqeli_connect.flowseal_alts import (
    ALT_MODES, ALT_PRIORITY, EXTRA_PROFILE_FILES, build_alt_arguments,
)


def main() -> None:
    assert ZAPRET_TAG == '1.10.4', 'Review compatibility after changing the pinned release'
    assert ZAPRET_SHA256 == '291af673bd0238506f9548e0e94ca0abf244000f4c9a06960544fb01c5f97b34'
    assert set(ALT_PRIORITY) == set(ALT_MODES)
    with TemporaryDirectory(prefix='vorqeli-official-flowseal-') as temporary:
        root = ensure_zapret(base_dir=Path(temporary))
        assert root.name == 'zapret-' + ZAPRET_TAG
        assert engine_integrity(root) == 'verified'
        expected_exe = str(root / 'bin' / 'winws.exe')
        profiles = (*ALT_MODES, *EXTRA_PROFILE_FILES)
        assert len(profiles) == 22
        for mode in profiles:
            args = build_alt_arguments(root, mode)
            assert args and args[0].startswith('--wf-tcp='), mode
            assert not any('.bat' in item.lower() for item in args), mode
            assert not any('%' in item for item in args), mode
            # Every profile must still work when Game Filter is enabled.
            game_args = build_alt_arguments(root, mode, game_mode='all',
                                            game_tcp_ports='1024-65535',
                                            game_udp_ports='1024-65535')
            assert game_args and game_args[0].startswith('--wf-tcp='), mode
        assert Path(expected_exe).is_file()
        print('Official Flowseal ' + ZAPRET_TAG + ': 22/22 profiles parsed safely')


if __name__ == '__main__':
    main()
