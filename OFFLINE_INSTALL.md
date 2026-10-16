# Установка без интернета, root, apt, npm и Docker

Цель: Debian 13.x Trixie amd64, обычный CPython 3.13 с работоспособными стандартными
модулями `ssl`, `zlib`, `sqlite3`, `ctypes`. Ядро должно разрешать Chromium sandbox.
Python другой minor-версии требует отдельной сборки wheels; не подменяйте метаданные.

Скопируйте из одного успешного Release в один каталог:

- `install_offline.py`
- `bundle_common.py` (стандартная библиотека проекта, без сторонних зависимостей)
- `security-tools-debian13-amd64.tar.gz`
- `security-tools-debian13-amd64.tar.gz.sha256`

```sh
python3 --version
python3 install_offline.py --bundle security-tools-debian13-amd64.tar.gz
. "$HOME/security-tools/activate.sh"
semgrep --version
checkov --version
gitleaks version
grype db status
python3 -c 'from playwright.sync_api import sync_playwright; print("OK")'
python3 "$HOME/security-tools/verify_tools.py"
python3 "$HOME/security-tools/test_security_audit.py" --strict
"$HOME/security-tools/run-opencode.sh"
```

При неактивированном окружении используйте полный путь `~/security-tools/bin/python3`.
Параметры CLI Python в fallback поддерживают скрипт, `-c`, `-m`, stdin и основные
флаги; произвольные сложные комбинации флагов требуют обычного venv.

Вызовы:

```sh
semgrep scan --config "$HOME/security-tools/current/payload/rules" /path/to/source
gitleaks dir /path/to/source
gitleaks git /path/to/existing/git/repo
checkov -d /path/to/iac
grype dir:/path/to/source
grype sbom:/path/to/bom.json
```

Semgrep registry/URL configs запрещены wrapper-ом. Базы Checkov встроены в wheels,
скачивание политик и внешних модулей отключено. Grype не ищет контейнерные образы в
реестрах по умолчанию. База CVE фиксируется на дату сборки: обновите весь комплект,
когда сможете перенести свежий Release. Наличие базы не гарантирует полноту SCA.

## Chromium

```sh
python3 "$HOME/security-tools/diagnose_browser.py"
```

Проверяются полные Chromium и headless shell, `ldd` и локальная HTML без сети.
Дополнительные совместимые Debian `.so` лежат в payload/runtime/lib. Они подключены
только wrapper-ами, системная glibc не заменяется. Если диагностика сообщает другую
отсутствующую `.so`, передайте её имя для обновления runtime-пакета. Не используйте
`--no-sandbox` для обхода ограничений LXC: администратор должен разрешить безопасную
работу namespace sandbox или предоставить VM.

## Опциональный ZAP

Скопируйте `security-zap-debian13-amd64.tar.gz` и соседний `.sha256`:

```sh
python3 install_offline.py --bundle security-zap-debian13-amd64.tar.gz
zap -version
```

ZAP использует отдельный переносимый JRE 21; список и версии включённых `.zap`
add-ons находятся в MANIFEST.json. Наличие ZAP не означает проверку всех активных
сканеров; активные проверки выполняйте только на согласованных целях. Для работы
с браузером ZAP может потребоваться настройка конкретного пути/драйвера; это не
заявляется как проверенная интеграция Selenium/AJAX Spider.

## Повторная установка и откат

Повторите ту же команду установки. Новое поколение создаётся отдельно и проверяется;
`current` переключается только после успеха. Предыдущее поколение сохраняется.
Проекты, skill и OpenCode config не затрагиваются. После завершения процессов старые
поколения можно удалить вручную. Не удаляйте каталог, на который указывает `current`.

Проверка fallback: `python3 install_offline.py --bundle ... --force-target`.
Если процесс принудительно завершён, убедитесь, что другого установщика нет, затем
удалите пустой `~/security-tools/.install-lock` через `rmdir` и повторите.

Установщик не настраивает UFW и доступ к Ollama. Существующие сетевые правила и
адрес сервера LLM сохраняются.
