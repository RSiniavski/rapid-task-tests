"""Markdown in ticket descriptions: safe display, ticket cards, WYSIWYG editor (MD-01..05)."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


def open_ticket_page(page, key):
    page.goto(f"/ticket.html?key={key}")
    page.wait_for_selector(".tk-page-card, [data-testid=ticket-page-error]")
    return page


def set_description(world, ticket, text):
    ok(world.a.c.patch(f"/api/tickets/{ticket['id']}", json={"description": text}))


def description_of(world, ticket):
    return ok(world.a.c.get(f"/api/tickets/{ticket['id']}")).json()["description"]


@pytest.fixture
def ticket(world, on_board):
    return world.a.ticket(title="Markdown ticket")


FULL = (
    "# Big title\n\n**bold** and *slanted* and ~~gone~~\n\n- one\n- two\n\n- [ ] open task\n- [x] done task\n\n"
    "> a quote\n\n`inline code`\n\n| head | other |\n|---|---|\n| cell | value |\n\n[site](https://example.com)"
)


# ---------------------------------------------------------------- MD-01 display
@pytest.mark.plan("MD-01")
def test_description_is_shown_as_formatted_markdown(page, login_ui, world, ticket):
    set_description(world, ticket, FULL)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    view = page.locator(".desc-view")
    expect(view.locator("h1")).to_have_text("Big title")
    expect(view.locator("strong")).to_have_text("bold")
    expect(view.locator("em")).to_have_text("slanted")
    expect(view.locator("del")).to_have_text("gone")
    expect(view.locator("li", has_text="two")).to_be_visible()
    boxes = view.locator("input[type=checkbox]")
    expect(boxes).to_have_count(2)
    expect(boxes.first).to_be_disabled()
    expect(boxes.first).not_to_be_checked()
    expect(boxes.nth(1)).to_be_checked()
    expect(view.locator("blockquote")).to_have_text("a quote")
    expect(view.locator("code")).to_have_text("inline code")
    expect(view.locator("td", has_text="value")).to_be_visible()
    link = view.locator("a[href='https://example.com']")
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in link.get_attribute("rel")


# ---------------------------------------------------------------- MD-02 safety
@pytest.mark.plan("MD-02")
def test_dangerous_markdown_is_not_executed_or_shown(page, login_ui, world, ticket):
    set_description(world, ticket,
                    '<script>window.__xss=1</script><img src=x onerror="window.__xss=2">\n\n'
                    "[bad](javascript:window.__xss=3)\n\n![ext](https://evil.example/pixel.png)\n\nvisible text")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    view = page.locator(".desc-view")
    expect(view).to_contain_text("visible text")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__xss") is None
    expect(view.locator("script")).to_have_count(0)
    expect(view.locator("img")).to_have_count(0)
    expect(view.locator("a[href^='javascript']")).to_have_count(0)


# ---------------------------------------------------------------- MD-03 ticket cards
@pytest.mark.plan("MD-03")
def test_ticket_key_in_text_becomes_a_card(page, login_ui, world, ticket):
    other = world.a.ticket(title="Linked target")
    world.a.move(other["id"], "In Progress")
    set_description(world, ticket, f"see {other['key']} and unknown NOPE-999 here")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    card = page.locator(".desc-view .tk-card", has_text=other["key"]).first
    expect(card).to_contain_text("Linked target")
    expect(card.locator(".tk-card-status")).to_contain_text("In Progress")
    assert card.get_attribute("href") == f"/ticket.html?key={other['key']}"
    expect(page.locator(".desc-view .tk-card", has_text="NOPE-999")).to_have_count(0)
    expect(page.locator(".desc-view")).to_contain_text("NOPE-999")
    card.click()
    page.wait_for_url(f"**/ticket.html?key={other['key']}")


@pytest.mark.plan("MD-03")
def test_link_with_own_words_keeps_the_words(page, login_ui, world, ticket):
    other = world.a.ticket(title="Hidden title")
    set_description(world, ticket, f"[look here]({other['key']})")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    link = page.locator(".desc-view a", has_text="look here")
    expect(link).to_be_visible()
    assert link.get_attribute("href") == f"/ticket.html?key={other['key']}"
    expect(link).not_to_contain_text("Hidden title")


# ---------------------------------------------------------------- MD-04 editor
def open_editor(page, world, ticket, role=None):
    open_ticket_page(page, ticket["key"])
    page.locator(".desc-view").click()
    editor = page.get_by_test_id("desc-editor")
    expect(editor).to_be_visible()
    return editor


@pytest.mark.plan("MD-04")
def test_bold_hotkey_formats_and_is_saved_as_markdown(page, login_ui, world, ticket):
    set_description(world, ticket, "hello")
    login_ui(world.roles.admin)
    editor = open_editor(page, world, ticket)
    page.keyboard.press("Control+A")
    page.keyboard.press("Control+B")
    expect(editor.locator("strong, b")).to_have_text("hello")          # formatted at once
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert description_of(world, ticket) == "**hello**"


@pytest.mark.plan("MD-04")
def test_toolbar_buttons_format_the_text(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    editor = open_editor(page, world, ticket)
    page.get_by_test_id("desc-editor-box").locator("[data-cmd=ul]").click()
    page.keyboard.type("item")
    expect(editor.locator("ul li")).to_have_text("item")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert description_of(world, ticket) == "- item"


@pytest.mark.plan("MD-04")
def test_typing_markdown_shortcuts_and_tab_nesting_survive_saving(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    editor = open_editor(page, world, ticket)
    page.keyboard.type("- first\nsecond")
    page.keyboard.press("Tab")                                         # second becomes a sub item
    expect(editor.locator("ul ul li")).to_have_text("second")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert description_of(world, ticket) == "- first\n    - second"
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".desc-view ul ul li")).to_have_text("second")   # still nested after reopening


@pytest.mark.plan("MD-04")
def test_task_checkbox_is_saved_as_markdown(page, login_ui, world, ticket):
    set_description(world, ticket, "- [ ] to do")
    login_ui(world.roles.admin)
    editor = open_editor(page, world, ticket)
    editor.locator("input[type=checkbox]").click()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert description_of(world, ticket) == "- [x] to do"


# ---------------------------------------------------------------- MD-05 permissions
@pytest.mark.plan("MD-05")
def test_read_only_user_cannot_open_the_editor(page, login_ui, world, ticket):
    set_description(world, ticket, "**locked** text")
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".desc-view strong")).to_have_text("locked")
    page.locator(".desc-view").click()
    expect(page.get_by_test_id("desc-editor")).to_have_count(0)


@pytest.mark.plan("MD-05")
def test_create_dialog_has_the_editor_and_saves_markdown(page, login_ui, world, on_board):
    from pages.base import Board, pick_milestone
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator("input.input").first.fill("With markdown")
    pick_milestone(dlg, world.a.default_milestone["title"])
    editor = dlg.get_by_test_id("desc-editor")
    editor.click()
    page.keyboard.press("Control+B")
    page.keyboard.type("strong")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(page.locator(".ticket-card", has_text="With markdown")).to_be_visible()
    got = [t for t in world.a.tickets() if t["title"] == "With markdown"]
    assert got[0]["description"] == "**strong**"
