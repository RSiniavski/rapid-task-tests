"""Platform admin tool, Project Insights tab in the browser (PLT-39 .. PLT-42)."""
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from framework.factory import create_project, ok, uid
from framework.platform_api import P, insight_projects

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

I = f"{P}/insights/projects"


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def rows(page):
    return page.locator("[data-testid='project-row']")


def row_of(page, project):
    return page.locator(f"[data-testid='project-row'][data-id='{project.id}']")


def person(make_user, tag="pi", token=None):
    return make_user(tag=f"{tag}_", full_name=f"QA {token or uid(8)} {tag}")


def build(make_user, token, label, members=0, tickets=0, name=None):
    """A project owned by a new person; `members` more people join; `tickets` tickets are created."""
    owner = person(make_user, f"o{label}", token)
    project = create_project(owner, name=name or f"QA {token} {label}")
    people = [person(make_user, f"m{label}{n}", token) for n in range(members)]
    for u in people:
        project.add_member(u, "editor")
    for _ in range(tickets):
        project.ticket()
    return owner, project


def backdate(server, project, days):
    old = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S.%f")
    ids = "(SELECT id FROM tickets WHERE project_id = ?)"
    server.sql("UPDATE projects SET created_at = ? WHERE id = ?", (old, project.id))
    server.sql("UPDATE tickets SET created_at = ? WHERE project_id = ?", (old, project.id))
    server.sql(f"UPDATE ticket_history SET created_at = ? WHERE ticket_id IN {ids}", (old, project.id))
    server.sql(f"UPDATE ticket_comments SET created_at = ? WHERE ticket_id IN {ids}", (old, project.id))


def act(root, project, action, **body):
    return ok(root.post(f"{I}/{project.id}/{action}", json=body or None))


def open_insights(page, plogin_ui, who):
    plogin_ui(who)
    page.goto("/platform.html#/insights")
    expect(tid(page, "insights-page")).to_be_visible()
    expect(tid(page, "insights-loading")).to_have_count(0)


def search(page, text):
    tid(page, "insights-search").fill(text)


def find(page, project):
    """Search by the unique key; wait until exactly this row is shown."""
    search(page, project.key)
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, project)).to_be_visible()
    return row_of(page, project)


# ---------------------------------------------------------------- PLT-39 the list
@pytest.mark.plan("PLT-39")
def test_a_row_shows_the_project_the_owner_and_the_numbers(page, plogin_ui, proot, make_user):
    owner, p = build(make_user, uid(8), "row", members=2, tickets=3)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    expect(r.locator("[data-testid='project-name']")).to_have_text(p.data["name"])
    expect(r.locator("[data-testid='project-key']")).to_have_text(p.key)
    expect(r.locator("[data-testid='project-owner']")).to_have_text(owner.full_name)
    expect(r.locator("[data-testid='project-owner-email']")).to_have_text(owner.email)
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    expect(r).to_have_attribute("data-status", "active")
    expect(r.locator("[data-testid='project-members']")).to_have_text("3")
    expect(r.locator("[data-testid='project-tickets']")).to_have_text("3")
    expect(r.locator("[data-testid='project-open']")).to_have_text("3")
    assert ":" in r.locator("[data-testid='project-activity']").inner_text()              # date and 24 h time
    expect(r.locator("[data-testid='project-flag-inactive']")).to_have_count(0)
    expect(r.locator("[data-testid='project-flag-empty']")).to_have_count(0)
    expect(tid(page, "insights-summary")).to_have_text("1–1 of 1 projects")


@pytest.mark.plan("PLT-39")
def test_search_by_name_key_owner_and_clear(page, plogin_ui, proot, make_user):
    token = uid(8)
    owner, p = build(make_user, token, "se1")
    _, other = build(make_user, token, "se2")
    open_insights(page, plogin_ui, proot)
    expect(tid(page, "insights-clear")).to_be_disabled()
    search(page, p.data["name"].upper())                                      # case does not matter
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, p)).to_be_visible()
    expect(tid(page, "insights-clear")).to_be_enabled()
    search(page, other.key.lower())
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, other)).to_be_visible()
    search(page, owner.email)
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, p)).to_be_visible()
    search(page, token)
    expect(rows(page)).to_have_count(2)
    search(page, "no_such_project_" + uid(10))
    expect(tid(page, "insights-empty")).to_have_text("No projects match these filters.")
    expect(tid(page, "insights-table")).to_have_count(0)
    tid(page, "insights-clear").click()
    expect(tid(page, "insights-search")).to_have_value("")
    expect(tid(page, "insights-empty")).to_have_count(0)
    assert rows(page).count() >= 2
    expect(tid(page, "insights-clear")).to_be_disabled()


@pytest.mark.plan("PLT-39")
def test_the_tab_counters_are_the_server_counters(page, plogin_ui, proot, make_user):
    token = uid(8)
    _, archived = build(make_user, token, "c1")
    _, suspended = build(make_user, token, "c2")
    act(proot, archived, "archive")
    act(proot, suspended, "suspend", reason="Counter test")
    open_insights(page, plogin_ui, proot)
    data = insight_projects(proot, page_size=1)
    for key in ("all", "active", "archived", "suspended"):
        expect(tid(page, f"insights-count-{key}")).to_have_text(str(data["counts"][key]))
    assert data["counts"]["archived"] >= 1 and data["counts"]["suspended"] >= 1
    c = data["counts"]
    assert c["all"] == c["active"] + c["archived"] + c["suspended"]


@pytest.mark.plan("PLT-39")
@pytest.mark.parametrize("status", ["active", "archived", "suspended"])
def test_a_status_tab_shows_only_that_status(page, plogin_ui, proot, make_user, status):
    token = uid(8)
    _, a = build(make_user, token, "t1")
    _, b = build(make_user, token, "t2")
    _, c = build(make_user, token, "t3")
    act(proot, b, "archive")
    act(proot, c, "suspend", reason="Tab test")
    open_insights(page, plogin_ui, proot)
    search(page, token)
    expect(rows(page)).to_have_count(3)
    tid(page, f"insights-tab-{status}").click()
    expect(tid(page, f"insights-tab-{status}")).to_have_attribute("aria-selected", "true")
    expect(rows(page)).to_have_count(1)
    expect(rows(page).first).to_have_attribute("data-status", status)
    expect(row_of(page, {"active": a, "archived": b, "suspended": c}[status])).to_be_visible()
    tid(page, "insights-tab-all").click()
    expect(rows(page)).to_have_count(3)


@pytest.mark.plan("PLT-39")
def test_sort_by_name_and_by_tickets(page, plogin_ui, proot, make_user):
    token = uid(8)
    _, bravo = build(make_user, token, "bravo", tickets=2)
    _, alpha = build(make_user, token, "Alpha")
    _, charlie = build(make_user, token, "charlie", tickets=1)
    open_insights(page, plogin_ui, proot)
    search(page, token)
    expect(rows(page)).to_have_count(3)
    names = lambda: [t.strip() for t in page.locator("[data-testid='project-key']").all_inner_texts()]
    tid(page, "insights-sort").select_option("name")
    expect(rows(page).first).to_have_attribute("data-id", str(alpha.id))
    assert names() == [alpha.key, bravo.key, charlie.key]
    tid(page, "insights-sort").select_option("tickets")
    expect(rows(page).first).to_have_attribute("data-id", str(bravo.id))
    assert names() == [bravo.key, charlie.key, alpha.key]


@pytest.mark.plan("PLT-39")
def test_pages(page, plogin_ui, proot, make_user):
    token = uid(8)
    owner = person(make_user, "pg", token)
    made = [create_project(owner, name=f"QA {token} pg{n:02d}") for n in range(26)]
    open_insights(page, plogin_ui, proot)
    search(page, token)
    expect(tid(page, "insights-summary")).to_have_text("1–25 of 26 projects")
    expect(rows(page)).to_have_count(25)
    expect(tid(page, "insights-page-info")).to_have_text("Page 1 of 2")
    expect(tid(page, "insights-prev")).to_be_disabled()
    tid(page, "insights-next").click()
    expect(rows(page)).to_have_count(1)
    expect(tid(page, "insights-summary")).to_have_text("26–26 of 26 projects")
    expect(tid(page, "insights-page-info")).to_have_text("Page 2 of 2")
    expect(tid(page, "insights-next")).to_be_disabled()
    tid(page, "insights-prev").click()
    expect(rows(page)).to_have_count(25)
    tid(page, "insights-page-size").select_option("50")
    expect(rows(page)).to_have_count(26)
    expect(tid(page, "insights-page-info")).to_have_text("Page 1 of 1")
    assert len(made) == 26


# ---------------------------------------------------------------- PLT-40 warnings
@pytest.mark.plan("PLT-40")
def test_an_old_project_is_inactive_and_the_chip_filters(page, plogin_ui, proot, make_user, server):
    token = uid(8)
    _, old = build(make_user, token, "old", members=1, tickets=1)
    _, fresh = build(make_user, token, "fresh", members=1, tickets=1)
    backdate(server, old, 45)
    open_insights(page, plogin_ui, proot)
    search(page, token)
    expect(rows(page)).to_have_count(2)
    expect(row_of(page, old).locator("[data-testid='project-flag-inactive']")).to_have_text("Inactive")
    expect(row_of(page, fresh).locator("[data-testid='project-flag-inactive']")).to_have_count(0)
    tid(page, "insights-flag-inactive").click()
    expect(tid(page, "insights-flag-inactive")).to_have_attribute("aria-pressed", "true")
    expect(rows(page)).to_have_count(1)
    expect(row_of(page, old)).to_be_visible()
    tid(page, "insights-flag-inactive").click()                               # second click switches it off
    expect(tid(page, "insights-flag-inactive")).to_have_attribute("aria-pressed", "false")
    expect(rows(page)).to_have_count(2)
    flags = insight_projects(proot, q=token, page_size=1)["flags"]                 # the counters follow the search too
    expect(tid(page, "insights-flagcount-inactive")).to_have_text(str(flags["inactive"]))
    assert flags["inactive"] == 1


@pytest.mark.plan("PLT-40")
def test_a_project_with_one_member_or_no_tickets_is_empty(page, plogin_ui, proot, make_user):
    token = uid(8)
    _, lonely = build(make_user, token, "lonely", tickets=2)                  # one member only
    _, bare = build(make_user, token, "bare", members=2)                      # no tickets
    _, busy = build(make_user, token, "busy", members=1, tickets=1)
    open_insights(page, plogin_ui, proot)
    search(page, token)
    expect(rows(page)).to_have_count(3)
    for p, expected in ((lonely, 1), (bare, 1), (busy, 0)):
        expect(row_of(page, p).locator("[data-testid='project-flag-empty']")).to_have_count(expected)
    tid(page, "insights-flag-empty").click()
    expect(rows(page)).to_have_count(2)
    expect(row_of(page, busy)).to_have_count(0)
    tid(page, "insights-clear").click()                                       # clear also switches the chip off
    expect(tid(page, "insights-flag-empty")).to_have_attribute("aria-pressed", "false")
    flags = insight_projects(proot, page_size=1)["flags"]
    expect(tid(page, "insights-flagcount-empty")).to_have_text(str(flags["empty"]))


@pytest.mark.plan("PLT-40")
def test_an_archived_project_has_no_warnings(page, plogin_ui, proot, make_user):
    _, p = build(make_user, uid(8), "arw")                                    # one member, no tickets = empty
    act(proot, p, "archive")
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    expect(r.locator("[data-testid='project-status']")).to_have_text("Archived")
    expect(r.locator("[data-testid='project-flag-empty']")).to_have_count(0)
    expect(r.locator("[data-testid='project-flag-inactive']")).to_have_count(0)


# ---------------------------------------------------------------- PLT-41 the root admin changes a project
@pytest.mark.plan("PLT-41")
def test_suspend_needs_a_reason_and_the_members_are_blocked(page, plogin_ui, proot, make_user):
    owner, p = build(make_user, uid(8), "sus", tickets=1)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    r.locator("[data-testid='project-suspend']").click()
    expect(tid(page, "project-modal")).to_be_visible()
    expect(tid(page, "project-target")).to_have_text(p.data["name"])
    expect(tid(page, "project-modal-confirm")).to_be_disabled()               # no reason yet
    tid(page, "project-modal-reason").fill("   ")
    expect(tid(page, "project-modal-confirm")).to_be_disabled()               # spaces are not a reason
    tid(page, "project-modal-reason").fill("Under investigation")
    tid(page, "project-modal-confirm").click()
    expect(tid(page, "project-modal")).to_have_count(0)
    expect(r.locator("[data-testid='project-status']")).to_have_text("Suspended")
    expect(r.locator("[data-testid='project-reason']")).to_have_text("Under investigation")
    expect(r.locator("[data-testid='project-suspend']")).to_have_count(0)
    expect(r.locator("[data-testid='project-archive']")).to_have_count(0)
    r_resp = owner.client.get(f"/api/tickets/project/{p.id}")
    assert r_resp.status_code == 403 and r_resp.json()["reason"] == "Under investigation"
    r.locator("[data-testid='project-unsuspend']").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    expect(r.locator("[data-testid='project-reason']")).to_have_count(0)
    assert owner.client.get(f"/api/tickets/project/{p.id}").status_code == 200


@pytest.mark.plan("PLT-41")
def test_archive_note_is_optional_and_restore_brings_the_project_back(page, plogin_ui, proot, make_user):
    owner, p = build(make_user, uid(8), "arc", tickets=1)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    r.locator("[data-testid='project-archive']").click()
    expect(tid(page, "project-modal-confirm")).to_be_enabled()                # the note is optional
    tid(page, "project-modal-confirm").click()
    expect(tid(page, "project-modal")).to_have_count(0)
    expect(r.locator("[data-testid='project-status']")).to_have_text("Archived")
    expect(r).to_have_attribute("data-status", "archived")
    assert owner.client.get(f"/api/tickets/project/{p.id}").status_code == 404
    expect(r.locator("[data-testid='project-archive']")).to_have_count(0)
    expect(r.locator("[data-testid='project-suspend']")).to_have_count(0)
    r.locator("[data-testid='project-restore']").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    assert owner.client.get(f"/api/tickets/project/{p.id}").status_code == 200


@pytest.mark.plan("PLT-41")
def test_delete_needs_the_key_and_removes_the_project(page, plogin_ui, proot, make_user):
    owner, p = build(make_user, uid(8), "del", tickets=2)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    r.locator("[data-testid='project-delete']").click()
    expect(tid(page, "project-target")).to_have_text(p.data["name"])
    expect(tid(page, "project-modal")).to_contain_text("2 ticket(s)")
    expect(tid(page, "project-modal-confirm")).to_be_disabled()
    tid(page, "project-modal-key").fill("WRONG")
    expect(tid(page, "project-modal-confirm")).to_be_disabled()
    tid(page, "project-modal-key").fill(p.key.lower())                        # case does not matter
    expect(tid(page, "project-modal-confirm")).to_be_enabled()
    tid(page, "project-modal-confirm").click()
    expect(tid(page, "project-modal")).to_have_count(0)
    expect(rows(page)).to_have_count(0)
    expect(tid(page, "insights-empty")).to_be_visible()
    assert owner.client.get(f"/api/projects/{p.id}").status_code in (403, 404)
    assert insight_projects(proot, q=p.key)["total"] == 0


@pytest.mark.plan("PLT-41")
@pytest.mark.parametrize("how", ["cancel", "escape", "close", "backdrop"])
def test_leaving_the_dialog_changes_nothing(page, plogin_ui, proot, make_user, how):
    _, p = build(make_user, uid(8), "lv", tickets=1)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    r.locator("[data-testid='project-suspend']").click()
    tid(page, "project-modal-reason").fill("Not sent")
    if how == "cancel":
        tid(page, "project-modal-cancel").click()
    elif how == "escape":
        page.keyboard.press("Escape")
    elif how == "close":
        tid(page, "project-modal-close").click()
    else:
        tid(page, "project-modal-backdrop").click(position={"x": 4, "y": 4})
    expect(tid(page, "project-modal")).to_have_count(0)
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    r.locator("[data-testid='project-suspend']").click()                      # a new dialog starts empty
    expect(tid(page, "project-modal-reason")).to_have_value("")
    assert find_status(proot, p) == "active"


def find_status(root, project):
    return next(r for r in insight_projects(root, q=project.key)["items"] if r["id"] == project.id)["status"]


@pytest.mark.plan("PLT-41")
def test_a_refused_change_shows_the_error_in_the_dialog(page, plogin_ui, proot, make_user):
    _, p = build(make_user, uid(8), "stale")
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    act(proot, p, "archive")                                                  # somebody else did it, the row is old
    r.locator("[data-testid='project-suspend']").click()
    tid(page, "project-modal-reason").fill("Too late")
    tid(page, "project-modal-confirm").click()
    expect(tid(page, "project-modal")).to_be_visible()
    expect(tid(page, "project-modal-error")).not_to_have_text("")
    expect(r.locator("[data-testid='project-status']")).to_have_text("Archived")   # the list was refreshed
    assert find_status(proot, p) == "archived"                                # nothing was suspended


# ---------------------------------------------------------------- PLT-42 who sees what, audit log, safe text
@pytest.mark.plan("PLT-42")
def test_an_admin_with_analytics_can_look_but_not_change(page, plogin_ui, padmin, make_user):
    a = padmin("ins1", can_view_analytics=True)
    _, p = build(make_user, uid(8), "ro", tickets=1)
    open_insights(page, plogin_ui, a)
    expect(tid(page, "insights-readonly")).to_be_visible()
    r = find(page, p)
    expect(r.locator("[data-testid='project-name']")).to_have_text(p.data["name"])
    for name in ("project-suspend", "project-archive", "project-delete", "project-unsuspend", "project-restore"):
        expect(page.locator(f"[data-testid='{name}']")).to_have_count(0)
    expect(page.locator("th.pl-th-actions")).to_have_count(0)


@pytest.mark.plan("PLT-42")
def test_the_root_admin_has_no_read_only_note_and_has_the_buttons(page, plogin_ui, proot, make_user):
    _, p = build(make_user, uid(8), "rt")
    open_insights(page, plogin_ui, proot)
    expect(tid(page, "insights-readonly")).to_have_count(0)
    r = find(page, p)
    for name in ("project-suspend", "project-archive", "project-delete"):
        expect(r.locator(f"[data-testid='{name}']")).to_be_visible()
    expect(r.locator("[data-testid='project-restore']")).to_have_count(0)
    expect(r.locator("[data-testid='project-unsuspend']")).to_have_count(0)


@pytest.mark.plan("PLT-42")
def test_the_changes_show_up_in_the_audit_log_tab(page, plogin_ui, proot, make_user):
    _, p = build(make_user, uid(8), "aud", tickets=1)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    r.locator("[data-testid='project-suspend']").click()
    tid(page, "project-modal-reason").fill("Spam")
    tid(page, "project-modal-confirm").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Suspended")
    r.locator("[data-testid='project-unsuspend']").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    r.locator("[data-testid='project-archive']").click()
    tid(page, "project-modal-confirm").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Archived")
    r.locator("[data-testid='project-restore']").click()
    expect(r.locator("[data-testid='project-status']")).to_have_text("Active")
    r.locator("[data-testid='project-delete']").click()
    tid(page, "project-modal-key").fill(p.key)
    tid(page, "project-modal-confirm").click()
    expect(rows(page)).to_have_count(0)
    tid(page, "nav-audit").click()
    expect(tid(page, "audit-page")).to_be_visible()
    tid(page, "audit-target").fill(p.data["name"])
    audit_rows = page.locator("[data-testid='audit-row']")
    expect(audit_rows).to_have_count(5)
    by = {x.get_attribute("data-action"): x for x in audit_rows.all()}
    assert set(by) == {"project_suspended", "project_unsuspended", "project_archived", "project_restored", "project_deleted"}
    assert by["project_suspended"].locator("[data-testid='audit-action-pill']").inner_text() == "Project suspended"
    assert by["project_deleted"].locator("[data-testid='audit-action-pill']").inner_text() == "Project deleted"
    assert "Reason: Spam" in by["project_suspended"].locator("[data-testid='audit-details']").inner_text()
    assert f"Key: {p.key}" in by["project_deleted"].locator("[data-testid='audit-details']").inner_text()
    assert "1 ticket(s) removed" in by["project_deleted"].locator("[data-testid='audit-details']").inner_text()


@pytest.mark.plan("PLT-42")
def test_a_name_with_html_is_shown_as_text(page, plogin_ui, proot, make_user):
    token = uid(8)
    evil = f"<img src=x onerror=window.__x=1> {token}"
    _, p = build(make_user, token, "xss", name=evil)
    open_insights(page, plogin_ui, proot)
    r = find(page, p)
    expect(r.locator("[data-testid='project-name']")).to_have_text(evil)
    assert page.locator("img[src='x']").count() == 0
    assert page.evaluate("window.__x") is None
    r.locator("[data-testid='project-suspend']").click()
    expect(tid(page, "project-target")).to_have_text(evil)                    # the question shows it as text too
    assert page.locator("[data-testid='project-modal'] img").count() == 0


@pytest.mark.plan("PLT-42")
def test_a_failed_list_shows_an_error_and_try_again_works(page, plogin_ui, proot):
    plogin_ui(proot)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body='{"detail": "Server broke"}')
        else:
            route.continue_()

    page.route("**/api/platform/insights/projects*", handler)
    page.goto("/platform.html#/insights")
    expect(tid(page, "insights-error")).to_be_visible()
    expect(tid(page, "insights-table")).to_have_count(0)
    state["fail"] = False
    tid(page, "insights-retry").click()
    expect(tid(page, "insights-error")).to_have_count(0)
    expect(tid(page, "insights-table")).to_be_visible()
