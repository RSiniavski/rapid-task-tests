"""PROJ-FE: dashboard, create project, settings (columns/members), delete project."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import create_project, ok
from pages.base import Dashboard

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


@pytest.mark.plan("PROJ-FE", "UI-04")
def test_empty_dashboard_state_and_zero_stats(page, login_ui, make_user):
    u = make_user(tag="uiempty_")
    login_ui(u)
    Dashboard(page).open()
    expect(page.get_by_text("No projects yet")).to_be_visible()
    expect(page.locator(".stat-value").first).to_have_text("0")
    assert not page.js_errors


@pytest.mark.plan("PROJ-FE", "E2E-01")
def test_create_project_via_dialog_persists_and_lists(page, login_ui, make_user):
    u = make_user(tag="uicreate_")
    login_ui(u)
    d = Dashboard(page).open()
    d.create_project("UI Created", "UIC")
    expect(d.card("UI Created")).to_be_visible()
    expect(d.card("UI Created").locator(".badge-accent")).to_have_text("UIC")
    page.reload()
    expect(d.card("UI Created")).to_be_visible()
    names = [p["name"] for p in ok(u.client.get("/api/projects")).json()]
    assert "UI Created" in names
    cols = ok(u.client.get(f"/api/projects/{next(p['id'] for p in ok(u.client.get('/api/projects')).json() if p['name']=='UI Created')}/columns")).json()
    assert len(cols) == 8


@pytest.mark.plan("PROJ-FE")
def test_create_project_duplicate_key_and_invalid_key_errors(page, login_ui, make_user):
    u = make_user(tag="uikey_")
    existing = create_project(u)
    login_ui(u)
    d = Dashboard(page).open()
    d.create_project("Another", existing.key)
    expect(page.locator(".modal-backdrop.open .form-error")).to_be_visible()
    assert len(ok(u.client.get("/api/projects")).json()) == 1
    page.reload()
    d.create_project("Bad key", "1bad")                              # violates the input pattern
    assert len(ok(u.client.get("/api/projects")).json()) == 1


@pytest.mark.plan("PROJ-FE")
def test_dashboard_cards_show_role_stats_and_links(page, login_ui, world):
    t = world.a.ticket()
    world.a.move(t["id"], "Done")
    world.a.ticket()
    login_ui(world.roles.reporter)
    d = Dashboard(page).open()
    card = d.card(world.a.data["name"])
    expect(card).to_contain_text("Reporter")
    expect(card).to_contain_text("2")
    assert card.get_by_role("link", name="Roadmap").get_attribute("href") == f"/roadmap.html?project={world.a.id}"
    card.get_by_role("button", name="Open board").click()
    page.wait_for_url(re.compile(rf"/board\.html\?project={world.a.id}$"))


@pytest.mark.plan("PROJ-FE")
def test_settings_dialog_columns_admin_can_add_rename_toggle_delete(page, login_ui, world):
    login_ui(world.roles.admin)
    d = Dashboard(page).open()
    d.card(world.a.data["name"]).get_by_role("button", name="Settings").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.get_by_placeholder("Column name").fill("QA Lane")
    dlg.get_by_role("button", name="Add").click()
    row = dlg.locator(".settings-row").last                      # new column is appended at the end
    expect(row.locator("input.input")).to_have_value("QA Lane")
    cols = {c["name"]: c for c in ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()}
    assert "QA Lane" in cols
    row.locator("input[type=checkbox]").check()
    page.wait_for_timeout(500)
    cols = {c["name"]: c for c in ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()}
    assert cols["QA Lane"]["is_done"] is True
    row.locator("button.danger").click()
    page.wait_for_timeout(500)
    assert "QA Lane" not in {c["name"] for c in ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()}


@pytest.mark.plan("PROJ-FE")
def test_settings_delete_column_with_tickets_requires_target(page, login_ui, world):
    world.a.ticket()                                                    # ticket sits in the first column
    login_ui(world.roles.admin)
    d = Dashboard(page).open()
    d.card(world.a.data["name"]).get_by_role("button", name="Settings").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator(".settings-row").first.locator("button.danger").click()
    expect(dlg.get_by_text("Move tickets to")).to_be_visible()
    dlg.locator(".settings-row").first.get_by_role("button", name="Delete").click()
    page.wait_for_timeout(600)
    assert len(ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()) == 7
    t = ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()
    assert len(t) == 1 and t[0]["column_id"] in {c["id"] for c in ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()}


@pytest.mark.plan("PROJ-FE", "E2E-02")
def test_members_tab_add_change_role_and_remove(page, login_ui, world, make_user):
    newbie = make_user(tag="uimember_")
    login_ui(world.roles.admin)
    d = Dashboard(page).open()
    d.card(world.a.data["name"]).get_by_role("button", name="Settings").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.get_by_role("button", name="Members").click()
    dlg.get_by_placeholder("User email").fill(newbie.email)
    dlg.get_by_role("button", name="Add").click()
    expect(dlg.get_by_text(newbie.email)).to_be_visible()
    row = dlg.locator(".settings-row", has_text=newbie.email)
    row.locator("select").select_option("editor")
    page.wait_for_timeout(500)
    members = ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()
    assert next(m for m in members if m["user"]["email"] == newbie.email)["role"] == "editor"
    row.locator("button.danger").click()
    page.wait_for_timeout(500)
    assert newbie.email not in [m["user"]["email"] for m in ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()]


@pytest.mark.plan("PROJ-FE")
def test_members_tab_unknown_email_shows_error(page, login_ui, world):
    login_ui(world.roles.admin)
    d = Dashboard(page).open()
    d.card(world.a.data["name"]).get_by_role("button", name="Settings").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.get_by_role("button", name="Members").click()
    dlg.get_by_placeholder("User email").fill("ghost@example.com")
    dlg.get_by_role("button", name="Add").click()
    expect(dlg.locator(".form-error")).to_be_visible()


@pytest.mark.plan("PROJ-FE", "E2E-08")
def test_non_admin_settings_are_read_only_and_owner_cannot_be_removed(page, login_ui, world):
    login_ui(world.roles.editor)
    d = Dashboard(page).open()
    d.card(world.a.data["name"]).get_by_role("button", name="Settings").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    assert dlg.get_by_placeholder("Column name").count() == 0
    assert dlg.locator("button.danger").count() == 0
    assert all(i.is_disabled() for i in dlg.locator(".settings-row input.input").all())
    dlg.get_by_role("button", name="Members").click()
    assert dlg.locator("button.danger").count() == 0


@pytest.mark.plan("PROJ-FE", "E2E-11")
def test_owner_deletes_project_with_confirmation(page, login_ui, make_user):
    u = make_user(tag="uidel_")
    p = create_project(u)
    p.ticket()
    login_ui(u)
    d = Dashboard(page).open()
    page.dialog_policy = "dismiss"
    d.card(p.data["name"]).get_by_role("button", name="Settings").click()
    page.locator(".modal-backdrop.open .btn-danger").click()
    assert page.dialogs and "cannot be undone" in page.dialogs[-1]
    assert ok(u.client.get(f"/api/projects/{p.id}")).status_code == 200      # dismissed -> still there
    page.dialog_policy = "accept"
    page.locator(".modal-backdrop.open .btn-danger").click()
    expect(page.get_by_text("No projects yet")).to_be_visible()
    assert u.client.get(f"/api/projects/{p.id}").status_code == 404
    assert u.client.get(f"/api/tickets/project/{p.id}").status_code == 404


@pytest.mark.plan("PROJ-FE", "UI-07")
@pytest.mark.security
def test_project_name_is_rendered_escaped(page, login_ui, make_user):
    u = make_user(tag="uixss_")
    payload = "<img src=x onerror=window.__xss=1>"
    ok(u.client.post("/api/projects", json={"name": payload, "key": "XSS"}), 201)
    login_ui(u)
    Dashboard(page).open()
    expect(page.get_by_text(payload)).to_be_visible()
    assert page.evaluate("window.__xss") is None and not page.dialogs
