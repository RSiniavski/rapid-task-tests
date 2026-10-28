"""Board scope: the board shows only tickets of OPEN milestones; the backlog shows everything (BKL-01..03)."""
import pytest

from framework.factory import ok

pytestmark = pytest.mark.api


def listing(world, scope=None, client=None):
    url = f"/api/tickets/project/{world.a.id}" + (f"?scope={scope}" if scope else "")
    return ok((client or world.a.c).get(url)).json()


def titles(rows):
    return sorted(t["title"] for t in rows)


@pytest.fixture
def mixed(world):
    """One ticket without milestone, one in an open milestone, one in a closed milestone."""
    open_m = world.a.milestone(title="Open one")
    closed_m = world.a.milestone(title="Closed one")
    world.a.ticket(title="no-ms")
    world.a.ticket(title="in-open", milestone_id=open_m["id"])
    t = world.a.ticket(title="in-closed", milestone_id=closed_m["id"])
    world.a.move(t["id"], "Done")
    world.a.close_milestone(closed_m["id"])
    return open_m, closed_m


# ---------------------------------------------------------------- scope
@pytest.mark.plan("BKL-01")
def test_default_and_all_scope_return_every_ticket(world, mixed):
    everything = ["in-closed", "in-open", "no-ms"]
    assert titles(listing(world)) == everything
    assert titles(listing(world, "all")) == everything


@pytest.mark.plan("BKL-01")
def test_board_scope_hides_tickets_without_milestone_and_of_closed_milestones(world, mixed):
    assert titles(listing(world, "board")) == ["in-open"]


@pytest.mark.plan("BKL-01")
def test_ticket_leaves_the_board_when_its_milestone_is_closed_and_returns_on_reopen(world):
    m = world.a.milestone()
    t = world.a.ticket(title="moves", milestone_id=m["id"])
    world.a.move(t["id"], "Done")
    assert titles(listing(world, "board")) == ["moves"]
    world.a.close_milestone(m["id"])
    assert listing(world, "board") == []
    world.a.reopen_milestone(m["id"])
    assert titles(listing(world, "board")) == ["moves"]


@pytest.mark.plan("BKL-01")
def test_ticket_without_milestone_appears_on_board_after_assigning_one(world):
    t = world.a.ticket(title="late")
    m = world.a.milestone()
    assert listing(world, "board") == []
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": m["id"]}))
    assert titles(listing(world, "board")) == ["late"]


@pytest.mark.plan("BKL-01")
def test_unknown_scope_is_rejected(world):
    assert world.a.c.get(f"/api/tickets/project/{world.a.id}?scope=other").status_code == 422


@pytest.mark.plan("BKL-01")
def test_scope_listing_requires_login_and_membership(world, anon):
    assert anon.get(f"/api/tickets/project/{world.a.id}?scope=board").status_code == 401
    r = world.roles.outsider.client.get(f"/api/tickets/project/{world.a.id}?scope=board")
    assert r.status_code == 403


@pytest.mark.plan("BKL-01")
@pytest.mark.parametrize("role", ["editor", "contributor", "reporter"])
def test_every_member_role_can_read_both_scopes(world, mixed, role):
    c = world.client(role)
    assert len(listing(world, "all", c)) == 3
    assert titles(listing(world, "board", c)) == ["in-open"]


# ---------------------------------------------------------------- milestone data in the ticket
@pytest.mark.plan("BKL-02")
def test_ticket_carries_a_short_milestone_description(world, mixed):
    open_m, closed_m = mixed
    rows = {t["title"]: t for t in listing(world)}
    assert rows["no-ms"]["milestone"] is None and rows["no-ms"]["milestone_id"] is None
    brief = rows["in-open"]["milestone"]
    assert (brief["id"], brief["title"], brief["is_closed"]) == (open_m["id"], "Open one", False)
    assert rows["in-closed"]["milestone"]["is_closed"] is True


# ---------------------------------------------------------------- children
@pytest.mark.plan("BKL-03")
def test_child_inherits_the_open_milestone_of_the_parent(world):
    m = world.a.milestone()
    epic = world.a.ticket(type="Epic", title="parent", milestone_id=m["id"])
    child = world.a.ticket(title="child", parent_id=epic["id"])
    assert child["milestone_id"] == m["id"]


@pytest.mark.plan("BKL-03")
def test_child_of_a_ticket_without_milestone_has_none(world):
    epic = world.a.ticket(type="Epic", title="parent")
    child = world.a.ticket(title="child", parent_id=epic["id"])
    assert child["milestone_id"] is None


@pytest.mark.plan("BKL-03")
def test_ticket_cannot_be_created_in_a_closed_milestone(world):
    m = world.a.milestone(status="done")
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "type": "Task", "milestone_id": m["id"]})
    assert r.status_code == 400
