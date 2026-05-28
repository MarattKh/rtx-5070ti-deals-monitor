# Локальный запуск Codex-агента

Этот каталог хранит небольшие markdown-задачи для локального агента. Одна задача должна описывать один узкий шаг: что проверить, какие файлы можно менять, какие проверки запустить и чего не делать.

## Одна задача

Безопасный порядок работы:

1. Подготовить один файл задачи в `tools/agent_tasks/`.
2. Запустить агент на отдельной ветке:

   ```powershell
   python tools/agent_run.py --task tools/agent_tasks/stage_1n_citilink_diagnostics.md --branch agent/stage-1n-citilink-diagnostics --create-pr --pr-title "Add Citilink diagnostics"
   ```

3. Скрипт проверит git-репозиторий и чистое рабочее дерево, перейдет на `main`, выполнит `git pull --ff-only`, создаст ветку, передаст текст задачи в `codex exec --profile agent`, запустит тесты и покажет краткий diff.
4. По умолчанию проверки: `python -m pytest -q` и `python tools/smoke_dns.py`, если файл существует.
5. `monitor_5070_ti_v_2.py` не запускается по умолчанию, потому что он может отправлять уведомления. Для ручной проверки используйте отдельную команду или флаг `--check-monitor`, только если окружение безопасно.
6. Коммит, push и PR выполняются только если проверки прошли и есть изменения. Автоматического merge нет.

Полезные режимы:

- `--dry-run` показывает изменяющие команды без их выполнения.
- `--create-pr` создает PR через `gh pr create` после успешного push.
- `--pr-title` задает заголовок PR и сообщение коммита.
- `--pr-body` задает описание PR.

Лог последнего запуска пишется в `C:\ProgramData\MonitorAgent\agent-last.log`, если у процесса есть права на запись. Если прав нет, вывод остается в консоли.

## Режим очереди

`tools/agent_cycle.py` запускает несколько подготовленных задач из `tools/agent_tasks/queue.json` и передает каждую задачу в `tools/agent_run.py`. Очередь остается чистой: результат выполнения хранится отдельно в `C:\ProgramData\MonitorAgent\agent-cycle-state.json`.

Пример безопасного запуска одной задачи с созданием PR:

```powershell
python tools/agent_cycle.py --once --max-tasks 1 --create-pr
```

Параметры:

- `--once` запускает один проход очереди и завершает процесс. Сейчас это основной режим; скрипт не делает бесконечный цикл.
- `--max-tasks N` ограничивает число задач за запуск. По умолчанию выполняется только одна задача.
- `--create-pr` передает в `agent_run.py` флаг создания PR. Без этого задача может завершиться локальным коммитом/веткой по логике `agent_run.py`.
- `--auto-merge-safe` разрешает осторожный auto-merge только после проверки PR через `gh`. По умолчанию auto-merge выключен.
- `--no-auto-merge` явно оставляет auto-merge выключенным.
- `--dry-run` передает dry-run в `agent_run.py` и печатает изменяющие команды без выполнения.
- `--state PATH` задает путь к runtime state, если нужно тестировать или изолировать запуск.
- `--log PATH` задает путь к логу. По умолчанию используется `C:\ProgramData\MonitorAgent\agent-cycle-last.log`, если есть права на запись.
- `--notify` включает необязательные уведомления в Telegram и/или email. По умолчанию уведомления выключены.
- `--notify-test` отправляет тестовое уведомление и завершает процесс без запуска очереди.
- `--notify-on failed,needs_review` ограничивает события для уведомлений. По умолчанию используется `all`.

Настройки уведомлений читаются из переменных окружения и из файла `C:\ProgramData\MonitorAgent\agent-notify.env`; переменные окружения имеют приоритет над файлом. Поддерживаемые ключи:

```text
AGENT_NOTIFY_TELEGRAM_TOKEN=...
AGENT_NOTIFY_TELEGRAM_CHAT_ID=...
AGENT_NOTIFY_EMAIL_HOST=smtp.example.com
AGENT_NOTIFY_EMAIL_PORT=587
AGENT_NOTIFY_EMAIL_USERNAME=...
AGENT_NOTIFY_EMAIL_PASSWORD=...
AGENT_NOTIFY_EMAIL_FROM=agent@example.com
AGENT_NOTIFY_EMAIL_TO=ops@example.com,dev@example.com
AGENT_NOTIFY_EMAIL_TLS=true
AGENT_NOTIFY_EMAIL_SSL=false
```

Для Telegram скрипт использует `urllib.request`, для email - стандартные `smtplib` и `email`. Если не настроен ни один канал, `--notify` ничего не отправляет. Доступные события: `needs_review`, `failed`, `auto_merge_denied`, `dirty_worktree`, `pr_created_without_merge`, `cycle_completed_with_errors`.

Auto-merge специально консервативный. Перед merge скрипт проверяет, что PR открыт и mergeable, получает список измененных файлов через `gh pr diff --name-only`, и отказывает в merge для инфраструктурных и чувствительных путей: `.github/`, `tools/agent_run.py`, `tools/agent_cycle.py`, `tools/agent_tasks/queue.json`, файлы с `secret`, `env`, `token`, `credential` или `key` в пути, scheduler/system setup файлы, а также dependency-файлы вроде `pyproject.toml`, `*.toml` и `requirements*.txt`.

Причина простая: изменения инфраструктуры, секретов, расписаний и зависимостей могут менять права, окружение запуска или supply chain. Такие PR должны оставаться открытыми для ручного просмотра. Первые задачи очереди рассчитаны на создание PR; merge выполняйте вручную или запускайте `--auto-merge-safe` только для небольших прикладных изменений.
