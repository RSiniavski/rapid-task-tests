"""MOD-01, MOD-02: a dialog closes on a click on the dark background only when the mouse button
goes down AND up on the background. Selecting text in a field and letting go outside keeps it open."""
import pytest
from playwright.sync_api import expect

from pages.base import Board, Dashboard, Landing

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

OPEN = ".modal-backdrop.open"
SURFACES = ["landing-login", "board-create-ticket", "dashboard-settings"]


@pytest.fixture
def dialog(request, page):
    """dialog(surface) -> a text field inside the open dialog (the dialog is open and the field has some text)."""
    def _open(surface):
        if surface == "landing-login":
            request.getfixturevalue("anon_ui")()
            Landing(page).open().open_login()
            field = page.locator("#login-email")
        elif surface == "board-create-ticket":
            request.getfixturevalue("on_board")
            world = request.getfixturevalue("world")
            request.getfixturevalue("login_ui")(world.roles.reporter)
            Board(page).open(world.a.id)
            page.get_by_role("button", name="＋ New ticket").click()
            field = page.locator(f"{OPEN} .modal input.input").first
        else:
            world = request.getfixturevalue("world")
            request.getfixturevalue("login_ui")(world.roles.admin)
            Dashboard(page).open().card(world.a.data["name"]).get_by_role("button", name="Settings").click()
            field = page.get_by_placeholder("Column name")
        expect(page.locator(OPEN)).to_have_count(1)
        field.fill("some words to select")
        return field
    return _open


def middle(locator):
    box = locator.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


@pytest.mark.plan("MOD-01")
@pytest.mark.parametrize("surface", SURFACES)
def test_selecting_text_and_letting_go_outside_keeps_the_dialog_open(page, dialog, surface):
    field = dialog(surface)
    x, y = middle(field)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 5, y)                                   # a few pixels: the text gets selected
    page.mouse.move(3, 3, steps=8)                              # the pointer leaves the dialog
    page.mouse.up()                                             # ... and the button goes up on the dark background
    page.wait_for_timeout(300)                                  # a wrong close would happen at once, give it a moment
    expect(page.locator(OPEN)).to_have_count(1)
    expect(field).to_have_value("some words to select")
    assert not page.js_errors


@pytest.mark.plan("MOD-02")
@pytest.mark.parametrize("surface", SURFACES)
def test_a_real_click_on_the_background_still_closes_the_dialog(page, dialog, surface):
    dialog(surface)
    page.mouse.click(3, 3)
    expect(page.locator(OPEN)).to_have_count(0)
    assert not page.js_errors


@pytest.mark.plan("MOD-02")
@pytest.mark.parametrize("surface", SURFACES)
def test_pressing_on_the_background_and_letting_go_inside_keeps_the_dialog_open(page, dialog, surface):
    field = dialog(surface)
    x, y = middle(field)
    page.mouse.move(3, 3)
    page.mouse.down()
    page.mouse.move(x, y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(300)
    expect(page.locator(OPEN)).to_have_count(1)
    assert not page.js_errors
