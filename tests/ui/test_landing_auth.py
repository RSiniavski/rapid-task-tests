"""AUTH-FE, UI-01 (landing), UI-06 landing links."""
import re

import pytest
from playwright.sync_api import expect

from framework.config import PASSWORD
from framework.factory import unique_email
from pages.base import Landing

pytestmark = [pytest.mark.ui]


@pytest.mark.plan("AUTH-FE")
def test_auth_dialog_opens_switches_tabs_and_closes(page, anon_ui):
    anon_ui()
    L = Landing(page).open().open_login()
    assert page.locator("#form-login").is_visible() and not page.locator("#form-register").is_visible()
    page.locator("#tab-register").click()
    assert page.locator("#form-register").is_visible() and not page.locator("#form-login").is_visible()
    page.keyboard.press("Escape")
    expect(L.modal).not_to_have_class(re.compile("open"))
    L.open_login()
    page.locator("#auth-close").click()
    expect(L.modal).not_to_have_class(re.compile("open"))
    L.open_login()
    page.mouse.click(5, 5)                                           # backdrop click closes
    expect(L.modal).not_to_have_class(re.compile("open"))
    assert not page.js_errors


@pytest.mark.plan("AUTH-FE", "E2E-01")
def test_register_through_ui_logs_in_and_lands_on_dashboard(page, anon_ui):
    anon_ui()
    Landing(page).open().open_register().register("UI Newbie", unique_email("ui_"), PASSWORD)
    page.wait_for_url(re.compile(r"/dashboard\.html"))
    assert page.evaluate("localStorage.getItem('rt_token')")
    expect(page.get_by_text("UI Newbie").first).to_be_visible()
    assert not page.js_errors


@pytest.mark.plan("AUTH-FE")
def test_login_success_redirects_and_stores_token(page, anon_ui, make_user):
    u = make_user(tag="uilogin_")
    anon_ui()
    Landing(page).open().open_login().login(u.email, u.password)
    page.wait_for_url(re.compile(r"/dashboard\.html"))
    assert page.evaluate("localStorage.getItem('rt_token')")


@pytest.mark.plan("AUTH-FE")
@pytest.mark.parametrize("email,password", [("nobody@example.com", "wrong-Pass1!"), ("", ""), ("not-an-email", "x")])
def test_login_failures_show_error_and_stay_on_landing(page, anon_ui, email, password):
    anon_ui()
    L = Landing(page).open().open_login()
    L.login(email, password)
    page.wait_for_timeout(600)
    assert "/dashboard.html" not in page.url
    assert not page.evaluate("localStorage.getItem('rt_token')")
    assert not page.js_errors


@pytest.mark.plan("AUTH-FE")
def test_wrong_password_message_is_localised_error(page, anon_ui, make_user):
    u = make_user(tag="uibad_")
    anon_ui()
    Landing(page).open().open_login().login(u.email, "WrongPassword1!")
    expect(page.locator("#login-error")).to_contain_text("Error: please try again")
    expect(page.locator("#login-error")).to_contain_text("Incorrect")


@pytest.mark.plan("AUTH-FE")
def test_duplicate_registration_shows_server_error(page, anon_ui, make_user):
    u = make_user(tag="uidup_")
    anon_ui()
    Landing(page).open().open_register().register("Dup", u.email, PASSWORD)
    expect(page.locator("#register-error")).to_contain_text("Error: please try again")
    assert "/dashboard.html" not in page.url


@pytest.mark.plan("AUTH-FE")
def test_register_form_validation_blocks_submit(page, anon_ui):
    anon_ui()
    Landing(page).open().open_register().register("", "bad", "")
    page.wait_for_timeout(400)
    assert "/dashboard.html" not in page.url
    assert page.locator("#reg-email").evaluate("e => !e.validity.valid")


@pytest.mark.plan("AUTH-FE")
def test_submit_button_is_disabled_while_request_in_flight(page, anon_ui, make_user):
    u = make_user(tag="uislow_")
    anon_ui()

    def slow(route):
        page.wait_for_timeout(800)
        route.continue_()
    page.route("**/api/auth/login", slow)
    Landing(page).open().open_login()
    page.fill("#login-email", u.email)
    page.fill("#login-password", u.password)
    btn = page.locator("#form-login button[type=submit]")
    btn.click()
    expect(btn).to_be_disabled()
    page.wait_for_url(re.compile(r"/dashboard\.html"))


@pytest.mark.plan("AUTH-FE", "AUTH-09")
def test_logged_in_visitor_is_redirected_and_stale_token_is_cleared(page, context, login_ui, make_user):
    u = make_user(tag="uistale_")
    login_ui(u)
    page.goto("/")
    page.wait_for_url(re.compile(r"/dashboard\.html"))
    page.evaluate("localStorage.setItem('rt_token','garbage.token.value')")
    page.goto("/")
    page.wait_for_function("!localStorage.getItem('rt_token')")
    assert page.url.rstrip("/").endswith(page.url.split("/")[2])      # still on landing


@pytest.mark.plan("AUTH-FE")
def test_logout_clears_token_and_protected_pages_redirect(page, login_ui, make_user):
    u = make_user(tag="uilogout_")
    login_ui(u)
    page.goto("/dashboard.html")
    page.get_by_role("button", name="Log out").click()
    page.wait_for_url(re.compile(r"/$"))
    assert not page.evaluate("localStorage.getItem('rt_token')")
    page.goto("/dashboard.html")
    page.wait_for_url(re.compile(r"/$"))


@pytest.mark.plan("UI-06", "STATIC")
def test_landing_links_and_new_tab_behaviour(page, anon_ui):
    anon_ui()
    page.goto("/")
    donate = page.locator("a[href='/donate.html']")
    assert donate.count() >= 2
    for i in range(donate.count()):
        assert donate.nth(i).get_attribute("target") == "_blank"
        assert "noopener" in (donate.nth(i).get_attribute("rel") or "")
    assert page.locator("a[href='/docs']").count() >= 1
    for ext in page.locator("a[href^='http']").all():
        assert ext.get_attribute("target") == "_blank" and "noopener" in (ext.get_attribute("rel") or "")
    assert page.request.get("/docs").status == 200
