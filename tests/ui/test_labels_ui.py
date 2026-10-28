"""Tags/components on the board (UI): picker, pending chips, cards, filters, initials avatars."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board, pick_milestone

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue, pytest.mark.usefixtures("on_board")]

DLG = ".modal-backdrop.open .modal"


def open_create(page, milestone="Board milestone"):
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(DLG)
    pick_milestone(dlg, milestone)       # a ticket without a milestone would not be on the board
    return dlg


def picker(scope, testid):
    """The data-testid sits on the <input>; return the whole .label-picker around it."""
    return scope.locator(f".label-picker:has(input[data-testid={testid}])")


def add_name(pk, text):
    pk.locator(".lp-input").fill(text)
    pk.locator(".lp-input").press("Enter")


def pick(pk, name):
    pk.locator(".lp-input").click()
    pk.locator(".lp-list li", has_text=name).first.click()


def api_tags(world, kind="tags"):
    return [x["name"] for x in ok(world.a.c.get(f"/api/projects/{world.a.id}/{kind}")).json()]


def show_filters(page):
    page.locator("[data-testid=filter-toggle]").click()
    expect(page.locator("input[data-testid=filter-tags]")).to_be_visible()


# =================================================================== LBL-06
@pytest.mark.plan("LBL-06")
def test_new_names_are_created_only_when_the_ticket_is_saved(page, login_ui, world):
    login_ui(world.roles.reporter)
    b = Board(page).open(world.a.id)
    dlg = open_create(page)
    dlg.locator("input.input").first.fill("With labels")
    add_name(picker(dlg, "create-tags"), "frontend")
    add_name(picker(dlg, "create-components"), "Checkout")
    expect(picker(dlg, "create-tags").locator(".lp-new")).to_have_count(1)
    assert api_tags(world) == [] and api_tags(world, "components") == []      # nothing yet
    dlg.get_by_role("button", name="Create ticket").click()
    expect(b.ticket("With labels")).to_be_visible()
    assert api_tags(world) == ["frontend"] and api_tags(world, "components") == ["Checkout"]
    expect(b.ticket("With labels").locator(".mini-chip", has_text="frontend")).to_be_visible()
    expect(b.ticket("With labels").locator(".mini-chip", has_text="Checkout")).to_be_visible()


@pytest.mark.plan("LBL-06")
def test_removing_a_pending_chip_never_creates_the_label(page, login_ui, world):
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    dlg = open_create(page)
    dlg.locator("input.input").first.fill("No trash")
    pk = picker(dlg, "create-tags")
    add_name(pk, "typo-tag")
    pk.locator(".lp-new .lp-x").click()
    expect(pk.locator(".lp-new")).to_have_count(0)
    dlg.get_by_role("button", name="Create ticket").click()
    expect(b.ticket("No trash")).to_be_visible()
    assert api_tags(world) == []


@pytest.mark.plan("LBL-06")
def test_cancelled_dialog_creates_no_labels(page, login_ui, world):
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    dlg = open_create(page)
    add_name(picker(dlg, "create-tags"), "abandoned")
    page.keyboard.press("Escape")
    page.reload()
    assert api_tags(world) == []


@pytest.mark.plan("LBL-06")
def test_existing_label_is_suggested_and_selected(page, login_ui, world):
    existing = ok(world.a.c.post(f"/api/projects/{world.a.id}/tags", json={"name": "backend"}), 201).json()
    login_ui(world.roles.contributor)
    b = Board(page).open(world.a.id)
    dlg = open_create(page)
    dlg.locator("input.input").first.fill("Picked")
    pk = picker(dlg, "create-tags")
    pk.locator(".lp-input").fill("back")
    pk.locator(".lp-list li", has_text="backend").first.click()
    dlg.get_by_role("button", name="Create ticket").click()
    expect(b.ticket("Picked").locator(".mini-chip", has_text="backend")).to_be_visible()
    t = ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()[0]
    assert [x["id"] for x in t["tags"]] == [existing["id"]]


@pytest.mark.plan("LBL-06")
def test_edit_dialog_changes_labels_and_they_survive_reload(page, login_ui, world):
    t = world.a.ticket(title="Editable")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("Editable").click()
    dlg = page.locator(DLG)
    add_name(picker(dlg, "edit-tags"), "urgent")
    add_name(picker(dlg, "edit-components"), "API")
    dlg.get_by_role("button", name="Save").click()
    expect(b.ticket("Editable").locator(".mini-chip", has_text="urgent")).to_be_visible()
    page.reload()
    expect(b.ticket("Editable").locator(".mini-chip", has_text="API")).to_be_visible()
    got = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert [x["name"] for x in got["tags"]] == ["urgent"] and [x["name"] for x in got["components"]] == ["API"]


@pytest.mark.plan("LBL-06")
def test_ticket_without_labels_shows_no_chips(page, login_ui, world):
    world.a.ticket(title="Plain")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    expect(b.ticket("Plain")).to_be_visible()
    expect(b.ticket("Plain").locator(".mini-chip")).to_have_count(0)


# =================================================================== LBL-07
def labelled_tickets(world):
    tag = ok(world.a.c.post(f"/api/projects/{world.a.id}/tags", json={"name": "alpha"}), 201).json()
    world.a.ticket(title="Has alpha", tag_ids=[tag["id"]])
    world.a.ticket(title="Has nothing")
    return tag


@pytest.mark.plan("LBL-07")
def test_tag_filter_narrows_the_board_and_reset_restores_it(page, login_ui, world):
    labelled_tickets(world)
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    show_filters(page)
    pick(picker(page, "filter-tags"), "alpha")
    expect(b.ticket("Has alpha")).to_be_visible()
    expect(page.locator(".ticket-card", has_text="Has nothing")).to_have_count(0)
    page.locator("[data-testid=filter-reset]").click()
    expect(b.ticket("Has nothing")).to_be_visible()


@pytest.mark.plan("LBL-07")
def test_filter_choice_is_remembered_per_project_after_reload(page, login_ui, world):
    tag = labelled_tickets(world)
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    show_filters(page)
    pick(picker(page, "filter-tags"), "alpha")
    expect(page.locator(".ticket-card", has_text="Has nothing")).to_have_count(0)
    assert str(tag["id"]) in page.evaluate(f"localStorage.getItem('rt_board_filters_{world.a.id}')")
    page.reload()
    expect(page.locator(".ticket-card", has_text="Has alpha")).to_be_visible()
    expect(page.locator(".ticket-card", has_text="Has nothing")).to_have_count(0)
    # another project is not affected
    assert page.evaluate(f"localStorage.getItem('rt_board_filters_{world.b.id}')") is None


@pytest.mark.plan("LBL-07")
def test_assignee_avatar_filters_the_board_and_toggles_off(page, login_ui, world):
    world.a.ticket(title="Mine", assignee_id=world.roles.editor.id)
    world.a.ticket(title="Not mine")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    strip = page.locator("[data-testid=assignee-filter]")
    expect(strip.locator(".as-btn")).to_have_count(1)          # only users who have tickets on the board
    strip.locator(".as-btn").click()
    expect(page.locator(".ticket-card", has_text="Not mine")).to_have_count(0)
    expect(b.ticket("Mine")).to_be_visible()
    strip.locator(".as-btn").click()
    expect(b.ticket("Not mine")).to_be_visible()


@pytest.mark.plan("LBL-07")
def test_extra_filters_are_hidden_until_the_toggle_is_used(page, login_ui, world):
    world.a.ticket(title="Assigned", assignee_id=world.roles.editor.id)
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    expect(page.locator("[data-testid=assignee-filter]")).to_be_visible()
    expect(picker(page, "filter-tags")).to_have_count(0)
    show_filters(page)
    page.locator("[data-testid=filter-toggle]").click()
    expect(picker(page, "filter-tags")).to_have_count(0)


# =================================================================== LBL-08
@pytest.mark.plan("LBL-08")
def test_user_without_photo_gets_initials_avatar_on_the_card(page, login_ui, world, make_user):
    u = make_user(tag="ini_", full_name="Mike Tyson")
    world.a.add_member(u, "contributor")
    world.a.ticket(title="Has owner", assignee_id=u.id)
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    av = b.ticket("Has owner").locator(".avatar-initials").first
    expect(av).to_have_text("MT")
    expect(av).to_have_class(__import__("re").compile(rf"avatar-c{u.id % 5}\b"))
    assert not page.js_errors


@pytest.mark.plan("LBL-08")
def test_single_name_gives_one_letter_and_initials_are_uppercase(page, login_ui, world, make_user):
    u = make_user(tag="ini2_", full_name="madonna")
    world.a.add_member(u, "contributor")
    world.a.ticket(title="One name", assignee_id=u.id)
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    expect(b.ticket("One name").locator(".avatar-initials").first).to_have_text("M")