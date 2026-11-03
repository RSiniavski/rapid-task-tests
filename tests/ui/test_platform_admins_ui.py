"""Platform admin tool, Administrators tab (PLT-12): list, create, edit, block, password, delete."""
import re

import pytest
from playwright.sync_api import expect

from framework import config
from framework.factory import ok, uid
from framework.platform_api import ADMIN_PASSWORD, P, PERMS, login_resp

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

ROOT = config.PLATFORM_ROOT_USERNAME


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def row(page, username):
    return page.locator(f"[data-testid='admin-row'][data-username='{username}']")


def open_admins(page, plogin_ui, proot):
    plogin_ui(proot)
    page.goto("/platform.html#/admins")
    expect(tid(page, "admins-table")).to_be_visible()


def api_row(proot, admin_id):
    return next(r for r in ok(proot.get(f"{P}/admins")).json() if r["id"] == admin_id)


def toast(page):
    return tid(page, "platform-toast")


def fill_create(page, username, name="Ui Created", password="Ui-Created-Pass-1", perms=()):
    tid(page, "admin-new").click()
    expect(tid(page, "admin-modal")).to_be_visible()
    tid(page, "admin-username").fill(username)
    tid(page, "admin-display-name").fill(name)
    tid(page, "admin-password-input").fill(password)
    for flag in perms:
        tid(page, f"admin-perm-{flag}").check()


@pytest.fixture
def cleanup(proot):
    """cleanup(username) -> the admin made through the page is deleted after the test."""
    names = []
    yield names.append
    for admin in ok(proot.get(f"{P}/admins")).json():
        if admin["username"] in names:
            proot.delete(f"{P}/admins/{admin['id']}")


# ---------------------------------------------------------------- the list
@pytest.mark.plan("PLT-12")
def test_the_list_shows_root_first_and_every_admin_with_status_and_permissions(page, plogin_ui, proot, padmin):
    a = padmin("al1", can_manage_users=True, can_view_audit_logs=True)
    b = padmin("al2")
    open_admins(page, plogin_ui, proot)
    first = page.locator("[data-testid='admin-row']").first
    expect(first).to_have_attribute("data-username", ROOT)
    expect(first.locator("[data-testid='admin-root-tag']")).to_have_text("ROOT")
    expect(first.locator("[data-testid='admin-perms']")).to_have_text("All")
    assert first.locator("button").count() == 0                              # root has no actions
    expect(row(page, a.username).locator("[data-testid='admin-status']")).to_have_text("Active")
    chips = row(page, a.username).locator("[data-testid='admin-perms'] .pl-chip").all_inner_texts()
    assert chips == ["Users", "Audit"]
    expect(row(page, b.username).locator("[data-testid='admin-perms']")).to_contain_text("No permissions")
    for name in ("admin-edit", "admin-password", "admin-toggle", "admin-delete"):
        expect(row(page, a.username).locator(f"[data-testid='{name}']")).to_have_count(1)
    total = len(ok(proot.get(f"{P}/admins")).json())
    expect(tid(page, "admins-count")).to_contain_text(f"{total} accounts")


@pytest.mark.plan("PLT-12")
def test_last_login_is_shown_as_a_24_hour_time(page, plogin_ui, proot, padmin):
    a = padmin("al3")                                                         # padmin logs in once: last_login is set
    open_admins(page, plogin_ui, proot)
    assert re.search(r"\b\d\d:\d\d\b", row(page, a.username).inner_text()), row(page, a.username).inner_text()


# ---------------------------------------------------------------- create
@pytest.mark.plan("PLT-12")
def test_create_an_admin_in_the_dialog(page, plogin_ui, proot, base_url, cleanup):
    username = f"qa_ui_{uid(6)}".lower()
    cleanup(username)
    open_admins(page, plogin_ui, proot)
    fill_create(page, f"  {username.upper()} ", "Ui Created", "Ui-Created-Pass-1",
                perms=("can_manage_users", "can_view_audit_logs"))
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal")).to_have_count(0)
    expect(row(page, username)).to_have_count(1)
    expect(row(page, username).locator("[data-testid='admin-name']")).to_have_text("Ui Created")
    assert row(page, username).locator("[data-testid='admin-perms'] .pl-chip").all_inner_texts() == ["Users", "Audit"]
    expect(toast(page)).to_contain_text("created")
    made = next(r for r in ok(proot.get(f"{P}/admins")).json() if r["username"] == username)
    assert made["is_root"] is False and made["is_active"] is True
    assert [f for f in PERMS if made[f]] == ["can_manage_users", "can_view_audit_logs"]
    ok(login_resp(base_url, username, "Ui-Created-Pass-1"))                   # the password works


@pytest.mark.plan("PLT-12")
def test_create_dialog_starts_empty_with_a_disabled_button(page, plogin_ui, proot):
    open_admins(page, plogin_ui, proot)
    tid(page, "admin-new").click()
    expect(tid(page, "admin-modal-title")).to_have_text("New administrator")
    expect(tid(page, "admin-save")).to_be_disabled()
    expect(tid(page, "admin-username")).to_be_focused()
    assert page.locator("[data-testid^='admin-perm-']").count() == 5
    assert page.locator("[data-testid^='admin-perm-']:checked").count() == 0
    expect(tid(page, "admin-password-input")).to_have_attribute("type", "password")


@pytest.mark.plan("PLT-12")
@pytest.mark.parametrize("username, name, password, message", [
    ("Bad Name!", "Valid Name", "Valid-Pass-123", "Username"),
    ("ab", "Valid Name", "Valid-Pass-123", "Username"),
    ("valid_name_x", "V", "Valid-Pass-123", "at least 2"),
    ("valid_name_y", "Valid Name", "short", "at least 8"),
    ("valid_name_z", "Valid Name", "я" * 37, "72"),
], ids=["bad-chars", "too-short-name-of-user", "one-letter-display-name", "short-password", "password-over-72-bytes"])
def test_create_dialog_checks_the_input_and_sends_nothing(page, plogin_ui, proot, username, name, password, message):
    open_admins(page, plogin_ui, proot)
    before = len(ok(proot.get(f"{P}/admins")).json())
    fill_create(page, username, name, password)
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal-error")).to_contain_text(message)
    expect(tid(page, "admin-modal")).to_be_visible()
    assert len(ok(proot.get(f"{P}/admins")).json()) == before


@pytest.mark.plan("PLT-12")
def test_a_used_name_is_refused_and_the_dialog_keeps_the_values(page, plogin_ui, proot, padmin):
    a = padmin("ac1")
    open_admins(page, plogin_ui, proot)
    fill_create(page, a.username.upper(), "Another Person")
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal-error")).to_have_text("This username is already used")
    expect(tid(page, "admin-modal")).to_be_visible()
    expect(tid(page, "admin-display-name")).to_have_value("Another Person")


@pytest.mark.plan("PLT-12")
def test_generate_gives_a_visible_random_password_that_works(page, plogin_ui, proot, base_url, cleanup):
    username = f"qa_gen_{uid(6)}".lower()
    cleanup(username)
    open_admins(page, plogin_ui, proot)
    tid(page, "admin-new").click()
    tid(page, "admin-username").fill(username)
    tid(page, "admin-display-name").fill("Generated Pass")
    tid(page, "admin-generate").click()
    field = tid(page, "admin-password-input")
    expect(field).to_have_attribute("type", "text")                          # shown, so root can hand it over
    first = field.input_value()
    assert len(first) == 16
    tid(page, "admin-generate").click()
    assert field.input_value() != first
    tid(page, "admin-password-show").click()
    expect(field).to_have_attribute("type", "password")
    password = field.input_value()
    tid(page, "admin-save").click()
    expect(row(page, username)).to_have_count(1)
    ok(login_resp(base_url, username, password))


# ---------------------------------------------------------------- closing the dialog
@pytest.mark.plan("PLT-12")
@pytest.mark.parametrize("how", ["escape", "cancel", "x", "outside"])
def test_the_dialog_closes_without_saving(page, plogin_ui, proot, how):
    open_admins(page, plogin_ui, proot)
    before = len(ok(proot.get(f"{P}/admins")).json())
    tid(page, "admin-new").click()
    tid(page, "admin-display-name").fill("Draft Person")
    {"escape": lambda: page.keyboard.press("Escape"),
     "cancel": lambda: tid(page, "admin-cancel").click(),
     "x": lambda: tid(page, "admin-modal-close").click(),
     "outside": lambda: page.mouse.click(5, 5)}[how]()
    expect(tid(page, "admin-modal")).to_have_count(0)
    tid(page, "admin-new").click()
    expect(tid(page, "admin-display-name")).to_have_value("")                 # a new dialog starts empty
    assert len(ok(proot.get(f"{P}/admins")).json()) == before


# ---------------------------------------------------------------- edit
@pytest.mark.plan("PLT-12")
def test_edit_changes_the_permissions_and_only_those(page, plogin_ui, proot, padmin):
    a = padmin("ae1", can_manage_users=True, can_view_audit_logs=True)
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-edit']").click()
    expect(tid(page, "admin-modal-title")).to_have_text("Edit administrator")
    expect(tid(page, "admin-username")).to_have_count(0)                      # the username can not be changed
    expect(tid(page, "admin-password-input")).to_have_count(0)
    expect(tid(page, "admin-display-name")).to_have_value("QA ae1")
    expect(tid(page, "admin-perm-can_manage_users")).to_be_checked()
    expect(tid(page, "admin-save")).to_be_disabled()                          # nothing changed yet
    tid(page, "admin-perm-can_manage_projects").check()
    expect(tid(page, "admin-save")).to_be_enabled()
    tid(page, "admin-perm-can_manage_projects").uncheck()
    expect(tid(page, "admin-save")).to_be_disabled()                          # undone: nothing to save
    tid(page, "admin-perm-can_manage_projects").check()
    tid(page, "admin-perm-can_view_audit_logs").uncheck()
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal")).to_have_count(0)
    expect(toast(page)).to_contain_text("Saved")
    assert row(page, a.username).locator("[data-testid='admin-perms'] .pl-chip").all_inner_texts() == ["Users", "Projects"]
    got = api_row(proot, a.id)
    assert [f for f in PERMS if got[f]] == ["can_manage_users", "can_manage_projects"]
    assert got["display_name"] == "QA ae1" and got["is_active"] is True


@pytest.mark.plan("PLT-12")
def test_edit_renames_an_admin_and_trims_the_name(page, plogin_ui, proot, padmin):
    a = padmin("ae2")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-edit']").click()
    tid(page, "admin-display-name").fill("  Renamed Person  ")
    tid(page, "admin-save").click()
    expect(row(page, a.username).locator("[data-testid='admin-name']")).to_have_text("Renamed Person")
    assert api_row(proot, a.id)["display_name"] == "Renamed Person"
    row(page, a.username).locator("[data-testid='admin-edit']").click()
    tid(page, "admin-display-name").fill("x")
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal-error")).to_contain_text("at least 2")
    assert api_row(proot, a.id)["display_name"] == "Renamed Person"


@pytest.mark.plan("PLT-12")
def test_a_permission_change_works_for_a_signed_in_admin_without_a_new_login(page, plogin_ui, proot, padmin):
    a = padmin("ae3")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-edit']").click()
    tid(page, "admin-perm-can_view_audit_logs").check()
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal")).to_have_count(0)
    assert a.client.get(f"{P}/audit").status_code == 200                      # the old token sees the new right


# ---------------------------------------------------------------- block, password, delete
@pytest.mark.plan("PLT-12")
def test_block_and_unblock(page, plogin_ui, proot, padmin, base_url):
    a = padmin("ab1")
    open_admins(page, plogin_ui, proot)
    r = row(page, a.username)
    r.locator("[data-testid='admin-toggle']").click()
    expect(r.locator("[data-testid='admin-status']")).to_have_text("Blocked")
    expect(r.locator("[data-testid='admin-toggle']")).to_have_text("Unblock")
    expect(toast(page)).to_contain_text("blocked")
    assert api_row(proot, a.id)["is_active"] is False
    resp = login_resp(base_url, a.username, a.password)
    assert resp.status_code == 403 and resp.json()["detail"] == "This account is disabled"
    assert a.client.get(f"{P}/auth/me").status_code == 403                    # the old token stops at once
    r.locator("[data-testid='admin-toggle']").click()
    expect(r.locator("[data-testid='admin-status']")).to_have_text("Active")
    expect(r.locator("[data-testid='admin-toggle']")).to_have_text("Block")
    ok(login_resp(base_url, a.username, a.password))
    assert a.client.get(f"{P}/auth/me").status_code == 200


@pytest.mark.plan("PLT-12")
def test_reset_password_in_the_dialog(page, plogin_ui, proot, padmin, base_url):
    a = padmin("ap1")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-password']").click()
    expect(tid(page, "admin-modal-title")).to_have_text("Reset password")
    expect(tid(page, "admin-password-input")).to_be_focused()
    expect(tid(page, "admin-display-name")).to_have_count(0)
    expect(tid(page, "admin-save")).to_be_disabled()
    tid(page, "admin-password-input").fill("short")
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal-error")).to_contain_text("at least 8")
    assert login_resp(base_url, a.username, ADMIN_PASSWORD).status_code == 200      # nothing was changed
    tid(page, "admin-password-input").fill("Brand-New-Pass-77")
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal")).to_have_count(0)
    expect(toast(page)).to_contain_text("password")
    assert "Brand-New-Pass-77" not in page.content()
    assert login_resp(base_url, a.username, ADMIN_PASSWORD).status_code == 401
    ok(login_resp(base_url, a.username, "Brand-New-Pass-77"))


@pytest.mark.plan("PLT-12")
def test_reset_password_removes_a_lock(page, plogin_ui, proot, padmin, base_url):
    a = padmin("ap2")
    for _ in range(config.PLATFORM_MAX_FAILED_LOGINS):
        login_resp(base_url, a.username, "Wrong-Passw0rd-1")
    assert login_resp(base_url, a.username, a.password).status_code == 429
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-password']").click()
    tid(page, "admin-password-input").fill("Unlock-Pass-1234")
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal")).to_have_count(0)
    ok(login_resp(base_url, a.username, "Unlock-Pass-1234"))


@pytest.mark.plan("PLT-12")
def test_delete_asks_first_and_cancel_keeps_the_admin(page, plogin_ui, proot, padmin):
    a = padmin("ad1")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-delete']").click()
    expect(tid(page, "admin-modal-title")).to_have_text("Delete administrator")
    expect(tid(page, "admin-target")).to_have_text("QA ad1")
    expect(tid(page, "admin-cancel")).to_be_focused()                         # the safe button has the focus
    tid(page, "admin-cancel").click()
    expect(row(page, a.username)).to_have_count(1)
    assert api_row(proot, a.id)["username"] == a.username


@pytest.mark.plan("PLT-12")
def test_delete_removes_the_admin_and_the_audit_log_keeps_the_name(page, plogin_ui, proot, padmin):
    a = padmin("ad2")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-delete']").click()
    tid(page, "admin-save").click()
    expect(row(page, a.username)).to_have_count(0)
    expect(toast(page)).to_contain_text("deleted")
    assert a.id not in [r["id"] for r in ok(proot.get(f"{P}/admins")).json()]
    assert a.client.get(f"{P}/auth/me").status_code == 401
    rows = ok(proot.get(f"{P}/audit", params={"target": a.username, "action": "admin_deleted"})).json()
    assert rows["total"] == 1


@pytest.mark.plan("PLT-12")
def test_an_admin_removed_elsewhere_gives_a_message_and_the_list_updates(page, plogin_ui, proot, padmin):
    a = padmin("ad3")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-edit']").click()
    tid(page, "admin-perm-can_manage_users").check()
    assert proot.delete(f"{P}/admins/{a.id}").status_code == 204             # somebody else was faster
    tid(page, "admin-save").click()
    expect(tid(page, "admin-modal-error")).to_have_text("Admin not found")
    expect(row(page, a.username)).to_have_count(0)                            # the list was reloaded


@pytest.mark.plan("PLT-12")
def test_every_action_shows_in_the_audit_log_tab(page, plogin_ui, proot, padmin):
    a = padmin("ad4")
    open_admins(page, plogin_ui, proot)
    row(page, a.username).locator("[data-testid='admin-toggle']").click()
    expect(row(page, a.username).locator("[data-testid='admin-status']")).to_have_text("Blocked")
    tid(page, "nav-audit").click()
    tid(page, "audit-target").fill(a.username)
    expect(page.locator("[data-testid='audit-row'][data-action='admin_disabled']")).to_have_count(1)
    expect(page.locator("[data-testid='audit-row'][data-action='admin_created']")).to_have_count(1)


@pytest.mark.plan("PLT-12")
def test_only_root_can_open_the_tab_and_the_server_agrees(page, plogin_ui, padmin):
    a = padmin("ao1", **{f: True for f in PERMS})                             # every permission, still not root
    plogin_ui(a)
    page.goto("/platform.html#/admins")
    expect(tid(page, "platform-view-title")).to_have_text("My account")
    assert tid(page, "nav-admins").count() == 0
    assert a.client.get(f"{P}/admins").status_code == 403
