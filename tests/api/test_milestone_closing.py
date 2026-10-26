"""Milestone manual closing: close / reopen, rules, permissions (ROAD-14)."""
import pytest

from framework.factory import ok

pytestmark = pytest.mark.api

NOT_ADMIN = ["editor", "contributor", "reporter"]


def url(m, action):
    return f"/api/roadmap/milestones/{m['id']}/{action}"


def admin(world):
    return world.client("admin")


def ready_milestone(world, tickets=2):
    """Milestone whose tickets are all in the Done column (ready to close)."""
    m = world.a.milestone()
    for _ in range(tickets):
        t = world.a.ticket(milestone_id=m["id"])
        world.a.move(t["id"], "Done")
    return m


# ---------------------------------------------------------------- permissions
@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("action", ["close", "reopen"])
def test_close_and_reopen_require_login(world, anon, action):
    m = world.a.milestone()
    assert anon.post(url(m, action)).status_code == 401


@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("action", ["close", "reopen"])
@pytest.mark.parametrize("role", NOT_ADMIN)
def test_only_admin_can_close_or_reopen(world, role, action):
    m = world.a.milestone(status="done") if action == "reopen" else world.a.milestone()
    r = world.client(role).post(url(m, action))
    assert r.status_code == 403
    assert world.a.milestone_row(m["id"])["is_closed"] is (action == "reopen")   # nothing changed


@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("action", ["close", "reopen"])
def test_outsider_cannot_close_or_reopen(world, action):
    m = world.a.milestone()
    assert world.client("outsider").post(url(m, action)).status_code == 403


@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("action", ["close", "reopen"])
def test_unknown_milestone_is_404(world, action):
    assert admin(world).post(f"/api/roadmap/milestones/99999999/{action}").status_code == 404


# ---------------------------------------------------------------- closing
@pytest.mark.plan("ROAD-14")
def test_close_with_unfinished_tickets_is_rejected(world):
    m = world.a.milestone()
    world.a.ticket(milestone_id=m["id"])
    r = admin(world).post(url(m, "close"))
    assert r.status_code == 400 and "not done" in r.json()["detail"]
    row = world.a.milestone_row(m["id"])
    assert (row["is_closed"], row["status"], row["closed_at"]) == (False, "planned", None)


@pytest.mark.plan("ROAD-14")
def test_close_with_one_ticket_still_open_is_rejected(world):
    m = ready_milestone(world, 2)
    world.a.ticket(milestone_id=m["id"])
    assert admin(world).post(url(m, "close")).status_code == 400


@pytest.mark.plan("ROAD-14")
def test_close_when_all_tickets_are_done(world):
    m = ready_milestone(world)
    row = ok(admin(world).post(url(m, "close"))).json()
    assert (row["status"], row["progress"], row["is_closed"], row["ready_to_close"]) == ("done", 100, True, False)
    assert row["closed_at"] is not None
    assert world.a.milestone_row(m["id"]) == row


@pytest.mark.plan("ROAD-14")
def test_empty_milestone_can_be_closed(world):
    m = world.a.milestone()
    row = ok(admin(world).post(url(m, "close"))).json()
    assert (row["status"], row["progress"], row["is_closed"]) == ("done", 100, True)


@pytest.mark.plan("ROAD-14")
def test_closing_twice_and_reopening_an_open_milestone_are_400(world):
    m = world.a.milestone()
    ok(admin(world).post(url(m, "close")))
    assert admin(world).post(url(m, "close")).status_code == 400
    other = world.a.milestone()
    assert admin(world).post(url(other, "reopen")).status_code == 400


# ---------------------------------------------------------------- no auto done
@pytest.mark.plan("ROAD-14")
def test_finishing_all_tickets_does_not_close_the_milestone(world):
    m = ready_milestone(world)
    row = world.a.milestone_row(m["id"])
    assert (row["status"], row["progress"], row["is_closed"], row["ready_to_close"]) == ("in_progress", 100, False, True)


@pytest.mark.plan("ROAD-14")
def test_ready_to_close_only_when_every_ticket_is_done(world):
    m = world.a.milestone()
    assert world.a.milestone_row(m["id"])["ready_to_close"] is False           # no tickets
    done = world.a.ticket(milestone_id=m["id"])
    world.a.ticket(milestone_id=m["id"])
    world.a.move(done["id"], "Done")
    assert world.a.milestone_row(m["id"])["ready_to_close"] is False           # one still open


# ---------------------------------------------------------------- reopen
@pytest.mark.plan("ROAD-14")
def test_reopen_returns_to_in_progress_when_tickets_are_done(world):
    m = ready_milestone(world)
    ok(admin(world).post(url(m, "close")))
    row = ok(admin(world).post(url(m, "reopen"))).json()
    assert (row["status"], row["progress"], row["is_closed"], row["closed_at"], row["ready_to_close"]) == \
        ("in_progress", 100, False, None, True)


@pytest.mark.plan("ROAD-14")
def test_reopen_empty_milestone_goes_back_to_planned(world):
    m = world.a.milestone(status="done")
    row = ok(admin(world).post(url(m, "reopen"))).json()
    assert (row["status"], row["progress"], row["is_closed"]) == ("planned", 0, False)


# ---------------------------------------------------------------- edit rules
@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("body", [{"status": "done"}, {"status": "done", "progress": 100}])
def test_done_cannot_be_set_through_patch(world, body):
    m = world.a.milestone()
    r = admin(world).patch(f"/api/roadmap/milestones/{m['id']}", json=body)
    assert r.status_code == 400 and "Close" in r.json()["detail"]


@pytest.mark.plan("ROAD-14")
@pytest.mark.parametrize("body", [{"status": "in_progress"}, {"progress": 10}])
def test_status_and_progress_of_closed_milestone_are_locked(world, body):
    m = world.a.milestone(status="done")
    r = admin(world).patch(f"/api/roadmap/milestones/{m['id']}", json=body)
    assert r.status_code == 400 and "Reopen" in r.json()["detail"]


@pytest.mark.plan("ROAD-14")
def test_title_of_closed_milestone_can_still_be_changed(world):
    m = world.a.milestone(status="done")
    row = ok(admin(world).patch(f"/api/roadmap/milestones/{m['id']}", json={"title": "Renamed"})).json()
    assert (row["title"], row["is_closed"], row["status"]) == ("Renamed", True, "done")


@pytest.mark.plan("ROAD-14")
def test_create_with_done_status_is_rejected(world):
    r = admin(world).post(f"/api/roadmap/project/{world.a.id}/milestones", json={"title": "x", "status": "done"})
    assert r.status_code == 400 and world.a.roadmap()["milestones"] == []


# ---------------------------------------------------------------- tickets vs closed milestone
@pytest.mark.plan("ROAD-14")
def test_ticket_cannot_be_assigned_to_a_closed_milestone(world):
    m = world.a.milestone(status="done")
    t = world.a.ticket()
    r = admin(world).patch(f"/api/tickets/{t['id']}", json={"milestone_id": m["id"]})
    assert r.status_code == 400 and "closed" in r.json()["detail"]
    assert world.a.milestone_row(m["id"])["tickets_total"] == 0


@pytest.mark.plan("ROAD-14")
def test_ticket_cannot_be_created_in_a_closed_milestone(world):
    m = world.a.milestone(status="done")
    r = admin(world).post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "milestone_id": m["id"]})
    assert r.status_code == 400 and world.a.tickets() == []


@pytest.mark.plan("ROAD-14")
def test_ticket_can_be_taken_out_of_a_closed_milestone(world):
    m = ready_milestone(world, 1)
    ok(admin(world).post(url(m, "close")))
    t = world.a.tickets()[0]
    assert ok(admin(world).patch(f"/api/tickets/{t['id']}", json={"milestone_id": None})).json()["milestone_id"] is None


@pytest.mark.plan("ROAD-14")
def test_closed_milestone_keeps_status_when_a_ticket_is_reopened(world):
    m = ready_milestone(world, 2)
    ok(admin(world).post(url(m, "close")))
    world.a.move(world.a.tickets()[0]["id"], "Open")
    row = world.a.milestone_row(m["id"])
    assert (row["status"], row["is_closed"]) == ("done", True)             # only Reopen changes it


@pytest.mark.plan("ROAD-14")
def test_closing_a_predecessor_satisfies_a_finish_to_start_dependency(world):
    pred, succ = world.a.milestone(), world.a.milestone()
    d = world.a.dependency(pred["id"], succ["id"])
    assert d["state"] == "waiting"
    ok(admin(world).post(url(pred, "close")))
    assert next(x for x in world.a.roadmap()["dependencies"] if x["id"] == d["id"])["state"] == "ok"
