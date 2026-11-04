"""Platform admin tool, Users tab in the browser (PLT-19 .. PLT-21)."""
import json

import pytest
from playwright.sync_api import expect

from framework.client import Client
from framework.factory import create_project, deactivate, ok, uid
from framework.platform_api import P, audit, users

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def rows(page):
    return page.locator("[data-testid='user-row']")


def row_of(page, user):
    return page.locator(f"[data-testid='user-row'][data-id='{user.id}']")


def person(make_user, tag="pu", **kw):
    """An app user with a unique name (the Users tab can find it by that name)."""
    return make_user(tag=f"{tag}_", full_name=f"QA {uid(8)} {tag}", **kw)


def open_users(page, plogin_ui, who):
    plogin_ui(who)
    page.goto("/platform.html#/users")
    expect(tid(page, "users-page")).to_be_visible()
    expect(tid(page, "users-loading")).to_have_count(0)


def find(page, user):
    """Search the user by the unique part of the name; wait until exactly this row is shown."""
    tid(page, "users-search").fill(user.full_name)
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, user)).to_be_visible()
    return row_of(page, user)


def block_api(root, user):
    ok(root.post(f"{P}/users/{user.id}/block"))


def app_login_status(base_url, user):
    return Client(base_url).login_form(user.email, user.password).status_code


# ---------------------------------------------------------------- PLT-19 the list
@pytest.mark.plan("PLT-19")
def test_a_row_shows_the_person_the_status_and_the_counters(page, plogin_ui, proot, make_user):
    owner, u = person(make_user, "own"), person(make_user, "row")
    p1, p2 = create_project(owner), create_project(owner)
    p1.add_member(u, "editor")
    p2.add_member(u, "editor")
    p1.ticket(client=u.client, assignee_id=u.id)
    p2.ticket(assignee_id=u.id)
    open_users(page, plogin_ui, proot)
    expect(tid(page, "platform-view-title")).to_have_text("Users")
    r = find(page, u)
    expect(r.locator("[data-testid='user-name']")).to_have_text(u.full_name)
    expect(r.locator("[data-testid='user-email']")).to_have_text(u.email)
    expect(r.locator("[data-testid='user-status']")).to_have_text("Active")
    expect(r).to_have_attribute("data-status", "active")
    expect(r.locator("[data-testid='user-projects']")).to_have_text("2")
    expect(r.locator("[data-testid='user-open']")).to_have_text("2")
    expect(r.locator("[data-testid='user-reported']")).to_have_text("1")
    assert r.locator("[data-testid='user-created']").inner_text() not in ("", "—")
    assert ":" in r.locator("[data-testid='user-last-login']").inner_text()                  # date and 24 h time
    expect(r.locator("[data-testid='user-block']")).to_be_visible()
    expect(r.locator("[data-testid='user-delete']")).to_be_visible()
    expect(r.locator("[data-testid='user-unblock']")).to_have_count(0)
    text = page.locator("body").inner_text()
    assert "password" not in text.lower() and "hash" not in text.lower()


@pytest.mark.plan("PLT-19")
def test_search_by_name_and_by_email_and_clear(page, plogin_ui, proot, make_user):
    u, other = person(make_user, "se1"), person(make_user, "se2")
    open_users(page, plogin_ui, proot)
    tid(page, "users-search").fill(u.full_name.upper())                       # case does not matter
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, u)).to_be_visible()
    tid(page, "users-search").fill(other.email)
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, other)).to_be_visible()
    tid(page, "users-search").fill("no_such_person_" + uid(10))
    expect(tid(page, "users-empty")).to_have_text("No users match these filters.")
    expect(tid(page, "users-table")).to_have_count(0)
    tid(page, "users-clear").click()
    expect(tid(page, "users-search")).to_have_value("")
    expect(tid(page, "users-empty")).to_have_count(0)
    assert rows(page).count() >= 2
    expect(tid(page, "users-clear")).to_be_disabled()


@pytest.mark.plan("PLT-19")
def test_the_tab_counters_are_the_server_counters(page, plogin_ui, proot, make_user):
    blocked, closed, gone = person(make_user, "tc1"), person(make_user, "tc2"), person(make_user, "tc3")
    block_api(proot, blocked)
    deactivate(closed)
    ok(proot.delete(f"{P}/users/{gone.id}"))
    open_users(page, plogin_ui, proot)
    counts = users(proot, page_size=1)["counts"]
    for key in ("all", "active", "blocked", "deactivated", "deleted"):
        expect(tid(page, f"users-count-{key}")).to_have_text(str(counts[key]))
    assert counts["blocked"] >= 1 and counts["deactivated"] >= 1 and counts["deleted"] >= 1
    assert counts["all"] == counts["active"] + counts["blocked"] + counts["deactivated"] + counts["deleted"]


@pytest.mark.plan("PLT-19")
@pytest.mark.parametrize("status", ["active", "blocked", "deactivated", "deleted"])
def test_a_status_tab_shows_only_that_status(page, plogin_ui, proot, make_user, status):
    u = person(make_user, "tb")
    if status == "blocked":
        block_api(proot, u)
    elif status == "deactivated":
        deactivate(u)
    elif status == "deleted":
        ok(proot.delete(f"{P}/users/{u.id}"))
    open_users(page, plogin_ui, proot)
    tid(page, f"users-tab-{status}").click()
    expect(tid(page, f"users-tab-{status}")).to_have_attribute("aria-selected", "true")
    expect(tid(page, "users-clear")).to_be_enabled()
    tid(page, "users-search").fill(u.full_name)
    expect(row_of(page, u)).to_be_visible()
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, u).locator("[data-testid='user-status']")).to_have_text(status.capitalize())
    tid(page, "users-clear").click()
    expect(tid(page, "users-tab-all")).to_have_attribute("aria-selected", "true")


@pytest.mark.plan("PLT-19")
def test_sorting_follows_the_server_order(page, plogin_ui, proot, make_user):
    person(make_user, "so1")
    person(make_user, "so2")
    open_users(page, plogin_ui, proot)
    first = tid(page, "user-name").first.inner_text()
    assert first == users(proot, sort="created", page_size=1)["items"][0]["full_name"]          # newest first
    tid(page, "users-sort").select_option("name")
    expected = [r["full_name"] for r in users(proot, sort="name", page_size=25)["items"]]
    expect(tid(page, "user-name").first).to_have_text(expected[0])
    assert tid(page, "user-name").all_inner_texts() == expected
    tid(page, "users-sort").select_option("last_login")                     # equal times may tie, so only the request is checked
    expect(tid(page, "users-sort")).to_have_value("last_login")
    expect(rows(page)).to_have_count(min(25, users(proot, page_size=1)["total"]))
    expect(tid(page, "users-error")).to_have_count(0)


@pytest.mark.plan("PLT-19")
def test_pages_and_page_size(page, plogin_ui, proot, make_user):
    while users(proot, page_size=1)["total"] < 26:                      # make sure there are two pages
        person(make_user, "pg")
    total = users(proot, page_size=1)["total"]
    open_users(page, plogin_ui, proot)
    expect(rows(page)).to_have_count(25)
    expect(tid(page, "users-summary")).to_have_text(f"1–25 of {total} users")
    expect(tid(page, "users-prev")).to_be_disabled()
    ids_1 = page.eval_on_selector_all("[data-testid='user-row']", "els => els.map(e => e.dataset.id)")
    tid(page, "users-next").click()
    expect(tid(page, "users-page-info")).to_contain_text("Page 2 of")
    expect(tid(page, "users-prev")).to_be_enabled()
    ids_2 = page.eval_on_selector_all("[data-testid='user-row']", "els => els.map(e => e.dataset.id)")
    assert ids_2 and not set(ids_1) & set(ids_2)
    tid(page, "users-page-size").select_option("50")
    expect(tid(page, "users-page-info")).to_contain_text("Page 1 of")           # a new size goes back to page 1
    expect(rows(page)).to_have_count(min(50, total))
    expect(tid(page, "users-prev")).to_be_disabled()


@pytest.mark.plan("PLT-19")
def test_a_failed_load_shows_the_error_and_try_again_works(page, plogin_ui, proot):
    plogin_ui(proot)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route("**/api/platform/users?*", handler)
    page.goto("/platform.html#/users")
    expect(tid(page, "users-error")).to_contain_text("Something broke")
    expect(tid(page, "users-table")).to_have_count(0)
    state["fail"] = False
    tid(page, "users-retry").click()
    expect(tid(page, "users-table")).to_be_visible()
    expect(tid(page, "users-error")).to_have_count(0)


# ---------------------------------------------------------------- PLT-20 block, unblock, delete
@pytest.mark.plan("PLT-20")
def test_block_and_unblock_change_the_row_the_counters_and_the_login(page, plogin_ui, proot, make_user, base_url):
    u = person(make_user, "bl")
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    mine = {"q": u.full_name}                                                 # the counters follow the search text
    before = users(proot, page_size=1, **mine)["counts"]
    r.locator("[data-testid='user-block']").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Blocked")
    expect(r).to_have_attribute("data-status", "blocked")
    expect(tid(page, "platform-toast")).to_contain_text("is blocked")
    expect(r.locator("[data-testid='user-unblock']")).to_be_visible()
    expect(r.locator("[data-testid='user-block']")).to_have_count(0)
    expect(tid(page, "users-count-blocked")).to_have_text(str(before["blocked"] + 1))
    expect(tid(page, "users-count-active")).to_have_text(str(before["active"] - 1))
    assert (before["blocked"], before["active"]) == (0, 1)
    assert app_login_status(base_url, u) == 403
    r.locator("[data-testid='user-unblock']").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Active")
    expect(tid(page, "users-count-blocked")).to_have_text(str(before["blocked"]))
    assert app_login_status(base_url, u) == 200
    assert page.js_errors == []


@pytest.mark.plan("PLT-20")
def test_a_stale_row_is_refused_and_the_list_is_refreshed(page, plogin_ui, proot, make_user):
    u = person(make_user, "st")
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    block_api(proot, u)                                                      # somebody else blocks it first
    r.locator("[data-testid='user-block']").click()
    expect(tid(page, "platform-toast")).to_contain_text("This user is already blocked")
    expect(r.locator("[data-testid='user-status']")).to_have_text("Blocked")      # the row was refreshed


@pytest.mark.plan("PLT-20")
def test_a_self_closed_account_can_only_be_deleted(page, plogin_ui, proot, make_user):
    u = person(make_user, "dc")
    deactivate(u)
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    expect(r.locator("[data-testid='user-status']")).to_have_text("Deactivated")
    expect(r.locator("[data-testid='user-block']")).to_have_count(0)
    expect(r.locator("[data-testid='user-unblock']")).to_have_count(0)
    expect(r.locator("[data-testid='user-delete']")).to_be_visible()


@pytest.mark.plan("PLT-20")
@pytest.mark.parametrize("how", ["cancel", "escape", "close-x", "click-outside"])
def test_closing_the_delete_question_deletes_nothing(page, plogin_ui, proot, make_user, how):
    u = person(make_user, "cx")
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    r.locator("[data-testid='user-delete']").click()
    expect(tid(page, "user-modal")).to_be_visible()
    expect(tid(page, "user-target")).to_have_text(u.full_name)
    expect(tid(page, "user-delete-cancel")).to_be_focused()                  # the safe button has the focus
    if how == "cancel":
        tid(page, "user-delete-cancel").click()
    elif how == "escape":
        page.keyboard.press("Escape")
    elif how == "close-x":
        tid(page, "user-modal-close").click()
    else:
        tid(page, "user-modal-backdrop").click(position={"x": 5, "y": 5})
    expect(tid(page, "user-modal")).to_have_count(0)
    expect(r.locator("[data-testid='user-status']")).to_have_text("Active")
    assert ok(proot.get(f"{P}/users", params={"q": u.full_name})).json()["items"][0]["status"] == "active"
    assert not [e for e in audit(proot)["items"] if e["action"] == "user_deleted" and e["target_name"] == u.email]


@pytest.mark.plan("PLT-20")
def test_confirmed_delete_frees_the_address_and_keeps_the_name(page, plogin_ui, proot, make_user, base_url):
    u = person(make_user, "dl")
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    r.locator("[data-testid='user-delete']").click()
    tid(page, "user-delete-confirm").click()
    expect(tid(page, "user-modal")).to_have_count(0)
    expect(r.locator("[data-testid='user-status']")).to_have_text("Deleted")
    expect(r.locator("[data-testid='user-name']")).to_have_text(u.full_name)
    expect(r.locator("[data-testid='user-email']")).to_contain_text(f"deleted_{u.id}_")
    expect(r.locator("[data-testid='user-no-actions']")).to_be_visible()
    expect(r.locator("button")).to_have_count(0)
    expect(tid(page, "platform-toast")).to_contain_text("is deleted")
    assert app_login_status(base_url, u) in (400, 401, 403)
    again = Client(base_url).post("/api/auth/register", json={"email": u.email, "password": u.password, "full_name": "Again"}, auth=False)
    assert again.status_code == 201                                           # the real address is free


@pytest.mark.plan("PLT-20")
def test_a_failed_delete_stays_in_the_question_and_can_be_repeated(page, plogin_ui, proot, make_user):
    u = person(make_user, "df")
    open_users(page, plogin_ui, proot)
    r = find(page, u)
    state = {"fail": True}

    def handler(route):
        if state["fail"] and route.request.method == "DELETE":
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route(f"**/api/platform/users/{u.id}", handler)
    r.locator("[data-testid='user-delete']").click()
    tid(page, "user-delete-confirm").click()
    expect(tid(page, "user-modal-error")).to_contain_text("Something broke")
    expect(tid(page, "user-modal")).to_be_visible()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Active")
    state["fail"] = False
    tid(page, "user-delete-confirm").click()
    expect(tid(page, "user-modal")).to_have_count(0)
    expect(r.locator("[data-testid='user-status']")).to_have_text("Deleted")


@pytest.mark.plan("PLT-20")
def test_a_blocked_user_can_be_deleted_from_the_blocked_tab(page, plogin_ui, proot, make_user):
    u = person(make_user, "bd")
    block_api(proot, u)
    open_users(page, plogin_ui, proot)
    tid(page, "users-tab-blocked").click()
    r = find(page, u)
    r.locator("[data-testid='user-delete']").click()
    tid(page, "user-delete-confirm").click()
    expect(tid(page, "user-modal")).to_have_count(0)
    expect(rows(page)).to_have_count(0)                                       # it left the Blocked tab
    expect(tid(page, "users-empty")).to_be_visible()


# ---------------------------------------------------------------- PLT-21 permissions, audit, safe text
@pytest.mark.plan("PLT-21")
def test_an_admin_with_manage_users_works_in_the_tab(page, plogin_ui, padmin, make_user):
    a = padmin("uu1", can_manage_users=True)
    u = person(make_user, "pm")
    plogin_ui(a)
    page.goto("/platform.html")
    expect(tid(page, "platform-sidebar")).to_be_visible()
    assert page.locator("a[data-testid^='nav-']").count() == 1
    tid(page, "nav-users").click()
    expect(tid(page, "users-page")).to_be_visible()
    r = find(page, u)
    r.locator("[data-testid='user-block']").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Blocked")


@pytest.mark.plan("PLT-21")
def test_without_the_permission_the_route_falls_back_to_my_account(page, plogin_ui, padmin):
    a = padmin("uu2", can_view_audit_logs=True)
    plogin_ui(a)
    page.goto("/platform.html#/users")
    expect(tid(page, "platform-account")).to_be_visible()
    expect(tid(page, "nav-users")).to_have_count(0)
    expect(tid(page, "users-page")).to_have_count(0)


@pytest.mark.plan("PLT-21")
def test_the_actions_show_up_in_the_audit_log_tab(page, plogin_ui, proot, padmin, make_user):
    a = padmin("uu3", can_manage_users=True, can_view_audit_logs=True)
    u = person(make_user, "au")
    plogin_ui(a)
    page.goto("/platform.html#/users")
    r = find(page, u)
    r.locator("[data-testid='user-block']").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Blocked")
    r.locator("[data-testid='user-unblock']").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Active")
    r.locator("[data-testid='user-delete']").click()
    tid(page, "user-delete-confirm").click()
    expect(r.locator("[data-testid='user-status']")).to_have_text("Deleted")
    tid(page, "nav-audit").click()
    expect(tid(page, "audit-page")).to_be_visible()
    tid(page, "audit-target").fill(u.email)
    audit_rows = page.locator("[data-testid='audit-row']")
    expect(audit_rows).to_have_count(3)
    by = {x.get_attribute("data-action"): x for x in audit_rows.all()}
    assert set(by) == {"user_blocked", "user_unblocked", "user_deleted"}
    assert by["user_blocked"].locator("[data-testid='audit-action-pill']").inner_text() == "User blocked"
    assert by["user_unblocked"].locator("[data-testid='audit-action-pill']").inner_text() == "User unblocked"
    assert by["user_deleted"].locator("[data-testid='audit-action-pill']").inner_text() == "User deleted"
    for x in by.values():
        assert x.locator("[data-testid='audit-actor-cell']").inner_text() == a.username
        assert f'User: "{u.full_name}"' in x.locator("[data-testid='audit-details']").inner_text()


@pytest.mark.plan("PLT-21")
def test_a_name_with_html_is_shown_as_text(page, plogin_ui, proot, make_user):
    evil = f"<img src=x onerror=window.__x=1> {uid(6)}"
    u = make_user(tag="xss_", full_name=evil)
    open_users(page, plogin_ui, proot)
    tid(page, "users-search").fill(evil.split(" ")[-1])
    r = row_of(page, u)
    expect(r).to_be_visible()
    expect(r.locator("[data-testid='user-name']")).to_have_text(evil)
    assert page.locator("img[src='x']").count() == 0
    assert page.evaluate("window.__x") is None
    r.locator("[data-testid='user-delete']").click()
    expect(tid(page, "user-target")).to_have_text(evil)                       # the question shows it as text too
    assert page.locator("[data-testid='user-modal'] img").count() == 0
    assert page.evaluate("window.__x") is None
