"""UI-01 localisation, UI-02 theme, UI-04/05 states + responsive/a11y, UI-06 links, UI-07 headers/XSS."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board, Dashboard, Roadmap

pytestmark = [pytest.mark.ui]


# ------------------------------------------------------------------ UI-01
@pytest.mark.plan("UI-01")
def test_landing_language_toggle_switches_and_persists(page, anon_ui):
    anon_ui("uk")
    page.goto("/")
    expect(page.locator("html")).to_have_attribute("lang", "uk")
    uk_title = page.locator("[data-i18n='hero.title']").inner_text()
    page.locator(".lang-switch [data-lang=en]").first.click()
    expect(page.locator("[data-i18n='hero.title']")).to_have_text("Manage tasks, fast")
    assert page.locator("[data-i18n='hero.title']").inner_text() != uk_title
    assert page.evaluate("localStorage.getItem('rt_lang')") == "en"
    page.reload()
    expect(page.locator("[data-i18n='hero.title']")).to_have_text("Manage tasks, fast")
    page.locator(".lang-switch [data-lang=uk]").first.click()
    expect(page.locator("html")).to_have_attribute("lang", "uk")


@pytest.mark.plan("UI-01")
def test_i18n_dictionaries_have_identical_keys(page, anon_ui):
    anon_ui()
    page.goto("/")
    uk, en = page.evaluate("[Object.keys(I18N.uk), Object.keys(I18N.en)]")
    assert sorted(set(uk) ^ set(en)) == []


@pytest.mark.plan("UI-01")
def test_no_untranslated_keys_visible_on_static_pages(page, anon_ui):
    anon_ui("en")
    for path in ("/", "/donate.html"):
        page.goto(path)
        text = page.inner_text("body")
        assert not re.search(r"\b(nav|hero|features|how|auth|footer|support|donate)\.[a-z0-9_.]+\b", text), path


@pytest.mark.plan("UI-01")
@pytest.mark.needs_vue
@pytest.mark.parametrize("lang,expected", [("en", "Control panel"), ("uk", "Панель керування")])
def test_dashboard_language(page, login_ui, make_user, lang, expected):
    login_ui(make_user(tag="uilang_"), lang=lang)
    Dashboard(page).open()
    expect(page.locator("h1")).to_have_text(expected)


@pytest.mark.plan("UI-01")
@pytest.mark.needs_vue
def test_board_has_no_hardcoded_ukrainian_in_english_mode(page, login_ui, world):
    login_ui(world.roles.admin, lang="en")
    Board(page).open(world.a.id)
    html = re.sub(r"<script.*?</script>", "", page.content(), flags=re.S)
    found = sorted(set(re.findall(r"[А-Яа-яІіЇїЄє][А-Яа-яІіЇїЄє \-:+.]{2,}", html)))
    assert not found, f"Ukrainian text still present in English mode: {found}"


@pytest.mark.plan("UI-01")
@pytest.mark.parametrize("lang,word", [("en", "Planned"), ("uk", "Заплановано")])
def test_roadmap_language(page, login_ui, world, lang, word):
    world.a.milestone(title="Lang block")
    login_ui(world.roles.admin, lang=lang)
    Roadmap(page).open(world.a.id)
    expect(page.locator(".rm-block .rm-badge-status").first).to_have_text(word)


# ------------------------------------------------------------------ UI-02
@pytest.mark.plan("UI-02")
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_pages_remain_readable_under_color_scheme_preference(page, anon_ui, scheme):
    anon_ui()
    page.emulate_media(color_scheme=scheme)
    page.goto("/")
    fg, bg = page.evaluate("[getComputedStyle(document.body).color, getComputedStyle(document.body).backgroundColor]")
    assert fg != bg


# ------------------------------------------------------------------ UI-05

@pytest.mark.plan("UI-05")
@pytest.mark.parametrize("width", [320, 390, 768, 1280])
@pytest.mark.parametrize("path", ["/", "/donate.html"])
def test_static_pages_have_no_horizontal_overflow(page, anon_ui, width, path):
    anon_ui()
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(path)
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{path}@{width}"


@pytest.mark.plan("UI-05")
@pytest.mark.needs_vue
@pytest.mark.parametrize("width", [320, 390])
def test_dashboard_has_no_horizontal_overflow_on_phones(page, login_ui, world, width):
    login_ui(world.roles.admin)
    page.set_viewport_size({"width": width, "height": 800})
    Dashboard(page).open()
    page.wait_for_selector(".project-card")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


@pytest.mark.plan("UI-05")
def test_auth_dialog_keyboard_access_and_labels(page, anon_ui):
    anon_ui()
    page.goto("/")
    page.locator("[data-open-auth='login']").first.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#auth-backdrop")).to_have_class(re.compile("open"))
    assert page.evaluate("document.activeElement && document.activeElement.tagName") == "INPUT"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "login-password"
    assert page.locator("#auth-close").get_attribute("aria-label") or page.locator("#auth-close").inner_text()
    for sel in ("#login-email", "#login-password"):
        assert page.locator(sel).evaluate("e => !!(e.labels && e.labels.length) || e.hasAttribute('aria-label') || e.placeholder")


@pytest.mark.plan("UI-05")
def test_images_have_alt_text_and_page_has_lang(page, anon_ui):
    anon_ui()
    page.goto("/")
    assert page.evaluate("document.documentElement.lang") in ("uk", "en")
    assert page.evaluate("[...document.images].every(i => i.hasAttribute('alt'))")


@pytest.mark.plan("UI-05")
def test_reduced_motion_preference_does_not_break_rendering(page, anon_ui):
    anon_ui()
    page.emulate_media(reduced_motion="reduce")
    page.goto("/")
    expect(page.locator("[data-i18n='hero.title']")).to_be_visible()
    assert not page.js_errors


# ------------------------------------------------------------------ UI-06
@pytest.mark.plan("UI-06")
@pytest.mark.known_issue
@pytest.mark.xfail(strict=False, reason="DEFECT: donate links in donate.js are still YOUR_* placeholders")
def test_donate_page_links_are_configured_and_open_safely(page, anon_ui):
    anon_ui("en")
    page.goto("/donate.html")
    links = page.locator("a[data-pay]")
    assert links.count() == 3
    hrefs = [links.nth(i).get_attribute("href") for i in range(3)]
    assert all(h.startswith("https://") for h in hrefs)
    for i in range(3):
        assert links.nth(i).get_attribute("target") == "_blank"
    assert not any("YOUR_" in h for h in hrefs), "donate links are still placeholders (YOUR_*)"
    expect(page.get_by_role("link", name="← Back to home")).to_have_attribute("href", "/")


@pytest.mark.plan("UI-06")
@pytest.mark.needs_vue
def test_header_and_footer_links_on_dashboard_and_board(page, login_ui, world):
    login_ui(world.roles.admin)
    Dashboard(page).open()
    expect(page.locator("a.logo")).to_have_attribute("href", "/")
    donate = page.locator(".footer-donate")
    expect(donate).to_have_attribute("href", "/donate.html")
    expect(donate).to_have_attribute("target", "_blank")
    Board(page).open(world.a.id)
    expect(page.locator("a.logo")).to_have_attribute("href", "/dashboard.html")
    expect(page.get_by_role("link", name="🗺 Roadmap")).to_have_attribute("href", f"/roadmap.html?project={world.a.id}")


@pytest.mark.plan("UI-06")
def test_no_failed_asset_requests_on_static_pages(page, anon_ui):
    anon_ui()
    bad = []
    page.on("response", lambda r: bad.append((r.url, r.status)) if r.status >= 400 and "unpkg" not in r.url else None)
    for p in ("/", "/donate.html"):
        page.goto(p)
        page.wait_for_load_state("networkidle")
    assert bad == []


# ------------------------------------------------------------------ UI-07
@pytest.mark.plan("UI-07")
@pytest.mark.security
def test_xss_in_user_name_is_escaped_in_header(page, login_ui, make_user):
    payload = "<img src=x onerror=window.__xss=1>"
    u = make_user(tag="uixssn_")
    ok(u.client.patch("/api/users/me", json={"full_name": payload}))
    login_ui(u)
    Dashboard(page).open()
    page.wait_for_timeout(400)
    assert page.evaluate("window.__xss") is None and not page.dialogs


@pytest.mark.plan("UI-07", "UI-04")
@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
def test_landing_login_handles_each_error_status(page, anon_ui, status):
    anon_ui()
    page.route("**/api/auth/login", lambda r: r.fulfill(status=status, content_type="application/json",
                                                         body='{"detail":"stubbed"}'))
    page.goto("/")
    page.locator("[data-open-auth='login']").first.click()
    page.fill("#login-email", "a@b.co")
    page.fill("#login-password", "whatever1")
    page.locator("#form-login button[type=submit]").click()
    expect(page.locator("#login-error")).to_contain_text("stubbed")
    assert not page.js_errors


@pytest.mark.plan("UI-04", "E2E-12")
def test_landing_login_malformed_json_offline_and_retry(page, anon_ui, make_user):
    u = make_user(tag="uiretry_")
    anon_ui()
    mode = {"m": "garbage"}

    def handler(route):
        if mode["m"] == "garbage":
            route.fulfill(status=200, content_type="application/json", body="{not json")
        elif mode["m"] == "offline":
            route.abort("failed")
        else:
            route.continue_()
    page.route("**/api/auth/login", handler)
    page.goto("/")
    page.locator("[data-open-auth='login']").first.click()
    page.fill("#login-email", u.email)
    page.fill("#login-password", u.password)
    btn = page.locator("#form-login button[type=submit]")
    for m in ("garbage", "offline"):
        mode["m"] = m
        btn.click()
        expect(page.locator("#login-error")).to_contain_text("Error")
        expect(btn).to_be_enabled()
        assert "/dashboard.html" not in page.url
    mode["m"] = "ok"
    btn.click()
    page.wait_for_url(re.compile(r"/dashboard\.html"))
