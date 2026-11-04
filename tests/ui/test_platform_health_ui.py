"""Platform admin tool, System health tab in the browser (PLT-24, PLT-25)."""
import json
import re

import pytest
from playwright.sync_api import expect

from framework import config
from framework.factory import create_project, ok, uid
from framework.platform_api import P, login_client

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

H = f"{P}/health"
RAISE = f"{H}/_raise"
DEBUG = {"PLATFORM_HEALTH_DEBUG": "1"}


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def api(client):
    return ok(client.get(H)).json()


def open_health(page, plogin_ui, who, base=""):
    plogin_ui(who)
    page.goto(f"{base}/platform.html#/health")
    expect(tid(page, "health-page")).to_be_visible()
    expect(tid(page, "health-banner")).to_be_visible()


def own_server(plt_server, env=None):
    """An extra isolated application and a root client of it."""
    srv = plt_server(env or {})
    return srv, login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)


# ---------------------------------------------------------------- PLT-24 what the page shows
@pytest.mark.plan("PLT-24")
def test_the_page_and_the_menu_item(page, plogin_ui, proot):
    open_health(page, plogin_ui, proot)
    expect(tid(page, "platform-view-title")).to_have_text("System Health")
    expect(tid(page, "nav-health")).to_have_attribute("aria-current", "page")
    expect(tid(page, "health-status-text")).to_have_text({
        "ok": "All systems normal", "warning": "Needs attention", "critical": "There is a problem"}[api(proot)["status"]])


@pytest.mark.plan("PLT-24")
def test_server_and_database_cards_match_the_api(page, plogin_ui, proot):
    open_health(page, plogin_ui, proot)
    h = api(proot)
    expect(tid(page, "server-version")).to_have_text(h["server"]["app_version"])
    expect(tid(page, "server-python")).to_have_text(h["server"]["python_version"])
    assert re.search(r"\b\d\d:\d\d\b", tid(page, "server-started").inner_text())                  # 24 h time
    expect(tid(page, "server-uptime")).to_have_text(re.compile(r"^\d+ (s|min|h|d)\b"))
    rows = page.locator("[data-testid='db-row']")
    expect(rows).to_have_count(2)
    for row, (name, file) in zip(rows.all(), (("Application", "rapid_task.db"), ("Platform", "platform.db"))):
        expect(row.locator("[data-testid='db-name']")).to_have_text(name)
        expect(row.locator("[data-testid='db-file']")).to_have_text(file)
        expect(row.locator("[data-testid='db-status']")).to_have_text("Reachable")
        expect(row).to_have_attribute("data-ok", "true")
        expect(row.locator("[data-testid='db-size']")).to_have_text(re.compile(r"^\d+(\.\d)? (B|KB|MB|GB)$"))
        expect(row.locator("[data-testid='db-error']")).to_have_count(0)


@pytest.mark.plan("PLT-24")
def test_the_disk_card_matches_the_api(page, plogin_ui, proot):
    open_health(page, plogin_ui, proot)
    shown = float(tid(page, "disk-percent").inner_text().rstrip("%"))                          # the disk can change a little, so no API compare
    level = "critical" if shown >= 90 else "warning" if shown >= 80 else "ok"
    bar = tid(page, "disk-bar")
    expect(bar).to_have_attribute("data-level", level)
    assert float(bar.get_attribute("aria-valuenow")) == shown
    expect(tid(page, "disk-level")).to_have_text({"ok": "OK", "warning": "Warning", "critical": "Critical"}[level])
    for key in ("disk-used", "disk-free", "disk-total", "uploads-size"):
        expect(tid(page, key)).to_have_text(re.compile(r"^\d+(\.\d)? (B|KB|MB|GB|TB)$"))
    expect(tid(page, "disk-limits")).to_contain_text("80%")
    expect(tid(page, "disk-limits")).to_contain_text("90%")
    filled = page.evaluate("document.querySelector('.pl-bar-fill').getBoundingClientRect().width / document.querySelector('.pl-bar').getBoundingClientRect().width")
    assert abs(filled - shown / 100) < 0.02                                         # the bar is as long as the percent


@pytest.mark.plan("PLT-24")
def test_the_counts_follow_the_application(page, plogin_ui, proot, make_user):
    owner = make_user(tag="hu_", full_name=f"QA {uid(8)} hu")
    project = create_project(owner)
    project.ticket()
    project.ticket()
    open_health(page, plogin_ui, proot)
    c = api(proot)["counts"]
    expect(tid(page, "count-users")).to_have_text(f"{c['users']:,}")
    expect(tid(page, "count-projects")).to_have_text(f"{c['projects']:,}")
    expect(tid(page, "count-tickets")).to_have_text(f"{c['tickets']:,}")
    make_user(tag="hu2_")                                                                       # one more user ...
    tid(page, "health-refresh").click()
    expect(tid(page, "count-users")).to_have_text(f"{c['users'] + 1:,}")                         # ... shows after Refresh
    expect(tid(page, "health-updated")).to_have_text(re.compile(r"^Updated \d\d:\d\d:\d\d$"))


@pytest.mark.plan("PLT-24")
def test_the_load_card_and_the_empty_error_list(page, plogin_ui, plt_server):
    srv, root = own_server(plt_server)
    for _ in range(3):
        ok(root.get(f"{P}/users"))
    open_health(page, plogin_ui, root, srv.base_url)
    total = int(tid(page, "load-total").inner_text().replace(",", ""))
    assert 3 <= total <= api(root)["load"]["requests_total"]                                    # the page may load its own data too
    expect(tid(page, "errors-hour")).to_have_text("0")
    expect(tid(page, "errors-total")).to_have_text("0")
    expect(tid(page, "errors-level")).to_have_text("OK")
    expect(tid(page, "errors-empty")).to_have_text("No server errors since the server started.")
    expect(tid(page, "errors-table")).to_have_count(0)


@pytest.mark.plan("PLT-24")
def test_the_uploads_folder_size_is_shown(page, plogin_ui, plt_server):
    srv, root = own_server(plt_server)
    (srv.uploads_dir / f"health_{uid(6)}.bin").write_bytes(b"x" * 1234)
    open_health(page, plogin_ui, root, srv.base_url)
    expect(tid(page, "uploads-size")).to_have_text("1.2 KB")
    expect(tid(page, "uploads-files")).to_have_text("1")


@pytest.mark.plan("PLT-24")
@pytest.mark.parametrize("warn, critical, level, label, text", [
    (0, 100, "warning", "Warning", "Needs attention"),
    (0, 0, "critical", "Critical", "There is a problem"),
    (101, 102, "ok", "OK", "All systems normal"),
], ids=["warning", "critical", "ok"])
def test_the_banner_and_the_disk_bar_use_the_level(page, plogin_ui, plt_server, warn, critical, level, label, text):
    srv, root = own_server(plt_server, {"HEALTH_DISK_WARN_PERCENT": str(warn), "HEALTH_DISK_CRITICAL_PERCENT": str(critical)})
    open_health(page, plogin_ui, root, srv.base_url)
    expect(tid(page, "health-banner")).to_have_attribute("data-level", level)
    expect(tid(page, "health-status")).to_have_text(label)
    expect(tid(page, "health-status-text")).to_have_text(text)
    expect(tid(page, "disk-bar")).to_have_attribute("data-level", level)
    expect(tid(page, "disk-level")).to_have_text(label)
    expect(tid(page, "disk-limits")).to_contain_text(f"{warn}%")
    pill = tid(page, "health-status").get_attribute("class")
    assert {"ok": "ok", "warning": "warn", "critical": "bad"}[level] in pill.split()


@pytest.mark.plan("PLT-24")
def test_the_page_shows_no_secret_and_no_server_folder(page, plogin_ui, proot):
    open_health(page, plogin_ui, proot)
    text = tid(page, "health-page").inner_text().lower()
    for word in ("password", "secret", "token", "sqlite"):
        assert word not in text, word
    assert ":\\" not in text and "/home/" not in text


# ---------------------------------------------------------------- PLT-25 errors, refresh, permission
@pytest.mark.plan("PLT-25")
def test_a_server_error_is_listed_and_colors_the_page(page, plogin_ui, plt_server):
    srv, root = own_server(plt_server, DEBUG)
    assert root.post(RAISE).status_code == 500
    assert root.post(RAISE).status_code == 500
    open_health(page, plogin_ui, root, srv.base_url)
    rows = page.locator("[data-testid='error-row']")
    expect(rows).to_have_count(2)
    first = rows.first
    expect(first.locator("[data-testid='error-method']")).to_have_text("POST")
    expect(first.locator("[data-testid='error-path']")).to_have_text(RAISE)
    expect(first.locator("[data-testid='error-status']")).to_have_text("500")
    expect(first.locator("[data-testid='error-class']")).to_have_text("RuntimeError")
    assert re.search(r"\b\d\d:\d\d\b", first.locator("[data-testid='error-time']").inner_text())
    expect(tid(page, "errors-hour")).to_have_text("2")
    expect(tid(page, "errors-total")).to_have_text("2")
    expect(tid(page, "errors-level")).to_have_text("Warning")
    expect(tid(page, "health-banner")).to_have_attribute("data-level", "warning")
    assert "raised on purpose" not in tid(page, "health-page").inner_text()                     # no error message, no stack


@pytest.mark.plan("PLT-25")
def test_many_errors_turn_the_page_critical(page, plogin_ui, plt_server):
    srv, root = own_server(plt_server, {**DEBUG, "HEALTH_ERRORS_WARN": "1", "HEALTH_ERRORS_CRITICAL": "2"})
    root.post(RAISE)
    root.post(RAISE)
    open_health(page, plogin_ui, root, srv.base_url)
    expect(tid(page, "errors-level")).to_have_text("Critical")
    expect(tid(page, "health-banner")).to_have_attribute("data-level", "critical")
    expect(tid(page, "health-status-text")).to_have_text("There is a problem")


@pytest.mark.plan("PLT-25")
def test_the_page_refreshes_by_itself_until_it_is_switched_off(page, context, plogin_ui, plt_server):
    context.add_init_script("window.__plHealthMs = 500")                                         # 0.5 s instead of 30 s
    srv, root = own_server(plt_server, DEBUG)
    open_health(page, plogin_ui, root, srv.base_url)
    expect(tid(page, "health-auto")).to_be_checked()
    expect(tid(page, "errors-total")).to_have_text("0")
    root.post(RAISE)
    expect(tid(page, "errors-total")).to_have_text("1")                                         # no click: it came by itself
    tid(page, "health-auto").uncheck()
    root.post(RAISE)
    page.wait_for_timeout(1600)
    expect(tid(page, "errors-total")).to_have_text("1")                                         # switched off: nothing changes
    page.reload()
    expect(tid(page, "health-banner")).to_be_visible()
    expect(tid(page, "health-auto")).not_to_be_checked()                                        # the choice is remembered
    expect(tid(page, "errors-total")).to_have_text("2")                                         # a reload always reads again
    tid(page, "health-auto").check()
    root.post(RAISE)
    expect(tid(page, "errors-total")).to_have_text("3")


@pytest.mark.plan("PLT-25")
def test_leaving_the_tab_stops_the_refresh(page, context, plogin_ui, proot):
    context.add_init_script("window.__plHealthMs = 400")
    calls = []
    page.on("request", lambda r: calls.append(r.url) if r.url.endswith("/api/platform/health") else None)
    open_health(page, plogin_ui, proot)
    page.wait_for_timeout(1300)
    assert len(calls) >= 3                                                                      # it was refreshing
    tid(page, "nav-users").click()
    expect(tid(page, "users-page")).to_be_visible()
    page.wait_for_timeout(500)
    seen = len(calls)
    page.wait_for_timeout(1500)
    assert len(calls) == seen                                                                   # and now it is quiet


@pytest.mark.plan("PLT-25")
def test_a_failed_refresh_keeps_the_old_numbers_and_says_so(page, plogin_ui, proot):
    open_health(page, plogin_ui, proot)
    users_before = tid(page, "count-users").inner_text()
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route("**/api/platform/health", handler)
    tid(page, "health-refresh").click()
    expect(tid(page, "health-error")).to_contain_text("Something broke")
    expect(tid(page, "count-users")).to_have_text(users_before)                                 # the old numbers stay
    expect(tid(page, "health-banner")).to_be_visible()
    state["fail"] = False
    tid(page, "health-refresh").click()
    expect(tid(page, "health-error")).to_have_count(0)


@pytest.mark.plan("PLT-25")
def test_a_first_load_error_has_try_again(page, plogin_ui, proot):
    plogin_ui(proot)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route("**/api/platform/health", handler)
    page.goto("/platform.html#/health")
    expect(tid(page, "health-error")).to_contain_text("Something broke")
    expect(tid(page, "health-banner")).to_have_count(0)
    state["fail"] = False
    tid(page, "health-retry").click()
    expect(tid(page, "health-banner")).to_be_visible()


@pytest.mark.plan("PLT-25")
def test_an_admin_with_the_permission_works(page, plogin_ui, padmin):
    allowed = padmin("hh1", can_view_system_health=True)
    open_health(page, plogin_ui, allowed)
    assert page.locator("a[data-testid^='nav-']").count() == 1
    expect(tid(page, "health-status")).to_be_visible()


@pytest.mark.plan("PLT-25")
def test_an_admin_without_the_permission_is_sent_to_my_account(page, plogin_ui, padmin):
    plain = padmin("hh2", can_view_audit_logs=True)
    plogin_ui(plain)
    page.goto("/platform.html#/health")
    expect(tid(page, "platform-account")).to_be_visible()
    expect(tid(page, "nav-health")).to_have_count(0)
    expect(tid(page, "health-page")).to_have_count(0)
