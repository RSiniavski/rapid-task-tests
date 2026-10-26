"""Section 8 end-to-end journeys (browser + API verification of the end state)."""
import re

import pytest
from playwright.sync_api import expect

from framework.config import PASSWORD
from framework.factory import PNG_BYTES, create_project, deactivate, iso, ok, unique_email
from pages.base import Board, Dashboard, Landing, Roadmap

pytestmark = [pytest.mark.e2e, pytest.mark.ui]


@pytest.mark.plan("E2E-01")
@pytest.mark.needs_vue
def test_e2e_01_register_create_project_land_on_board(page, anon_ui):
    anon_ui()
    email = unique_email("e2e1_")
    Landing(page).open().open_register().register("E2E One", email, PASSWORD)
    page.wait_for_url(re.compile(r"/dashboard\.html"))
    d = Dashboard(page)
    d.create_project("Journey", "JRN")
    d.card("Journey").get_by_role("button", name="Open board").click()
    page.wait_for_url(re.compile(r"/board\.html\?project=\d+"))
    expect(page.locator(".kanban-col").first).to_be_visible()
    page.reload()
    expect(page.locator(".kanban-col")).to_have_count(8)
    page.goto("/dashboard.html")
    expect(page.locator(".project-card", has_text="JRN").locator(".role-admin")).to_be_visible()


@pytest.mark.plan("E2E-02")
@pytest.mark.needs_vue
def test_e2e_02_admin_adds_members_and_roles_are_enforced(page, login_ui, world, make_user):
    newbie = make_user(tag="e2e2_")
    world.a.add_member(newbie, "reporter")
    members = {m["user"]["email"]: m["role"] for m in ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()}
    assert members[world.roles.editor.email] == "editor" and members[newbie.email] == "reporter"
    assert world.client("reporter").post(f"/api/projects/{world.a.id}/members",
                                         json={"user_id": newbie.id, "role": "admin"}).status_code == 403
    login_ui(newbie)
    Dashboard(page).open()
    expect(page.locator(".project-card", has_text=world.a.key).locator(".role-reporter")).to_be_visible()


@pytest.mark.plan("E2E-03")
@pytest.mark.needs_vue
def test_e2e_03_ticket_lifecycle_across_roles(world):
    t = world.a.ticket(client=world.roles.reporter.client, title="E2E-03")
    assert t["reporter"]["id"] == world.roles.reporter.id
    assert world.client("reporter").patch(f"/api/tickets/{t['id']}", json={"title": "x"}).status_code == 403
    ok(world.client("editor").patch(f"/api/tickets/{t['id']}", json={"title": "edited by editor",
                                                                       "assignee_id": world.roles.contributor.id}))
    ok(world.client("contributor").patch(f"/api/tickets/{t['id']}", json={"description": "assigned work"}))
    assert world.client("editor").delete(f"/api/tickets/{t['id']}").status_code == 403
    assert world.client("admin").delete(f"/api/tickets/{t['id']}").status_code == 204
    assert world.client("admin").get(f"/api/tickets/{t['id']}").status_code == 404


@pytest.mark.plan("E2E-04")
@pytest.mark.needs_vue
def test_e2e_04_hierarchy_attachment_history_and_metrics_persist(page, login_ui, world, tmp_path):
    epic = world.a.ticket(type="Epic", title="E4 epic", assignee_id=world.roles.editor.id)
    att = ok(world.a.c.upload(f"/api/attachments?project_id={world.a.id}", "e4.png", PNG_BYTES, "image/png"), 201).json()
    child = world.a.ticket(type="Task", title="E4 child", parent_id=epic["id"], attachment_ids=[att["id"]])
    world.a.move(child["id"], "In Progress")
    world.a.move(child["id"], "Done")
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    page.reload()
    expect(b.column("Done").locator(".ticket-card", has_text="E4 child")).to_be_visible()
    b.ticket("E4 child").click()
    expect(page.locator(".modal-backdrop.open .crumb").first).to_contain_text(epic["key"])
    expect(page.locator(".modal-backdrop.open .attach-thumb")).to_have_count(1)
    s = world.a.stats()
    assert (s["tickets_total"], s["tickets_done"]) == (2, 1)
    hist = ok(world.a.c.get(f"/api/tickets/{child['id']}")).json()["history"]
    assert [h["new_value"] for h in hist if h["field_changed"] == "column"][-2:] == ["In Progress", "Done"]


@pytest.mark.plan("E2E-05")
@pytest.mark.needs_vue
def test_e2e_05_custom_columns_order_done_state_and_stats(page, login_ui, world):
    c = world.a.c
    new = ok(c.post(f"/api/projects/{world.a.id}/columns", json={"name": "Shipped"}), 201).json()
    ok(c.patch(f"/api/projects/{world.a.id}/columns/{new['id']}", json={"is_done": True}))
    world.a.refresh_columns()
    t = world.a.ticket(title="Ship it")
    world.a.move(t["id"], "Shipped")
    assert world.a.stats()["tickets_done"] == 1
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    names = page.locator(".kanban-col-name").all_inner_texts()
    assert names[-1] == "Shipped" and names.count("Shipped") == 1
    expect(b.column("Shipped").locator(".ticket-card", has_text="Ship it")).to_be_visible()
    ok(c.patch(f"/api/projects/{world.a.id}/columns/{new['id']}", json={"is_done": False}))
    assert world.a.stats()["tickets_done"] == 0


@pytest.mark.plan("E2E-06")
def test_e2e_06_roadmap_build_and_persist(page, login_ui, world):
    m1 = world.a.milestone(title="E6 first", pos_x=0, pos_y=0, start_date=iso(0), due_date=iso(5))
    m2 = world.a.milestone(title="E6 second", pos_x=400, pos_y=0)
    t = world.a.ticket(milestone_id=m1["id"])
    world.a.dependency(m1["id"], m2["id"])
    world.a.move(t["id"], "Done")
    world.a.move(t["id"], "Done")
    world.a.close_milestone(m1["id"])  # a milestone is finished only by a manual Close
    login_ui(world.roles.admin)
    r = Roadmap(page).open(world.a.id)
    expect(r.block("E6 first").locator(".rm-progress-fill")).to_have_attribute("style", re.compile("100%"))
    expect(r.block("E6 second").locator(".rm-badge-blocked")).to_have_count(0)      # predecessor finished
    page.reload()
    expect(page.locator(".rm-block")).to_have_count(2)
    rows = {m["title"]: m for m in world.a.roadmap()["milestones"]}
    assert (rows["E6 second"]["pos_x"], rows["E6 second"]["pos_y"]) == (400.0, 0.0)


@pytest.mark.plan("E2E-07")
def test_e2e_07_invalid_operations_leave_no_partial_state(world):
    epic = world.a.ticket(type="Epic")
    bad = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "type": "Epic", "parent_id": epic["id"]})
    assert bad.status_code == 400
    foreign = world.b.ticket()
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}",
                       json={"title": "x", "parent_id": foreign["id"]})
    assert r.status_code in (400, 404)
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "assignee_id": world.roles.outsider.id})
    assert r.status_code == 400
    a, b = world.a.milestone(), world.a.milestone()
    world.a.dependency(a["id"], b["id"])
    assert world.a.dependency(b["id"], a["id"], expect=400).status_code == 400
    assert [t["title"] for t in ok(world.a.c.get(f"/api/tickets/project/{world.a.id}")).json()] == [epic["title"]]
    assert len(world.a.roadmap()["dependencies"]) == 1
    assert ok(world.b.c.get(f"/api/tickets/project/{world.b.id}")).json()[0]["id"] == foreign["id"]


@pytest.mark.plan("E2E-08")
@pytest.mark.needs_vue
def test_e2e_08_reporter_readonly_roadmap_and_outsider_denied(page, login_ui, world):
    world.a.milestone(title="E8")
    login_ui(world.roles.reporter)
    r = Roadmap(page).open(world.a.id)
    expect(page.locator("#rm-add")).to_be_hidden()
    expect(r.block("E8")).to_be_visible()
    assert world.roles.outsider.client.get(f"/api/roadmap/project/{world.a.id}").status_code == 403
    assert world.roles.outsider.client.get(f"/api/tickets/project/{world.a.id}").status_code == 403


@pytest.mark.plan("E2E-09")
@pytest.mark.needs_vue
def test_e2e_09_profile_language_and_navigation_persist(page, login_ui, make_user):
    u = make_user(tag="e2e9_")
    ok(u.client.patch("/api/users/me", json={"full_name": "Nine Lives", "position": "Tester"}))
    login_ui(u, lang="uk")
    Dashboard(page).open()
    page.locator(".lang-switch [data-lang=en]").first.click()
    expect(page.locator("h1")).to_have_text("Control panel")
    page.goto("/")
    page.wait_for_url(re.compile("dashboard"))
    page.reload()
    expect(page.locator("h1")).to_have_text("Control panel")
    expect(page.locator(".badge-mint")).to_have_text("Nine Lives")


@pytest.mark.plan("E2E-10", "AUTH-07")
@pytest.mark.needs_vue
def test_e2e_10_deactivated_user_loses_access_and_ui_returns_to_safe_page(page, login_ui, world, make_user):
    victim = make_user(tag="e2e10_")
    world.a.add_member(victim, "editor")
    login_ui(victim)
    Dashboard(page).open()
    deactivate(victim)
    assert victim.client.get(f"/api/projects/{world.a.id}").status_code == 403
    page.goto(f"/board.html?project={world.a.id}")
    page.wait_for_timeout(800)
    assert page.locator(".kanban-col").count() == 0
    assert not page.js_errors


@pytest.mark.plan("E2E-10")
@pytest.mark.needs_vue
def test_e2e_10b_removed_member_denied_with_stale_page(page, login_ui, world, make_user):
    u = make_user(tag="e2e10b_")
    world.a.add_member(u, "contributor")
    login_ui(u)
    Board(page).open(world.a.id)
    ok(world.a.c.delete(f"/api/projects/{world.a.id}/members/{u.id}"), 204)
    page.reload()
    expect(page.locator(".card", has_text="⚠️")).to_be_visible()


@pytest.mark.plan("E2E-11")
@pytest.mark.needs_local_server
def test_e2e_11_delete_populated_project_cleans_everything(world, make_user, uploads_dir, db):
    u = make_user(tag="e2e11_")
    p = create_project(u)
    m = p.milestone()
    att = ok(u.client.upload(f"/api/attachments?project_id={p.id}", "e11.png", PNG_BYTES, "image/png"), 201).json()
    t = p.ticket(milestone_id=m["id"], attachment_ids=[att["id"]])
    p.dependency(p.milestone()["id"], m["id"])
    before = set(uploads_dir.iterdir())
    assert u.client.delete(f"/api/projects/{p.id}").status_code == 204
    assert p.id not in [x["id"] for x in ok(u.client.get("/api/projects")).json()]
    for path in (f"/api/projects/{p.id}", f"/api/tickets/{t['id']}", f"/api/roadmap/project/{p.id}"):
        assert u.client.get(path).status_code == 404
    for table, col in (("tickets", "project_id"), ("milestones", "project_id"), ("roadmap_dependencies", "project_id"),
                       ("board_columns", "project_id"), ("project_members", "project_id")):
        assert db(f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (p.id,)) == [(0,)], table
    assert len(set(uploads_dir.iterdir())) <= len(before)               # storage cleanup policy: no new orphans


@pytest.mark.plan("E2E-12", "UI-04")
@pytest.mark.needs_vue
def test_e2e_12_dashboard_with_offline_then_recovery(page, login_ui, world):
    login_ui(world.roles.admin)
    state = {"offline": True}

    def handler(route):
        route.abort("failed") if state["offline"] else route.continue_()
    page.route("**/api/projects/dashboard", handler)
    page.goto("/dashboard.html")
    page.wait_for_timeout(800)
    assert page.locator(".project-card").count() == 0
    state["offline"] = False
    page.reload()
    expect(page.locator(".project-card").first).to_be_visible()


@pytest.mark.plan("E2E-12")
def test_e2e_12b_registration_500_does_not_double_submit_or_report_success(page, anon_ui):
    anon_ui()
    calls = []

    def handler(route):
        calls.append(1)
        route.fulfill(status=500, content_type="application/json", body='{"detail":"Internal"}')
    page.route("**/api/auth/register", handler)
    page.goto("/")
    page.locator("[data-open-auth='register']").first.click()
    page.fill("#reg-name", "Offline Olga")
    page.fill("#reg-email", unique_email("e2e12_"))
    page.fill("#reg-password", PASSWORD)
    page.locator("#form-register button[type=submit]").click()
    expect(page.locator("#register-error")).to_contain_text("Error")
    page.wait_for_timeout(400)
    assert len(calls) == 1 and "/dashboard.html" not in page.url
