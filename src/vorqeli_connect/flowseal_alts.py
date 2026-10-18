"""Safely derive winws argv from the pinned Flowseal 1.10.3 ALT batch profiles.

Never execute CMD, .bat, service.bat or shell commands. The only executable is
bin/winws.exe inside the archive SHA-256 verified by assets_manager. Unsupported
placeholders and unexpected token syntax fail closed. Optional game-specific
filters are skipped because service.bat is deliberately NOT executed.
"""
from __future__ import annotations

import re
from pathlib import Path

ALT_MODES = tuple(f'alt{i}' for i in range(1, 14))
# An empirical trial order, NOT an assertion of universal effectiveness.
ALT_PRIORITY = ('alt2', 'alt6', 'alt11', 'alt12', 'alt13',
                'alt4', 'alt3', 'alt8', 'alt9', 'alt7', 'alt10', 'alt1', 'alt5')
assert set(ALT_MODES) == set(ALT_PRIORITY)
_SCRIPT = re.compile(r'\bstart\s+"zapret:\s*%~n0"\s+/min\s+"%BIN%winws\.exe"\s+(.*)',
                     flags=re.IGNORECASE | re.DOTALL)
_TOKEN = re.compile(r'--[a-z0-9][a-z0-9-]*(?:=(?:"[^"]*"|[^\s]+))?', re.IGNORECASE)
_OPTION = re.compile(r'--[a-z0-9][a-z0-9-]*(?:=.*)?\Z', re.IGNORECASE)
_VARIABLE = re.compile(r'%[a-zA-Z0-9_]+%')


def alt_filename(mode: str) -> str:
    if mode not in ALT_MODES:
        raise ValueError('Неизвестный профиль Flowseal ALT')
    return 'general (ALT).bat' if mode == 'alt1' else f'general (ALT{int(mode[3:])}).bat'


def _source_options(script: str) -> tuple[str, ...]:
    """Only read the options after the single official WinWS start declaration.

    Reject embedded commands rather than running a BAT interpreter. The tag's
    scripts contain only --option arguments after this marker and caret/newline
    continuations; an unexpected fragment means an unsupported upstream layout.
    """
    match = _SCRIPT.search(script)
    if not match or script[:match.start()].count('start "zapret:'):
        raise ValueError('Не найден официальный запуск WinWS в ALT-профиле')
    body = re.sub(r'\^\s*\r?\n', ' ', match.group(1)).strip()
    # Catch any non-option token / injected extra command.
    options = []
    cursor = 0
    for token in _TOKEN.finditer(body):
        if body[cursor:token.start()].strip():
            raise ValueError('ALT-профиль содержит неподдерживаемый фрагмент')
        options.append(token.group())
        cursor = token.end()
    if body[cursor:].strip() or not options:
        raise ValueError('ALT-профиль содержит неподдерживаемый фрагмент')
    if not options[0].startswith('--wf-tcp=') or not any(o.startswith('--filter-tcp=') for o in options):
        raise ValueError('В ALT-профиле отсутствуют обязательные TCP-фильтры')
    return tuple(options)


def build_alt_arguments(root: Path, mode: str) -> tuple[str, ...]:
    """Parse a trusted extracted profile to argv; never pass text through a shell.

    The official service.bat creates optional *-user.txt lists and game filter
    variables. Missing optional user lists are omitted, while unexpanded game
    filters are omitted as whole --new groups. No unverified script is run.
    """
    script_path = root / alt_filename(mode)
    if script_path.is_symlink() or not script_path.is_file() or script_path.stat().st_size > 40_000:
        raise ValueError('ALT-файл Flowseal отсутствует либо недопустим')
    try:
        src = script_path.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Неверная кодировка ALT-профиля') from exc
    options = _source_options(src)
    groups: list[list[str]] = [[]]
    for entry in options:
        if entry == '--new':
            groups.append([])
        else:
            groups[-1].append(entry)
    output: list[str] = []
    for group in groups:
        if not group:
            continue
        if any('--filter-tcp=%GameFilterTCP%' in entry or
               '--filter-udp=%GameFilterUDP%' in entry for entry in group):
            continue
        converted: list[str] = []
        for token in group:
            if token.startswith('--wf-'):
                token = token.replace(',%GameFilterTCP%', '').replace(',%GameFilterUDP%', '')
            if token.startswith('--filter-') and _VARIABLE.search(token) and 'GameFilter' in token:
                raise ValueError('Неразрешённый игровой фильтр Flowseal')
            # Strip surrounding quotes on a value; the subprocess argv preserves
            # spaces without shell quoting.
            if '="' in token and token.endswith('"'):
                key, value = token.split('=', 1)
                token = f'{key}={value[1:-1]}'
            if '%LISTS%' in token or '%BIN%' in token:
                if '=' not in token:
                    raise ValueError('Недопустимая ссылка на файл Flowseal')
                key, value = token.split('=', 1)
                prefix = '%LISTS%' if value.startswith('%LISTS%') else '%BIN%'
                if not value.startswith(prefix):
                    raise ValueError('Неизвестное размещение ресурса Flowseal')
                name = value[len(prefix):]
                if not re.fullmatch(r'[a-zA-Z0-9_.-]+', name) or '..' in name:
                    raise ValueError('Недопустимое имя ресурса Flowseal')
                base = root / ('lists' if prefix == '%LISTS%' else 'bin')
                path = base / name
                if not path.is_file() or path.is_symlink():
                    if prefix == '%LISTS%' and name.endswith('-user.txt'):
                        # Original service.bat creates these; omitted safely.
                        continue
                    raise ValueError('В официальном профиле не найден ресурс: ' + name)
                token = key + '=' + str(path)
            if '%' in token or not _OPTION.fullmatch(token):
                raise ValueError('Неизвестная переменная или аргумент ALT-профиля')
            converted.append(token)
        if converted:
            if output:
                output.append('--new')
            output.extend(converted)
    if not output or '--wf-tcp=' not in ''.join(output):
        raise ValueError('ALT-профиль не содержит правил перехвата')
    if len(output) > 280:
        raise ValueError('ALT-профиль слишком большой')
    return tuple(output)
