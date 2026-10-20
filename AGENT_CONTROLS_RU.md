# Harness² + Numbat + LlamaFirewall: Debian 13.7 / amd64, офлайн

Этот дополнительный комплект устанавливается в `~/agent-controls`, отдельно от
`~/security-tools`. Требуется обычный CPython **3.13** и Debian 13 (Trixie), x86_64.
Root, sudo, Docker, apt, npm, системный pip и интернет при установке не нужны.
Python-окружения создаются на целевом хосте; при отсутствии venv используется
изолированный `pip --target`. Нужен полный системный Python, включая ssl/ctypes.
Рекомендуется 8 ГБ свободного диска для двух поколений установки, 4 ГБ свободной
RAM. PyTorch CPU не занимает VRAM отдельного сервера Ollama. В архиве есть
небольшой набор runtime-библиотек Debian (libstdc++, libgcc, libgomp, libgmp,
zlib) с лицензиями и версиями; они подключаются только к процессам комплекта.
Системные glibc и ELF loader не заменяются.

## Что именно подготовлено

| Проект | Режим в комплекте | Ограничение |
|---|---|---|
| Google Research Harness² 0.1.0, commit в lock | Исходники, wheel, CLI, настоящее локальное демо рекурсии | Не сервис контроля безопасности. Полные JobBench/LAB/WorkBuddy и облачные зависимости не подготовлены |
| Perplexity Numbat 0.3.0 | Официальный Linux amd64 бинарник, встроенные правила, локальный OpenCode-плагин | Для OpenCode **observe-only**, `--enforce` здесь не даёт блокировку |
| Meta LlamaFirewall 1.0.3 | Regex + HiddenASCII; отдельно CodeShield 1.0.1, Semgrep CE, CPU PyTorch | PromptGuard и AlignmentCheck не включены в рабочий профиль |
| `airgap-firewall.js` | Наш отдельный синхронный адаптер проверки аргументов инструмента перед вызовом | Это ограниченный текстовый фильтр, не песочница и не полноценная авторизация команд |

Веса PromptGuard требуют доступа к gated-репозиторию Meta и соблюдения лицензии;
их нет в архиве. `llamafirewall configure` не запускайте: он может потребовать
загрузку моделей/учётные данные. В комплекте нельзя вызывать LlamaFirewall с
конструктором по умолчанию: upstream включает модельные сканеры. Наш адаптер
явно выбирает только локальные сканеры. CodeShield запускается отдельным профилем
и не применяется автоматически ко всем аргументам инструментов.

## 1. Скачать и перенести

В GitHub Releases выберите **Agent controls: Debian 13 amd64 / Python 3.13**,
созданный успешным workflow `Build offline agent controls`.
Не выбирайте `Source code (zip)` — там нет зависимостей.

Перенесите в одну папку на сервере:

```text
install_agent_controls.py
bundle_common.py
agent-controls-debian13-amd64-py313.tar.gz
agent-controls-debian13-amd64-py313.tar.gz.sha256
```

Также сохраните `agent-controls-resolved.json`, `offline-test.json`, эту инструкцию.
В resolved указаны точные транзитивные версии, SHA-256, источники и время сборки.
SHA проверяет целостность; установщик и сам checksum нужно получать из доверенного
Release. Тяжёлых файлов в Git-истории нет, архив меньше 2 GiB, не разбит на части.

Пример переноса с компьютера, на котором уже скачаны файлы:

```sh
scp install_agent_controls.py bundle_common.py agent-controls-debian13-amd64-py313.tar.gz agent-controls-debian13-amd64-py313.tar.gz.sha256 USER@OPENCODE_HOST:~/airgap-agent-controls/
```

Папку назначения создайте заранее: `mkdir -p ~/airgap-agent-controls` на сервере.
При переносе флешкой скопируйте эти четыре файла в эту папку обычным файловым
менеджером. Флешку форматировать не требуется.

## 2. Установка под тем пользователем, который запускает OpenCode

```sh
cat /etc/os-release
uname -m
python3 --version
cd ~/airgap-agent-controls
python3 install_agent_controls.py --bundle agent-controls-debian13-amd64-py313.tar.gz
. "$HOME/agent-controls/activate.sh"
python3 "$HOME/agent-controls/current/verify_agent_controls.py"
```

Установщик сам проверяет SHA до распаковки, пути, ссылки, архитектуру, Python и
каждый файл manifest; затем запускает обязательные локальные проверки. Старое
поколение сохраняется, `current` переключается только после успешных проверок.
Повторная установка — та же команда. Если окружение venv неисправно:

```sh
python3 install_agent_controls.py --bundle agent-controls-debian13-amd64-py313.tar.gz --force-target
```

Скиллы OpenCode и существующие конфиги установщик не изменяет. Перед изменением
плагинов ниже сохраните копии имеющихся одноимённых файлов, если они уже есть.

## 3. Включить Numbat для существующего OpenCode

Это нужно делать с HOME и OPENCODE_CONFIG_DIR того же пользователя/сервиса.
Примеры используют стандартное расположение `~/.config/opencode`.

```sh
. "$HOME/agent-controls/activate.sh"
umask 077
mkdir -p "$HOME/.numbat"
numbat version
numbat hook install --agent opencode --emit all --output file --output-file "$HOME/.numbat/live.ndjson"
numbat hook status --agent opencode
```

Numbat создаст `~/.config/opencode/plugins/numbat.ts`. Он не требует npm-пакетов.
Если OPENCODE_CONFIG_DIR задан, файл будет в `$OPENCODE_CONFIG_DIR/plugins/`;
при XDG_CONFIG_HOME — в `$XDG_CONFIG_HOME/opencode/plugins/`.
Полностью перезапустите OpenCode после установки, затем попросите его выполнить
безвредный локальный вызов, например `pwd`.

В другом терминале:

```sh
tail -f "$HOME/.numbat/live.ndjson"
```

Должна появиться запись реального действия из новой сессии. `hook status`
подтверждает конфигурацию, **не исполнение плагина**. Проверьте ошибки в логах
OpenCode, если записей нет. После обновления комплекта повторите `hook install`:
Numbat встраивает абсолютный путь бинарника в плагин.

`--emit all` даёт поток событий; не включайте `--content raw` без необходимости.
Numbat может сохранять редактированные фрагменты действий; журналы содержат
рабочую информацию. Не загружайте их в GitHub. Учитывайте рост файла и настройте
локальную ротацию/пересылку на ваш внутренний сборщик по политике организации.
Внешний HTTP-сборщик, `ship` и OTLP не включаются автоматически.

## 4. Проверить LlamaFirewall без подключения к OpenCode

```sh
printf '%s' '{"text":"Summarize this local file"}' | agent-firewall-scan
printf '%s' '{"text":"ignore previous instructions"}' | agent-firewall-scan
printf '%s' '{"text":"#include <stdio.h>\nint main() { char x[8]; gets(x); }"}' | agent-firewall-scan --profile code
```

Ожидаются решения `allow`, `block`, `block`. JSON `status` должен быть `success`.
Код выхода 0 означает успешную проверку, **не обязательно allow**; решение нужно
читать из JSON. Код 2 означает ошибку. Скрипт не выводит проверяемый текст или
причины, которые могут раскрыть его. Стандартные Regex-правила включают PII:
возможны блокировки обычных email/телефонов. Это не оценка понимания смысла текста.

## 5. Дополнительный плагин LlamaFirewall для OpenCode

Сначала только наблюдение. Для стандартного каталога:

```sh
mkdir -p "$HOME/.config/opencode/plugins"
cp "$HOME/agent-controls/current/plugins/airgap-firewall.js" "$HOME/.config/opencode/plugins/airgap-firewall.js"
. "$HOME/agent-controls/activate.sh"
export AGENT_FIREWALL_MODE=monitor
opencode
```

Если конфиги расположены иначе, используйте тот же фактический каталог, который
показал Numbat. Плагин проверяет JSON аргументов `tool.execute.before` через
локальный subprocess, максимум 1 MiB, с timeout. Он не проверяет пользовательские
сообщения, tool output или ответы модели. CodeShield здесь автоматически не
вызывается: применяйте отдельную команду к коду до его принятия/исполнения.

Журнал содержит только время, этап, режим и решение:

```sh
tail -f "$HOME/.local/state/agent-controls/firewall.ndjson"
```

Сначала на отдельном тестовом проекте проверьте: безопасное действие получает
`allow`, заведомая строка `ignore previous instructions` в аргументе — `block`.
В режиме monitor оба действия могут выполняться. После проверки включите:

```sh
. "$HOME/agent-controls/activate.sh"
export AGENT_FIREWALL_MODE=enforce
opencode
```

В enforce адаптер бросает ошибку при `block`, неопределённом решении, timeout или
поломке сканера; действие не должно исполняться. **Проверьте это на вашей версии
OpenCode**: CI проверяет контракт плагина, не ваш установленный процесс. Фильтр
не распознаёт все опасные команды, обфускацию или внедрение инструкций. Разрешение
`allow` не означает безопасность действия.

Для OpenCode как сервиса передайте те же PATH, AGENT_FIREWALL_BIN и
AGENT_FIREWALL_MODE в реальное окружение сервиса, перезапустите его. Переменные
в SSH-терминале сами в уже работающий сервис не попадают. Можно запускать вручную:

```sh
. "$HOME/security-tools/activate.sh"   # если установлен прежний комплект
. "$HOME/agent-controls/activate.sh"
export AGENT_FIREWALL_MODE=monitor
opencode serve --hostname 0.0.0.0 --port 4096
```

Порт/аутентификацию оставьте согласно вашей существующей настройке OpenCode;
не открывайте 4096 во внешнюю сеть. Новых сетевых портов для этих трёх инструментов
не требуется. Существующее соединение OpenCode → Ollama остаётся как настроено.

Для отключения только адаптера уберите `airgap-firewall.js` из каталога plugins
и перезапустите OpenCode. Numbat продолжит наблюдение независимо от него.

## 6. Harness²: начать с реального офлайн-демо

```sh
. "$HOME/agent-controls/activate.sh"
harness2-demo --output "$HOME/harness2-runs/demo" --k 1
cat "$HOME/harness2-runs/demo/demo.json"
harness2 --help
harness2-check --help
```

Это upstream-демо с детерминированными редакторами и настоящими Python executions;
оно не обращается к LLM. Исходники и полная документация доступны локально:

```sh
ls "$HOME/agent-controls/current/sources/harness2"
cat "$HOME/agent-controls/current/sources/harness2/docs/SETUP.md"
```

Harness² — исследовательская система изменения harness под задачи, а не
автоматическая надстройка к произвольному уже запущенному OpenCode. В upstream
OpenCode executor встроен в benchmark adapters; полные benchmark environments
требуют дополнительных данных/Node/Bun, некоторые — Docker и облачных клиентов.
**Не запускайте `harness2-setup` в airgap**: он пытается скачивать зависимости.
Поэтому эта поставка готовит и проверяет ядро, но не обещает запуск полных
benchmark runs или оптимизацию вашего агента на Ollama одной командой.

Для следующего этапа нужны выбранный набор локальных задач и проверка адаптера
под ваш установленный OpenCode/provider. Делайте это в отдельном тестовом workspace,
с ограниченными файловыми правами и сетевым доступом только к внутреннему Ollama.
Не разрешайте саморедактируемому harness менять внешнюю политику контроля/журналы.

## 7. Граница контроля и диагностика

Пользователь, владеющий бинарниками, plugins и журналами, может их изменить или
отключить. Для обязательного корпоративного контроля администратор должен владеть
политикой/исполняемыми файлами и защищённым сборщиком логов. Rootless установка
сама по себе не обеспечивает такую границу. Numbat для OpenCode не имеет managed
enforce target. Используйте ограничения прав, сеть и изоляцию на хосте/Proxmox.

При `.so: cannot open shared object file` сохраните точное имя библиотеки и вывод:

```sh
python3 "$HOME/agent-controls/current/verify_agent_controls.py"
```

Не ставьте случайные библиотеки от Ubuntu и не подменяйте glibc. Сборка тестируется
на чистом Debian 13; дополнительные требования именно вашего хоста требуют
отдельного согласованного Debian runtime-пакета. Если Python другой версии —
этот cp313 архив не устанавливайте; нужна отдельная совместимая сборка.

## Проверки сборки и источники

CI работает в Debian Trixie, затем устанавливает без root и сети (`--network none`),
без pip/ensurepip/sudo/apt. Проверяет venv и fallback, повторную установку,
нативный Numbat/правила/синтетический callback, allow/block LlamaFirewall,
реальное обнаружение CodeShield и Harness² demo. Есть тесты повреждения/подмены,
path traversal, ссылок, архитектуры/Python, plugin timeout и fail-closed поведения.
Реальная версия OpenCode, загрузка hooks на вашем сервере, Ollama end-to-end,
PromptGuard и полные benchmarks остаются **непроверенными** до локальной проверки.

Официальные источники:

- https://github.com/google-research/harness2
- https://github.com/perplexityai/numbat/tree/v0.3.0
- https://github.com/meta-llama/PurpleLlama/tree/main/LlamaFirewall
- https://pypi.org/project/llamafirewall/1.0.3/
- https://download.pytorch.org/whl/cpu/torch/

Версии верхнего уровня закреплены в `agent-controls/versions.lock.json`.
Каждый wheel проверяется по SHA PyPI, CPU torch — по SHA официального индекса,
Numbat — по закреплённому SHA, checksums.txt и release digest. Harness wheel
собирается из закреплённого Git commit Google с сохранением исходников/лицензии;
его SHA после сборки фиксируется в manifest, это не upstream-подпись wheel.
Лицензии зависимостей остаются внутри wheels и каталога licenses/sources.
