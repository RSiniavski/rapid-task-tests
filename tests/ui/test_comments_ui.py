"""Comments and history in one section: dropdown, sorting, editor, permissions, history details (CMT-06..10)."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board
from tests.api.test_files import attach

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

DLG = ".modal-backdrop.open .modal"


def open_ticket_page(page, key):
    page.goto(f"/ticket.html?key={key}")
    page.wait_for_selector(".tk-page-card, [data-testid=ticket-page-error]")
    expect(page.get_by_test_id("ticket-activity")).to_be_visible()
    return page


def add_comment(client, ticket, body):
    return ok(client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": body}), 201).json()


def api_comments(world, ticket):
    return ok(world.client("admin").get(f"/api/tickets/{ticket['id']}/comments")).json()


def show_history(page):
    page.get_by_test_id("activity-view").select_option("history")


@pytest.fixture
def ticket(world, on_board):
    return world.a.ticket(title="Talk here")


# ---------------------------------------------------------------- CMT-06 the section
@pytest.mark.plan("CMT-06")
def test_one_section_with_a_dropdown_that_opens_on_comments(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "one")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    select = page.get_by_test_id("activity-view")
    assert select.input_value() == "comments"
    assert [o.strip() for o in select.locator("option").all_inner_texts()][0].startswith("Comments (1)")
    expect(page.get_by_test_id("ticket-comments")).to_be_visible()
    expect(page.get_by_test_id("ticket-history")).to_have_count(0)
    show_history(page)
    expect(page.get_by_test_id("ticket-history")).to_be_visible()
    expect(page.get_by_test_id("ticket-comments")).to_have_count(0)
    assert page.get_by_test_id("ticket-activity").count() == 1       # one section for both


@pytest.mark.plan("CMT-06")
def test_selected_view_and_order_are_remembered(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-order").select_option("desc")
    show_history(page)
    page.reload()
    expect(page.get_by_test_id("activity-view")).to_have_value("history")
    page.get_by_test_id("activity-view").select_option("comments")
    expect(page.get_by_test_id("comment-order")).to_have_value("desc")


@pytest.mark.plan("CMT-06")
def test_the_section_is_also_in_the_board_dialog(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "in the dialog")
    login_ui(world.roles.admin)
    Board(page).open(world.a.id).ticket("Talk here").click()
    dlg = page.locator(DLG)
    expect(dlg.get_by_test_id("ticket-activity")).to_be_visible()
    expect(dlg.get_by_test_id("comment-body")).to_have_text("in the dialog")


@pytest.mark.plan("CMT-06")
def test_empty_ticket_shows_the_empty_note(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comments-empty")).to_be_visible()


# ---------------------------------------------------------------- CMT-07 writing
@pytest.mark.plan("CMT-07")
def test_write_a_formatted_comment_with_a_ticket_card(page, login_ui, world, ticket):
    other = world.a.ticket(title="Referenced one")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-editor").click()
    page.keyboard.press("Control+B")
    page.keyboard.type("loud")
    page.keyboard.press("Control+B")
    page.keyboard.type(f" see {other['key']}")
    page.get_by_test_id("comment-send").click()
    body = page.get_by_test_id("comment-body")
    expect(body.locator("strong")).to_have_text("loud")
    expect(body.locator(".tk-card", has_text="Referenced one")).to_be_visible()
    assert api_comments(world, ticket)[0]["body"].startswith("**loud**")
    expect(page.get_by_test_id("comment-author")).to_have_text(world.roles.admin.full_name)
    expect(page.get_by_test_id("comment-send")).to_be_disabled()              # the editor was cleared


@pytest.mark.plan("CMT-07")
def test_blank_comment_cannot_be_sent(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comment-send")).to_be_disabled()
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type("   ")
    expect(page.get_by_test_id("comment-send")).to_be_disabled()
    assert api_comments(world, ticket) == []


@pytest.mark.plan("CMT-07")
def test_ctrl_enter_sends_the_comment(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type("sent by keyboard")
    page.keyboard.press("Control+Enter")
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert api_comments(world, ticket)[0]["body"] == "sent by keyboard"


@pytest.mark.plan("CMT-07")
def test_read_only_user_can_comment(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type("from a reporter")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert api_comments(world, ticket)[0]["author_id"] == world.roles.reporter.id


# ---------------------------------------------------------------- CMT-08 sorting
def authors_bodies(page):
    return page.get_by_test_id("comment-body").all_inner_texts()


@pytest.mark.plan("CMT-08")
def test_sorting_oldest_first_and_newest_first(page, login_ui, world, ticket):
    for text in ("first", "second", "third"):
        add_comment(world.client("admin"), ticket, text)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comment")).to_have_count(3)
    assert page.get_by_test_id("comment-order").input_value() == "asc"
    assert [t.strip() for t in authors_bodies(page)] == ["first", "second", "third"]
    page.get_by_test_id("comment-order").select_option("desc")
    expect(page.get_by_test_id("comment-body").first).to_have_text("third")
    assert [t.strip() for t in authors_bodies(page)] == ["third", "second", "first"]


@pytest.mark.plan("CMT-08")
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_the_editor_stays_above_the_comments_in_both_orders(page, login_ui, world, ticket, order):
    add_comment(world.client("admin"), ticket, "x")
    add_comment(world.client("admin"), ticket, "y")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-order").select_option(order)
    expect(page.get_by_test_id("comment").first).to_be_visible()
    editor_y = page.get_by_test_id("comment-editor").bounding_box()["y"]
    first_comment_y = page.get_by_test_id("comment").first.bounding_box()["y"]
    assert editor_y < first_comment_y


@pytest.mark.plan("CMT-08")
def test_a_new_comment_lands_in_the_right_place_for_the_order(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "old")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-order").select_option("desc")
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type("fresh")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(2)
    assert [t.strip() for t in authors_bodies(page)] == ["fresh", "old"]


# ---------------------------------------------------------------- CMT-09 edit and delete
@pytest.mark.plan("CMT-09")
def test_author_edits_the_comment_and_it_is_marked_edited(page, login_ui, world, ticket):
    add_comment(world.client("editor"), ticket, "draft")
    login_ui(world.roles.editor)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comment-edited")).to_have_count(0)
    page.get_by_test_id("comment-edit").click()
    page.get_by_test_id("comment-edit-editor").click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" final")
    page.get_by_test_id("comment-edit-save").click()
    expect(page.get_by_test_id("comment-edited")).to_be_visible()
    expect(page.get_by_test_id("comment-body")).to_have_text("draft final")
    assert api_comments(world, ticket)[0]["body"] == "draft final"


@pytest.mark.plan("CMT-09")
def test_nobody_gets_an_edit_button_on_a_foreign_comment(page, login_ui, world, ticket):
    add_comment(world.client("reporter"), ticket, "not yours")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comment")).to_have_count(1)
    expect(page.get_by_test_id("comment-edit")).to_have_count(0)
    expect(page.get_by_test_id("comment-delete")).to_have_count(1)          # an admin may delete it


@pytest.mark.plan("CMT-09")
def test_non_admin_cannot_delete_a_foreign_comment_but_can_delete_own(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "admin text")
    add_comment(world.client("editor"), ticket, "editor text")
    login_ui(world.roles.editor)
    open_ticket_page(page, ticket["key"])
    expect(page.get_by_test_id("comment")).to_have_count(2)
    expect(page.get_by_test_id("comment-delete")).to_have_count(1)
    page.get_by_test_id("comment-delete").click()                    # the page's default policy accepts confirm()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert [c["body"] for c in api_comments(world, ticket)] == ["admin text"]


@pytest.mark.plan("CMT-09")
def test_delete_asks_for_confirmation(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "keep me")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.dialog_policy = "dismiss"
    page.get_by_test_id("comment-delete").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    assert len(page.dialogs) == 1 and "comment" in page.dialogs[0].lower()
    assert len(api_comments(world, ticket)) == 1
    page.dialog_policy = "accept"
    page.get_by_test_id("comment-delete").click()
    expect(page.get_by_test_id("comment")).to_have_count(0)


@pytest.mark.plan("CMT-09")
def test_cancel_leaves_the_comment_unchanged(page, login_ui, world, ticket):
    add_comment(world.client("admin"), ticket, "as it was")
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-edit").click()
    page.get_by_test_id("comment-edit-editor").click()
    page.keyboard.type(" junk")
    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_test_id("comment-body")).to_have_text("as it was")
    assert api_comments(world, ticket)[0]["body"] == "as it was"


# ---------------------------------------------------------------- CMT-10 history
@pytest.mark.plan("CMT-10")
def test_comment_events_show_up_in_the_history(page, login_ui, world, ticket):
    c = add_comment(world.client("admin"), ticket, "tmp")
    ok(world.client("admin").patch(f"/api/comments/{c['id']}", json={"body": "tmp2"}))
    ok(world.client("admin").delete(f"/api/comments/{c['id']}"), 204)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    show_history(page)
    text = page.get_by_test_id("ticket-history").inner_text()
    for line in ("Comment added", "Comment edited", "Comment deleted"):
        assert line in text, text


@pytest.mark.plan("CMT-10")
def test_description_change_has_a_diff_with_added_and_removed_lines(page, login_ui, world, ticket):
    admin = world.client("admin")
    ok(admin.patch(f"/api/tickets/{ticket['id']}", json={"description": "keep\nold line"}))
    ok(admin.patch(f"/api/tickets/{ticket['id']}", json={"description": "keep\nnew line"}))
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    show_history(page)
    expect(page.get_by_test_id("history-diff")).to_have_count(0)               # closed by default
    toggles = page.get_by_test_id("history-diff-toggle")
    toggles.first.click()                                                      # the newest change
    diff = page.get_by_test_id("history-diff").first
    expect(diff.locator(".tk-diff-line.is-del")).to_contain_text("old line")
    expect(diff.locator(".tk-diff-line.is-add")).to_contain_text("new line")
    expect(diff.locator(".tk-diff-line.is-same")).to_contain_text("keep")
    toggles.first.click()
    expect(page.get_by_test_id("history-diff")).to_have_count(0)


@pytest.mark.plan("CMT-10")
def test_first_description_is_all_added_lines(page, login_ui, world, ticket):
    ok(world.client("admin").patch(f"/api/tickets/{ticket['id']}", json={"description": "line a\nline b"}))
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    show_history(page)
    page.get_by_test_id("history-diff-toggle").first.click()
    diff = page.get_by_test_id("history-diff").first
    expect(diff.locator(".tk-diff-line.is-add")).to_have_count(2)
    expect(diff.locator(".tk-diff-line.is-del")).to_have_count(0)


@pytest.mark.plan("CMT-10")
def test_files_and_sub_tickets_show_up_in_the_history(page, login_ui, world):
    epic = world.a.ticket(type="Epic", title="Big parent")
    child = world.a.ticket(title="Small kid", parent_id=epic["id"])
    a = ok(attach(world.client("admin"), world.a.id, name="notes.txt", ticket_id=epic["id"]), 201).json()
    login_ui(world.roles.admin)
    open_ticket_page(page, epic["key"])
    show_history(page)
    text = page.get_by_test_id("ticket-history").inner_text()
    assert "File added" in text and "notes.txt" in text, text
    assert "Sub-ticket added" in text and child["key"] in text, text
    link = page.get_by_test_id("ticket-history").get_by_role("link", name=child["key"])
    assert link.get_attribute("href") == f"/ticket.html?key={child['key']}"
    ok(world.client("admin").delete(f"/api/attachments/{a['id']}"), 204)
    page.reload()
    show_history(page)
    assert "File removed" in page.get_by_test_id("ticket-history").inner_text()


@pytest.mark.plan("CMT-10")
def test_creation_line_is_shown_as_ticket_created(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    show_history(page)
    expect(page.get_by_test_id("history-row").last).to_contain_text("Ticket created")


@pytest.mark.plan("CMT-10")
def test_writing_a_comment_adds_a_history_row_without_reloading(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-editor").click()
    page.keyboard.type("hello")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment")).to_have_count(1)
    show_history(page)
    expect(page.get_by_test_id("history-row").first).to_contain_text("Comment added")
