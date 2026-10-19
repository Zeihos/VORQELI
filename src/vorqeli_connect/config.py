"""Persist user preferences in their profile, not beside an executable."""
from dataclasses import asdict, dataclass, field
from .secret_storage import serialize_secret, deserialize_secret
from pathlib import Path
import json
import os
import threading
import shutil
import re
import tempfile
import io

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VorqeliConnect"
CONFIG_PATH = APP_DIR / "settings.json"
_WRITE_LOCK = threading.RLock()


def off_intent_path(path: Path = CONFIG_PATH) -> Path:
    """Independent, persistent OFF intent, deliberately outside settings.json.

    Unlike a previous settings.bak snapshot, an OFF marker cannot be mistaken
    for an old ON choice when the primary settings write is interrupted.
    """
    return path.with_name(path.name + '.off-intent')


def _persist_off_intent(path: Path) -> None:
    """Write and fsync the OFF marker before replacing any settings file.

    The marker remains present for as long as OFF is intended. The temporary
    file is created exclusively in the same directory, and its rename is atomic.
    """
    marker = off_intent_path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.off-intent-', dir=marker.parent)
    try:
        with io.open(fd, 'wb') as stream:
            stream.write(b'OFF\n')
            stream.flush()
            os.fsync(stream.fileno())
        Path(temp_name).replace(marker)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _off_intent_present(path: Path) -> bool:
    """Fail CLOSED on an unexpected failure inspecting the OFF marker."""
    try:
        return off_intent_path(path).exists() or off_intent_path(path).is_symlink()
    except OSError:
        return True



@dataclass
class Settings:
    dpi_profile: str = "Not configured"
    telegram_port: int = 1443
    telegram_source_dir: str = ""
    telegram_python: str = ""
    telegram_secret: str = ""
    # Runtime-only recovery fields; never included in JSON as plain metadata.
    telegram_secret_dpapi_blob: str = field(default='',repr=False,compare=False)
    telegram_secret_error: str = field(default='',repr=False,compare=False)
    dpi_bundle_dir: str = ""
    dpi_mode: str = "alt_auto"
    dns_mode: str = "plain"
    launch_at_startup: bool = True
    minimize_to_tray: bool = True
    admin_on_launch: bool = True
    restore_last_mode: bool = True
    desired_enabled: bool = False
    connect_dpi: bool = True
    connect_telegram: bool = True
    connect_dns: bool = True
    window_geometry: str = "1170x740"
    first_launch_notice: bool = True
    telegram_link_opened: bool = False


_FLAGS = frozenset({
    'launch_at_startup', 'desired_enabled', 'connect_dpi', 'connect_telegram',
    'connect_dns', 'first_launch_notice', 'telegram_link_opened',
    'minimize_to_tray', 'admin_on_launch', 'restore_last_mode',
})
_STRINGS = frozenset({
    'dpi_profile', 'telegram_source_dir', 'telegram_python', 'dpi_bundle_dir',
})
_GEOMETRY = re.compile(r'^[0-9]{3,5}x[0-9]{3,5}(?:\+[0-9]{1,5}\+[0-9]{1,5})?$')


def _validate_settings_fields(data: dict) -> dict:
    """Reject malformed persisted values rather than misreading e.g. 'false' as True.

    A corrupted primary file is rejected so a known-good backup can be used.
    Unknown keys are ignored for compatibility with later schema versions.
    """
    if not isinstance(data, dict):
        raise ValueError('Настройки должны быть JSON-объектом')
    result = {}
    fields = Settings.__dataclass_fields__
    for name in _FLAGS:
        if name in data:
            if type(data[name]) is not bool:
                raise ValueError(f'Некорректная логическая настройка: {name}')
            result[name] = data[name]
    for name in _STRINGS:
        if name in data:
            if not isinstance(data[name], str) or len(data[name]) > 4096:
                raise ValueError(f'Некорректная текстовая настройка: {name}')
            result[name] = data[name]
    if 'telegram_port' in data:
        port = data['telegram_port']
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Некорректный порт Telegram')
        result['telegram_port'] = port
    if 'dpi_mode' in data:
        if data['dpi_mode'] not in ('fake', 'multisplit', 'auto', 'alt_auto',
                                    *(f'alt{i}' for i in range(1,14))):
            raise ValueError('Неизвестная DPI-стратегия')
        result['dpi_mode'] = data['dpi_mode']
    if 'dns_mode' in data:
        if type(data['dns_mode']) is not str or data['dns_mode'] not in ('plain', 'doh'):
            raise ValueError('Неизвестный режим GeoHide DNS')
        result['dns_mode'] = data['dns_mode']
    if 'window_geometry' in data:
        size = data['window_geometry']
        if not isinstance(size, str) or not _GEOMETRY.fullmatch(size):
            raise ValueError('Некорректный размер окна')
        result['window_geometry'] = size
    for name in ('telegram_secret', 'telegram_secret_dpapi'):
        if name in data:
            if not isinstance(data[name], str) or len(data[name]) > 16384:
                raise ValueError('Некорректные данные защищённого ключа Telegram')
    # These are never read as user-configurable fields, even if the JSON has them.
    return result


def _read_settings_data(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    _validate_settings_fields(data)
    return data


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    """Recover last known-good settings if the primary JSON was interrupted.

    Neither a backup nor a decryption failure should cause the protected
    Telegram secret to be silently erased by a following autosave.
    """
    if not path.exists():
        # A previous interrupted rename may have left only the backup.
        if not path.with_suffix('.bak').exists():
            return Settings()
    data = None
    recovered_from_backup = False
    for candidate in (path, path.with_suffix('.bak')):
        try:
            data = _read_settings_data(candidate)
            recovered_from_backup = candidate != path
            break
        except (OSError, ValueError, TypeError, UnicodeError):
            continue
    if data is None:
        return Settings()
    selected = _validate_settings_fields(data)
    if _off_intent_present(path):
        # The last explicit OFF request wins over older/corrupt JSON and
        # even a previously persisted ON state.
        selected['desired_enabled'] = False
    if recovered_from_backup:
        # A backup is a prior state. It can contain ON even if the most recent
        # user action was OFF. Never silently re-enable networking after a
        # damaged/missing primary configuration; require one explicit click.
        selected['desired_enabled'] = False
    try:
        selected['telegram_secret'] = deserialize_secret(data)
    except (OSError, ValueError, UnicodeError):
        selected['telegram_secret'] = ''
        selected['telegram_secret_dpapi_blob'] = str(data.get('telegram_secret_dpapi', ''))[:16384]
        selected['telegram_secret_error'] = 'Ключ Telegram недоступен для текущего профиля Windows'
    try:
        return Settings(**selected)
    except (ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings, path: Path = CONFIG_PATH) -> None:
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not settings.desired_enabled:
            # If writing settings.json now fails or power is lost mid-rename,
            # the old ON value cannot cause unwanted autoconnection on reboot.
            _persist_off_intent(path)
        tmp = path.with_suffix(".tmp")
        data = asdict(settings)
        data.pop('telegram_secret', None)
        data.pop('telegram_secret_dpapi_blob', None)
        data.pop('telegram_secret_error', None)
        if settings.telegram_secret:
            data.update(serialize_secret(settings.telegram_secret))
        elif settings.telegram_secret_dpapi_blob:
            data['telegram_secret_dpapi'] = settings.telegram_secret_dpapi_blob
        else:
            data['telegram_secret'] = '' 
        # Never replace a valid backup with a corrupted primary file.
        # Also never perpetuate a plaintext Telegram secret from old releases
        # in settings.bak when Windows DPAPI migration is available.
        backup = path.with_suffix('.bak')
        if path.is_file():
            try:
                old_data = _read_settings_data(path)
            except (OSError, ValueError, TypeError, UnicodeError):
                pass
            else:
                if os.name == 'nt' and old_data.get('telegram_secret'):
                    migrated = dict(old_data)
                    plaintext = migrated.pop('telegram_secret')
                    migrated.update(serialize_secret(plaintext))
                    backup_tmp = backup.with_suffix('.bak.tmp')
                    with backup_tmp.open('w', encoding='utf-8') as handle:
                        json.dump(migrated, handle, ensure_ascii=False, indent=2)
                        handle.flush()
                        os.fsync(handle.fileno())
                    backup_tmp.replace(backup)
                else:
                    shutil.copy2(path, backup)
        # Flush file content before atomic rename. Backup provides a way out
        # if power is lost during settings serialization or storage failure.
        with tmp.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
        if settings.desired_enabled:
            # Only re-arm autoconnection AFTER an ON state is durably saved.
            # Failure leaves OFF marker in place (the safer recovery option).
            off_intent_path(path).unlink(missing_ok=True)
