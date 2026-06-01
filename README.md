# Мониторинг предложений RTX 5070 Ti для покупки в РФ

Проект отслеживает предложения по **RTX 5070 Ti** в российских магазинах и маркетплейсах, фильтрует нерелевантные позиции, сравнивает цены с заданными порогами и отправляет отчёты/сигналы в **Telegram**.

## Основные возможности

- **Мониторинг магазинов и маркетплейсов РФ** — отслеживание предложений на основных площадках и у отдельных продавцов.
- **Фильтрация нерелевантного** — отсев дублей, неподходящих моделей и завышенных цен.
- **Гибкие ценовые пороги** — отдельные пороги для обычного и срочного сигнала.
- **Отчёты в Telegram** — автоматическая отправка найденных предложений.
- **Браузерный режим** — отдельный запуск для источников с JS-рендерингом (может требовать доустановки браузерных зависимостей).
- **Автономный режим** — работа на отдельной Windows-машине через Task Scheduler с самостоятельным циклом доработки через ИИ-агентов.
- **Диагностика источников** — учёт доступности, блокировок и ошибок парсинга.

## Безопасность и секреты

**В репозитории не хранятся никакие токены или учётные данные.** Telegram-токен и chat_id читаются **из переменных окружения**, а не из файлов проекта:

- Обычный мониторинг (`monitor_5070_ti_v_2.py`) читает `TG_BOT_TOKEN` и `TG_CHAT_ID` из окружения.
- Автономный агент читает `AGENT_NOTIFY_TELEGRAM_BOT_TOKEN` и `AGENT_NOTIFY_TELEGRAM_CHAT_ID` из локального файла **вне репозитория** (`C:\ProgramData\MonitorAgent\agent-notify.env`).

Файл `config.json` содержит **только несекретные ценовые пороги** — поэтому он спокойно хранится в репозитории. Токены в него вписывать не нужно.

## Быстрый старт

### Требования
- Python 3.10+
- pip

### Установка
```bash
git clone https://github.com/MarattKh/monitor-5070ti.git
cd monitor-5070ti
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### Настройка Telegram (через переменные окружения)
Токен в файлы проекта вписывать не нужно — задай переменные окружения перед запуском:

```powershell
# Windows (PowerShell), на текущую сессию:
$env:TG_BOT_TOKEN = "<токен_бота>"
$env:TG_CHAT_ID   = "<id_чата>"
```
```bash
# macOS/Linux:
export TG_BOT_TOKEN="<токен_бота>"
export TG_CHAT_ID="<id_чата>"
```

### Ценовые пороги
Пороги задаются в `config.json` (это не секрет):
`max_price_rub`, `new_good_price`, `new_urgent_buy`, `used_good_price`, `used_urgent_buy`.
За образцом структуры можно смотреть `config.example.json`.

### Запуск

**Разовый мониторинг (с отправкой в Telegram):**
```bash
.\.venv\Scripts\python.exe monitor_5070_ti_v_2.py
```

**Вариант с браузерным рендерингом** (для источников, требующих JS):
```bash
run_monitor_browser.bat
```

**Обслуживание истории цен** (обрезка/ротация файла истории):
```bash
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --keep-records 5000
```

### Автономный запуск (Windows Task Scheduler)
Для регулярной работы используются батники в корне проекта (`run_monitor.bat`, `run_daily_report.bat`, `run_monitor_browser.bat`) — настрой их в Task Scheduler на нужное расписание.

## Структура проекта

```
monitor-5070ti/
├── parsers/                # Парсеры для разных магазинов и маркетплейсов
├── tests/                  # Набор тестов
├── tools/                  # Утилиты: история цен, диагностика, автономный агент
├── config.example.json     # Пример структуры конфигурации
├── config.json             # Ценовые пороги (несекретные)
├── models.py               # Модели данных и логика фильтрации
├── monitor_5070_ti_v_2.py  # Основной скрипт мониторинга
├── requirements.txt        # Зависимости
├── run_*.bat               # Батники запуска для Windows
└── LICENSE                 # MIT
```

## История цен

Найденные предложения сохраняются в `price_history.jsonl` (в репозиторий не коммитится). Управление размером файла:

```bash
# Оставить последние 5000 записей
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --keep-records 5000

# Ротация при превышении 10 МБ
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --rotate-over-bytes 10485760

# Предпросмотр без записи
.\.venv\Scripts\python.exe -m tools.price_history_maintenance price_history.jsonl --keep-records 5000 --dry-run
```

## Разработка и тестирование

Проект развивается через **Pull Request** и ИИ-агентов (**Claude Code**, **Codex**). Автономный агент работает по циклу «ветка → изменения → тесты → PR» с защитой от наложения запусков и безопасным авто-мержем только для неопасных изменений (изменения в ядре агента уходят на ручное ревью).

**Запуск тестов:**
```bash
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

**Рабочий процесс:**
1. Отдельная ветка (`git checkout -b feature/что-то-новое`).
2. Изменения + прогон тестов.
3. Pull Request с описанием.
4. После review и merge ветка удаляется.

## Лицензия

Проект распространяется под лицензией **MIT** — см. файл [LICENSE](./LICENSE).

## Обратная связь

Вопросы и идеи улучшений — через [Issues](https://github.com/MarattKh/monitor-5070ti/issues) или Pull Request.

---

**Статус:** активная разработка · набор тестов проходит ✅
