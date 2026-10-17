from vorqeli_connect.config import Settings, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(telegram_port=24444)
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_missing_settings(tmp_path):
    assert load_settings(tmp_path / "missing.json") == Settings()
