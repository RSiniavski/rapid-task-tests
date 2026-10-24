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