# Stage 1N: автоматизированное рабочее место

Цель: сделать воспроизводимое рабочее пространство для `monitor-5070ti`, чтобы Windows PC или сервер могли быстро подготовить проект, проверить окружение, выполнить тесты, запустить smoke-проверки и сформировать отчет.

## Базовый путь

```text
F:\Codex\monitor-5070ti
```

## Что должно быть установлено

- Git.
- GitHub CLI (`gh`) и авторизация `gh auth login`.
- Python 3.12.
- PowerShell 7.
- Node.js LTS и npm для установки Codex CLI.
- Codex CLI.

## Команды проверки проекта

```powershell
cd F:\Codex\monitor-5070ti
$env:PYTHONPATH = "F:\Codex\monitor-5070ti"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=F:\Codex\monitor-5070ti\.pytest-tmp
.\.venv\Scripts\python.exe tools\smoke_dns.py
.\.venv\Scripts\python.exe tools\smoke_dns.py --browser
.\.venv\Scripts\python.exe monitor_5070_ti_v_2.py --browser --daily-report
```

## Команда Codex для неинтерактивной задачи

Шаблон:

```powershell
codex exec --cd F:\Codex\monitor-5070ti --sandbox workspace-write "Выполни задачу по AGENTS.md. Сначала проверь main, создай stage-ветку, внеси минимальные изменения, запусти тесты и smoke, подготовь краткий отчет."
```

Важно: режим полного автоматического выполнения без внешней изоляции небезопасен. Для обычной локальной работы использовать `--sandbox workspace-write`.

## Планировщик Windows

Ежедневный отчет можно запускать через Task Scheduler командой, которая вызывает PowerShell 7 и `scripts/run_monitor.ps1` после добавления файла в проект.

## Что не коммитить

- `.venv/`
- `.env`
- `results.json`
- `results.csv`
- `results.md`
- `urgent_deals.md`
- `latest_ai_prompt.md`
- `monitor.log`
- `debug_html/`
- `.pytest-tmp/`

## Граница автоматизации

Можно автоматизировать установку зависимостей, тесты, smoke, запуск отчетов, создание веток и PR. Нельзя безопасно полностью убрать контроль человека для доступа к аккаунтам, секретам, платежам, покупкам, изменению защищенных настроек ОС и слиянию непроверенного кода в `main`.
