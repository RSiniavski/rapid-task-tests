# Rapid Task autotests

pytest + Playwright tests for the Rapid Task app (FastAPI backend, Vue front end).

## Setup (Windows PowerShell)

    pip install -r requirements.txt
    playwright install chromium
    python tools/fetch_vendor.py      # copies Vue, Sortable, marked, DOMPurify, turndown into vendor/

The browser tests serve these libraries from `vendor/`, so they run offline and the same every time.

## Run

By default the suite starts its own isolated copy of the app (own SQLite DB and uploads folder):

    $env:RAPID_TASK_SRC = "D:\path\to\rapid-task"     # folder that contains app/ and static/
    pytest -q

Useful options (environment variables):

| Variable | Meaning |
|----------|---------|
| `RAPID_TASK_SRC` | App source folder (needed for the local server mode) |
| `BASE_URL` | Use an already running app instead; tests that need the DB or files are skipped |
| `HEADED=1` | Show the browser |
| `SLOW_MO` | Slow browser actions down (ms) |
| `UI_TIMEOUT_MS` | Browser wait timeout (default 10000) |

A variable can also be put in a `.env` file. The HTML report is written to `reports/report.html`.

Run parts of the suite:

    pytest tests/api -q             # API only
    pytest -m ui -q                 # browser tests
    pytest -k markdown -q           # by name

## Structure

- `tests/api`, `tests/ui`, `tests/e2e`, `tests/meta`: the tests
- `pages/`: page objects (Board, Roadmap ...), `framework/`: server, factory, fixtures, plan-ID registry
- Every test has `@pytest.mark.plan("ID")`. All IDs live in `framework/plan_ids.py`; a meta test fails on an unknown ID.
- Known defects are marked `known_issue` (xfail). Now: the donate links are still placeholders.

## Markdown tests (MD-01 ... MD-05)

| ID | What it checks | File |
|----|----------------|------|
| MD-01 | Description is shown as formatted Markdown | tests/ui/test_markdown_ui.py |
| MD-02 | Scripts, `javascript:` links and external images are not executed or shown | tests/ui/test_markdown_ui.py |
| MD-03 | Ticket keys become cards (icon, key, title, status); own link words are kept | tests/ui/test_markdown_ui.py |
| MD-04 | WYSIWYG editor: hotkeys, toolbar, Tab nesting, checkboxes, saved as Markdown | tests/ui/test_markdown_ui.py |
| MD-05 | Read-only users have no editor; the Create dialog has one | tests/ui/test_markdown_ui.py |

Note: the description editor is `[data-testid=desc-editor]` (a contenteditable box), not a `textarea`.

## Theme Engine tests (THEME-01 … THEME-08)

| ID | What it checks | File |
|----|----------------|------|
| THEME-01 | Theme list: 6 presets, auth required, custom themes are private | tests/api/test_themes.py |
| THEME-02 | Personal theme (`PUT /api/users/me/theme`): set, reset, unknown id, foreign theme | tests/api/test_themes.py |
| THEME-03 | Import and strict validation: 21 attack cases (CSS injection, `url()`, fonts, sizes, unknown keys), size limit, 20 themes per user | tests/api/test_themes.py |
| THEME-04 | Export and delete: round trip, presets cannot be deleted, links are cleared | tests/api/test_themes.py |
| THEME-05 | Project theme and lock: only admin can change, members can read, lock needs a theme | tests/api/test_themes.py |
| THEME-06 | Which theme wins in the UI: project lock > personal > project theme > default | tests/ui/test_themes_ui.py |
| THEME-07 | Profile selector, import, export, delete, lock hint | tests/ui/test_themes_ui.py |
| THEME-08 | "Theme" tab in project settings (admin edits, others read only) | tests/ui/test_themes_ui.py |

Run only these tests:

    pytest tests/api/test_themes.py tests/ui/test_themes_ui.py

Notes:
- Tests use throw-away users (`make_user`), so the shared role users keep no personal theme.
- Avatar tests must skip the theme file input: `input[type=file]:not([data-testid=theme-file])`.
- Known gap: the live color picker with preview was intentionally not built.
