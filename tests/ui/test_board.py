"""TICKET-FE, FILE-FE (board flow), UI-03 route handling, TICKET-14 (UI XSS)."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import PNG_BYTES, ok
from pages.base import Board, pick_milestone

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue, pytest.mark.usefixtures("on_board")]


@pytest.mark.plan("TICKET-FE")
def test_board_renders_columns_tickets_and_counts(page, login_ui, world):
    t = world.a.ticket(title="Rendered ticket")
    world.a.move(t["id"], "In Progress")
    login_ui(world.roles.reporter)
    b = Board(page).open(world.a.id)
    assert page.locator(".kanban-col").count() == 8
    expect(b.column("In Progress").locator(".kanban-count")).to_have_text("1")
    expect(b.ticket("Rendered ticket")).to_contain_text(t["key"])
    expect(page.locator(".badge", has_text="Reporter")).to_be_visible()
    assert not page.js_errors


@pytest.mark.plan("TICKET-FE", "E2E-03")
def test_create_ticket_via_dialog(page, login_ui, world):
    login_ui(world.roles.reporter)
    b = Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator("input.input").first.fill("Created from UI")
    dlg.locator("select").first.select_option("Bug")
    dlg.locator("textarea").fill("some description")
    pick_milestone(dlg, world.a.default_milestone["title"])
    dlg.get_by_role("button", name="Create ticket").click()
    expect(b.ticket("Created from UI")).to_be_visible()
    got = ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()
    assert [(t["title"], t["type"], t["reporter"]["id"]) for t in got] == [("Created from UI", "Bug", world.roles.reporter.id)]


@pytest.mark.plan("TICKET-FE")
def test_create_ticket_with_blank_title_is_blocked(page, login_ui, world):
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    page.locator(".modal-backdrop.open").get_by_role("button", name="Create ticket").click()
    assert ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json() == []


@pytest.mark.plan("TICKET-FE", "E2E-04")
def test_create_with_subtasks_assignee_and_hierarchy(page, login_ui, world):
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator("input.input").first.fill("Parent epic")
    dlg.locator("select").first.select_option("Epic")
    dlg.get_by_role("button", name="＋ Add subtask").click()
    dlg.locator(".subtask-title").first.fill("child one")
    pick_milestone(dlg, world.a.default_milestone["title"])
    dlg.get_by_role("button", name="Create ticket").click()
    expect(b.ticket("child one")).to_be_visible()
    tickets = {t["title"]: t for t in ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()}
    assert tickets["child one"]["parent_id"] == tickets["Parent epic"]["id"]


@pytest.mark.plan("TICKET-FE")
def test_open_edit_save_changes_persist(page, login_ui, world):
    t = world.a.ticket(title="Old title")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("Old title").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator("input.input").first.fill("New title")
    dlg.get_by_test_id("ticket-fields").locator("select").nth(1).select_option(label="In Progress")
    dlg.get_by_role("button", name="Save").click()
    expect(b.ticket("New title")).to_be_visible()
    got = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert got["title"] == "New title" and got["column_id"] == world.a.columns["In Progress"]
    page.reload()
    expect(b.column("In Progress").locator(".ticket-card", has_text="New title")).to_be_visible()


@pytest.mark.plan("TICKET-FE", "E2E-03")
@pytest.mark.parametrize("role,which,editable,deletable", [
    ("contributor", "own", True, False), ("contributor", "other", False, False),
    ("editor", "other", True, False), ("reporter", "other", False, False), ("admin", "other", True, True)])
def test_permission_matrix_visible_in_edit_dialog(page, login_ui, world, role, which, editable, deletable):
    world.a.ticket(client=world.roles.contributor.client, title="Contributor own")
    world.a.ticket(title="Admin owned")
    title = "Contributor own" if which == "own" else "Admin owned"
    login_ui(world.roles.by_name(role))
    b = Board(page).open(world.a.id)
    b.ticket(title).click()
    dlg = page.locator(".modal-backdrop.open .modal")
    # the dialog loads its data after it opens: wait until the ticket itself is shown
    expect(dlg.locator(".crumb.self")).to_be_visible()
    assert (dlg.get_by_role("button", name="Save").count() == 1) is editable
    assert (dlg.get_by_role("button", name="Delete").count() == 1) is deletable
    if not editable:
        expect(dlg.get_by_text("You don't have permission to edit this ticket")).to_be_visible()


@pytest.mark.plan("TICKET-FE", "E2E-03")
def test_admin_deletes_ticket_from_dialog(page, login_ui, world):
    t = world.a.ticket(title="To delete")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("To delete").click()
    page.locator(".modal-backdrop.open").get_by_role("button", name="Delete").click()
    expect(page.get_by_text("To delete")).to_have_count(0)
    assert world.a.c.get(f"/api/tickets/{t['id']}").status_code == 404


@pytest.mark.plan("TICKET-FE", "E2E-04")
def test_quick_subtask_from_edit_dialog(page, login_ui, world):
    t = world.a.ticket(type="Epic", title="Quick parent")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("Quick parent").click()
    dlg = page.locator(".modal-backdrop.open .modal")
    dlg.locator(".quick-add-row input").fill("quick child")
    dlg.locator(".quick-add-row .btn").click()
    page.wait_for_timeout(600)
    kids = [x for x in ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json() if x["parent_id"] == t["id"]]
    assert [k["title"] for k in kids] == ["quick child"]


@pytest.mark.plan("TICKET-FE", "E2E-05")
@pytest.mark.slow
def test_drag_and_drop_moves_ticket_to_neighbouring_column_and_persists(page, login_ui, world):
    t = world.a.ticket(title="Drag me")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    src = b.ticket("Drag me")
    dst = b.column("ToDo")                                     # adjacent column is always inside the viewport
    sb, db_ = src.bounding_box(), dst.bounding_box()
    page.mouse.move(sb["x"] + 20, sb["y"] + 20)
    page.mouse.down()
    for step in range(1, 13):                                  # Sortable needs intermediate moves
        page.mouse.move(sb["x"] + 20 + (db_["x"] + db_["width"] / 2 - sb["x"] - 20) * step / 12,
                        sb["y"] + 20 + (db_["y"] + 80 - sb["y"] - 20) * step / 12)
    page.mouse.up()
    page.wait_for_timeout(1000)
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["column_id"] == world.a.columns["ToDo"]
    page.reload()
    expect(b.column("ToDo").locator(".ticket-card", has_text="Drag me")).to_be_visible()


@pytest.mark.plan("FILE-FE", "E2E-04")
def test_attach_file_in_edit_dialog(page, login_ui, world, tmp_path):
    t = world.a.ticket(title="With file")
    f = tmp_path / "pic.png"
    f.write_bytes(PNG_BYTES)
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    b.ticket("With file").click()
    with page.expect_file_chooser() as fc:
        page.locator(".modal-backdrop.open").get_by_role("button", name="📎 Attach file").click()
    fc.value.set_files(str(f))
    expect(page.locator(".modal-backdrop.open .attach-thumb")).to_have_count(1)
    got = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert [a["filename"] for a in got["attachments"]] == ["pic.png"]


@pytest.mark.plan("UI-03")
@pytest.mark.parametrize("query", ["", "?project=", "?project=abc", "?project=99999999", "?project=-1",
                                   "?project=%3Cimg%20src=x%20onerror=window.__xss=1%3E"])
def test_board_bad_project_query_fails_gracefully(page, login_ui, world, query):
    login_ui(world.roles.admin)
    page.goto("/board.html" + query)
    page.wait_for_timeout(800)
    assert page.evaluate("window.__xss") is None
    assert not page.js_errors
    assert page.locator(".kanban-col").count() == 0


@pytest.mark.plan("UI-03")
def test_board_malformed_numeric_query_is_rejected(page, login_ui, world):
    login_ui(world.roles.admin)
    page.goto(f"/board.html?project={world.a.id}%27%20OR%201=1")
    page.wait_for_timeout(800)
    assert page.locator(".kanban-col").count() == 0


@pytest.mark.plan("UI-03", "E2E-08")
def test_non_member_direct_board_url_shows_denial(page, login_ui, world):
    login_ui(world.roles.outsider)
    page.goto(f"/board.html?project={world.a.id}")
    expect(page.locator(".card", has_text="⚠️")).to_be_visible()
    assert page.locator(".kanban-col").count() == 0
    assert world.a.data["name"] not in page.content()


@pytest.mark.plan("TICKET-14", "UI-07")
@pytest.mark.security
def test_ticket_text_is_escaped_on_board_and_in_description(page, login_ui, world):
    payload = "<img src=x onerror=window.__xss=1>"
    t = world.a.ticket(title=payload, description=f"{payload}<script>window.__xss=2</script>")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    expect(page.locator(".ticket-title", has_text=payload)).to_be_visible()
    b.ticket(t["key"]).click()
    page.wait_for_timeout(500)
    assert page.evaluate("window.__xss") is None and not page.dialogs and not page.js_errors


@pytest.mark.plan("UI-04", "E2E-12")
def test_board_load_500_and_recovery(page, login_ui, world):
    login_ui(world.roles.admin)
    state = {"fail": True}

    def flaky(route):
        if state["fail"]:
            route.fulfill(status=500, body="boom")
        else:
            route.continue_()
    page.route(re.compile(r".*/api/projects/\d+$"), flaky)
    page.goto(f"/board.html?project={world.a.id}")
    expect(page.locator(".card", has_text="⚠️")).to_be_visible()
    state["fail"] = False
    page.reload()
    expect(page.locator(".kanban-col").first).to_be_visible()
