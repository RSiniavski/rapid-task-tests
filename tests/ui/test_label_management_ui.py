"""Project settings, Labels tab: rename, delete with confirm, counts, admin-only (LBL-12)."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


def make(world, kind, name):
    r = world.a.c.post(f"/api/projects/{world.a.id}/{kind}", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def open_labels(page, world, user, login_ui):
    login_ui(user)
    page.goto("/dashboard.html")
    page.locator(".project-card", has_text=world.a.data["name"]).get_by_role("button", name="Settings").click()
    modal = page.locator(".modal-backdrop.open .modal")
    page.get_by_test_id("settings-tab-labels").click()
    expect(page.get_by_test_id("labels-tab")).to_be_visible()
    return modal


@pytest.mark.plan("LBL-12")
def test_tab_lists_tags_and_components_with_counts(page, login_ui, world):
    tag = make(world, "tags", "urgent")
    comp = make(world, "components", "backend")
    world.a.ticket(tag_ids=[tag["id"]], component_ids=[comp["id"]])
    world.a.ticket(tag_ids=[tag["id"]])
    open_labels(page, world, world.roles.admin, login_ui)
    expect(page.get_by_test_id(f"label-name-tag-{tag['id']}")).to_have_value("urgent")
    expect(page.get_by_test_id(f"label-count-tag-{tag['id']}")).to_have_text("2")
    expect(page.get_by_test_id(f"label-name-component-{comp['id']}")).to_have_value("backend")
    expect(page.get_by_test_id(f"label-count-component-{comp['id']}")).to_have_text("1")
    assert not page.js_errors


@pytest.mark.plan("LBL-12")
def test_empty_lists_show_a_hint(page, login_ui, world):
    open_labels(page, world, world.roles.admin, login_ui)
    expect(page.get_by_test_id("labels-empty-tag")).to_be_visible()
    expect(page.get_by_test_id("labels-empty-component")).to_be_visible()


@pytest.mark.plan("LBL-12")
def test_rename_is_saved_and_survives_reload(page, login_ui, world):
    tag = make(world, "tags", "old")
    world.a.ticket(tag_ids=[tag["id"]])
    open_labels(page, world, world.roles.admin, login_ui)
    field = page.get_by_test_id(f"label-name-tag-{tag['id']}")
    field.fill("fresh")
    field.press("Tab")
    page.wait_for_timeout(300)
    got = ok(world.a.c.get(f"/api/projects/{world.a.id}/tags")).json()
    assert [x["name"] for x in got] == ["fresh"]
    open_labels(page, world, world.roles.admin, login_ui)
    expect(page.get_by_test_id(f"label-name-tag-{tag['id']}")).to_have_value("fresh")


@pytest.mark.plan("LBL-12")
def test_duplicate_name_shows_error_and_restores_the_old_name(page, login_ui, world):
    a = make(world, "tags", "Bug")
    make(world, "tags", "Other")
    open_labels(page, world, world.roles.admin, login_ui)
    field = page.get_by_test_id(f"label-name-tag-{a['id']}")
    field.fill("other")
    field.press("Tab")
    expect(page.get_by_test_id("label-error")).to_be_visible()
    expect(field).to_have_value("Bug")


@pytest.mark.plan("LBL-12")
def test_empty_name_shows_error_and_restores_the_old_name(page, login_ui, world):
    a = make(world, "components", "keep")
    open_labels(page, world, world.roles.admin, login_ui)
    field = page.get_by_test_id(f"label-name-component-{a['id']}")
    field.fill("   ")
    field.press("Tab")
    expect(page.get_by_test_id("label-error")).to_be_visible()
    expect(field).to_have_value("keep")


@pytest.mark.plan("LBL-12")
def test_delete_asks_to_confirm_and_removes_the_label_from_tickets(page, login_ui, world):
    tag = make(world, "tags", "doomed")
    t = world.a.ticket(tag_ids=[tag["id"]])
    open_labels(page, world, world.roles.admin, login_ui)
    page.get_by_test_id(f"label-del-tag-{tag['id']}").click()
    assert len(page.dialogs) == 1
    assert "doomed" in page.dialogs[0] and "1" in page.dialogs[0]
    expect(page.get_by_test_id(f"label-row-tag-{tag['id']}")).to_have_count(0)
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["tags"] == []


@pytest.mark.plan("LBL-12")
def test_delete_cancelled_keeps_the_label(page, login_ui, world):
    comp = make(world, "components", "stay")
    open_labels(page, world, world.roles.admin, login_ui)
    page.dialog_policy = "dismiss"
    page.get_by_test_id(f"label-del-component-{comp['id']}").click()
    assert len(page.dialogs) == 1
    expect(page.get_by_test_id(f"label-row-component-{comp['id']}")).to_have_count(1)
    assert len(ok(world.a.c.get(f"/api/projects/{world.a.id}/components")).json()) == 1


@pytest.mark.plan("LBL-12")
@pytest.mark.parametrize("role", ["editor", "contributor", "reporter"])
def test_non_admin_sees_labels_but_cannot_change_them(page, login_ui, world, role):
    tag = make(world, "tags", "readonly")
    open_labels(page, world, world.roles.by_name(role), login_ui)
    field = page.get_by_test_id(f"label-name-tag-{tag['id']}")
    expect(field).to_have_value("readonly")
    expect(field).to_be_disabled()
    expect(page.get_by_test_id(f"label-del-tag-{tag['id']}")).to_have_count(0)


@pytest.mark.plan("LBL-12")
def test_renamed_label_shows_new_name_on_the_board_filter(page, login_ui, world):
    tag = make(world, "tags", "before")
    m = world.a.milestone()
    world.a.ticket(title="Tagged", tag_ids=[tag["id"]], milestone_id=m["id"])
    open_labels(page, world, world.roles.admin, login_ui)
    field = page.get_by_test_id(f"label-name-tag-{tag['id']}")
    field.fill("after")
    field.press("Tab")
    page.wait_for_timeout(300)
    page.goto(f"/board.html?project={world.a.id}")
    page.wait_for_selector(".ticket-card")
    expect(page.locator(".ticket-card", has_text="Tagged")).to_contain_text("after")
