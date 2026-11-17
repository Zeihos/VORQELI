<div align="center">

<img src="assets/VORQELI-logo.png" alt="VORQELI Connect" width="108">

# VORQELI Connect

**Центр управления подключением для Windows 10/11**

Управление DPI / WinWS, локальным Telegram MTProto и GeoHide DNS в одном приложении.

[![Windows CI](https://github.com/Zeihos/VORQELI/actions/workflows/windows-build.yml/badge.svg)](https://github.com/Zeihos/VORQELI/actions/workflows/windows-build.yml)
![Версия](https://img.shields.io/badge/версия-0.41.0_RC-8f69ca)
![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-30313f)
[![Лицензия MIT](https://img.shields.io/badge/лицензия-MIT-6a5acd)](LICENSE)

[**Скачать тестовую Windows-сборку**](https://github.com/Zeihos/VORQELI/actions/workflows/windows-build.yml) ·
[**Быстрый старт**](docs/QUICK_START.md) ·
[**Сообщить об ошибке**](https://github.com/Zeihos/VORQELI/issues)

</div>

![Фирменное оформление VORQELI Connect](assets/brand-banner.jpg)

> [!IMPORTANT]
> **v0.41.0 — Release Candidate, не стабильная v1.0.0.** Автоматические тесты Windows, создание EXE и установщика не доказывают доступность отдельных сайтов и корректность обхода на любой сети. Требуются ручные испытания на Windows 10/11. Сборки из GitHub Actions могут не иметь цифровой подписи издателя.

## Возможности

| Компонент | Назначение |
| --- | --- |
| **DPI / WinWS** | Управление стратегиями Flowseal, включая AUTO и ALT1–ALT13 |
| **Telegram MTProto** | Управление локальным прокси для Telegram Desktop |
| **GeoHide DNS** | Настройка системного IPv4 DNS или DoH при явном выборе |
| **GeoHide HOSTS** | Просмотр и применение дополнительных правил по отдельному подтверждению |
| **Диагностика** | Проверка HTTPS-ответов сервисов, DNS и состояния модулей |
| **Восстановление** | Резервные копии DNS/HOSTS, контролируемый откат при ошибках |
| **Windows** | Трей, автозапуск, восстановление выбранного состояния, установщик |

Интерфейс выполнен в **Premium Dark**: чёрно-фиолетовые поверхности, шесть разделов, настоящие элементы Tkinter Canvas и управление с клавиатуры. Статус «Модули запущены» **не является** подтверждением обхода ограничений.

Проект **не является VPN**, не обещает анонимность или шифрование всего интернет-трафика и не связан официально с Flowseal или GeoHide. DPI, DNS и HOSTS — разные механизмы, поэтому результаты их работы могут различаться.

## Установка на Windows

1. Откройте [**Windows build — GitHub Actions**](https://github.com/Zeihos/VORQELI/actions/workflows/windows-build.yml) и выберите **успешный** запуск ветки `main`.
2. В разделе **Artifacts** скачайте `VORQELI-Connect-v0.41.0-Windows` и распакуйте ZIP.
3. Сверьте SHA-256 файлов с `SHA256SUMS.txt` внутри артефакта, проверьте источник загрузки и при необходимости запустите `VORQELI-Connect-Setup.exe`.
4. При первом запуске выберите компоненты и нажмите **«Подключить»**. Для WinWS и системных DNS/HOSTS могут потребоваться права администратора.
5. После использования нажмите **«Отключить»**; перед удалением приложения проверьте, что DNS и HOSTS восстановлены.

**Важно:** не устанавливайте неподписанные исполняемые файлы из посторонних источников. SHA-256 служит проверкой целостности относительно опубликованного артефакта, но не заменяет Authenticode-подпись.

Подробные инструкции, Telegram Desktop, DoH, HOSTS и восстановление: **[Быстрый старт](docs/QUICK_START.md)**.

## Интерфейс

| Раздел | Что доступно |
| --- | --- |
| Главная | Общий статус и подключение / отключение |
| Диагностика | Результаты сервисов и дополнительные проверки |
| История | События, фильтры и экспорт |
| О проекте | Версия, компоненты, проверка обновлений |
| Настройки | Трей, автозапуск, выбор модулей |
| Сеть и стратегии | AUTO / ALT1–ALT13, DNS, DoH, HOSTS и восстановление |

**Принципы:** реальные данные вместо нарисованных статусов, кнопки реагируют на повторное нажатие, отдельный фокус для клавиатуры, прокрутка при компактном окне. HTTP 403/429 не считается подтверждённой доступностью сервиса.

## Запуск из исходников

Требуются Windows 10/11, Python 3.12, Git. В PowerShell:

```powershell
git clone https://github.com/Zeihos/VORQELI.git
cd VORQELI
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m vorqeli_connect --version
.\.venv\Scripts\python.exe -m vorqeli_connect
```

Для использования встроенного Telegram-модуля из Python-исходников дополнительно требуется закреплённая версия зависимого проекта:

```powershell
.\.venv\Scripts\python.exe -m pip install "git+https://github.com/Flowseal/tg-ws-proxy.git@307a384ab7f522e34bb1a045884d0bd90f40bee5"
```

Проверка исходников без запуска сетевых компонентов:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_repo_layout.py
.\.venv\Scripts\python.exe scripts/verify_build_manifest.py
```

Полный EXE и Inno Setup-установщик собираются через **[GitHub Actions](https://github.com/Zeihos/VORQELI/actions)** на Windows.

## Структура репозитория

```text
VORQELI/
├── .github/       # Windows CI, шаблоны Issues и PR
├── assets/        # Логотип, значок и ресурсы приложения
├── docs/          # Руководства, архитектура и история изменений
├── installer/     # Inno Setup
├── scripts/       # Проверки, Windows smoke-тесты
├── src/           # Исходный код VORQELI Connect
├── tests/         # Регрессионные тесты
├── BUILD_MANIFEST.json
├── SHA256SUMS.txt
└── pyproject.toml
```

Манифест сборки проверяет полный перечень значимых файлов и SHA-256 до начала Windows-сборки. Подробности — [документация по релизу](docs/RELEASE_VALIDATION.md).

## Состояние проекта

- **Реализовано и проверяется автоматически:** Python-тесты, проверка манифеста, сборка EXE, Inno Setup и ряд безопасных Windows smoke-тестов.
- **До стабильного релиза:** реальные испытания WinWS / Telegram / GeoHide на разных сетях, проверка восстановления DNS/HOSTS, UAC, автозапуска после перезагрузки, различных масштабов интерфейса и подписи издателя.
- **Поддержка:** Windows 10/11 x64. Поддержка других ОС не заявлена.

План работ: [ROADMAP](docs/ROADMAP.md) · Регламент испытаний: [RELEASE_VALIDATION](docs/RELEASE_VALIDATION.md) · Изменения: [CHANGELOG](CHANGELOG.md).

## Участие и безопасность

Предложения и исправления приветствуются: [**CONTRIBUTING.md**](CONTRIBUTING.md). Сообщать о дефектах можно через [Issues](https://github.com/Zeihos/VORQELI/issues), не публикуя Telegram-secret, содержимое журналов с личными данными или другие конфиденциальные сведения.

Для потенциальных уязвимостей используйте [**SECURITY.md**](SECURITY.md). Сведения о сторонних компонентах и их лицензиях: [NOTICE.md](NOTICE.md) и [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).

**Лицензия исходного кода:** [MIT](LICENSE). Сторонние компоненты распространяются на условиях собственных лицензий.
