"""The platform admin tool in the browser (platform.html): login, menu, themes (PLT-09 .. PLT-11, PLT-14)."""
import pytest
from playwright.sync_api import expect

from framework import config
from framework.factory import ok
from framework.platform_api import P, PERMS, login_resp
from framework.ui_fixtures import seed_session

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

ROOT = config.PLATFORM_ROOT_USERNAME
DEFAULT_THEME = "rapid_task_dark_pastel"
ALL_NAV = ["nav-health", "nav-overview", "nav-users", "nav-insights", "nav-admins", "nav-audit"]
BUILT_NAV = ["nav-health", "nav-users", "nav-admins", "nav-audit"]                    # the sections that are real pages today


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def nav_ids(page):
    return page.eval_on_selector_all("[data-testid^='nav-']", "els => els.map(e => e.dataset.testid)")


def ls(page, key):
    return page.evaluate(f"localStorage.getItem('{key}')")


def theme_of(page):
    return page.evaluate("document.documentElement.dataset.theme")


def open_tool(page, hash_=""):
    page.goto("/platform.html" + hash_)
    expect(tid(page, "platform-sidebar")).to_be_visible()


def sign_in_form(page, username, password):
    tid(page, "platform-username").fill(username)
    tid(page, "platform-password").fill(password)
    tid(page, "platform-login-submit").click()


# ---------------------------------------------------------------- PLT-09 login page and session
@pytest.mark.plan("PLT-09")
def test_login_page_has_the_form_and_no_hints_about_the_root_account(page, anon_ui):
    anon_ui()
    page.goto("/platform.html")
    expect(tid(page, "platform-login")).to_be_visible()
    expect(page).to_have_title("Rapid Task Platform")
    expect(tid(page, "platform-login-submit")).to_be_disabled()               # nothing typed yet
    text = page.locator("body").inner_text()
    for word in ("PLATFORM_ROOT", ".env", "root account"):
        assert word.lower() not in text.lower(), word
    assert page.locator("a[href='/']").count() >= 1                            # the way back to the app
    assert tid(page, "platform-sidebar").count() == 0


@pytest.mark.plan("PLT-09")
def test_wrong_password_shows_a_message_and_keeps_the_name(page, anon_ui, padmin):
    a = padmin("ul1")
    anon_ui()
    page.goto("/platform.html")
    sign_in_form(page, a.username, "Wrong-Passw0rd-1")
    expect(tid(page, "platform-login-error")).to_have_text("Invalid username or password")
    expect(tid(page, "platform-password")).to_have_value("")
    expect(tid(page, "platform-username")).to_have_value(a.username)
    assert ls(page, "rt_platform_token") is None
    assert tid(page, "platform-sidebar").count() == 0


@pytest.mark.plan("PLT-09")
def test_good_login_opens_the_tool_and_a_reload_keeps_the_session(page, anon_ui, padmin):
    a = padmin("ul2", can_view_audit_logs=True)
    anon_ui()
    page.goto("/platform.html")
    sign_in_form(page, f"  {a.username.upper()} ", a.password)                 # case and spaces do not matter
    expect(tid(page, "platform-sidebar")).to_be_visible()
    expect(tid(page, "profile-username")).to_have_text(a.username)
    assert ls(page, "rt_platform_token")
    assert ls(page, "rt_token") is None                                        # the app token is never touched
    page.reload()
    expect(tid(page, "profile-username")).to_have_text(a.username)
    assert tid(page, "platform-login").count() == 0


@pytest.mark.plan("PLT-09")
def test_an_app_user_cannot_sign_in_to_the_tool(page, anon_ui, make_user):
    u = make_user(tag="ul3_")
    anon_ui()
    page.goto("/platform.html")
    sign_in_form(page, u.email, u.password)
    expect(tid(page, "platform-login-error")).to_have_text("Invalid username or password")
    assert tid(page, "platform-sidebar").count() == 0


@pytest.mark.plan("PLT-09")
def test_a_locked_name_shows_the_wait_message(page, anon_ui, padmin, base_url):
    a = padmin("ul4")
    for _ in range(config.PLATFORM_MAX_FAILED_LOGINS):
        login_resp(base_url, a.username, "Wrong-Passw0rd-1")
    anon_ui()
    page.goto("/platform.html")
    sign_in_form(page, a.username, a.password)                                 # even the right password waits
    expect(tid(page, "platform-login-error")).to_contain_text("Too many failed attempts")
    assert tid(page, "platform-sidebar").count() == 0


@pytest.mark.plan("PLT-09")
def test_a_blocked_admin_sees_that_the_account_is_disabled(page, anon_ui, proot, padmin):
    a = padmin("ul5")
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    anon_ui()
    page.goto("/platform.html")
    sign_in_form(page, a.username, a.password)
    expect(tid(page, "platform-login-error")).to_have_text("This account is disabled")


@pytest.mark.plan("PLT-09")
def test_logout_goes_back_to_the_login_and_removes_the_token(page, plogin_ui, padmin):
    a = padmin("ul6")
    plogin_ui(a)
    open_tool(page)
    tid(page, "platform-logout").click()
    expect(tid(page, "platform-login")).to_be_visible()
    expect(tid(page, "platform-login-info")).to_contain_text("signed out")
    assert ls(page, "rt_platform_token") is None
    page.reload()                                                              # still signed out after a reload
    expect(tid(page, "platform-login")).to_be_visible()


@pytest.mark.plan("PLT-09")
def test_an_old_token_goes_to_the_login_with_a_message(page, context):
    seed_session(context, None, "en", extra_local={"rt_platform_token": "garbage.token.value"})
    page.goto("/platform.html")
    expect(tid(page, "platform-login")).to_be_visible()
    expect(tid(page, "platform-login-info")).to_contain_text("session has ended")
    assert ls(page, "rt_platform_token") is None


@pytest.mark.plan("PLT-09")
def test_an_app_token_in_the_platform_slot_is_not_accepted(page, context, make_user):
    seed_session(context, None, "en", extra_local={"rt_platform_token": make_user(tag="ul7_").token})
    page.goto("/platform.html")
    expect(tid(page, "platform-login")).to_be_visible()


@pytest.mark.plan("PLT-09")
def test_session_ends_when_the_admin_is_deleted_while_working(page, plogin_ui, proot, padmin):
    a = padmin("ul8")
    plogin_ui(a)
    open_tool(page)
    assert proot.delete(f"{P}/admins/{a.id}").status_code == 204
    tid(page, "theme-nord").click()                                            # any request now gets 401
    expect(tid(page, "platform-login")).to_be_visible()
    expect(tid(page, "platform-login-info")).to_contain_text("session has ended")


@pytest.mark.plan("PLT-09")
def test_session_ends_at_once_when_the_admin_is_blocked_while_working(page, plogin_ui, proot, padmin):
    a = padmin("ul9")
    plogin_ui(a)
    open_tool(page)
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    tid(page, "theme-nord").click()
    expect(tid(page, "platform-login")).to_be_visible()
    expect(tid(page, "platform-login-info")).to_have_text("This account is disabled")


# ---------------------------------------------------------------- PLT-10 menu, account page, routes
@pytest.mark.plan("PLT-10")
def test_root_sees_every_section_and_all_permissions(page, plogin_ui, proot):
    plogin_ui(proot)
    open_tool(page)
    assert nav_ids(page) == ALL_NAV
    expect(tid(page, "platform-role")).to_have_text("ROOT")
    expect(tid(page, "platform-perm-count")).to_contain_text("5 of 5")
    expect(tid(page, "profile-role")).to_have_text("Root")
    assert ".env" not in tid(page, "platform-account").inner_text()
    assert page.locator("[data-testid^='perm-'][data-on='true']").count() == 5


@pytest.mark.plan("PLT-10")
@pytest.mark.parametrize("flags, expected", [
    ({}, []),
    ({"can_manage_users": True}, ["nav-users"]),
    ({"can_view_analytics": True}, ["nav-overview", "nav-insights"]),
    ({"can_view_system_health": True, "can_view_audit_logs": True}, ["nav-health", "nav-audit"]),
    ({f: True for f in PERMS}, ["nav-health", "nav-overview", "nav-users", "nav-insights", "nav-audit"]),
], ids=["none", "users", "analytics", "health+audit", "all-five-but-not-root"])
def test_the_menu_shows_only_what_the_permissions_allow(page, plogin_ui, padmin, flags, expected):
    a = padmin("um1", **flags)
    plogin_ui(a)
    open_tool(page)
    assert nav_ids(page) == expected
    assert "nav-admins" not in nav_ids(page)                                   # Administrators is for root only
    expect(tid(page, "platform-role")).to_have_text("ADMIN")
    expect(tid(page, "platform-perm-count")).to_contain_text(f"{len(flags)} of 5")


@pytest.mark.plan("PLT-10")
def test_sections_that_are_not_built_yet_are_not_links(page, plogin_ui, proot):
    plogin_ui(proot)
    open_tool(page)
    for name in ("nav-overview", "nav-insights"):
        assert page.locator(f"a[data-testid='{name}']").count() == 0, name
        assert tid(page, name).locator(".pl-soon").count() == 1, name
    for name in BUILT_NAV:
        assert page.locator(f"a[data-testid='{name}']").count() == 1, name


@pytest.mark.plan("PLT-10")
def test_the_account_page_shows_the_profile_and_the_permissions(page, plogin_ui, padmin):
    a = padmin("ua1", can_view_analytics=True, can_view_audit_logs=True)
    plogin_ui(a)
    open_tool(page)
    expect(tid(page, "platform-view-title")).to_have_text("My account")
    expect(tid(page, "profile-name")).to_have_text("QA ua1")
    expect(tid(page, "profile-username")).to_have_text(a.username)
    expect(tid(page, "profile-role")).to_have_text("Administrator")
    for flag in PERMS:
        expect(tid(page, f"perm-{flag}")).to_have_attribute("data-on", "true" if flag in ("can_view_analytics", "can_view_audit_logs") else "false")
    assert page.locator("[data-testid^='perm-'][data-on='true']").count() == 2


@pytest.mark.plan("PLT-10")
@pytest.mark.parametrize("route", ["#/admins", "#/audit", "#/nonsense"])
def test_a_section_without_permission_falls_back_to_my_account(page, plogin_ui, padmin, route):
    a = padmin("ur1")
    plogin_ui(a)
    open_tool(page, route)
    expect(tid(page, "platform-view-title")).to_have_text("My account")
    assert tid(page, "admins-page").count() == 0 and tid(page, "audit-page").count() == 0


@pytest.mark.plan("PLT-10")
def test_the_address_keeps_the_section_after_a_reload(page, plogin_ui, proot):
    plogin_ui(proot)
    open_tool(page)
    tid(page, "nav-audit").click()
    expect(tid(page, "platform-view-title")).to_have_text("Audit log")
    assert page.url.endswith("#/audit")
    page.reload()
    expect(tid(page, "platform-view-title")).to_have_text("Audit log")
    tid(page, "nav-admins").click()
    expect(tid(page, "platform-view-title")).to_have_text("Administrators")
    tid(page, "platform-user-block").click()
    expect(tid(page, "platform-view-title")).to_have_text("My account")


@pytest.mark.plan("PLT-10")
def test_the_back_button_follows_the_sections(page, plogin_ui, proot):
    plogin_ui(proot)
    open_tool(page)
    tid(page, "nav-audit").click()
    tid(page, "nav-admins").click()
    page.go_back()
    expect(tid(page, "platform-view-title")).to_have_text("Audit log")
    page.go_back()
    expect(tid(page, "platform-view-title")).to_have_text("My account")


# ---------------------------------------------------------------- PLT-11 theme picker
@pytest.mark.plan("PLT-11")
def test_the_picker_lists_all_twelve_looks_and_marks_the_default(page, plogin_ui, padmin, make_user):
    keys = [t["key"] for t in ok(make_user(tag="ut0_").client.get("/api/themes")).json()]
    plogin_ui(padmin("ut1"))
    open_tool(page)
    shown = page.eval_on_selector_all("[data-testid^='theme-']", "els => els.map(e => e.dataset.testid.slice(6))")
    assert sorted(shown) == sorted(keys) and len(shown) >= 12
    expect(tid(page, f"theme-{DEFAULT_THEME}")).to_have_attribute("aria-checked", "true")
    assert page.locator("[data-testid^='theme-'][aria-checked='true']").count() == 1
    assert theme_of(page) == DEFAULT_THEME


@pytest.mark.plan("PLT-11")
@pytest.mark.parametrize("key", ["lavender_light", "mint_night", "nord"])
def test_picking_a_look_applies_it_saves_it_and_keeps_it_after_a_reload(page, plogin_ui, padmin, key):
    a = padmin("ut2")
    plogin_ui(a)
    open_tool(page)
    tid(page, f"theme-{key}").click()
    expect(page.locator("html")).to_have_attribute("data-theme", key)
    expect(tid(page, f"theme-{key}")).to_have_attribute("aria-checked", "true")
    assert ls(page, "rt_platform_theme") == key
    assert ok(a.client.get(f"{P}/auth/me")).json()["theme_key"] == key        # saved for the account
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", key)
    expect(tid(page, f"theme-{key}")).to_have_attribute("aria-checked", "true")


@pytest.mark.plan("PLT-11")
def test_the_saved_look_of_the_account_wins_over_the_browser(page, plogin_ui, padmin):
    a = padmin("ut3")
    ok(a.client.put(f"{P}/auth/me/theme", json={"theme_key": "nord"}))
    plogin_ui(a, rt_platform_theme="lavender_light")                           # an old choice of this browser
    open_tool(page)
    expect(page.locator("html")).to_have_attribute("data-theme", "nord")


@pytest.mark.plan("PLT-11")
def test_a_new_browser_gets_the_look_of_the_account_after_login(page, anon_ui, padmin):
    a = padmin("ut4")
    ok(a.client.put(f"{P}/auth/me/theme", json={"theme_key": "midnight_neon"}))
    anon_ui()
    page.goto("/platform.html")
    assert theme_of(page) == DEFAULT_THEME                                     # before the login: the default
    sign_in_form(page, a.username, a.password)
    expect(tid(page, "platform-sidebar")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-theme", "midnight_neon")


@pytest.mark.plan("PLT-11")
def test_the_look_stays_after_logout(page, plogin_ui, padmin):
    plogin_ui(padmin("ut5"))
    open_tool(page)
    tid(page, "theme-lavender_light").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "lavender_light")
    tid(page, "platform-logout").click()
    expect(tid(page, "platform-login")).to_be_visible()
    assert theme_of(page) == "lavender_light"


@pytest.mark.plan("PLT-11")
def test_the_app_theme_and_the_tool_theme_do_not_mix(page, plogin_ui, padmin):
    a = padmin("ut6")
    plogin_ui(a, rt_theme="solarized_dark")                                    # the personal theme of the Rapid Task app
    open_tool(page)
    assert theme_of(page) == DEFAULT_THEME                                     # the app theme is ignored here
    tid(page, "theme-mint_night").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "mint_night")
    assert ls(page, "rt_theme") == "solarized_dark"                            # and left untouched
    page.evaluate("localStorage.setItem('rt_theme', 'nord'); window.dispatchEvent(new StorageEvent('storage', {key: 'rt_theme'}))")
    page.wait_for_timeout(300)
    assert theme_of(page) == "mint_night"                                      # a change in another tab does not repaint the tool


@pytest.mark.plan("PLT-11")
def test_every_new_look_can_be_picked_without_breaking_the_page(page, plogin_ui, padmin):
    """The tool paints with the theme variables only: no look may add sideways scrolling or throw."""
    plogin_ui(padmin("ut7", can_view_audit_logs=True))
    open_tool(page)
    for key in ("lavender_light", "violet_pop_light", "navy_orange_light", "fresh_lime_light", "mint_night", "midnight_neon"):
        tid(page, f"theme-{key}").click()
        expect(page.locator("html")).to_have_attribute("data-theme", key)
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1, key
        text, bg = page.evaluate("[getComputedStyle(document.body).color, getComputedStyle(document.body).backgroundColor]")
        assert text != bg, key
    assert page.js_errors == []


# ---------------------------------------------------------------- PLT-14 no errors, no sideways scrolling, text is text
@pytest.mark.plan("PLT-14")
def test_walking_through_every_tab_throws_no_script_errors(page, plogin_ui, proot):
    plogin_ui(proot)
    open_tool(page)
    for nav, shown in (("nav-health", "health-page"), ("nav-users", "users-page"), ("nav-admins", "admins-page"), ("nav-audit", "audit-page")):
        tid(page, nav).click()
        expect(tid(page, shown)).to_be_visible()
        expect(tid(page, "platform-view-title")).not_to_have_text("My account")
    tid(page, "platform-user-block").click()
    expect(tid(page, "platform-account")).to_be_visible()
    assert page.js_errors == []
    assert page.console_errors == [], page.console_errors


@pytest.mark.plan("PLT-14")
@pytest.mark.parametrize("width, height", [(390, 800), (768, 900), (1024, 768), (1366, 850), (1920, 1080)])
@pytest.mark.parametrize("route", ["", "#/health", "#/users", "#/admins", "#/audit"], ids=["account", "health", "users", "admins", "audit"])
def test_no_sideways_scrolling(page, plogin_ui, proot, width, height, route):
    page.set_viewport_size({"width": width, "height": height})
    plogin_ui(proot)
    open_tool(page, route)
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1


@pytest.mark.plan("PLT-14")
def test_a_name_with_html_is_shown_as_text_everywhere(page, plogin_ui, proot, padmin):
    evil = "<img src=x onerror=window.__x=1>"
    a = padmin("ux1", display_name=evil, can_view_audit_logs=True)
    plogin_ui(a)
    open_tool(page)
    expect(tid(page, "profile-name")).to_have_text(evil)
    expect(tid(page, "platform-user-block")).to_contain_text(evil)
    assert page.locator("img[src='x']").count() == 0
    assert page.evaluate("window.__x") is None
    # the same name seen by root in the Administrators tab (a second tab with the root token)
    other = page.context.new_page()
    other.goto("/platform.html")
    other.evaluate("t => localStorage.setItem('rt_platform_token', t)", proot.token)
    other.goto("/platform.html#/admins")
    other.reload()
    row = other.locator(f"[data-testid='admin-row'][data-username='{a.username}'] [data-testid='admin-name']")
    expect(row).to_have_text(evil)
    assert other.locator("img[src='x']").count() == 0
    assert other.evaluate("window.__x") is None
    other.close()


@pytest.mark.plan("PLT-14")
def test_the_page_never_shows_a_password_or_a_hash(page, plogin_ui, proot, padmin):
    a = padmin("ux2", password="Visible-Secret-Pass-1!")
    plogin_ui(proot)
    open_tool(page, "#/admins")
    expect(tid(page, "admins-table")).to_be_visible()
    html = page.content()
    assert "Visible-Secret-Pass-1!" not in html and "hashed_password" not in html and "$2b$" not in html
    assert a.username in html
