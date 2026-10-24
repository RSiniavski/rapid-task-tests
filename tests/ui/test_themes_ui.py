"""Theme Engine (UI): profile selector, import/export/delete, effective-theme rules, project Theme tab."""
import json

import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

HTML = "html"


def theme_by_key(client, key):
    return next(t for t in ok(client.get("/api/themes")).json() if t["key"] == key)


def valid_body(client, name="UI import", key="nord"):
    body = ok(client.get(f"/api/themes/{theme_by_key(client, key)['id']}/export")).json()
    body["name"] = name
    return body


def as_file(body, name="theme.json"):
    raw = body if isinstance(body, (bytes, str)) else json.dumps(body)
    return {"name": name, "mimeType": "application/json",
            "buffer": raw if isinstance(raw, bytes) else raw.encode()}


def open_profile(page, url="/dashboard.html"):
    page.goto(url)
    page.locator(".cabinet-btn").click()
    dlg = page.locator(".profile-modal")
    select = dlg.locator("[data-testid=theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)   # list loaded from the server
    return dlg, select


def data_theme(page, value):
    expect(page.locator(HTML)).to_have_attribute("data-theme", value)


def project_member(world, make_user, role="reporter"):
    u = make_user(tag="thui_")
    world.a.add_member(u, role)
    return u


# =================================================================== UI-02 / THEME-07
@pytest.mark.plan("UI-02", "THEME-07")
def test_profile_theme_selector_changes_and_persists(page, login_ui, make_user):
    u = make_user(tag="thui1_")
    login_ui(u)
    dlg, select = open_profile(page)
    select.select_option(label="Solarized Light")
    data_theme(page, "solarized_light")
    assert page.evaluate("localStorage.getItem('rt_theme')") == "solarized_light"
    assert page.evaluate("document.documentElement.style.colorScheme") == "light"
    page.reload()
    data_theme(page, "solarized_light")


@pytest.mark.plan("THEME-07")
def test_theme_choice_is_saved_on_the_server_and_follows_the_user(page, login_ui, make_user):
    u = make_user(tag="thui2_")
    login_ui(u)
    dlg, select = open_profile(page)
    select.select_option(label="Nord")
    data_theme(page, "nord")
    nord = theme_by_key(u.client, "nord")["id"]
    expect_saved = ok(u.client.get("/api/auth/me")).json()["theme_id"]
    assert expect_saved == nord
    # simulate another browser: forget the local cache, the server value must win
    page.evaluate("localStorage.removeItem('rt_theme'); localStorage.removeItem('rt_theme_data')")
    page.reload()
    data_theme(page, "nord")


@pytest.mark.plan("THEME-07")
def test_theme_set_via_api_is_applied_on_next_visit(page, login_ui, make_user):
    u = make_user(tag="thui3_")
    ok(u.client.put("/api/users/me/theme", json={"theme_id": theme_by_key(u.client, "one_dark")["id"]}))
    login_ui(u)
    page.goto("/dashboard.html")
    data_theme(page, "one_dark")


@pytest.mark.plan("THEME-07")
def test_default_theme_is_dark_pastel(page, anon_ui):
    anon_ui()
    page.goto("/")
    data_theme(page, "rapid_task_dark_pastel")
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#a78bfa"


@pytest.mark.plan("THEME-07")
def test_import_theme_from_file_selects_it(page, login_ui, make_user):
    u = make_user(tag="thui4_")
    login_ui(u)
    dlg, select = open_profile(page)
    body = valid_body(u.client, name="Pink import")
    body["colors"]["accent"] = "#ff00aa"
    dlg.locator("[data-testid=theme-file]").set_input_files(files=[as_file(body)])
    expect(dlg.locator(".form-ok")).to_contain_text("imported")
    expect(select.locator("option", has_text="Pink import")).to_have_count(1)
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#ff00aa"
    page.reload()                                                    # custom theme survives a reload
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#ff00aa"


@pytest.mark.plan("THEME-07", "THEME-03")
def test_import_with_css_injection_is_rejected_with_a_clear_error(page, login_ui, make_user):
    u = make_user(tag="thui5_")
    login_ui(u)
    dlg, select = open_profile(page)
    body = valid_body(u.client)
    body["colors"]["accent"] = "red; } body{display:none"
    dlg.locator("[data-testid=theme-file]").set_input_files(files=[as_file(body)])
    expect(dlg.locator(".form-error")).to_contain_text("colors.accent")
    expect(page.locator("body")).to_be_visible()


@pytest.mark.plan("THEME-07")
def test_import_of_non_json_file_is_rejected_client_side(page, login_ui, make_user):
    u = make_user(tag="thui6_")
    login_ui(u)
    dlg, select = open_profile(page)
    dlg.locator("[data-testid=theme-file]").set_input_files(files=[as_file("this is not json")])
    expect(dlg.locator(".form-error")).to_contain_text("not valid JSON")


@pytest.mark.plan("THEME-07")
def test_import_of_oversized_file_is_rejected_client_side(page, login_ui, make_user):
    u = make_user(tag="thui7_")
    login_ui(u)
    dlg, select = open_profile(page)
    dlg.locator("[data-testid=theme-file]").set_input_files(files=[as_file("x" * 25000)])
    expect(dlg.locator(".form-error")).to_contain_text("too large")


@pytest.mark.plan("THEME-07")
def test_export_downloads_a_valid_theme_file(page, login_ui, make_user):
    u = make_user(tag="thui8_")
    login_ui(u)
    dlg, select = open_profile(page)
    select.select_option(label="Nord")
    with page.expect_download() as info:
        dlg.locator("[data-testid=theme-export]").click()
    download = info.value
    assert download.suggested_filename.endswith(".json")
    data = json.loads(open(download.path(), encoding="utf-8").read())
    assert set(data) == {"name", "colors", "shadows", "typography"} and data["name"] == "Nord"


@pytest.mark.plan("THEME-07")
def test_delete_button_only_for_custom_themes_and_falls_back_to_default(page, login_ui, make_user):
    u = make_user(tag="thui9_")
    ok(u.client.post("/api/themes/import", json=valid_body(u.client, name="Disposable")), 201)
    login_ui(u)
    dlg, select = open_profile(page)
    select.select_option(label="Nord")
    expect(dlg.locator("[data-testid=theme-delete]")).to_have_count(0)      # presets are not deletable
    select.select_option(label="Disposable")
    page.once("dialog", lambda d: d.accept())
    dlg.locator("[data-testid=theme-delete]").click()
    expect(select.locator("option", has_text="Disposable")).to_have_count(0)
    data_theme(page, "rapid_task_dark_pastel")


# =================================================================== THEME-06
def set_project_theme(world, key, locked):
    c = world.client("admin")
    ok(c.put(f"/api/projects/{world.a.id}/theme-settings",
             json={"theme_id": theme_by_key(c, key)["id"], "is_locked": locked}))


def set_personal(user, key):
    ok(user.client.put("/api/users/me/theme", json={"theme_id": theme_by_key(user.client, key)["id"]}))


@pytest.mark.plan("THEME-06")
def test_project_theme_is_used_when_member_has_no_personal_theme(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=False)
    login_ui(u)
    Board(page).open(world.a.id)
    data_theme(page, "one_dark")


@pytest.mark.plan("THEME-06")
def test_personal_theme_wins_when_project_is_not_locked(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=False)
    set_personal(u, "nord")
    login_ui(u)
    Board(page).open(world.a.id)
    data_theme(page, "nord")


@pytest.mark.plan("THEME-06")
def test_locked_project_theme_wins_over_personal_theme(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=True)
    set_personal(u, "nord")
    login_ui(u)
    Board(page).open(world.a.id)
    data_theme(page, "one_dark")


@pytest.mark.plan("THEME-06")
def test_lock_does_not_leak_outside_the_project(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=True)
    set_personal(u, "nord")
    login_ui(u)
    Board(page).open(world.a.id)
    data_theme(page, "one_dark")
    page.goto("/dashboard.html")                                   # no project in the URL
    data_theme(page, "nord")


@pytest.mark.plan("THEME-06")
def test_project_theme_applies_on_roadmap_too(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "solarized_dark", locked=True)
    login_ui(u)
    page.goto(f"/roadmap.html?project={world.a.id}")
    data_theme(page, "solarized_dark")


@pytest.mark.plan("THEME-06", "THEME-07")
def test_profile_selector_is_disabled_while_project_is_locked(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=True)
    login_ui(u)
    Board(page).open(world.a.id)
    page.locator(".cabinet-btn").click()
    select = page.locator(".profile-modal [data-testid=theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)
    expect(select).to_be_disabled()
    expect(page.locator(".profile-modal")).to_contain_text("locked")


@pytest.mark.plan("THEME-06", "THEME-07")
def test_profile_selector_is_enabled_when_project_is_not_locked(page, login_ui, world, make_user):
    u = project_member(world, make_user)
    set_project_theme(world, "one_dark", locked=False)
    login_ui(u)
    Board(page).open(world.a.id)
    page.locator(".cabinet-btn").click()
    select = page.locator(".profile-modal [data-testid=theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)
    expect(select).to_be_enabled()
    select.select_option(label="Nord")
    data_theme(page, "nord")


# =================================================================== THEME-08
def open_theme_tab(page, world, user, login_ui):
    login_ui(user)
    page.goto("/dashboard.html")
    card = page.locator(".project-card", has_text=world.a.data["name"])
    card.get_by_role("button", name="Settings").click()
    modal = page.locator(".modal-backdrop.open .modal")
    modal.locator(".modal-tabs button", has_text="Theme").click()
    select = modal.locator("[data-testid=project-theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)
    return modal, select


@pytest.mark.plan("THEME-08")
def test_admin_sets_project_theme_and_lock_in_the_theme_tab(page, login_ui, world):
    modal, select = open_theme_tab(page, world, world.roles.admin, login_ui)
    select.select_option(label="One Dark")
    modal.locator("[data-testid=project-theme-lock]").check()
    modal.locator("[data-testid=project-theme-save]").click()
    expect(modal.locator(".form-ok")).to_contain_text("saved")
    s = ok(world.client("admin").get(f"/api/projects/{world.a.id}/theme-settings")).json()
    assert s["is_locked"] is True and s["theme"]["key"] == "one_dark"


@pytest.mark.plan("THEME-08")
def test_lock_checkbox_is_disabled_without_a_theme(page, login_ui, world):
    modal, select = open_theme_tab(page, world, world.roles.admin, login_ui)
    expect(modal.locator("[data-testid=project-theme-lock]")).to_be_disabled()
    select.select_option(label="Nord")
    expect(modal.locator("[data-testid=project-theme-lock]")).to_be_enabled()


@pytest.mark.plan("THEME-08")
def test_tab_shows_saved_settings_when_reopened(page, login_ui, world):
    set_project_theme(world, "nord", locked=True)
    modal, select = open_theme_tab(page, world, world.roles.admin, login_ui)
    expect(select.locator("option:checked")).to_have_text("Nord")
    expect(modal.locator("[data-testid=project-theme-lock]")).to_be_checked()


@pytest.mark.plan("THEME-08")
def test_non_admin_sees_theme_tab_read_only(page, login_ui, world):
    set_project_theme(world, "nord", locked=False)
    modal, select = open_theme_tab(page, world, world.roles.editor, login_ui)
    expect(select).to_be_disabled()
    expect(modal.locator("[data-testid=project-theme-lock]")).to_be_disabled()
    expect(modal.locator("[data-testid=project-theme-save]")).to_have_count(0)


@pytest.mark.plan("THEME-08", "THEME-06")
def test_theme_saved_in_the_tab_is_applied_on_the_board(page, login_ui, world):
    modal, select = open_theme_tab(page, world, world.roles.admin, login_ui)
    select.select_option(label="Nord")
    modal.locator("[data-testid=project-theme-save]").click()
    expect(modal.locator(".form-ok")).to_be_visible()
    Board(page).open(world.a.id)
    data_theme(page, "nord")
