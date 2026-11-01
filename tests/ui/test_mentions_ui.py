"""@mentions in the editors: dropdown, picking, display of chips (MEN-03..05)."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import deactivate, ok
from pages.base import Board, pick_milestone

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

DLG = ".modal-backdrop.open .modal"


def open_ticket_page(page, key):
    page.goto(f"/ticket.html?key={key}")
    page.wait_for_selector(".tk-page-card, [data-testid=ticket-page-error]")
    expect(page.get_by_test_id("ticket-activity")).to_be_visible()
    return page


def menu(page):
    return page.get_by_test_id("mention-menu")


def items(page):
    return page.get_by_test_id("mention-item")


def api_comments(world, ticket):
    return ok(world.client("admin").get(f"/api/tickets/{ticket['id']}/comments")).json()


def description_of(world, ticket):
    return ok(world.a.c.get(f"/api/tickets/{ticket['id']}")).json()["description"]


def set_description(world, ticket, text):
    ok(world.a.c.patch(f"/api/tickets/{ticket['id']}", json={"description": text}))


def token(user, name=None):
    return f"@[{name or user.full_name}](user:{user.id})"


def flat(text):
    return " ".join(text.split())


def type_in_comment(page, text):
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type(text)


@pytest.fixture
def ticket(world, on_board):
    return world.a.ticket(title="Talk about people")


@pytest.fixture
def mates(world, make_user):
    """Two extra members with easy-to-filter names."""
    alpha = make_user(tag="alpha", full_name="Zephyr Alpha")
    beta = make_user(tag="beta", full_name="Zephyr Beta")
    world.a.add_member(alpha, "contributor")
    world.a.add_member(beta, "contributor")
    return alpha, beta


# ---------------------------------------------------------------- MEN-03 the dropdown
@pytest.mark.plan("MEN-03")
def test_at_sign_shows_the_members(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@")
    rows = ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()
    expect(items(page)).to_have_count(min(8, len(rows)))
    for name in ("QA Admin", "Zephyr Alpha", "Zephyr Beta"):
        expect(menu(page)).to_contain_text(name)


@pytest.mark.plan("MEN-03")
def test_letters_filter_the_list_and_backspace_widens_it(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr")
    expect(items(page)).to_have_count(2)
    page.keyboard.type(" a")
    expect(items(page)).to_have_count(1)
    expect(items(page).first).to_contain_text("Zephyr Alpha")
    page.keyboard.press("Backspace")
    page.keyboard.press("Backspace")
    expect(items(page)).to_have_count(2)


@pytest.mark.plan("MEN-03")
def test_one_letter_is_enough_and_any_word_of_the_name_counts(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@b")                                     # the second word of "Zephyr Beta"
    expect(items(page)).to_have_count(1)
    expect(items(page).first).to_contain_text("Zephyr Beta")


@pytest.mark.plan("MEN-03")
def test_nobody_fits_so_no_dropdown_and_the_text_stays_plain(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@qqq")
    expect(menu(page)).to_have_count(0)
    page.keyboard.type(" hi")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert api_comments(world, ticket)[0]["body"] == "@qqq hi"
    expect(page.get_by_test_id("comment-body").locator(".mention")).to_have_count(0)


@pytest.mark.plan("MEN-03")
def test_typing_on_without_choosing_makes_no_mention(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr alpha")
    expect(items(page)).to_have_count(1)
    page.keyboard.type("!")                                          # nobody is called "zephyr alpha!"
    expect(menu(page)).to_have_count(0)
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    body = api_comments(world, ticket)[0]["body"]
    assert body == "@zephyr alpha!" and "user:" not in body


@pytest.mark.plan("MEN-03")
def test_an_email_address_does_not_open_the_dropdown(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "write to me@zephyr")                      # an address, not a mention
    expect(menu(page)).to_have_count(0)


@pytest.mark.plan("MEN-03")
def test_removed_and_deactivated_members_are_not_offered(page, login_ui, world, ticket, mates, make_user):
    gone = make_user(tag="gone", full_name="Zephyr Gone")
    ghost = make_user(tag="ghost", full_name="Zephyr Ghost")
    world.a.add_member(gone, "contributor")
    world.a.add_member(ghost, "contributor")
    assert world.a.c.delete(f"/api/projects/{world.a.id}/members/{gone.id}").status_code == 204
    deactivate(ghost)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr")
    expect(items(page)).to_have_count(2)
    expect(menu(page)).not_to_contain_text("Gone")
    expect(menu(page)).not_to_contain_text("Ghost")


@pytest.mark.plan("MEN-03")
def test_esc_closes_only_the_dropdown_and_it_stays_closed(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    Board(page).open(world.a.id).ticket("Talk about people").click()
    dlg = page.locator(DLG)
    dlg.get_by_test_id("comment-editor").click()
    page.keyboard.type("@zephyr")
    expect(menu(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu(page)).to_have_count(0)
    expect(dlg).to_be_visible()                                      # the dialog was not closed
    page.keyboard.type(" a")                                         # would match again, but it was dismissed
    expect(menu(page)).to_have_count(0)


@pytest.mark.plan("MEN-03")
def test_dropdown_closes_when_the_editor_loses_focus(page, login_ui, world, ticket, mates):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr")
    expect(menu(page)).to_be_visible()
    page.get_by_test_id("activity-view").focus()
    expect(menu(page)).to_have_count(0)


# ---------------------------------------------------------------- MEN-04 picking
@pytest.mark.plan("MEN-04")
def test_arrow_keys_and_enter_pick_the_highlighted_member(page, login_ui, world, ticket, mates):
    alpha, beta = mates
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr")
    expect(items(page)).to_have_count(2)
    expect(items(page).first).to_have_class(re.compile(r"\bon\b"))
    page.keyboard.press("ArrowDown")
    expect(items(page).nth(1)).to_have_class(re.compile(r"\bon\b"))
    page.keyboard.press("Enter")
    chip = page.get_by_test_id("comment-editor").locator(".mention")
    expect(chip).to_have_text("@Zephyr Beta")
    expect(chip).to_have_attribute("contenteditable", "false")
    expect(menu(page)).to_have_count(0)
    page.keyboard.press("Control+Enter")
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert flat(api_comments(world, ticket)[0]["body"]) == token(beta)
    shown = page.get_by_test_id("comment-body").locator(".mention")
    expect(shown).to_have_text("@Zephyr Beta")
    expect(shown).not_to_have_class(re.compile("is-gone"))


@pytest.mark.plan("MEN-04")
def test_a_click_picks_the_member(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr a")
    items(page).first.click()
    expect(page.get_by_test_id("comment-editor").locator(".mention")).to_have_text("@Zephyr Alpha")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert flat(api_comments(world, ticket)[0]["body"]) == token(alpha)


@pytest.mark.plan("MEN-04")
def test_tab_picks_and_typing_goes_on_after_the_chip(page, login_ui, world, ticket, mates):
    _, beta = mates
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "Hi @zephyr b")
    page.keyboard.press("Tab")
    page.keyboard.type("please look")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert flat(api_comments(world, ticket)[0]["body"]) == f"Hi {token(beta)} please look"


@pytest.mark.plan("MEN-04")
def test_two_mentions_in_one_comment(page, login_ui, world, ticket, mates):
    alpha, beta = mates
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr a")
    page.keyboard.press("Enter")
    page.keyboard.type("and @zephyr b")
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("comment-editor").locator(".mention")).to_have_count(2)
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert flat(api_comments(world, ticket)[0]["body"]) == f"{token(alpha)} and {token(beta)}"


@pytest.mark.plan("MEN-04")
def test_mention_in_the_description_is_saved_as_markdown(page, login_ui, world, ticket, mates):
    _, beta = mates
    set_description(world, ticket, "Hi")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.locator(".desc-view").click()
    editor = page.get_by_test_id("desc-editor")
    editor.click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" @zephyr b")
    page.keyboard.press("Enter")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert flat(description_of(world, ticket)) == f"Hi {token(beta)}"
    page.reload()
    expect(page.locator(".desc-view .mention")).to_have_text("@Zephyr Beta")


@pytest.mark.plan("MEN-04")
def test_a_chip_survives_editing_the_rest_of_the_description(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    set_description(world, ticket, f"Hi {token(alpha)} there")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.locator(".desc-view").click()
    editor = page.get_by_test_id("desc-editor")
    expect(editor.locator(".mention")).to_have_text("@Zephyr Alpha")
    editor.click()
    page.keyboard.press("Control+End")
    page.keyboard.type("!")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert flat(description_of(world, ticket)) == f"Hi {token(alpha)} there!"


@pytest.mark.plan("MEN-04")
def test_mention_in_the_create_dialog(page, login_ui, world, on_board, mates):
    alpha, _ = mates
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(DLG)
    dlg.locator("input.input").first.fill("Born with a mention")
    pick_milestone(dlg, world.a.default_milestone["title"])
    dlg.get_by_test_id("desc-editor").click()
    page.keyboard.type("@zephyr a")
    page.keyboard.press("Enter")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(page.locator(".ticket-card", has_text="Born with a mention")).to_be_visible()
    got = [t for t in world.a.tickets() if t["title"] == "Born with a mention"]
    assert flat(got[0]["description"]) == token(alpha)


@pytest.mark.plan("MEN-04")
def test_mention_when_editing_a_comment(page, login_ui, world, ticket, mates):
    _, beta = mates
    ok(world.client("admin").post(f"/api/tickets/{ticket['id']}/comments", json={"body": "first"}), 201)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-edit").click()
    page.get_by_test_id("comment-edit-editor").click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" @zephyr b")
    page.keyboard.press("Enter")
    page.get_by_test_id("comment-edit-save").click()
    expect(page.get_by_test_id("comment-body").locator(".mention")).to_have_text("@Zephyr Beta")
    assert flat(api_comments(world, ticket)[0]["body"]) == f"first {token(beta)}"


@pytest.mark.plan("MEN-04")
def test_reporter_can_mention_too(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    type_in_comment(page, "@zephyr a")
    page.keyboard.press("Enter")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert flat(api_comments(world, ticket)[0]["body"]) == token(alpha)


# ---------------------------------------------------------------- MEN-05 chip display
@pytest.mark.plan("MEN-05")
def test_member_is_a_chip_not_a_link(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    set_description(world, ticket, f"Ask {token(alpha)} please")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    chip = page.locator(".desc-view .mention")
    expect(chip).to_have_text("@Zephyr Alpha")
    expect(chip).not_to_have_class(re.compile("is-gone"))
    expect(page.locator(".desc-view a")).to_have_count(0)


@pytest.mark.plan("MEN-05")
def test_removed_member_is_a_grey_disabled_chip(page, login_ui, world, ticket, make_user):
    guest = make_user(tag="leaver", full_name="Leaving Person")
    world.a.add_member(guest, "contributor")
    set_description(world, ticket, f"Was {token(guest)}")
    assert world.a.c.delete(f"/api/projects/{world.a.id}/members/{guest.id}").status_code == 204
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    chip = page.locator(".desc-view .mention")
    expect(chip).to_have_class(re.compile("is-gone"))
    expect(chip).to_have_attribute("data-gone", "(deactivated)")
    expect(chip).to_have_attribute("title", re.compile(r"\S"))
    expect(chip).to_have_css("cursor", "not-allowed")


@pytest.mark.plan("MEN-05")
def test_deactivated_member_and_unknown_user_are_grey_chips(page, login_ui, world, ticket, make_user):
    ghost = make_user(tag="ghost2", full_name="Quiet Ghost")
    world.a.add_member(ghost, "contributor")
    set_description(world, ticket, f"{token(ghost)} and @[Nobody](user:99999999)")
    deactivate(ghost)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    chips = page.locator(".desc-view .mention")
    expect(chips).to_have_count(2)
    for i in range(2):
        expect(chips.nth(i)).to_have_class(re.compile("is-gone"))


@pytest.mark.plan("MEN-05")
def test_chip_in_a_comment_follows_the_same_rule(page, login_ui, world, ticket, mates, make_user):
    alpha, _ = mates
    guest = make_user(tag="leaver2", full_name="Second Leaver")
    world.a.add_member(guest, "contributor")
    ok(world.client("admin").post(f"/api/tickets/{ticket['id']}/comments",
                                  json={"body": f"{token(alpha)} {token(guest)}"}), 201)
    assert world.a.c.delete(f"/api/projects/{world.a.id}/members/{guest.id}").status_code == 204
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    chips = page.get_by_test_id("comment-body").locator(".mention")
    expect(chips).to_have_count(2)
    expect(chips.nth(0)).not_to_have_class(re.compile("is-gone"))
    expect(chips.nth(1)).to_have_class(re.compile("is-gone"))


@pytest.mark.plan("MEN-05")
def test_a_name_with_html_is_shown_as_text(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    evil = "<img src=x onerror=alert(1)>"
    set_description(world, ticket, f"@[{evil}](user:{alpha.id})")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".desc-view .mention")).to_have_text(f"@{evil}")
    expect(page.locator(".desc-view img")).to_have_count(0)
    assert page.js_errors == []


@pytest.mark.plan("MEN-05")
def test_mention_in_a_code_span_stays_text(page, login_ui, world, ticket, mates):
    alpha, _ = mates
    set_description(world, ticket, f"`{token(alpha)}`")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".desc-view code")).to_have_text(token(alpha))
    expect(page.locator(".desc-view .mention")).to_have_count(0)
