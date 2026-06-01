# Agent Pipeline Fix Report — 2026-06-01

## Что было сломано

**Корневая причина:** Файл `docs/agent-runs/cycle-log.md` был untracked в рабочем дереве.
`agent_run.py` проверяет `git status --porcelain` перед запуском задачи и выдаёт ошибку
"Working tree is not clean" если вывод непустой — любой untracked файл блокирует все задачи.

Следствие: все задачи цикла (`stage_2e_automerge_validator`, `stage_2e_retry_resume`
и все более поздние) падали с `exit code 1` и записывались в state.json со статусом
`failed` (терминальный статус). Цикл выдавал `Selected tasks: 0` и ничего не делал.

**Вторая проблема (PowerShell 5.1):** Codex-агент внутри задачи использовал
`Get-Date -AsUTC`, который не поддерживается в PowerShell 5.1. Codex сам обошёл это
через `[DateTime]::UtcNow.ToString()`. Код `agent_cycle.py` / `agent_run.py` использует
Python datetime, проблема только внутри сессий Codex.

## Что починено

1. `docs/agent-runs/cycle-log.md` закоммичен в репозиторий через PR #58 — рабочее дерево стало чистым.
2. В `agent-cycle-state.json` статусы `stage_2e_automerge_validator` и `stage_2e_retry_resume`
   переведены из `failed` в `pending`.
3. Запущен один цикл — `stage_2e_automerge_validator` прошла, PR #59 создан и авто-смержен.
4. Запущен второй цикл — `stage_2e_retry_resume` отработала, PR #60 создан (статус `needs_review`,
   авто-мерж заблокирован: изменены `tools/agent_cycle.py` и `tools/agent_run.py`).

## Состояние очереди после починки

| Задача | Статус |
|--------|--------|
| stage_2e_automerge_validator | completed (PR #59 merged) |
| stage_2e_retry_resume | needs_review (PR #60, ожидает ручного мержа) |
| stage_2f_browser_helper | failed → ожидает ночного планировщика |
| stage_2f_browser_first_source | failed → ожидает ночного планировщика |
| stage_2f_browser_batch2 | failed → ожидает ночного планировщика |
| stage_2f_browser_batch3 | failed → ожидает ночного планировщика |
| stage_2g_queue_validator | failed → ожидает ночного планировщика |

> Задачи 2f/2g были заблокированы той же dirty-worktree проблемой.
> После включения планировщика их нужно будет перевести из `failed` в `pending` в state.json.

## 4 открытых вопроса

1. **PR #44 закрывать?** — Это DRAFT PR (Fix agent recovery, ветка `stability-reconciliation-contract`).
   Задание запрещает его трогать. Требует твоего решения.

2. **PR #50 влить?** — Не проверялся в рамках этого сеанса. Требует ручного ревью.

3. **Ветку `stage-1m-fix-dns-deep-parser` влить отдельно или оставить агенту?** —
   Задание запрещает удалять ветку, вопрос о мерже остаётся за тобой.

4. **Локальную ветку `agent/stage-2c-generic-browser-scraper` удалить?** —
   Ветка присутствует локально. Требует твоего решения.
