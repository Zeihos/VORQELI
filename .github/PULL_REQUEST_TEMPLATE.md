## Что изменено

<!-- Краткое описание и ссылка на связанную задачу -->

## Как проверено

- [ ] `python -m compileall -q src scripts tests`
- [ ] `python -m pytest -q`
- [ ] `python scripts/check_repo_layout.py`
- [ ] `python scripts/verify_build_manifest.py`
- [ ] `BUILD_MANIFEST.json` и `SHA256SUMS.txt` обновлены
- [ ] Сетевые изменения и риски описаны
- [ ] Windows CI прошёл (для изменений EXE/установщика)

## Риски и совместимость

<!-- Включая DNS/HOSTS, права администратора, трей, автозапуск и восстановление -->
