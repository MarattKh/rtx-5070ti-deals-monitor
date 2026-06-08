# Руководство по сопровождению

## 1. Как перенацелить на другой товар

Все продуктовые параметры находятся в **`target.json`**. Файл читается один раз при старте — ничего больше менять не нужно.

```json
{
  "product_id": "rtx_5070_ti",
  "label": "RTX 5070 Ti",
  "query": "rtx 5070 ti",
  "relevance": { ... },
  "source_filters": { ... }
}
```

### Поля

| Поле | Назначение |
|---|---|
| `product_id` | Идентификатор в `price_history.jsonl` и медианном фильтре |
| `label` | Название в Telegram-отчётах и `results.md` |
| `query` | Поисковый запрос для 4 текстовых источников (Ситилинк, Регард, СДЭК Shopping, Яндекс Маркет) |
| `relevance` | Правила фильтрации; см. ниже |
| `source_filters` | Продуктовый токен для 5 фильтровых источников; см. ниже |

### `relevance`

```json
"relevance": {
  "match_any": [
    {"all_tokens": ["5070", "ti"]},
    {"compact": "5070ti"},
    {"part_codes": ["n507t", "ne7507t"]}
  ],
  "exclude_patterns": ["5070\\s+super"]
}
```

- **`all_tokens`** — все перечисленные токены должны присутствовать в заголовке (пробелы, точки, скобки игнорируются).
- **`compact`** — строка без пробелов должна содержать подстроку (подходит для `"RTX5070Ti"`).
- **`part_codes`** — список префиксов парт-кода производителя (первые символы после `NE`/`N`); совпадение регистронезависимо.
- **`exclude_patterns`** — Python-регексы; совпадение исключает товар даже при срабатывании `match_any`.

### `source_filters`

Пять источников фильтруют каталог по продуктовому токену. Значение пустая строка — источник пропускается с пометкой «не настроен» (не ошибка).

| Источник | Что означает значение | Где взять |
|---|---|---|
| `XCOM-SHOP` | Slug в пути `/filter/graficheskiy-processor=<slug>/` | URL страницы категории товара на xcom-shop.ru |
| `KNS` | Slug в пути `/_graficheskij-protsessor_<slug>/` | URL страницы категории товара на kns.ru |
| `Ф-Центр` | Числовой `param=` в URL (`/product/type/7?param=<id>`) | URL категории товара на fcenter.ru |
| `Позитроника` | Ключ Bitrix-фильтра (`arrFilter_NNNN_XXXXXXXXXX`); значение всегда `=Y` | Значение поля `name` у чекбокса фильтра на positronica.ru |
| `НИКС` | Токен в пути URL товара (`/autocatalog/...<token>_<id>.html`) | URL любой карточки товара на nix.ru |

### Пороги в `config.json`

```json
{
  "new_good_price":    90000,
  "new_urgent_buy":    75000,
  "used_good_price":   65000,
  "used_urgent_buy":   50000,
  "median_window_days": 30,
  "median_min_count":   5,
  "suspicious_pct":    65,
  "buy_pct":           90,
  "at_market_pct":    110
}
```

`suspicious_pct` / `buy_pct` / `at_market_pct` — пороги относительно медианы (%). `median_min_count` — минимальное число точек истории для надёжной медианы.

### История цен при смене товара

Медиана фильтруется по `product_id`. При смене товара:

- **Вариант 1 — архивировать:** переименовать `price_history.jsonl` в `price_history_rtx5070ti.jsonl`; новый файл создастся автоматически.
- **Вариант 2 — перетегировать:** если хочется сохранить историю под новым `product_id`:

```bash
python -m tools.price_history_maintenance price_history.jsonl --set-product-id <new_product_id>
```

---

## 2. Что делать, когда источник перестал отдавать офферы

### Шаг 1 — читать source-health в Telegram-отчёте

Строка `source_health` делит источники на четыре группы:

- **Рабочие** — вернули офферы после фильтра.
- **Молчат** — подключились, но вернули 0 офферов (нет товара в наличии или изменилась вёрстка).
- **Не настроены для товара** — токен в `source_filters` пустой; источник не опрашивался.
- **Заблокировано / Проблемы** — 401/403/429 или сетевая ошибка.

### Шаг 2 — диагностика по типу проблемы

#### Молчат: изменилась вёрстка или логика каталога

Анатомия парсера (`parsers/<источник>.py`):

```
CATALOG_URL / SEARCH_URL   — точка входа
CARD_RE / PRODUCT_RE / ITEM_RE  — regex или microdata блока карточки
LINK_RE + PRICE_RE / NAME_RE    — поля внутри блока
parse_cards(html)          — возвращает list[dict] из title/price/url
detect_block_reason(html)  — отличает антибот-стр. от пустого каталога
parse_offers_with_status() — точка входа для монитора
```

Действия:
1. Скачать страницу каталога вручную (curl/браузер).
2. Проверить, изменился ли HTML вокруг CATALOG_URL, CARD_RE, PRICE_RE.
3. Обновить regex/селекторы в `parse_cards`. URL не меняется, пока slug не переехал.

#### Заблокировано: 401/403 или жёсткий антибот

Не пробивать. Отключить источник (см. ниже) и оставить заметку в PR.

#### Не настроены для товара

Дописать нужный токен в `source_filters` в `target.json`.

### Отключить / включить источник

В `monitor_5070_ti_v_2.py`:

```python
ENABLED_SOURCES: tuple[tuple[str, Any], ...] = (
    ("Ситилинк", citilink),
    # ("Регард", regard),   ← закомментировать для отключения
    ...
)
```

Если у источника есть `detect_block_reason` и `parse_offers_with_status`, он также должен быть в `STATUS_AWARE_SOURCE_NAMES` (строка сразу после `ENABLED_SOURCES`). При отключении удалить оттуда тоже.

---

## 3. Как добавить новый источник

### Шаблон модуля `parsers/<name>.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from models import ProductOffer
from parsers.common import _clean_text
from target_config import get_source_filter

_FILTER = get_source_filter("<Название>")          # если фильтровый источник
CATALOG_URL = f"https://example.com/gpu/?filter={_FILTER}" if _FILTER else ""

_NOT_CONFIGURED = {
    "offers": [], "blocked": False, "block_reason": None,
    "warnings": ["Источник не настроен для данного товара"], "errors": 0,
}

_UA = "Mozilla/5.0 ..."

def parse_cards(html: str) -> list[dict]:
    ...  # возвращает [{"title": str, "price": float, "url": str}, ...]

def detect_block_reason(html: str) -> str | None:
    ...  # "403 forbidden" / "429 too many requests" / None

def parse_offers_with_status(browser_mode: bool = False) -> dict:
    if not CATALOG_URL:
        return _NOT_CONFIGURED
    try:
        html = ...  # urlopen
    except HTTPError as exc:
        if exc.code in (401, 403, 429):
            return {"offers": [], "blocked": True, "block_reason": f"{exc.code} ...",
                    "warnings": ["<Name> access blocked."], "errors": 1}
        return {"offers": [], "blocked": False, "block_reason": None,
                "warnings": [str(exc)], "errors": 1}
    except (URLError, TimeoutError) as exc:
        return {"offers": [], "blocked": False, "block_reason": None,
                "warnings": [str(exc)], "errors": 1}

    offers = _build_offers(html)
    if offers:
        return {"offers": offers, "blocked": False, "block_reason": None, "warnings": [], "errors": 0}
    block_reason = detect_block_reason(html)
    if block_reason:
        return {"offers": [], "blocked": True, "block_reason": block_reason,
                "warnings": ["<Name> access blocked."], "errors": 1}
    return {"offers": [], "blocked": False, "block_reason": None, "warnings": [], "errors": 0}

def parse_offers(browser_mode: bool = False) -> list[ProductOffer]:
    return parse_offers_with_status(browser_mode)["offers"]
```

**Контракт `parse_offers_with_status`** — возвращает dict с полями:

| Поле | Тип | Значение |
|---|---|---|
| `offers` | `list[ProductOffer]` | Найденные офферы |
| `blocked` | `bool` | True при антибот-ответе |
| `block_reason` | `str \| None` | Причина блокировки |
| `warnings` | `list[str]` | Некритичные предупреждения |
| `errors` | `int` | Число ошибок (0 или 1) |

### Регистрация

В `monitor_5070_ti_v_2.py`:

```python
from parsers import ..., myshop

ENABLED_SOURCES = (
    ...
    ("МойМагазин", myshop),
)

STATUS_AWARE_SOURCE_NAMES = {..., "МойМагазин"}   # если есть detect_block_reason
```

### Тест

Создать `tests/test_myshop.py` с fixture из реального HTML-фрагмента (минимум одна карточка). Обязательно проверить:

- `parse_cards` возвращает хотя бы один dict с `title`, `price`, `url`.
- `parse_offers` возвращает `list[ProductOffer]` без исключений.
- `parse_offers_with_status` с пустым `CATALOG_URL` (монкипатч) возвращает `_NOT_CONFIGURED`.

### Fixture-trap guard

Перед мерджем — живой прогон с реальным сетевым запросом к источнику:

```bash
python -c "from parsers.myshop import parse_offers_with_status; r = parse_offers_with_status(); print(len(r['offers']), r['warnings'])"
```

Убедиться, что возвращается хотя бы один оффер. Фикстуры из устаревшего HTML дают 100% тестов при нулевом парсинге в проде.
