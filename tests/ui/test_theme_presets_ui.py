"""The six new presets in the browser (THEME-11)."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

NEW = {
    "lavender_light": ("Lavender Light", "light"),
    "violet_pop_light": ("Violet Pop Light", "light"),
    "navy_orange_light": ("Navy Orange Light", "light"),
    "mint_night": ("Mint Night", "dark"),
    "midnight_neon": ("Midnight Neon", "dark"),
    "fresh_lime_light": ("Fresh Lime Light", "light"),
}


def server_theme(client, key):
    return next(t for t in ok(client.get("/api/themes")).json() if t["key"] == key)


def css_var(page, name):
    return page.evaluate(f"document.documentElement.style.getPropertyValue('{name}').trim()")


def pick(page, label):
    page.goto("/dashboard.html")
    page.locator(".cabinet-btn").click()
    select = page.locator(".profile-modal [data-testid=theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)
    select.select_option(label=label)
    return select


@pytest.mark.plan("THEME-11")
def test_selector_lists_all_twelve_presets(page, login_ui, make_user):
    login_ui(make_user(tag="thu1_"))
    page.goto("/dashboard.html")
    page.locator(".cabinet-btn").click()
    select = page.locator(".profile-modal [data-testid=theme-select]")
    expect(select.locator("option", has_text="Nord")).to_have_count(1)
    labels = [o.strip() for o in select.locator("option").all_inner_texts()]
    for name, _ in NEW.values():
        assert name in labels, name
    assert len([x for x in labels if x]) >= 12


@pytest.mark.plan("THEME-11")
@pytest.mark.parametrize("key", list(NEW))
def test_picking_a_new_preset_applies_its_colors(page, login_ui, make_user, key):
    u = make_user(tag="thu2_")
    login_ui(u)
    name, mode = NEW[key]
    pick(page, name)
    expect(page.locator("html")).to_have_attribute("data-theme", key)
    colors = server_theme(u.client, key)["colors"]
    assert css_var(page, "--bg-0") == colors["background"]
    assert css_var(page, "--accent") == colors["accent"]
    assert css_var(page, "--text-1") == colors["text_primary"]
    assert page.evaluate("document.documentElement.style.colorScheme") == mode


@pytest.mark.plan("THEME-11")
@pytest.mark.parametrize("key", ["lavender_light", "midnight_neon"])
def test_new_preset_survives_reload_and_is_saved_on_the_server(page, login_ui, make_user, key):
    u = make_user(tag="thu3_")
    login_ui(u)
    pick(page, NEW[key][0])
    expect(page.locator("html")).to_have_attribute("data-theme", key)
    assert ok(u.client.get("/api/auth/me")).json()["theme_id"] == server_theme(u.client, key)["id"]
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", key)


@pytest.mark.plan("THEME-11")
def test_script_copy_of_every_preset_equals_the_server_copy(page, login_ui, make_user):
    """The presets live in two files (theme-engine.js and theme_presets.py): they must not drift apart."""
    u = make_user(tag="thu4_")
    login_ui(u)
    page.goto("/dashboard.html")
    js = {t["key"]: t for t in page.evaluate("ThemeEngine.list()")}
    server = {t["key"]: t for t in ok(u.client.get("/api/themes")).json() if t["is_preset"]}
    assert set(js) == set(server) and len(js) == 12
    for key, t in server.items():
        assert js[key]["name"] == t["name"], key
        assert js[key]["colors"] == t["colors"], key
        assert js[key]["shadows"] == t["shadows"], key


@pytest.mark.plan("THEME-11")
@pytest.mark.parametrize("key", ["navy_orange_light", "mint_night"])
def test_board_renders_in_a_new_preset_without_errors(page, login_ui, world, on_board, make_user, key):
    # a fresh user: picking a theme saves it on the user, and the shared role users must stay untouched
    u = make_user(tag="thu5_")
    world.a.add_member(u, "admin")
    login_ui(u)
    world.a.ticket(title="Themed ticket")
    pick(page, NEW[key][0])
    Board(page).open(world.a.id)
    expect(page.locator(".ticket-card", has_text="Themed ticket")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-theme", key)
    assert page.js_errors == []
