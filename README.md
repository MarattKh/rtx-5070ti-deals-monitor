# RTX 5070 Ti — мониторинг цен по российской рознице

Автономный ежедневный мониторинг цен на **GeForce RTX 5070 Ti** в 9 российских магазинах. Сравнивает цены с рыночной медианой, формирует сигналы на покупку и отправляет отчёт в **Telegram**.

## Источники (9 активных)

| Магазин | Тип |
|---|---|
| Ситилинк | Сетевой ритейлер |
| Регард | Онлайн-магазин |
| СДЭК Shopping | Маркетплейс |
| Яндекс Маркет | Маркетплейс |
| XCOM-SHOP | Онлайн-магазин |
| Ф-Центр | Онлайн-магазин |
| KNS | Онлайн-магазин |
| Позитроника | Сетевой ритейлер |
| НИКС | Онлайн-магазин |

## Как работает

```
Windows Task Scheduler
    └─► C:\ProgramData\MonitorAgent\run-monitor.cmd
            └─► python monitor_5070_ti_v_2.py
                    ├─► парсинг 9 источников
                    ├─► фильтрация (RTX 5070 Ti, не аксессуары)
                    ├─► сравнение с рыночной медианой (история цен)
                    ├─► сигналы: URGENT_BUY / GOOD_PRICE / NORMAL
                    └─► Telegram: алерт + ежедневный отчёт
```

Медиана считается по последним 30 дням из `price_history.jsonl`. Пороги сигналов настраиваются в `config.json`.

## Быстрый старт

### Требования

- Python 3.10+
- pip

### Установка

```bash
git clone https://github.com/MarattKh/rtx-5070ti-deals-monitor.git
cd rtx-5070ti-deals-monitor
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Настройка Telegram

Токены задаются через переменные окружения, не хранятся в файлах:

```powershell
$env:TG_BOT_TOKEN = "<токен_бота>"
$env:TG_CHAT_ID   = "<id_чата>"
```

### Ценовые пороги

Пример структуры — в `config.example.json`. Скопируй в `config.json` и задай значения в рублях:

```json
{
  "new_good_price": 90000,
  "new_urgent_buy": 75000,
  "used_good_price": 65000,
  "used_urgent_buy": 50000
}
```

### Запуск

```bash
# Разовый мониторинг
python monitor_5070_ti_v_2.py

# С ежедневным отчётом в Telegram
python monitor_5070_ti_v_2.py --daily-report

# Браузерный режим (для источников с JS-рендерингом)
python monitor_5070_ti_v_2.py --browser

# Локальный хелпер (Windows)
run_monitor.bat
```

## Структура проекта

```
rtx-5070ti-deals-monitor/
├── parsers/                 # Парсеры 9 магазинов
├── tests/                   # Набор тестов (268 тестов)
├── tools/                   # Утилиты: агент, история цен, диагностика
├── config.example.json      # Пример конфигурации
├── config.json              # Ценовые пороги (не секрет)
├── models.py                # Модели данных
├── monitor_5070_ti_v_2.py   # Основной скрипт
├── requirements.txt         # Зависимости
├── run_monitor.bat          # Локальный хелпер запуска
└── LICENSE                  # MIT
```

## История цен

Предложения сохраняются в `price_history.jsonl` (в репозиторий не коммитится). Управление:

```bash
# Оставить последние 5000 записей
python -m tools.price_history_maintenance price_history.jsonl --keep-records 5000

# Ротация при превышении 10 МБ
python -m tools.price_history_maintenance price_history.jsonl --rotate-over-bytes 10485760
```

## Безопасность

- Telegram-токены читаются из переменных окружения, не хранятся в репозитории.
- `price_history.jsonl`, `debug_html/`, `*.log`, `.env` перечислены в `.gitignore`.
- `config.json` содержит только несекретные числовые пороги.

## Тестирование

```bash
python -m pytest tests/ -v
```

268 тестов, покрывают парсеры, фильтрацию, Telegram-отчёт, историю цен.

## Лицензия

MIT — см. [LICENSE](./LICENSE).
