# Восстановление Zeihos/VORQELI после удаления файлов

Сборка **Windows build #27** завершилась ошибкой `Directory '.[dev]' is not installable` потому что к моменту запуска в `main` не оказалось `pyproject.toml`. Перед публикацией нового ZIP проверьте, что репозиторий содержит **все файлы проекта на верхнем уровне**, в частности `pyproject.toml`, `src/`, `assets/`, `installer/`, `scripts/`, `.github/workflows/`.

## Способ 1 — Git (рекомендуется для обновлений)

Требуется установленный Git. Запустите PowerShell в каталоге загрузок:

```powershell
git clone https://github.com/Zeihos/VORQELI.git
Expand-Archive -Path .\VORQELI-Connect-v0.26.0-source.zip -DestinationPath .\VORQELI -Force
cd .\VORQELI
py -3 scripts/check_repo_layout.py
git status --short
git add -A
git commit -m "Restore project and release v0.26.0"
git push origin main
```

Если `git clone` сообщает, что папка уже существует, используйте другой каталог или существующую чистую копию. Не выполняйте `git init` поверх уже клонированного репозитория.

После push проверьте [Actions](https://github.com/Zeihos/VORQELI/actions). Первый шаг **Verify checkout completeness and release versions** должен завершиться успешно; если файлов не хватает, он покажет точные имена.

## Способ 2 — сайт GitHub

Разархивируйте ZIP и загрузите **содержимое** архива в [корень репозитория](https://github.com/Zeihos/VORQELI/upload/main), не папку `VORQELI-v0.26.0` и не ZIP-файл как единственный объект. Веб-интерфейс может не сохранять вложенные папки в зависимости от способа выбора файлов — после загрузки обязательно проверьте наличие `.github/workflows/windows-build.yml`.

## Проверка и установка

- `py -3 scripts/check_repo_layout.py` — проверка полного состава файлов (без внешних библиотек).
- `py -3 -m pip install -e ".[dev]"` — установка пакета для разработки.
- `py -3 -m pytest -q` — юнит-тесты.
- GitHub Actions проверяет создание EXE, диагностику без сетевых изменений, упаковку Inno Setup и безопасное удаление.

**Не распространяйте сборку как стабильную, пока не пройдены испытания DNS, WinDivert, Telegram и автозапуска после перезагрузки Windows.**
