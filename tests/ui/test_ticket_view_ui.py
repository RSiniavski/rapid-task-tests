"""Ticket view: two-column dialogs, history, breadcrumb links, full page (TKV-01..05)."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board, Roadmap

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

DLG = ".modal-backdrop.open .modal"


def open_ticket_page(page, key):
    page.goto(f"/ticket.html?key={key}")
    page.wait_for_selector(".tk-page-card, [data-testid=ticket-page-error]")
    return page


@pytest.fixture
def ticket(world, on_board):
    return world.a.ticket(title="Two columns")


def columns_of(page, scope):
    """x position of the content column and of the fields column."""
    main = page.locator(f"{scope} .tk-main").bounding_box()
    side = page.locator(f"{scope} .tk-side").bounding_box()
    return main, side


# ---------------------------------------------------------------- TKV-01 layout
@pytest.mark.plan("TKV-01")
def test_edit_dialog_has_content_left_and_fields_right(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("Two columns").click()
    dlg = page.locator(DLG)
    expect(dlg.locator(".tk-main")).to_be_visible()
    main, side = columns_of(page, DLG)
    assert main["x"] < side["x"] and abs(main["y"] - side["y"]) < 40
    expect(dlg.locator(".tk-main input.input").first).to_have_value("Two columns")
    expect(dlg.locator(".tk-main textarea, .tk-main .desc-view").first).to_be_visible()
    fields = dlg.get_by_test_id("ticket-fields")
    for name in ("Type", "Status", "Milestone", "Assignee", "Tester", "Author", "Tags", "Components"):
        expect(fields.locator("label", has_text=name).first).to_be_visible()


@pytest.mark.plan("TKV-01")
def test_create_dialog_has_two_columns_too(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(DLG)
    expect(dlg.locator(".tk-side")).to_be_visible()
    main, side = columns_of(page, DLG)
    assert main["x"] < side["x"]
    fields = dlg.get_by_test_id("ticket-fields")
    for name in ("Type", "Parent", "Milestone", "Assignee", "Tester", "Tags", "Components"):
        expect(fields.locator("label", has_text=name).first).to_be_visible()
    expect(dlg.get_by_role("button", name="Create ticket")).to_be_visible()


@pytest.mark.plan("TKV-01")
def test_narrow_screen_puts_fields_first_in_one_column(page, login_ui, world, ticket):
    page.set_viewport_size({"width": 560, "height": 900})
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.locator(".ticket-card", has_text="Two columns").first.click()
    main, side = columns_of(page, DLG)
    assert side["y"] < main["y"]
    assert abs(side["x"] - main["x"]) < 5


@pytest.mark.plan("TKV-01")
def test_quick_subtask_enter_does_not_save_the_ticket(page, login_ui, world, ticket):
    epic = world.a.ticket(type="Epic", title="Parent epic")
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.locator(".ticket-card", has_text="Parent epic").first.click()
    dlg = page.locator(DLG)
    dlg.locator(".quick-add-row input").fill("typed child")
    dlg.locator(".quick-add-row input").press("Enter")
    expect(page.locator(DLG)).to_be_visible()                  # still open: Enter did not submit the form
    kids = [t["title"] for t in ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()
            if t["parent_id"] == epic["id"]]
    assert kids == ["typed child"]


# ---------------------------------------------------------------- TKV-02 history
@pytest.mark.plan("TKV-02")
def test_history_lists_changes_newest_first_with_names(page, login_ui, world, ticket):
    t = ticket
    world.a.move(t["id"], "In Progress")
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"assignee_id": world.roles.editor.id}))
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"description": "secret text of the description"}))
    login_ui(world.roles.admin)
    open_ticket_page(page, t["key"])
    rows = page.get_by_test_id("history-row")
    expect(rows.first).to_contain_text("Description")               # the newest change is on top
    expect(rows.first).not_to_contain_text("secret text")           # only "changed" is shown
    text = page.get_by_test_id("ticket-history").inner_text()
    assert "Assignee" in text and world.roles.editor.full_name in text
    assert "In Progress" in text


@pytest.mark.plan("TKV-02")
def test_history_shows_first_ten_and_show_all(page, login_ui, world, ticket):
    for i in range(12):
        ok(world.a.c.patch(f"/api/tickets/{ticket['id']}", json={"title": f"Title {i}"}))
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("history-row")).to_have_count(10)
    page.get_by_test_id("history-more").click()
    expect(page.get_by_test_id("history-row")).to_have_count(13)   # 12 edits + the creation line
    expect(page.get_by_test_id("history-more")).to_have_count(0)


@pytest.mark.plan("TKV-02")
def test_read_only_user_sees_the_history_too(page, login_ui, world, ticket):
    world.a.move(ticket["id"], "In Progress")
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("history-row").first).to_be_visible()


# ---------------------------------------------------------------- TKV-03 breadcrumbs
@pytest.mark.plan("TKV-03")
def test_crumbs_are_real_links_to_the_ticket_pages(page, login_ui, world, on_board):
    epic = world.a.ticket(type="Epic", title="Top")
    child = world.a.ticket(title="Kid", parent_id=epic["id"])
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.locator(".ticket-card", has_text="Kid").first.click()
    dlg = page.locator(DLG)
    parent = dlg.get_by_test_id(f"crumb-{epic['key']}")
    assert parent.get_attribute("href") == f"/ticket.html?key={epic['key']}"
    assert dlg.get_by_test_id("ticket-link").get_attribute("href") == f"/ticket.html?key={child['key']}"
    expect(dlg.get_by_role("link", name="Open as page")).to_have_count(0)


@pytest.mark.plan("TKV-03")
def test_plain_click_on_parent_crumb_opens_the_parent_in_the_same_dialog(page, login_ui, world, on_board):
    epic = world.a.ticket(type="Epic", title="Top")
    world.a.ticket(title="Kid", parent_id=epic["id"])
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.locator(".ticket-card", has_text="Kid").first.click()
    dlg = page.locator(DLG)
    dlg.get_by_test_id(f"crumb-{epic['key']}").click()
    expect(dlg.locator(".tk-main input.input").first).to_have_value("Top")
    assert "/board.html" in page.url


@pytest.mark.plan("TKV-03")
def test_modified_click_on_a_crumb_opens_a_new_tab_with_that_ticket(page, login_ui, world, on_board):
    epic = world.a.ticket(type="Epic", title="Top")
    world.a.ticket(title="Kid", parent_id=epic["id"])
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.locator(".ticket-card", has_text="Kid").first.click()
    with page.context.expect_page() as popup:
        page.locator(DLG).get_by_test_id(f"crumb-{epic['key']}").click(modifiers=["Control"])
    new = popup.value
    new.wait_for_load_state()
    assert re.search(rf"/ticket\.html\?key={epic['key']}$", new.url)
    expect(new.locator(".tk-page-card .tk-main input.input").first).to_have_value("Top")


# ---------------------------------------------------------------- TKV-04 ticket page
@pytest.mark.plan("TKV-04")
def test_page_shows_the_ticket_and_project_links(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".tk-page-card .tk-main input.input").first).to_have_value("Two columns")
    assert page.get_by_test_id("tp-to-board").get_attribute("href") == f"/board.html?project={world.a.id}"
    assert page.get_by_test_id("tp-to-backlog").get_attribute("href") == f"/backlog.html?project={world.a.id}"
    assert page.get_by_test_id("tp-to-roadmap").get_attribute("href") == f"/roadmap.html?project={world.a.id}"
    assert not page.js_errors


@pytest.mark.plan("TKV-04")
def test_page_save_stays_on_the_page_and_shows_saved(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    field = page.locator(".tk-page-card .tk-main input.input").first
    field.fill("Renamed on page")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("ticket-saved")).to_be_visible()
    assert "/ticket.html" in page.url
    assert ok(world.a.c.get(f"/api/tickets/{ticket['id']}")).json()["title"] == "Renamed on page"
    expect(page.get_by_test_id("history-row").first).to_contain_text("Title")


@pytest.mark.plan("TKV-04")
def test_page_delete_goes_back_to_the_board(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_role("button", name="Delete").click()
    page.wait_for_url(re.compile(rf"/board\.html\?project={world.a.id}"))
    assert world.a.c.get(f"/api/tickets/{ticket['id']}").status_code == 404


@pytest.mark.plan("TKV-04")
@pytest.mark.parametrize("key", ["abc", "ZZ-99999", "<b>-1"])
def test_page_with_a_bad_key_shows_an_error(page, login_ui, world, key):
    login_ui(world.roles.admin)
    page.goto("/ticket.html?key=" + key)
    expect(page.get_by_test_id("ticket-page-error")).to_be_visible()
    assert not page.locator(".tk-page-card").count()


@pytest.mark.plan("TKV-04")
def test_page_of_a_foreign_project_is_refused(page, login_ui, world, ticket):
    login_ui(world.roles.outsider)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("ticket-page-error")).to_be_visible()
    expect(page.get_by_text("Two columns")).to_have_count(0)


@pytest.mark.plan("TKV-04")
def test_page_without_login_goes_to_the_landing_page(page, anon_ui, world, ticket):
    anon_ui()
    page.goto(f"/ticket.html?key={ticket['key']}")
    page.wait_for_url(re.compile(r"/(index\.html)?$"))


@pytest.mark.plan("TKV-04")
def test_read_only_user_cannot_save_on_the_page(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    expect(page.locator(".tk-page-card .tk-main input.input").first).to_be_disabled()
    expect(page.get_by_role("button", name="Save")).to_have_count(0)


# ---------------------------------------------------------------- TKV-05 roadmap
@pytest.mark.plan("TKV-05")
def test_roadmap_backlog_chip_opens_the_ticket_dialog(page, login_ui, world):
    t = world.a.ticket(title="Loose chip")             # no milestone: listed in the Roadmap backlog
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    if not page.locator("#rm-backlog").is_visible():
        page.locator("#rm-toggle-backlog").click()
    page.locator("#rm-backlog-list .rm-chip", has_text="Loose chip").click()
    expect(page.locator(DLG).locator(".crumb.self")).to_contain_text(t["key"])
