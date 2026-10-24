"""Section 4 - projects, members, dashboard and board configuration (API / backend)."""
import pytest

from framework import config
from framework.factory import create_project, ok, unique_key

pytestmark = pytest.mark.api

ROLE_NAMES = ["admin", "editor", "contributor", "reporter"]


# =================================================================== PROJ-01
@pytest.mark.plan("PROJ-01")
def test_create_project_makes_creator_admin_with_default_columns(make_user):
    u = make_user(tag="proj_")
    key = unique_key()
    r = ok(u.client.post("/api/projects", json={"name": "Alpha", "key": key, "language": "en",
                                                "project_type": "software_dev"}), 201).json()
    assert (r["name"], r["key"], r["language"], r["project_type"]) == ("Alpha", key, "en", "software_dev")
    assert r["owner"]["id"] == u.id and r["created_at"]
    cols = sorted(r["columns"], key=lambda c: c["position"])
    assert [c["name"] for c in cols] == config.DEFAULT_COLUMNS
    assert [c["position"] for c in cols] == list(range(len(cols)))
    assert [c["name"] for c in cols if c["is_done"]] == ["Done"]

    members = ok(u.client.get(f"/api/projects/{r['id']}/members")).json()
    assert [(m["user"]["id"], m["role"]) for m in members] == [(u.id, "admin")]
    stats = ok(u.client.get(f"/api/projects/{r['id']}/stats")).json()
    assert (stats["tickets_total"], stats["tickets_done"], stats["tickets_open"], stats["role"]) == (0, 0, 0, "admin")


@pytest.mark.plan("PROJ-01")
def test_language_and_type_defaults(make_user):
    u = make_user(tag="proj_")
    r = ok(u.client.post("/api/projects", json={"name": "Defaults", "key": unique_key()}), 201).json()
    assert r["language"] == "uk" and r["project_type"] == "software_dev"


@pytest.mark.plan("PROJ-01")
@pytest.mark.parametrize("length", [2, 3, 10])
def test_key_length_boundaries_accepted(make_user, length):
    import random
    import string
    u = make_user(tag="proj_")
    k = "Q" + "".join(random.choices(string.ascii_uppercase + string.digits, k=length - 1))
    assert ok(u.client.post("/api/projects", json={"name": "K", "key": k}), 201).json()["key"] == k


@pytest.mark.plan("PROJ-01")
def test_unicode_and_markup_project_name_roundtrip(make_user):
    u = make_user(tag="proj_")
    name = "Проєкт <b>№1</b> & \"q\" 🚀"
    r = ok(u.client.post("/api/projects", json={"name": name, "key": unique_key()}), 201).json()
    assert r["name"] == name


# =================================================================== PROJ-02
@pytest.mark.plan("PROJ-02")
def test_duplicate_key_conflicts_across_users_and_creates_nothing(make_user):
    a, b = make_user(tag="proj_"), make_user(tag="proj_")
    p = create_project(a)
    r = b.client.post("/api/projects", json={"name": "Dup", "key": p.key})
    assert r.status_code == 409 and p.key in r.json()["detail"]
    assert ok(b.client.get("/api/projects")).json() == []


BAD_PROJECTS = {
    "key_too_short": {"name": "N", "key": "A"},
    "key_lowercase": {"name": "N", "key": "abc"},
    "key_starts_with_digit": {"name": "N", "key": "1AB"},
    "key_too_long": {"name": "N", "key": "A" * 11},
    "key_symbol": {"name": "N", "key": "AB-C"},
    "key_unicode": {"name": "N", "key": "АБВ"},
    "name_empty": {"name": "", "key": "OKKEY"},
    "name_too_long": {"name": "n" * 101, "key": "OKKEY"},
    "language_invalid": {"name": "N", "key": "OKKEY", "language": "de"},
    "type_invalid": {"name": "N", "key": "OKKEY", "project_type": "kanban"},
    "missing_name": {"key": "OKKEY"},
    "missing_key": {"name": "N"},
    "empty_body": {},
    "name_wrong_type": {"name": 5, "key": "OKKEY"},
}


@pytest.mark.plan("PROJ-02")
@pytest.mark.parametrize("case", sorted(BAD_PROJECTS))
def test_invalid_project_payloads_are_422_without_partial_data(make_user, case):
    u = make_user(tag="proj_")
    assert u.client.post("/api/projects", json=BAD_PROJECTS[case]).status_code == 422
    assert ok(u.client.get("/api/projects")).json() == []
    assert ok(u.client.get("/api/projects/dashboard")).json()["projects"] == []


# =================================================================== PROJ-03
@pytest.mark.plan("PROJ-03")
def test_user_without_projects_sees_empty_list_and_dashboard(make_user):
    u = make_user(tag="proj_")
    assert ok(u.client.get("/api/projects")).json() == []
    d = ok(u.client.get("/api/projects/dashboard")).json()
    assert d["projects"] == [] and d["tickets_total"] == 0 and d["avg_lifetime_hours"] is None


@pytest.mark.plan("PROJ-03")
def test_list_and_dashboard_show_only_memberships(make_user):
    owner, member, stranger = make_user(tag="proj_"), make_user(tag="proj_"), make_user(tag="proj_")
    mine, shared, hidden = create_project(owner), create_project(owner), create_project(stranger)
    shared.add_member(member, "reporter")
    listing = {p["id"] for p in ok(member.client.get("/api/projects")).json()}
    assert listing == {shared.id}
    dash = ok(member.client.get("/api/projects/dashboard")).json()
    assert [(p["project_id"], p["role"]) for p in dash["projects"]] == [(shared.id, "reporter")]
    assert {p["id"] for p in ok(owner.client.get("/api/projects")).json()} == {mine.id, shared.id}
    assert hidden.id not in {p["project_id"] for p in dash["projects"]}


@pytest.mark.plan("PROJ-03", "PROJ-10")
def test_dashboard_counts_agree_with_tickets_and_done_columns(make_user):
    u = make_user(tag="proj_")
    p1, p2 = create_project(u), create_project(u)
    t1, t2, t3 = p1.ticket(type="Task"), p1.ticket(type="Bug"), p1.ticket(type="Task")
    p1.move(t1["id"], "Done")
    p1.move(t2["id"], "In Progress")
    p2.ticket(type="Idea")
    dash = ok(u.client.get("/api/projects/dashboard")).json()
    rows = {p["project_id"]: p for p in dash["projects"]}
    assert (rows[p1.id]["tickets_total"], rows[p1.id]["tickets_done"], rows[p1.id]["tickets_open"]) == (3, 1, 2)
    assert rows[p1.id]["by_type"] == {"Task": 2, "Bug": 1}
    assert rows[p1.id]["by_column"] == {"Done": 1, "In Progress": 1, "Open": 1}
    assert (rows[p2.id]["tickets_total"], rows[p2.id]["tickets_done"]) == (1, 0)
    assert dash["tickets_total"] == 4
    assert rows[p1.id]["avg_lifetime_hours"] is not None and rows[p1.id]["avg_lifetime_hours"] >= 0
    assert rows[p2.id]["avg_lifetime_hours"] is None
    assert t3["key"] == f"{p1.key}-3"


# =================================================================== PROJ-04
@pytest.mark.plan("PROJ-04")
@pytest.mark.parametrize("role", ROLE_NAMES)
def test_every_member_can_read_project_with_members(world, role):
    r = ok(world.client(role).get(f"/api/projects/{world.a.id}")).json()
    assert r["id"] == world.a.id and len(r["members"]) == 4
    assert {m["role"] for m in r["members"]} == set(ROLE_NAMES)


@pytest.mark.plan("PROJ-04")
def test_non_member_and_unknown_project_reads(world):
    out = world.roles.outsider.client
    for path in ("", "/members", "/columns", "/stats"):
        r = out.get(f"/api/projects/{world.a.id}{path}")
        assert r.status_code == 403 and world.a.key not in r.text
        assert out.get(f"/api/projects/987654321{path}").status_code == 404


@pytest.mark.plan("PROJ-04")
def test_only_admin_can_update_project_and_denials_leave_state_untouched(world):
    base = f"/api/projects/{world.a.id}"
    for role in ("editor", "contributor", "reporter"):
        assert world.client(role).patch(base, json={"name": "HACK"}).status_code == 403
    assert world.roles.outsider.client.patch(base, json={"name": "HACK"}).status_code == 403
    assert world.a.c.patch("/api/projects/987654321", json={"name": "x"}).status_code == 404
    before = ok(world.a.c.get(base)).json()
    assert before["name"] != "HACK"
    r = ok(world.a.c.patch(base, json={"name": "Renamed", "language": "en"})).json()
    assert (r["name"], r["language"], r["key"]) == ("Renamed", "en", world.a.key)


@pytest.mark.plan("PROJ-04")
@pytest.mark.parametrize("body", [{"name": ""}, {"name": "n" * 101}, {"language": "de"}, {"name": 5}])
def test_invalid_project_update_is_422(world, body):
    assert world.a.c.patch(f"/api/projects/{world.a.id}", json=body).status_code == 422


@pytest.mark.plan("PROJ-04")
def test_project_key_cannot_be_changed_through_update(world):
    r = ok(world.a.c.patch(f"/api/projects/{world.a.id}", json={"key": "HACKED", "name": "N2"})).json()
    assert r["key"] == world.a.key


@pytest.mark.plan("PROJ-04")
def test_second_admin_can_update_but_only_owner_can_delete(world, make_user):
    admin2 = make_user(tag="adm2_")
    world.a.add_member(admin2, "admin")
    assert admin2.client.patch(f"/api/projects/{world.a.id}", json={"name": "By Admin2"}).status_code == 200
    assert admin2.client.delete(f"/api/projects/{world.a.id}").status_code == 403
    for role in ("editor", "contributor", "reporter"):
        assert world.client(role).delete(f"/api/projects/{world.a.id}").status_code == 403
    assert world.roles.outsider.client.delete(f"/api/projects/{world.a.id}").status_code == 403
    assert world.a.c.get(f"/api/projects/{world.a.id}").status_code == 200   # still there


@pytest.mark.plan("PROJ-04")
def test_owner_deletes_project_and_everything_becomes_404(world):
    t = world.a.ticket()
    m = world.a.milestone()
    assert world.a.c.delete(f"/api/projects/{world.a.id}").status_code == 204
    c = world.a.c
    for path in (f"/api/projects/{world.a.id}", f"/api/projects/{world.a.id}/columns", f"/api/tickets/{t['id']}",
                 f"/api/tickets/project/{world.a.id}", f"/api/roadmap/project/{world.a.id}"):
        assert c.get(path).status_code == 404, path
    assert c.patch(f"/api/roadmap/milestones/{m['id']}", json={"title": "x"}).status_code == 404
    assert c.delete(f"/api/projects/{world.a.id}").status_code == 404
    assert world.a.id not in {p["id"] for p in ok(c.get("/api/projects")).json()}


@pytest.mark.plan("PROJ-04")
def test_delete_unknown_project_is_404(world):
    assert world.a.c.delete("/api/projects/987654321").status_code == 404


# =================================================================== PROJ-05
@pytest.mark.plan("PROJ-05")
@pytest.mark.parametrize("role", ROLE_NAMES)
def test_add_member_by_email_for_each_role(world, make_user, role):
    u = make_user(tag="mem_")
    r = ok(world.a.c.post(f"/api/projects/{world.a.id}/members", json={"email": u.email, "role": role}), 201).json()
    assert r["user"]["id"] == u.id and r["role"] == role
    assert u.client.get(f"/api/projects/{world.a.id}").status_code == 200


@pytest.mark.plan("PROJ-05")
def test_add_member_by_user_id_default_role_is_contributor(world, make_user):
    u = make_user(tag="mem_")
    r = ok(world.a.c.post(f"/api/projects/{world.a.id}/members", json={"user_id": u.id}), 201).json()
    assert r["role"] == "contributor"


@pytest.mark.plan("PROJ-05")
def test_add_member_errors_and_no_duplicate_membership(world, make_user):
    u = make_user(tag="mem_")
    base = f"/api/projects/{world.a.id}/members"
    ok(world.a.c.post(base, json={"user_id": u.id, "role": "editor"}), 201)
    dup = world.a.c.post(base, json={"user_id": u.id, "role": "admin"})
    assert dup.status_code == 404 and "already" in dup.json()["detail"].lower()
    for body in ({"email": "nobody_xyz@example.com"}, {"user_id": 987654321}, {}):
        assert world.a.c.post(base, json=body).status_code == 404
    members = ok(world.a.c.get(base)).json()
    assert sum(1 for m in members if m["user"]["id"] == u.id) == 1
    assert [m["role"] for m in members if m["user"]["id"] == u.id] == ["editor"]    # unchanged by the duplicate


@pytest.mark.plan("PROJ-05")
@pytest.mark.parametrize("body", [{"user_id": 1, "role": "owner"}, {"user_id": 1, "role": ""}, {"email": "not-an-email"},
                                  {"user_id": "abc"}])
def test_add_member_validation_errors_are_422(world, body):
    assert world.a.c.post(f"/api/projects/{world.a.id}/members", json=body).status_code == 422


@pytest.mark.plan("PROJ-05")
def test_only_admin_can_add_members(world, make_user):
    u = make_user(tag="mem_")
    for role in ("editor", "contributor", "reporter"):
        assert world.client(role).post(f"/api/projects/{world.a.id}/members", json={"user_id": u.id}).status_code == 403
    assert world.roles.outsider.client.post(f"/api/projects/{world.a.id}/members",
                                            json={"user_id": u.id}).status_code == 403
    assert u.client.get(f"/api/projects/{world.a.id}").status_code == 403


@pytest.mark.plan("PROJ-05")
def test_member_list_visible_to_members_only(world):
    assert world.roles.reporter.client.get(f"/api/projects/{world.a.id}/members").status_code == 200
    assert world.roles.outsider.client.get(f"/api/projects/{world.a.id}/members").status_code == 403


# =================================================================== PROJ-06
@pytest.mark.plan("PROJ-06")
@pytest.mark.parametrize("new_role", ROLE_NAMES)
def test_admin_changes_member_role(world, new_role):
    r = ok(world.a.c.patch(f"/api/projects/{world.a.id}/members/{world.roles.contributor.id}", json={"role": new_role}))
    assert r.json()["role"] == new_role
    members = ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()
    assert {m["user"]["id"]: m["role"] for m in members}[world.roles.contributor.id] == new_role
    stats = ok(world.roles.contributor.client.get(f"/api/projects/{world.a.id}/stats")).json()
    assert stats["role"] == new_role                                    # takes effect immediately


@pytest.mark.plan("PROJ-06")
def test_owner_role_is_fixed_and_absent_users_rejected(world):
    base = f"/api/projects/{world.a.id}/members"
    assert world.a.c.patch(f"{base}/{world.roles.admin.id}", json={"role": "reporter"}).status_code == 400
    assert world.a.c.patch(f"{base}/987654321", json={"role": "editor"}).status_code == 400
    assert world.a.c.patch(f"{base}/{world.roles.outsider.id}", json={"role": "editor"}).status_code == 400
    assert world.a.c.patch(f"{base}/{world.roles.editor.id}", json={"role": "boss"}).status_code == 422
    assert world.a.c.delete(f"{base}/{world.roles.admin.id}").status_code == 400   # owner cannot be removed
    assert world.a.c.delete(f"{base}/987654321").status_code == 400
    owner = [m for m in ok(world.a.c.get(base)).json() if m["user"]["id"] == world.roles.admin.id][0]
    assert owner["role"] == "admin"


@pytest.mark.plan("PROJ-06")
def test_non_admin_cannot_change_or_remove_members(world):
    base = f"/api/projects/{world.a.id}/members"
    for role in ("editor", "contributor", "reporter"):
        c = world.client(role)
        assert c.patch(f"{base}/{world.roles.reporter.id}", json={"role": "admin"}).status_code == 403
        assert c.delete(f"{base}/{world.roles.reporter.id}").status_code == 403
    out = world.roles.outsider.client
    assert out.patch(f"{base}/{world.roles.reporter.id}", json={"role": "admin"}).status_code == 403
    assert out.delete(f"{base}/{world.roles.reporter.id}").status_code == 403
    roles = {m["user"]["id"]: m["role"] for m in ok(world.a.c.get(base)).json()}
    assert roles[world.roles.reporter.id] == "reporter"


@pytest.mark.plan("PROJ-06")
def test_remove_member_ends_access_and_repeat_is_rejected(world):
    base = f"/api/projects/{world.a.id}/members/{world.roles.reporter.id}"
    assert world.a.c.delete(base).status_code == 204
    assert world.roles.reporter.client.get(f"/api/projects/{world.a.id}").status_code == 403
    assert world.a.c.delete(base).status_code == 400


# =================================================================== PROJ-07
@pytest.mark.plan("PROJ-07")
def test_removed_member_with_tickets_and_history_keeps_data_consistent(world):
    contrib = world.roles.contributor
    own = world.a.ticket(client=contrib.client, title="reported by contributor")
    assigned = world.a.ticket(title="assigned to contributor", assignee_id=contrib.id, tester_id=contrib.id)
    ok(contrib.client.patch(f"/api/tickets/{own['id']}", json={"title": "edited by contributor"}))

    assert world.a.c.delete(f"/api/projects/{world.a.id}/members/{contrib.id}").status_code == 204

    tickets = {t["id"]: t for t in world.a.tickets()}
    assert tickets[own["id"]]["reporter"]["id"] == contrib.id                  # references stay valid
    assert tickets[assigned["id"]]["assignee"]["id"] == contrib.id
    hist = ok(world.a.c.get(f"/api/tickets/{own['id']}")).json()["history"]
    assert any(h["user_id"] == contrib.id and h["field_changed"] == "title" for h in hist)

    c = contrib.client                                                           # access ends immediately
    for path in (f"/api/projects/{world.a.id}", f"/api/projects/{world.a.id}/columns",
                 f"/api/projects/{world.a.id}/stats", f"/api/tickets/project/{world.a.id}",
                 f"/api/tickets/{own['id']}", f"/api/roadmap/project/{world.a.id}"):
        assert c.get(path).status_code == 403, path
    assert c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x"}).status_code == 403
    assert c.patch(f"/api/tickets/{own['id']}", json={"title": "again"}).status_code == 403
    assert world.a.id not in {p["id"] for p in ok(c.get("/api/projects")).json()}


# =================================================================== PROJ-08
def columns(world):
    return ok(world.a.c.get(f"/api/projects/{world.a.id}/columns")).json()


def names(cols):
    return [c["name"] for c in sorted(cols, key=lambda c: c["position"])]


@pytest.mark.plan("PROJ-08")
def test_create_column_appends_by_default_and_inserts_at_position(world):
    base = f"/api/projects/{world.a.id}/columns"
    end = ok(world.a.c.post(base, json={"name": "Review"}), 201).json()
    assert end["position"] == 8 and end["is_done"] is False
    first = ok(world.a.c.post(base, json={"name": "Inbox", "position": 0}), 201).json()
    mid = ok(world.a.c.post(base, json={"name": "Middle", "position": 3}), 201).json()
    cols = columns(world)
    assert [c["position"] for c in sorted(cols, key=lambda c: c["position"])] == list(range(len(cols)))
    order = names(cols)
    assert order[0] == "Inbox" and order[3] == "Middle" and order[-1] == "Review"
    assert first["position"] == 0 and mid["position"] == 3


@pytest.mark.plan("PROJ-08")
def test_rename_and_validation(world):
    col = columns(world)[0]
    path = f"/api/projects/{world.a.id}/columns/{col['id']}"
    assert ok(world.a.c.patch(path, json={"name": "Backlog"})).json()["name"] == "Backlog"
    assert world.a.c.patch(path, json={"name": ""}).status_code == 422
    assert world.a.c.patch(path, json={"name": "n" * 51}).status_code == 422
    assert world.a.c.post(f"/api/projects/{world.a.id}/columns", json={"name": ""}).status_code == 422
    assert world.a.c.post(f"/api/projects/{world.a.id}/columns", json={"name": "n" * 51}).status_code == 422
    assert world.a.c.patch(f"/api/projects/{world.a.id}/columns/987654321", json={"name": "x"}).status_code == 404
    assert "Backlog" in names(columns(world))


@pytest.mark.plan("PROJ-08")
@pytest.mark.parametrize("name,new_pos,expected", [
    ("Open", 2, ["ToDo", "In Progress", "Open", "Ready For Testing", "Testing", "Ready for Deploy", "Deployed", "Done"]),
    ("Done", 0, ["Done", "Open", "ToDo", "In Progress", "Ready For Testing", "Testing", "Ready for Deploy", "Deployed"]),
    ("Testing", 1, ["Open", "Testing", "ToDo", "In Progress", "Ready For Testing", "Ready for Deploy", "Deployed", "Done"]),
])
def test_reorder_column_persists_and_keeps_positions_contiguous(world, name, new_pos, expected):
    col = next(c for c in columns(world) if c["name"] == name)
    ok(world.a.c.patch(f"/api/projects/{world.a.id}/columns/{col['id']}", json={"position": new_pos}))
    cols = columns(world)
    assert names(cols) == expected
    assert sorted(c["position"] for c in cols) == list(range(len(cols)))
    assert names(ok(world.roles.reporter.client.get(f"/api/projects/{world.a.id}/columns")).json()) == expected


@pytest.mark.plan("PROJ-08")
def test_null_column_position_should_be_ignored_or_422(world):
    col = columns(world)[0]
    r = world.a.c.patch(f"/api/projects/{world.a.id}/columns/{col['id']}", json={"position": None})
    assert r.status_code in (200, 422)


@pytest.mark.plan("PROJ-08", "TICKET-09")
def test_toggle_done_sets_and_clears_closed_at_for_tickets_in_column(world):
    t = world.a.ticket()
    todo = world.a.columns["Open"]
    path = f"/api/projects/{world.a.id}/columns/{todo}"
    ok(world.a.c.patch(path, json={"is_done": True}))
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["closed_at"] is not None
    assert world.a.stats()["tickets_done"] == 1
    ok(world.a.c.patch(path, json={"is_done": False}))
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["closed_at"] is None
    assert world.a.stats()["tickets_done"] == 0


@pytest.mark.plan("PROJ-08", "CLAR")
@pytest.mark.characterization
def test_multiple_done_columns_are_currently_allowed_and_both_count_as_done(world):
    t1, t2 = world.a.ticket(), world.a.ticket()
    ok(world.a.c.patch(f"/api/projects/{world.a.id}/columns/{world.a.columns['Deployed']}", json={"is_done": True}))
    world.a.move(t1["id"], "Deployed")
    world.a.move(t2["id"], "Done")
    assert sum(c["is_done"] for c in columns(world)) == 2
    assert world.a.stats()["tickets_done"] == 2


@pytest.mark.plan("PROJ-08")
def test_moving_tickets_updates_stats(world):
    t = world.a.ticket()
    assert world.a.stats()["tickets_open"] == 1
    world.a.move(t["id"], "Done")
    s = world.a.stats()
    assert (s["tickets_done"], s["tickets_open"], s["by_column"]) == (1, 0, {"Done": 1})


@pytest.mark.plan("PROJ-08")
def test_only_admin_can_configure_columns(world):
    base = f"/api/projects/{world.a.id}/columns"
    col = columns(world)[0]["id"]
    for role in ("editor", "contributor", "reporter"):
        c = world.client(role)
        assert c.post(base, json={"name": "X"}).status_code == 403
        assert c.patch(f"{base}/{col}", json={"name": "X"}).status_code == 403
        assert c.delete(f"{base}/{col}").status_code == 403
    assert "X" not in names(columns(world))


# =================================================================== PROJ-09
@pytest.mark.plan("PROJ-09")
def test_delete_empty_column_compacts_positions(world):
    base = f"/api/projects/{world.a.id}/columns"
    col = columns(world)[2]
    assert world.a.c.delete(f"{base}/{col['id']}").status_code == 204
    cols = columns(world)
    assert col["name"] not in names(cols) and len(cols) == 7
    assert sorted(c["position"] for c in cols) == list(range(7))


@pytest.mark.plan("PROJ-09")
def test_delete_occupied_column_needs_target_and_is_atomic(world):
    t = world.a.ticket()                                  # in "Open"
    base = f"/api/projects/{world.a.id}/columns"
    open_id, done_id = world.a.columns["Open"], world.a.columns["Done"]
    r = world.a.c.delete(f"{base}/{open_id}")
    assert r.status_code == 409 and "move_tickets_to" in r.json()["detail"]
    other = ok(world.b.c.get(f"/api/projects/{world.b.id}/columns")).json()[0]["id"]
    for bad in (open_id, other, 987654321):               # same column / foreign project / missing
        assert world.a.c.delete(f"{base}/{open_id}", params={"move_tickets_to": bad}).status_code == 400
    assert open_id in {c["id"] for c in columns(world)}
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["column_id"] == open_id


@pytest.mark.plan("PROJ-09")
def test_delete_occupied_column_with_valid_target_moves_tickets(world):
    t1, t2 = world.a.ticket(), world.a.ticket()
    base = f"/api/projects/{world.a.id}/columns"
    open_id, todo_id = world.a.columns["Open"], world.a.columns["ToDo"]
    assert world.a.c.delete(f"{base}/{open_id}", params={"move_tickets_to": todo_id}).status_code == 204
    for t in (t1, t2):
        assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["column_id"] == todo_id
    assert open_id not in {c["id"] for c in columns(world)}
    assert world.a.stats()["by_column"] == {"ToDo": 2}


@pytest.mark.plan("PROJ-09")
def test_delete_empty_column_with_valid_target_succeeds(world):
    c = ok(world.a.c.post(f"/api/projects/{world.a.id}/columns", json={"name": "Tmp"}), 201).json()
    assert world.a.c.delete(f"/api/projects/{world.a.id}/columns/{c['id']}",
                            params={"move_tickets_to": world.a.columns["Open"]}).status_code == 204


@pytest.mark.plan("PROJ-09")
def test_delete_unknown_or_foreign_column_is_404(world):
    foreign = ok(world.b.c.get(f"/api/projects/{world.b.id}/columns")).json()[0]["id"]
    base = f"/api/projects/{world.a.id}/columns"
    assert world.a.c.delete(f"{base}/987654321").status_code == 404
    assert world.a.c.delete(f"{base}/{foreign}").status_code == 404
    assert ok(world.b.c.get(f"/api/projects/{world.b.id}/columns")).json()[0]["id"] == foreign


@pytest.mark.plan("PROJ-09", "TICKET-09")
def test_tickets_moved_into_done_column_by_column_delete_get_closed(world):
    t = world.a.ticket()
    world.a.c.delete(f"/api/projects/{world.a.id}/columns/{world.a.columns['Open']}",
                     params={"move_tickets_to": world.a.columns["Done"]})
    fresh = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert world.a.stats()["tickets_done"] == 1 and fresh["closed_at"] is not None


# =================================================================== PROJ-10
@pytest.mark.plan("PROJ-10")
def test_stats_for_empty_project_for_every_role(world):
    for role in ROLE_NAMES:
        s = ok(world.client(role).get(f"/api/projects/{world.a.id}/stats")).json()
        assert s["role"] == role and s["project_id"] == world.a.id and s["key"] == world.a.key
        assert (s["tickets_total"], s["tickets_done"], s["tickets_open"]) == (0, 0, 0)
        assert s["by_type"] == {} and s["by_column"] == {} and s["avg_lifetime_hours"] is None


@pytest.mark.plan("PROJ-10")
def test_stats_count_assigned_and_unassigned_tickets_for_all_roles(world):
    world.a.ticket(assignee_id=world.roles.editor.id)
    world.a.ticket()
    t = world.a.ticket(type="Bug")
    world.a.move(t["id"], "Done")
    for role in ROLE_NAMES:
        s = ok(world.client(role).get(f"/api/projects/{world.a.id}/stats")).json()
        assert (s["tickets_total"], s["tickets_done"], s["tickets_open"]) == (3, 1, 2)
        assert s["by_type"] == {"Task": 2, "Bug": 1}
        assert s["avg_lifetime_hours"] is not None


@pytest.mark.plan("PROJ-10")
def test_stats_denied_for_non_member_and_unknown_project(world):
    assert world.roles.outsider.client.get(f"/api/projects/{world.a.id}/stats").status_code == 403
    assert world.roles.outsider.client.get("/api/projects/987654321/stats").status_code == 404


# =================================================================== PROJ-11
@pytest.mark.plan("PROJ-11")
def test_cross_project_member_and_column_ids_cannot_be_used(world):
    a_only = world.roles.editor                           # member of A, not of B
    a_col = world.a.columns["Open"]
    b_col = world.b.columns["Open"]
    base_b = f"/api/projects/{world.b.id}"
    assert world.b.c.patch(f"{base_b}/members/{a_only.id}", json={"role": "admin"}).status_code == 400
    assert world.b.c.delete(f"{base_b}/members/{a_only.id}").status_code == 400
    assert world.b.c.patch(f"{base_b}/columns/{a_col}", json={"name": "HACK"}).status_code == 404
    assert world.b.c.delete(f"{base_b}/columns/{a_col}").status_code == 404
    assert world.a.c.patch(f"/api/projects/{world.a.id}/columns/{b_col}", json={"name": "HACK"}).status_code == 404
    assert "HACK" not in names(columns(world))
    assert "HACK" not in names(ok(world.b.c.get(f"{base_b}/columns")).json())
    roles_in_a = {m["user"]["id"]: m["role"] for m in ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()}
    assert roles_in_a[a_only.id] == "editor"


@pytest.mark.plan("PROJ-11")
def test_cross_project_tickets_are_not_readable_or_writable(world):
    t_b = world.b.ticket(title="secret-b-ticket")
    c = world.a.c
    for path in (f"/api/tickets/{t_b['id']}", f"/api/tickets/key/{t_b['key']}", f"/api/tickets/project/{world.b.id}"):
        r = c.get(path)
        assert r.status_code == 403 and "secret-b-ticket" not in r.text, path
    assert c.patch(f"/api/tickets/{t_b['id']}", json={"title": "HACK"}).status_code == 403
    assert c.patch(f"/api/tickets/{t_b['id']}/column", json={"column_id": world.b.columns["Done"]}).status_code == 403
    assert c.delete(f"/api/tickets/{t_b['id']}").status_code == 403
    assert ok(world.b.c.get(f"/api/tickets/{t_b['id']}")).json()["title"] == "secret-b-ticket"


@pytest.mark.plan("PROJ-11", "TICKET-02")
def test_ticket_in_a_cannot_reference_column_of_b(world):
    t = world.a.ticket()
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "column_id": world.b.columns["Open"]})
    assert r.status_code == 400
    r = world.a.c.patch(f"/api/tickets/{t['id']}", json={"column_id": world.b.columns["Done"]})
    assert r.status_code == 400
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["column_id"] == world.a.columns["Open"]
