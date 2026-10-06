# Rapid Task — Набір автоматизованих тестів

Даний репозиторій містить набір автоматизованих UI-тестів (Playwright) та API-тестів (pytest + requests) для системи управління завданнями **Rapid Task**.

---

## 🛠 Передумови та встановлення

1. **Python 3.10+**
2. **Запущений бекенд / додаток Rapid Task** на `http://127.0.0.1:8000`.

### Встановлення залежностей

```bash
# Створення та активація віртуального середовища (опціонально)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Встановлення необхідних бібліотек
pip install -r requirements.txt

# Встановлення браузерів для Playwright
playwright install chromium
```

---

## 📁 Структура тестів

- **`conftest.py`**:
  - `authenticated_page` — фікстура Playwright для UI-тестів (автоматична реєстрація, авторизація та подальший Hard Delete користувача для очищення БД).
  - `api_client` — хелпер `APIClient` для зручного виконання API-запитів.
  - `test_user` — фікстура створення тестового користувача з Bearer-токеном та автоочищенням після завершення тесту.
  
- **`tests/test_board.py`** — UI-тести дошки завдань:
  - `test_create_ticket` — створення тікета через UI модальне вікно та перевірка його наявності в колонці `ToDo`.
  - `test_drag_and_drop_ticket` — перетягування (Drag & Drop) картки тікета між колонками `ToDo` -> `In progress`.
  - `test_open_ticket_modal` — відкриття детального перегляду тікета по кліку на картку.

- **`tests/test_tickets_api.py`** — API-тести управління тікетами:
  - `test_delete_ticket_by_id_success` — видалення тікета за числовим ID (`DELETE /api/tickets/{ticket_id}`) зі статусом `204 No Content`.
  - `test_delete_ticket_by_key_success` — видалення тікета за ключем (`DELETE /api/tickets/key/{ticket_key}`) зі статусом `204 No Content`.
  - `test_delete_ticket_not_found` — перевірка повернення `404 Not Found` при спробі видалити неіснуючий тікет.
  - `test_delete_ticket_unauthorized` — перевірка повернення `401 Unauthorized` при відсутності або невалідному токені.

- **`tests/test_users_api.py`** — API-тести видалення та деактивації користувачів:
  - **Режим 1: М'яке видалення (Soft Delete / Деактивація)**:
    - `test_soft_delete_user_via_delete_endpoint` — `DELETE /api/users/{user_id}` без прапорців. Встановлює `is_active = False`, блокує токени та вхід, зберігаючи дані тікетів.
    - `test_soft_delete_user_via_deactivate_endpoint` — `POST /api/users/{user_id}/deactivate`. Деактивація облікового запису.
  - **Режим 2: Повне видалення (Hard Delete / Cleanup)**:
    - `test_hard_delete_user_via_users_endpoint` — `DELETE /api/users/{user_id}?hard_delete=true`. Каскадне видалення користувача, його тікетів та історії.
    - `test_hard_delete_user_via_auth_users_endpoint` — `DELETE /api/auth/users/{user_id}?hard_delete=true`.
  - **Перевірки валідації та доступу**:
    - `test_delete_user_not_found` — перевірка `404` для неіснуючих користувачів.
    - `test_delete_user_unauthorized` — перевірка захисту ендпоінтів (`401 Unauthorized`).

---

## 🚀 Параметри та команди запуску тестів

За замовчуванням у файлі `pytest.ini` встановлено опції:
`--headed --browser chromium --slowmo 500`

### 1. Запуск усіх тестів

```bash
pytest
```

### 2. Запуск конкретного тестового файлу

```bash
# Лише UI тести дошки
pytest tests/test_board.py

# Лише API тести видалення тікетів
pytest tests/test_tickets_api.py

# Лише API тести користувачів (Soft/Hard delete)
pytest tests/test_users_api.py
```

### 3. Запуск конкретного тесту за назвою (фільтрація через `-k`)

```bash
# Запустити тест видалення тікета за ID
pytest -k "test_delete_ticket_by_id_success"

# Запустити всі тести, пов'язані з hard delete
pytest -k "hard_delete"
```

### 4. Налаштування відображення браузера (UI тести)

```bash
# Запуск у фоновому (headless) режимі без відкриття вікна браузера
pytest -o addopts="" tests/test_board.py

# Запуск із відкриттям вікна браузера (headed)
pytest --headed tests/test_board.py

# Зміна швидкості виконання (уповільнення на N мілісекунд між діями)
pytest --slowmo 1000 tests/test_board.py
```

### 5. Вибір браузера

```bash
# Chromium (за замовчуванням)
pytest --browser chromium

# Firefox
pytest --browser firefox

# WebKit (Safari engine)
pytest --browser webkit
```

### 6. Додаткові корисні параметри `pytest`

| Параметр | Опис |
| :--- | :--- |
| `-v` / `--verbose` | Детальний вивід результатів кожного тесту |
| `-s` | Відображення виводу в консоль (`print` / `stdout`) під час прогону |
| `-x` / `--exitfirst` | Зупинити виконання тестів після першого падіння |
| `--maxfail=N` | Зупинити прогін після `N` падінь |
| `-q` / `--quiet` | Скорочений вивід |
| `--durations=N` | Показати `N` найповільніших тестів |

---

## 🧹 Очищення даних (Cleanup)

Усі тести автоматично очищають тестові сутності в БД після кожного прогону за допомогою виклику ендпоінта повної сесійної зачистки:
`DELETE /api/users/{user_id}?hard_delete=true`
Це забезпечує ізольованість тестів та відсутність накопичення сміттєвих даних у тестовій базі.
