"""Roadmap UI: close / reopen buttons and the "ready to close" badge (ROAD-FE-CLOSE)."""
import pytest
from playwright.sync_api import expect

from pages.base import Roadmap

pytestmark = [pytest.mark.ui]


def ready(world, title):
    m = world.a.milestone(title=title)
    t = world.a.ticket(milestone_id=m["id"])
    world.a.move(t["id"], "Done")
    return m


@pytest.mark.plan("ROAD-FE-CLOSE")
def test_ready_milestone_shows_badge_and_admin_closes_it(page, login_ui, world):
    m = ready(world, "Finished work")
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    expect(r.block("Finished work").locator(".rm-badge-ready")).to_be_visible()
    page.dialog_policy = "dismiss"
    r.block("Finished work").locator("[data-act=close]").click()
    assert page.dialogs and "Finished work" in page.dialogs[-1]
    assert world.a.milestone_row(m["id"])["is_closed"] is False                 # confirmation dismissed
    page.dialog_policy = "accept"
    r.block("Finished work").locator("[data-act=close]").click()
    expect(r.block("Finished work").locator("[data-act=reopen]")).to_be_visible()
    expect(r.block("Finished work").locator(".rm-badge-ready")).to_have_count(0)
    row = world.a.milestone_row(m["id"])
    assert (row["is_closed"], row["status"]) == (True, "done")
    assert not page.js_errors


@pytest.mark.plan("ROAD-FE-CLOSE")
def test_admin_reopens_a_closed_milestone(page, login_ui, world):
    m = world.a.milestone(title="Was closed", status="done")
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    page.dialog_policy = "accept"
    r.block("Was closed").locator("[data-act=reopen]").click()
    expect(r.block("Was closed").locator("[data-act=reopen]")).to_have_count(0)
    row = world.a.milestone_row(m["id"])
    assert (row["is_closed"], row["status"]) == (False, "planned")


@pytest.mark.plan("ROAD-FE-CLOSE")
def test_milestone_with_unfinished_tickets_has_no_close_button(page, login_ui, world):
    m = world.a.milestone(title="Still working")
    world.a.ticket(milestone_id=m["id"])
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    expect(r.block("Still working")).to_be_visible()
    expect(r.block("Still working").locator("[data-act=close]")).to_have_count(0)
    expect(r.block("Still working").locator(".rm-badge-ready")).to_have_count(0)


@pytest.mark.plan("ROAD-FE-CLOSE")
@pytest.mark.parametrize("role", ["editor", "contributor", "reporter"])
def test_only_admin_sees_close_and_reopen_buttons(page, login_ui, world, role):
    ready(world, "Ready one")
    world.a.milestone(title="Closed one", status="done")
    login_ui(world.roles.by_name(role))
    r = Roadmap(page).open(world.a.id)
    expect(r.block("Ready one")).to_be_visible()
    assert page.locator("[data-act=close], [data-act=reopen]").count() == 0


@pytest.mark.plan("ROAD-FE-CLOSE")
def test_closed_milestone_edit_dialog_locks_status_and_progress(page, login_ui, world):
    world.a.milestone(title="Locked one", status="done")
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    r.block("Locked one").locator("[data-act=edit]").click()
    expect(page.locator("#rm-f-status")).to_be_disabled()
    expect(page.locator("#rm-f-progress")).to_be_disabled()
    expect(page.locator("#rm-f-auto")).to_be_visible()
    page.fill("#rm-f-title", "Locked one renamed")                      # a title edit still saves
    page.locator("#rm-form button[type=submit]").click()
    expect(r.block("Locked one renamed")).to_be_visible()
