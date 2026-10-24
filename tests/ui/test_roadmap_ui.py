"""ROAD-FE: roadmap page (vanilla JS, no Vue needed)."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import iso, ok
from pages.base import Roadmap

pytestmark = [pytest.mark.ui]


@pytest.mark.plan("ROAD-FE", "UI-04")
def test_empty_roadmap_state_for_planner(page, login_ui, world):
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    expect(page.locator("#rm-empty")).to_be_visible()
    expect(page.locator("#rm-add")).to_be_visible()
    expect(page.locator("#rm-readonly")).to_be_hidden()
    expect(page.locator("#rm-project-key")).to_have_text(world.a.key)
    assert not page.js_errors


@pytest.mark.plan("ROAD-FE", "E2E-06")
def test_milestone_blocks_show_derived_progress_and_badges(page, login_ui, world):
    m1 = world.a.milestone(title="Alpha", due_date=iso(-2))
    m2 = world.a.milestone(title="Beta")
    t = world.a.ticket(milestone_id=m1["id"])
    world.a.ticket(milestone_id=m1["id"])
    world.a.move(t["id"], "Done")
    world.a.dependency(m1["id"], m2["id"])
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    expect(page.locator(".rm-block")).to_have_count(2)
    alpha, beta = r.block("Alpha"), r.block("Beta")
    expect(alpha.locator(".rm-progress-fill")).to_have_attribute("style", re.compile("width:\\s*50%"))
    expect(alpha.locator(".rm-badge-danger")).to_be_visible()                      # overdue -> critical
    expect(beta.locator(".rm-badge-blocked")).to_be_visible()
    expect(beta.locator(".rm-badge-warning")).to_be_visible()                      # upstream risk
    assert page.locator("#rm-links-layer [data-dep]").count() >= 1


@pytest.mark.plan("ROAD-FE", "E2E-06")
def test_create_milestone_through_modal_persists(page, login_ui, world):
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    page.locator("#rm-add").click()
    expect(page.locator("#rm-modal-backdrop")).to_have_class(re.compile("open"))
    page.fill("#rm-f-title", "Created in UI")
    page.fill("#rm-f-desc", "ui description")
    page.fill("#rm-f-start", iso(1))
    page.fill("#rm-f-due", iso(10))
    page.locator("#rm-form button[type=submit]").click()
    expect(r.block("Created in UI")).to_be_visible()
    row = world.a.roadmap()["milestones"][0]
    assert (row["title"], row["description"], row["start_date"], row["due_date"]) == (
        "Created in UI", "ui description", iso(1), iso(10))
    page.reload()
    expect(r.block("Created in UI")).to_be_visible()


@pytest.mark.plan("ROAD-FE")
def test_modal_validation_errors_leave_no_partial_state(page, login_ui, world):
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    page.locator("#rm-add").click()
    page.fill("#rm-f-title", "Bad dates")
    page.fill("#rm-f-start", iso(10))
    page.fill("#rm-f-due", iso(1))
    page.locator("#rm-form button[type=submit]").click()
    expect(page.locator("#rm-form-error")).to_be_visible()
    assert world.a.roadmap()["milestones"] == []


@pytest.mark.plan("ROAD-FE")
def test_edit_milestone_and_auto_managed_fields_locked(page, login_ui, world):
    m = world.a.milestone(title="Editable")
    auto = world.a.milestone(title="Automatic")
    world.a.ticket(milestone_id=auto["id"])
    login_ui(world.roles.editor)
    r = Roadmap(page).open(world.a.id)
    r.block("Editable").locator("[data-act=edit]").click()
    page.fill("#rm-f-title", "Edited title")
    page.locator("#rm-form button[type=submit]").click()
    expect(r.block("Edited title")).to_be_visible()
    assert world.a.milestone_row(m["id"])["title"] == "Edited title"
    r.block("Automatic").locator("[data-act=edit]").click()
    expect(page.locator("#rm-f-auto")).to_be_visible()
    expect(page.locator("#rm-f-progress")).to_be_disabled()
    expect(page.locator("#rm-f-status")).to_be_disabled()


@pytest.mark.plan("ROAD-FE")
def test_delete_milestone_with_confirmation(page, login_ui, world):
    m = world.a.milestone(title="Doomed")
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    r.block("Doomed").locator("[data-act=edit]").click()
    page.dialog_policy = "dismiss"
    page.locator("#rm-f-delete").click()
    assert page.dialogs and "Doomed" in page.dialogs[-1]
    assert world.a.milestone_row(m["id"])
    page.dialog_policy = "accept"
    page.locator("#rm-f-delete").click()
    expect(page.locator(".rm-block")).to_have_count(0)
    assert world.a.roadmap()["milestones"] == []


@pytest.mark.plan("ROAD-FE", "E2E-08")
@pytest.mark.parametrize("role", ["contributor", "reporter"])
def test_read_only_roles_cannot_plan(page, login_ui, world, role):
    world.a.milestone(title="Visible")
    login_ui(world.roles.by_name(role))
    r = Roadmap(page).open(world.a.id)
    expect(r.block("Visible")).to_be_visible()
    expect(page.locator("#rm-readonly")).to_be_visible()
    expect(page.locator("#rm-add")).to_be_hidden()
    expect(page.locator("#rm-auto-layout")).to_be_hidden()
    assert page.locator("[data-act=edit], .rm-handle").count() == 0


@pytest.mark.plan("ROAD-FE", "E2E-08", "UI-03")
def test_non_member_sees_denial_and_no_data(page, login_ui, world):
    world.a.milestone(title="secret-roadmap")
    login_ui(world.roles.outsider)
    page.goto(f"/roadmap.html?project={world.a.id}")
    expect(page.locator("#rm-error")).to_be_visible()
    assert "secret-roadmap" not in page.content() and page.locator(".rm-block").count() == 0


@pytest.mark.plan("UI-03", "ROAD-FE")
@pytest.mark.parametrize("query", ["", "?project=abc", "?project=9999999", "?project=%3Cb%3Ex%3C/b%3E"])
def test_bad_project_query_shows_error_not_crash(page, login_ui, world, query):
    login_ui(world.roles.admin)
    page.goto("/roadmap.html" + query)
    expect(page.locator("#rm-error")).to_be_visible()
    assert not page.js_errors


@pytest.mark.plan("ROAD-FE", "TICKET-14", "UI-07")
@pytest.mark.security
def test_milestone_and_ticket_text_escaped(page, login_ui, world):
    payload = "<img src=x onerror=window.__xss=1>"
    m = world.a.milestone(title=payload, description=payload)
    world.a.ticket(title=payload, milestone_id=m["id"])
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    page.wait_for_timeout(500)
    assert page.evaluate("window.__xss") is None and not page.dialogs


@pytest.mark.plan("ROAD-FE")
def test_zoom_controls_and_view_persistence(page, login_ui, world):
    world.a.milestone(title="Zoomable")
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    before = page.locator("#rm-zoom-label").inner_text()
    page.locator("#rm-zoom-in").click()
    assert page.locator("#rm-zoom-label").inner_text() != before
    page.locator("#rm-zoom-reset").click()
    expect(page.locator("#rm-zoom-label")).to_have_text("100%")
    page.locator("#rm-zoom-out").click()
    page.reload()
    page.wait_for_selector(".rm-block")
    assert page.locator("#rm-zoom-label").inner_text().endswith("%")           # view restored without errors
    assert not page.js_errors


@pytest.mark.plan("ROAD-FE")
def test_backlog_lists_unassigned_tickets_and_search_filters(page, login_ui, world):
    m = world.a.milestone(title="Holder")
    world.a.ticket(title="Assigned one", milestone_id=m["id"])
    world.a.ticket(title="Floating banana")
    world.a.ticket(title="Floating cherry")
    login_ui(world.roles.admin)
    Roadmap(page).open(world.a.id)
    if not page.locator("#rm-backlog").is_visible():
        page.locator("#rm-toggle-backlog").click()
    expect(page.locator("#rm-backlog-list .rm-chip")).to_have_count(2)
    page.fill("#rm-backlog-search", "banana")
    expect(page.locator("#rm-backlog-list .rm-chip")).to_have_count(1)


@pytest.mark.plan("ROAD-FE", "E2E-06")
@pytest.mark.slow
def test_drag_block_persists_layout(page, login_ui, world):
    m = world.a.milestone(title="Movable", pos_x=100, pos_y=100)
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    head = r.block("Movable").locator(".rm-block-head")
    box = head.bounding_box()
    page.mouse.move(box["x"] + 20, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 120, box["y"] + 90, steps=8)
    page.mouse.up()
    page.wait_for_timeout(1200)
    row = world.a.milestone_row(m["id"])
    assert (row["pos_x"], row["pos_y"]) != (100.0, 100.0)


@pytest.mark.plan("ROAD-FE", "E2E-06")
@pytest.mark.slow
def test_drag_handle_creates_dependency_and_cycle_is_refused(page, login_ui, world):
    a = world.a.milestone(title="From", pos_x=0, pos_y=0)
    b = world.a.milestone(title="To", pos_x=500, pos_y=0)
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)

    def link(src, dst):
        h = r.block(src).locator(".rm-handle").first.bounding_box()
        t = r.block(dst).bounding_box()
        page.mouse.move(h["x"] + h["width"] / 2, h["y"] + h["height"] / 2)
        page.mouse.down()
        page.mouse.move(t["x"] + t["width"] / 2, t["y"] + t["height"] / 2, steps=10)
        page.mouse.up()
        page.wait_for_timeout(800)
    link("From", "To")
    assert [(d["predecessor_id"], d["successor_id"]) for d in world.a.roadmap()["dependencies"]] == [(a["id"], b["id"])]
    link("To", "From")                                                            # would close a cycle
    assert len(world.a.roadmap()["dependencies"]) == 1
    assert not page.js_errors


@pytest.mark.plan("ROAD-FE", "UI-04", "E2E-12")
def test_roadmap_load_failure_then_recovery(page, login_ui, world):
    world.a.milestone(title="After retry")
    login_ui(world.roles.admin)
    state = {"fail": True}

    def flaky(route):
        route.fulfill(status=500, body="boom") if state["fail"] else route.continue_()
    page.route(re.compile(r".*/api/roadmap/project/\d+$"), flaky)
    page.goto(f"/roadmap.html?project={world.a.id}")
    expect(page.locator("#rm-error")).to_be_visible()
    state["fail"] = False
    page.reload()
    expect(page.locator(".rm-block", has_text="After retry")).to_be_visible()

@pytest.mark.plan("UI-03", "ROAD-FE")
def test_malformed_numeric_project_query_is_rejected(page, login_ui, world):
    world.a.milestone(title="must-not-open")
    login_ui(world.roles.admin)
    page.goto(f"/roadmap.html?project={world.a.id}abc")        # parseInt would read this as a valid id
    expect(page.locator("#rm-error")).to_be_visible()
    assert page.locator(".rm-block").count() == 0