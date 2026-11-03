"""Platform admin tool, Audit log tab (PLT-13): events, filters, pages, readable details."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import ok, uid
from framework.platform_api import P, audit, login_resp

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def rows(page):
    return page.locator("[data-testid='audit-row']")


def open_audit(page, plogin_ui, who):
    plogin_ui(who)
    page.goto("/platform.html#/audit")
    expect(tid(page, "audit-page")).to_be_visible()
    expect(tid(page, "audit-loading")).to_have_count(0)


def filter_target(page, username):
    tid(page, "audit-target").fill(username)
    expect(tid(page, "audit-summary")).to_be_visible()


def actions_of(page):
    return page.eval_on_selector_all("[data-testid='audit-row']", "els => els.map(e => e.dataset.action)")


# ---------------------------------------------------------------- the table
@pytest.mark.plan("PLT-13")
def test_the_log_shows_the_newest_event_first_with_all_columns(page, plogin_ui, proot, padmin):
    a = padmin("gl1")
    ok(proot.patch(f"{P}/admins/{a.id}", json={"display_name": "Newest Name"}))      # the last event of the test
    open_audit(page, plogin_ui, proot)
    expect(tid(page, "platform-view-title")).to_have_text("Audit log")
    first = rows(page).first
    expect(first).to_have_attribute("data-action", "admin_updated")
    expect(first.locator("[data-testid='audit-actor-cell']")).not_to_be_empty()
    expect(first.locator("[data-testid='audit-target-cell']")).to_have_text(a.username)
    expect(first.locator("[data-testid='audit-action-pill']")).to_have_text("Admin changed")
    assert re.search(r"\b\d\d:\d\d\b", first.locator("[data-testid='audit-time']").inner_text())      # 24 h
    expect(first.locator("[data-testid='audit-ip']")).not_to_have_text("—")
    ids_desc = [r["id"] for r in audit(proot)["items"]]
    assert ids_desc == sorted(ids_desc, reverse=True)


@pytest.mark.plan("PLT-13")
def test_events_have_readable_names_and_details(page, plogin_ui, proot, padmin):
    a = padmin("gl2", can_view_audit_logs=True, can_manage_users=True)
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_projects": True, "display_name": "Detail Name"}))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": "Fresh-Passw0rd-9"}))
    open_audit(page, plogin_ui, proot)
    filter_target(page, a.username)
    expect(rows(page)).to_have_count(4)
    by = {r.get_attribute("data-action"): r for r in rows(page).all()}
    assert set(by) == {"admin_created", "admin_updated", "admin_disabled", "admin_password_reset"}
    pills = {k: v.locator("[data-testid='audit-action-pill']").inner_text() for k, v in by.items()}
    assert pills == {"admin_created": "Admin created", "admin_updated": "Admin changed",
                     "admin_disabled": "Admin blocked", "admin_password_reset": "Password reset"}
    created = by["admin_created"].locator("[data-testid='audit-details']").inner_text()
    assert "Permissions: Manage users, Audit log" in created and "QA gl2" in created
    changed = by["admin_updated"].locator("[data-testid='audit-details']").inner_text()
    assert "Manage projects: on" in changed and 'Name: "QA gl2" → "Detail Name"' in changed
    assert by["admin_disabled"].locator("[data-testid='audit-details']").inner_text().strip() == ""
    assert "{" not in changed and "can_manage" not in changed               # no raw JSON, no field names


@pytest.mark.plan("PLT-13")
def test_login_events_show_the_reason(page, plogin_ui, proot, padmin, base_url):
    a = padmin("gl3")
    for _ in range(5):
        login_resp(base_url, a.username, "Wrong-Passw0rd-1")                  # the 5th one locks the name
    login_resp(base_url, a.username, a.password)                              # refused: locked
    open_audit(page, plogin_ui, proot)
    tid(page, "audit-actor").fill(a.username)
    expect(tid(page, "audit-summary")).to_contain_text("of 7 events")         # 1 ok (padmin) + 5 failed + 1 blocked
    pill = lambda action: page.locator(f"[data-testid='audit-row'][data-action='{action}'] [data-testid='audit-action-pill']").first
    expect(pill("login_ok")).to_have_text("Signed in")
    expect(pill("login_failed")).to_have_text("Failed sign-in")
    expect(pill("login_blocked")).to_have_text("Sign-in blocked")
    blocked = page.locator("[data-testid='audit-row'][data-action='login_blocked'] [data-testid='audit-details']").first
    expect(blocked).to_contain_text("Too many failed attempts")
    locked = page.locator("[data-testid='audit-row'][data-action='login_failed'] [data-testid='audit-details']").first
    expect(locked).to_contain_text("locked")                                  # the 5th failure is the newest failed one


# ---------------------------------------------------------------- filters
@pytest.mark.plan("PLT-13")
def test_filter_by_target_and_actor(page, plogin_ui, proot, padmin):
    a, b = padmin("gf1"), padmin("gf2")
    open_audit(page, plogin_ui, proot)
    filter_target(page, a.username)
    expect(tid(page, "audit-summary")).to_contain_text(f"of {audit(proot, target=a.username)['total']} events")
    cells = page.eval_on_selector_all("[data-testid='audit-target-cell']", "els => els.map(e => e.textContent.trim())")
    assert cells and set(cells) == {a.username}
    tid(page, "audit-target").fill("")
    tid(page, "audit-actor").fill(b.username)                                 # what b did: its own sign-in
    expect(page.locator("[data-testid='audit-actor-cell']").first).to_have_text(b.username)    # wait for the new list
    expect(rows(page)).to_have_count(audit(proot, actor=b.username)["total"])
    actors = page.eval_on_selector_all("[data-testid='audit-actor-cell']", "els => els.map(e => e.textContent.trim())")
    assert set(actors) == {b.username}


@pytest.mark.plan("PLT-13")
def test_filter_by_event(page, plogin_ui, proot, padmin):
    padmin("gf3")
    open_audit(page, plogin_ui, proot)
    options = tid(page, "audit-action").locator("option").all_inner_texts()
    assert options[0] == "All events" and "Admin created" in options and "Signed in" in options
    tid(page, "audit-action").select_option(label="Admin created")
    expect(tid(page, "audit-summary")).to_contain_text(f"of {audit(proot, action='admin_created')['total']} events")
    assert set(actions_of(page)) == {"admin_created"}
    expect(tid(page, "audit-clear")).to_be_enabled()


@pytest.mark.plan("PLT-13")
def test_filters_work_together_and_clear_resets_them(page, plogin_ui, proot, padmin):
    a = padmin("gf4")
    open_audit(page, plogin_ui, proot)
    expect(tid(page, "audit-clear")).to_be_disabled()
    tid(page, "audit-action").select_option(label="Admin created")
    filter_target(page, a.username)
    expect(rows(page)).to_have_count(1)
    expect(rows(page).first.locator("[data-testid='audit-target-cell']")).to_have_text(a.username)
    tid(page, "audit-actor").fill("nobody_" + uid(6))
    expect(tid(page, "audit-empty")).to_have_text("No events match these filters.")
    expect(tid(page, "audit-summary")).to_have_text("No events")
    tid(page, "audit-clear").click()
    expect(tid(page, "audit-actor")).to_have_value("")
    expect(tid(page, "audit-target")).to_have_value("")
    expect(tid(page, "audit-action")).to_have_value("")
    expect(rows(page).first).to_be_visible()
    expect(tid(page, "audit-clear")).to_be_disabled()


@pytest.mark.plan("PLT-13")
def test_special_characters_in_a_filter_are_plain_text(page, plogin_ui, proot, padmin):
    padmin("gf5")
    open_audit(page, plogin_ui, proot)
    tid(page, "audit-target").fill("%")
    expect(tid(page, "audit-empty")).to_be_visible()                          # % is not a wildcard
    tid(page, "audit-target").fill("_")
    expect(tid(page, "audit-empty")).to_be_visible()


@pytest.mark.plan("PLT-13")
def test_refresh_brings_new_events(page, plogin_ui, proot, padmin):
    open_audit(page, plogin_ui, proot)
    total = audit(proot)["total"]
    padmin("gr1")                                                             # two more events: created + signed in
    tid(page, "audit-refresh").click()
    expect(tid(page, "audit-summary")).to_contain_text(f"of {audit(proot)['total']} events")
    assert audit(proot)["total"] >= total + 2


# ---------------------------------------------------------------- pages
@pytest.mark.plan("PLT-13")
def test_pages_per_page_and_the_buttons(page, plogin_ui, proot, padmin):
    a = padmin("gp1")
    for n in range(28):                                                        # 1 created + 28 changes = 29 events
        ok(proot.patch(f"{P}/admins/{a.id}", json={"display_name": f"Name {n:02d}"}))
    open_audit(page, plogin_ui, proot)
    filter_target(page, a.username)
    expect(tid(page, "audit-summary")).to_have_text("1–29 of 29 events")
    expect(tid(page, "audit-page-info")).to_have_text("Page 1 of 1")
    expect(tid(page, "audit-prev")).to_be_disabled()
    expect(tid(page, "audit-next")).to_be_disabled()
    tid(page, "audit-page-size").select_option("25")
    expect(tid(page, "audit-page-info")).to_have_text("Page 1 of 2")
    expect(rows(page)).to_have_count(25)
    expect(tid(page, "audit-prev")).to_be_disabled()
    tid(page, "audit-next").click()
    expect(tid(page, "audit-summary")).to_have_text("26–29 of 29 events")
    expect(rows(page)).to_have_count(4)
    expect(tid(page, "audit-next")).to_be_disabled()
    expect(tid(page, "audit-prev")).to_be_enabled()
    ids = [r["id"] for r in audit(proot, target=a.username)["items"]]
    assert len(ids) == 29
    expect(rows(page).last).to_have_attribute("data-action", "admin_created")  # the oldest event is the last row
    tid(page, "audit-prev").click()
    expect(tid(page, "audit-page-info")).to_have_text("Page 1 of 2")
    expect(rows(page).first).to_have_attribute("data-action", "admin_updated")


@pytest.mark.plan("PLT-13")
def test_changing_a_filter_goes_back_to_page_one(page, plogin_ui, proot, padmin):
    a = padmin("gp2")
    for n in range(27):
        ok(proot.patch(f"{P}/admins/{a.id}", json={"display_name": f"Name {n:02d}"}))
    open_audit(page, plogin_ui, proot)
    filter_target(page, a.username)
    tid(page, "audit-page-size").select_option("25")
    tid(page, "audit-next").click()
    expect(tid(page, "audit-page-info")).to_have_text("Page 2 of 2")
    tid(page, "audit-action").select_option(label="Admin created")
    expect(tid(page, "audit-page-info")).to_have_text("Page 1 of 1")
    expect(rows(page)).to_have_count(1)


# ---------------------------------------------------------------- permissions and safety
@pytest.mark.plan("PLT-13")
def test_an_admin_with_the_audit_permission_can_read_the_log(page, plogin_ui, padmin):
    a = padmin("gv1", can_view_audit_logs=True)
    plogin_ui(a)
    page.goto("/platform.html")
    expect(tid(page, "platform-sidebar")).to_be_visible()
    assert [n for n in page.eval_on_selector_all("[data-testid^='nav-']", "els => els.map(e => e.dataset.testid)")] == ["nav-audit"]
    tid(page, "nav-audit").click()
    expect(tid(page, "audit-table")).to_be_visible()
    expect(rows(page).first).to_be_visible()


@pytest.mark.plan("PLT-13")
def test_an_admin_without_the_permission_does_not_get_the_log(page, plogin_ui, padmin, base_url):
    a = padmin("gv2", can_manage_users=True)
    plogin_ui(a)
    page.goto("/platform.html#/audit")
    expect(tid(page, "platform-view-title")).to_have_text("My account")
    assert tid(page, "nav-audit").count() == 0 and tid(page, "audit-page").count() == 0
    assert a.client.get(f"{P}/audit").status_code == 403


@pytest.mark.plan("PLT-13")
def test_passwords_never_show_in_the_log_page(page, plogin_ui, proot, padmin, base_url):
    first, second, wrong = "Visible-First-Pass-1", "Visible-Second-Pass-2", "Visible-Wrong-Pass-3"
    a = padmin("gs1", password=first)
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": second}))
    login_resp(base_url, a.username, wrong)
    open_audit(page, plogin_ui, proot)
    tid(page, "audit-action").select_option("login_failed")
    tid(page, "audit-actor").fill(a.username)
    expect(rows(page).first).to_be_visible()
    tid(page, "audit-actor").fill("")
    tid(page, "audit-target").fill(a.username)
    expect(rows(page).first).to_be_visible()
    html = page.content()
    for secret in (first, second, wrong):
        assert secret not in html


@pytest.mark.plan("PLT-13")
def test_a_name_with_html_in_the_log_is_shown_as_text(page, plogin_ui, proot, base_url):
    evil = "<img src=x onerror=window.__x=1>"
    login_resp(base_url, evil, "Wrong-Passw0rd-1")                              # the typed name is written to the log
    open_audit(page, plogin_ui, proot)
    tid(page, "audit-actor").fill("onerror")
    expect(rows(page).first).to_be_visible()
    expect(rows(page).first.locator("[data-testid='audit-actor-cell']")).to_have_text(evil)
    assert page.locator("img[src='x']").count() == 0
    assert page.evaluate("window.__x") is None
    assert page.js_errors == []


@pytest.mark.plan("PLT-13")
def test_the_log_survives_a_server_error_with_a_retry_button(page, plogin_ui, proot):
    plogin_ui(proot)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body='{"detail": "Something broke on the server"}')
        else:
            route.continue_()

    page.route("**/api/platform/audit?*", handler)
    page.goto("/platform.html#/audit")
    expect(tid(page, "audit-error")).to_have_text("Something broke on the server")
    state["fail"] = False
    tid(page, "audit-retry").click()
    expect(tid(page, "audit-table")).to_be_visible()
