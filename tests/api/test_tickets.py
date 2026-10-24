"""Section 5 - tickets, hierarchy, permissions, history and board (API / backend)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from framework.client import Client
from framework.factory import deactivate, ok

pytestmark = pytest.mark.api

TYPES = ["Idea", "Epic", "Task", "Subtask", "Bug", "Incident"]
ROLE_NAMES = ["admin", "editor", "contributor", "reporter"]


def seq(key: str) -> int:
    return int(key.rsplit("-", 1)[1])


def get(world, tid, role="admin"):
    return ok(world.client(role).get(f"/api/tickets/{tid}")).json()


def history(world, tid, field=None):
    h = get(world, tid)["history"]
    return [x for x in h if field is None or x["field_changed"] == field]


# =================================================================== TICKET-01
@pytest.mark.plan("TICKET-01")
def test_create_each_type_with_sequential_project_prefixed_keys(world):
    keys = []
    for tp in TYPES:
        t = world.a.ticket(type=tp, title=f"{tp} sample", description=f"about {tp}")
        assert t["type"] == tp and t["title"] == f"{tp} sample" and t["description"] == f"about {tp}"
        assert t["project_id"] == world.a.id and t["reporter"]["id"] == world.roles.admin.id
        keys.append(t["key"])
    assert keys == [f"{world.a.key}-{i}" for i in range(1, 7)]
    assert len(set(keys)) == 6


@pytest.mark.plan("TICKET-01")
def test_defaults_are_applied(world):
    t = ok(world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "Only title"}), 201).json()
    assert t["type"] == "Task" and t["description"] is None
    assert t["column_id"] == world.a.columns["Open"] and t["column"]["name"] == "Open"
    assert t["assignee"] is None and t["tester"] is None and t["parent_id"] is None
    assert t["milestone_id"] is None and t["closed_at"] is None and t["ancestors"] == [] and t["attachments"] == []
    assert [(h["field_changed"], h["old_value"], h["new_value"]) for h in t["history"]] == [("column", None, "Open")]
    assert t["history"][0]["user_id"] == world.roles.admin.id


@pytest.mark.plan("TICKET-01")
@pytest.mark.parametrize("role", ROLE_NAMES)
def test_every_role_can_create_and_becomes_reporter(world, role):
    t = world.a.ticket(client=world.client(role))
    assert t["reporter"]["id"] == world.roles.by_name(role).id


@pytest.mark.plan("TICKET-01")
def test_create_in_specific_column_and_in_done_column_sets_closed_at(world):
    t = world.a.ticket(column_id=world.a.columns["In Progress"])
    assert t["column"]["name"] == "In Progress" and t["closed_at"] is None
    d = world.a.ticket(column_id=world.a.columns["Done"])
    assert d["closed_at"] is not None


@pytest.mark.plan("TICKET-01", "TICKET-14")
def test_unicode_and_boundary_titles(world):
    assert world.a.ticket(title="Тікет №1 — 🚀 日本語")["title"] == "Тікет №1 — 🚀 日本語"
    assert len(world.a.ticket(title="t" * 200)["title"]) == 200
    assert world.a.ticket(title="x")["title"] == "x"
    assert len(world.a.ticket(description="d" * 50000)["description"]) == 50000


# =================================================================== TICKET-02
INVALID_CREATE = {
    "missing_title": {"type": "Task"},
    "blank_title": {"title": ""},
    "title_201_chars": {"title": "t" * 201},
    "invalid_type": {"title": "x", "type": "Story"},
    "column_not_int": {"title": "x", "column_id": "abc"},
    "assignee_not_int": {"title": "x", "assignee_id": "abc"},
    "tester_not_int": {"title": "x", "tester_id": []},
    "parent_not_int": {"title": "x", "parent_id": "abc"},
    "milestone_not_int": {"title": "x", "milestone_id": "abc"},
    "title_wrong_type": {"title": 123},
    "subtask_blank_title": {"title": "x", "type": "Task", "subtasks": [{"title": ""}]},
    "subtasks_not_list": {"title": "x", "subtasks": "nope"},
}


@pytest.mark.plan("TICKET-02")
@pytest.mark.parametrize("case", sorted(INVALID_CREATE))
def test_invalid_create_payload_is_422_and_leaves_no_trace(world, case):
    before = world.a.tickets()
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json=INVALID_CREATE[case])
    assert r.status_code == 422
    assert world.a.tickets() == before


@pytest.mark.plan("TICKET-02")
def test_unknown_project_and_foreign_or_unknown_column(world):
    assert world.a.c.post("/api/tickets/project/987654321", json={"title": "x"}).status_code == 404
    assert world.a.c.post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "x", "column_id": 987654321}).status_code == 400
    assert world.a.c.post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "x", "column_id": world.b.columns["Open"]}).status_code == 400


@pytest.mark.plan("TICKET-02")
def test_failed_creations_do_not_consume_key_sequence(world):
    first = world.a.ticket()
    base = f"/api/tickets/project/{world.a.id}"
    assert world.a.c.post(base, json={"title": "x", "column_id": 987654321}).status_code == 400
    assert world.a.c.post(base, json={"title": "x", "parent_id": 987654321}).status_code == 400
    assert world.a.c.post(base, json={"title": "x", "milestone_id": 987654321}).status_code == 400
    assert world.a.c.post(base, json={"title": "x", "assignee_id": world.roles.outsider.id}).status_code == 400
    assert world.a.c.post(base, json={"title": ""}).status_code == 422
    second = world.a.ticket()
    assert seq(second["key"]) == seq(first["key"]) + 1
    assert len(world.a.tickets()) == 2


@pytest.mark.plan("TICKET-02")
def test_whitespace_only_title_should_be_rejected(world):
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "     "})
    assert r.status_code in (400, 422)


# =================================================================== TICKET-03
@pytest.mark.plan("TICKET-03")
def test_assign_and_test_by_project_members_including_self(world):
    me = world.roles.admin
    t = world.a.ticket(assignee_id=world.roles.editor.id, tester_id=world.roles.reporter.id)
    assert t["assignee"]["id"] == world.roles.editor.id and t["tester"]["id"] == world.roles.reporter.id
    own = world.a.ticket(assignee_id=me.id, tester_id=me.id)                # self
    assert own["assignee"]["id"] == own["tester"]["id"] == own["reporter"]["id"] == me.id
    upd = ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"assignee_id": world.roles.contributor.id})).json()
    assert upd["assignee"]["id"] == world.roles.contributor.id


@pytest.mark.plan("TICKET-03")
def test_non_member_or_unknown_user_cannot_be_assigned(world):
    t = world.a.ticket()
    out = world.roles.outsider.id
    base = f"/api/tickets/project/{world.a.id}"
    for field in ("assignee_id", "tester_id"):
        for uid_ in (out, 987654321):
            assert world.a.c.post(base, json={"title": "x", field: uid_}).status_code == 400
            assert world.a.c.patch(f"/api/tickets/{t['id']}", json={field: uid_}).status_code == 400
    assert world.a.c.post(base, json={"title": "x", "type": "Task",
                                      "subtasks": [{"title": "s", "assignee_id": out}]}).status_code == 400
    fresh = get(world, t["id"])
    assert fresh["assignee"] is None and fresh["tester"] is None
    assert len(world.a.tickets()) == 1


@pytest.mark.plan("TICKET-03")
def test_removed_member_cannot_be_assigned_anymore(world, make_user):
    u = make_user(tag="asg_")
    world.a.add_member(u, "contributor")
    t = world.a.ticket(assignee_id=u.id)
    ok(world.a.c.delete(f"/api/projects/{world.a.id}/members/{u.id}"), 204)
    assert world.a.c.patch(f"/api/tickets/{t['id']}", json={"assignee_id": u.id}).status_code == 400
    assert world.a.c.post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "x", "tester_id": u.id}).status_code == 400


@pytest.mark.plan("TICKET-03")
def test_deactivated_user_should_not_be_assignable(world, make_user):
    u = make_user(tag="asg_")
    world.a.add_member(u, "contributor")
    deactivate(u)
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "assignee_id": u.id})
    assert r.status_code == 400


# =================================================================== TICKET-04
ALLOWED = [("Idea", "Epic"), ("Idea", "Task"), ("Epic", "Task"), ("Epic", "Subtask"), ("Epic", "Bug"),
           ("Task", "Subtask"), ("Task", "Bug"), ("Task", "Incident")]
ILLEGAL = [("Task", "Epic"), ("Task", "Idea"), ("Task", "Task"), ("Epic", "Idea"), ("Epic", "Epic"),
           ("Epic", "Incident"), ("Idea", "Subtask"), ("Idea", "Bug"), ("Idea", "Incident"), ("Idea", "Idea"),
           ("Subtask", "Task"), ("Subtask", "Subtask"), ("Bug", "Subtask"), ("Bug", "Task"),
           ("Incident", "Task"), ("Incident", "Bug")]


@pytest.mark.plan("TICKET-04")
@pytest.mark.parametrize("parent_type,child_type", ALLOWED)
def test_allowed_parent_child_combinations(world, parent_type, child_type):
    p = world.a.ticket(type=parent_type)
    c = world.a.ticket(type=child_type, parent_id=p["id"])
    assert c["parent_id"] == p["id"]
    assert [a["key"] for a in c["ancestors"]] == [p["key"]]
    assert c["ancestors"][0] == {"id": p["id"], "key": p["key"], "title": p["title"], "type": parent_type}


@pytest.mark.plan("TICKET-04")
def test_nested_hierarchy_has_root_first_ancestor_chain(world):
    idea = world.a.ticket(type="Idea")
    epic = world.a.ticket(type="Epic", parent_id=idea["id"])
    task = world.a.ticket(type="Task", parent_id=epic["id"])
    sub = world.a.ticket(type="Subtask", parent_id=task["id"])
    chain = [a["key"] for a in get(world, sub["id"])["ancestors"]]
    assert chain == [idea["key"], epic["key"], task["key"]]
    by_key = ok(world.a.c.get(f"/api/tickets/key/{sub['key']}")).json()
    assert [a["type"] for a in by_key["ancestors"]] == ["Idea", "Epic", "Task"]


@pytest.mark.plan("TICKET-04")
def test_subtasks_created_together_with_parent(world, make_user):
    m = world.a.milestone()
    t = world.a.ticket(type="Task", milestone_id=m["id"], assignee_id=world.roles.editor.id, subtasks=[
        {"title": "  s1  ", "type": "Subtask", "assignee_id": world.roles.reporter.id},
        {"title": "s2", "type": "Subtask"}, {"title": "bug", "type": "Bug"}, {"title": "inc", "type": "Incident"}])
    children = [x for x in world.a.tickets() if x["parent_id"] == t["id"]]
    assert sorted(x["title"] for x in children) == ["bug", "inc", "s1", "s2"]          # title trimmed
    assert sorted(seq(x["key"]) for x in children) == [seq(t["key"]) + i for i in (1, 2, 3, 4)]
    for ch in children:
        assert ch["column_id"] == world.a.columns["Open"] and ch["milestone_id"] == m["id"]
        assert ch["reporter"]["id"] == world.roles.admin.id
    s1 = next(x for x in children if x["title"] == "s1")
    assert s1["assignee"]["id"] == world.roles.reporter.id


@pytest.mark.plan("TICKET-04")
def test_multiple_children_under_one_parent(world):
    epic = world.a.ticket(type="Epic")
    kids = [world.a.ticket(type="Task", parent_id=epic["id"]) for _ in range(3)]
    assert len([t for t in world.a.tickets() if t["parent_id"] == epic["id"]]) == 3
    assert all(k["ancestors"][0]["id"] == epic["id"] for k in kids)


# =================================================================== TICKET-05
@pytest.mark.plan("TICKET-05")
@pytest.mark.parametrize("parent_type,child_type", ILLEGAL)
def test_illegal_child_type_is_400_without_creating_a_ticket(world, parent_type, child_type):
    p = world.a.ticket(type=parent_type)
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "type": child_type,
                                                                  "parent_id": p["id"]})
    assert r.status_code == 400 and "cannot be a child" in r.json()["detail"]
    assert len(world.a.tickets()) == 1


@pytest.mark.plan("TICKET-05")
def test_missing_and_foreign_parent_are_400_with_stable_message(world):
    foreign = world.b.ticket(type="Epic")
    for pid in (987654321, foreign["id"]):
        r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "type": "Task", "parent_id": pid})
        assert r.status_code == 400 and r.json()["detail"] == "Parent ticket not found in this project"
    t = world.a.ticket()
    r = world.a.c.patch(f"/api/tickets/{t['id']}", json={"parent_id": foreign["id"]})
    assert r.status_code == 400 and get(world, t["id"])["parent_id"] is None


@pytest.mark.plan("TICKET-05")
def test_self_parent_is_rejected(world):
    t = world.a.ticket(type="Task")
    r = world.a.c.patch(f"/api/tickets/{t['id']}", json={"parent_id": t["id"]})
    assert r.status_code == 400 and r.json()["detail"] == "Ticket cannot be its own parent or ancestor"
    assert get(world, t["id"])["parent_id"] is None


@pytest.mark.plan("TICKET-05")
def test_ancestor_cycle_attempts_are_rejected_and_graph_unchanged(world):
    idea = world.a.ticket(type="Idea")
    epic = world.a.ticket(type="Epic", parent_id=idea["id"])
    task = world.a.ticket(type="Task", parent_id=epic["id"])
    for victim, new_parent in ((idea, task), (idea, epic), (epic, task)):
        r = world.a.c.patch(f"/api/tickets/{victim['id']}", json={"parent_id": new_parent["id"]})
        assert r.status_code == 400, (victim["type"], new_parent["type"])
    assert get(world, idea["id"])["parent_id"] is None
    assert get(world, epic["id"])["parent_id"] == idea["id"]
    assert get(world, task["id"])["parent_id"] == epic["id"]


@pytest.mark.plan("TICKET-05")
@pytest.mark.parametrize("parent_type,subtask_type", [("Task", "Epic"), ("Task", "Idea"), ("Task", "Task"),
                                                      ("Idea", "Subtask"), ("Bug", "Subtask"), ("Subtask", "Subtask"),
                                                      ("Epic", "Incident"), ("Incident", "Bug")])
def test_invalid_subtask_type_for_new_ticket_is_rejected_atomically(world, parent_type, subtask_type):
    r = world.a.c.post(f"/api/tickets/project/{world.a.id}", json={
        "title": "x", "type": parent_type, "subtasks": [{"title": "ok", "type": "Subtask" if parent_type != "Idea" else "Epic"},
                                                          {"title": "bad", "type": subtask_type}]})
    assert r.status_code == 400
    assert world.a.tickets() == []


@pytest.mark.plan("TICKET-05")
def test_reparenting_and_detaching(world):
    i1, i2 = world.a.ticket(type="Idea"), world.a.ticket(type="Idea")
    t = world.a.ticket(type="Task", parent_id=i1["id"])
    moved = ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"parent_id": i2["id"]})).json()
    assert moved["parent_id"] == i2["id"] and moved["ancestors"][0]["key"] == i2["key"]
    h = history(world, t["id"], "parent")
    assert [(x["old_value"], x["new_value"]) for x in h] == [(i1["key"], i2["key"])]
    detached = ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"parent_id": None})).json()
    assert detached["parent_id"] is None and detached["ancestors"] == []


@pytest.mark.plan("TICKET-05")
def test_changing_parent_to_illegal_combination_is_rejected(world):
    task = world.a.ticket(type="Task")
    epic = world.a.ticket(type="Epic")
    assert world.a.c.patch(f"/api/tickets/{epic['id']}", json={"parent_id": task["id"]}).status_code == 400
    assert get(world, epic["id"])["parent_id"] is None


# =================================================================== TICKET-06
@pytest.mark.plan("TICKET-06")
def test_set_change_and_clear_milestone_with_history(world):
    m1, m2 = world.a.milestone(title="Alpha"), world.a.milestone(title="Beta")
    t = world.a.ticket()
    c = world.a.c
    assert ok(c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": m1["id"]})).json()["milestone_id"] == m1["id"]
    assert ok(c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": m2["id"]})).json()["milestone_id"] == m2["id"]
    assert ok(c.patch(f"/api/tickets/{t['id']}", json={"title": "other"})).json()["milestone_id"] == m2["id"]  # omitted
    assert ok(c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": None})).json()["milestone_id"] is None
    assert [(h["old_value"], h["new_value"]) for h in history(world, t["id"], "milestone")] == [
        (None, "Alpha"), ("Alpha", "Beta"), ("Beta", None)]


@pytest.mark.plan("TICKET-06")
def test_create_with_milestone_and_foreign_or_missing_milestone(world):
    m = world.a.milestone()
    foreign = world.b.milestone()
    t = world.a.ticket(milestone_id=m["id"])
    assert t["milestone_id"] == m["id"]
    base = f"/api/tickets/project/{world.a.id}"
    for bad in (foreign["id"], 987654321):
        r = world.a.c.post(base, json={"title": "x", "milestone_id": bad})
        assert r.status_code == 400 and r.json()["detail"] == "Milestone not found in this project"
        assert world.a.c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": bad}).status_code == 400
    assert get(world, t["id"])["milestone_id"] == m["id"]
    assert len(world.a.tickets()) == 1


# =================================================================== TICKET-07
@pytest.mark.plan("TICKET-07")
def test_list_returns_all_project_tickets_newest_first_with_full_schema(world):
    ts = [world.a.ticket(title=f"n{i}") for i in range(3)]
    world.b.ticket(title="belongs to B")
    listing = world.a.tickets()
    assert [t["id"] for t in listing] == [t["id"] for t in reversed(ts)]
    for field in ("id", "key", "title", "description", "type", "project_id", "column_id", "column", "parent_id",
                  "milestone_id", "ancestors", "assignee", "tester", "reporter", "created_at", "closed_at",
                  "attachments", "history"):
        assert field in listing[0], field
    for role in ROLE_NAMES:       # every role can read
        assert len(ok(world.client(role).get(f"/api/tickets/project/{world.a.id}")).json()) == 3


@pytest.mark.plan("TICKET-07")
def test_get_by_id_and_by_key_are_consistent(world):
    t = world.a.ticket(title="lookup")
    by_id = ok(world.roles.reporter.client.get(f"/api/tickets/{t['id']}")).json()
    by_key = ok(world.roles.reporter.client.get(f"/api/tickets/key/{t['key']}")).json()
    assert by_id == by_key and by_id["title"] == "lookup"


@pytest.mark.plan("TICKET-07")
def test_unknown_ids_keys_projects_and_non_member_access(world):
    t = world.a.ticket()
    c = world.a.c
    assert c.get("/api/tickets/987654321").status_code == 404
    assert c.get(f"/api/tickets/key/{world.a.key}-9999").status_code == 404
    assert c.get("/api/tickets/key/NOPE-1").status_code == 404
    assert c.get("/api/tickets/project/987654321").status_code == 404
    assert c.get("/api/tickets/abc").status_code == 422
    out = world.roles.outsider.client
    for path in (f"/api/tickets/{t['id']}", f"/api/tickets/key/{t['key']}", f"/api/tickets/project/{world.a.id}"):
        r = out.get(path)
        assert r.status_code == 403 and t["title"] not in r.text


# =================================================================== TICKET-08
@pytest.mark.plan("TICKET-08")
def test_patch_each_editable_field(world):
    m = world.a.milestone()
    t = world.a.ticket(title="orig", description="orig d")
    c = world.a.c
    p = f"/api/tickets/{t['id']}"
    assert ok(c.patch(p, json={"title": "new"})).json()["title"] == "new"
    assert ok(c.patch(p, json={"description": "new d"})).json()["description"] == "new d"
    assert ok(c.patch(p, json={"type": "Bug"})).json()["type"] == "Bug"
    assert ok(c.patch(p, json={"assignee_id": world.roles.editor.id})).json()["assignee"]["id"] == world.roles.editor.id
    assert ok(c.patch(p, json={"tester_id": world.roles.reporter.id})).json()["tester"]["id"] == world.roles.reporter.id
    assert ok(c.patch(p, json={"column_id": world.a.columns["Testing"]})).json()["column"]["name"] == "Testing"
    assert ok(c.patch(p, json={"milestone_id": m["id"]})).json()["milestone_id"] == m["id"]
    final = get(world, t["id"])
    assert (final["title"], final["description"], final["type"]) == ("new", "new d", "Bug")


@pytest.mark.plan("TICKET-08")
def test_omitted_fields_stay_unchanged_and_null_clears_nullable_ones(world):
    m = world.a.milestone()
    parent = world.a.ticket(type="Epic")
    t = world.a.ticket(description="keep", assignee_id=world.roles.editor.id, tester_id=world.roles.reporter.id,
                       parent_id=parent["id"], milestone_id=m["id"])
    c = world.a.c
    after = ok(c.patch(f"/api/tickets/{t['id']}", json={"title": "only title"})).json()
    assert after["description"] == "keep" and after["assignee"]["id"] == world.roles.editor.id
    assert after["tester"]["id"] == world.roles.reporter.id and after["parent_id"] == parent["id"]
    assert after["milestone_id"] == m["id"]
    cleared = ok(c.patch(f"/api/tickets/{t['id']}", json={"description": None, "assignee_id": None,
                                                         "tester_id": None, "parent_id": None,
                                                         "milestone_id": None})).json()
    assert cleared["description"] is None and cleared["assignee"] is None and cleared["tester"] is None
    assert cleared["parent_id"] is None and cleared["milestone_id"] is None and cleared["title"] == "only title"


@pytest.mark.plan("TICKET-08")
def test_empty_patch_is_a_noop_without_history(world):
    t = world.a.ticket()
    before = get(world, t["id"])
    after = ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={})).json()
    assert after == before


@pytest.mark.plan("TICKET-08")
@pytest.mark.parametrize("body", [{"title": ""}, {"title": "t" * 201}, {"type": "Story"}, {"assignee_id": "x"},
                                  {"column_id": "x"}, {"parent_id": "x"}, {"milestone_id": "x"}, {"title": 5}])
def test_invalid_patch_values_are_422_and_change_nothing(world, body):
    t = world.a.ticket(title="stable")
    assert world.a.c.patch(f"/api/tickets/{t['id']}", json=body).status_code == 422
    assert get(world, t["id"])["title"] == "stable"


@pytest.mark.plan("TICKET-08")
def test_patch_unknown_column_is_400_and_unknown_ticket_404(world):
    t = world.a.ticket()
    assert world.a.c.patch(f"/api/tickets/{t['id']}", json={"column_id": 987654321}).status_code == 400
    assert world.a.c.patch("/api/tickets/987654321", json={"title": "x"}).status_code == 404
    assert world.a.c.patch("/api/tickets/987654321/column", json={"column_id": 1}).status_code == 404


@pytest.mark.plan("TICKET-08")
@pytest.mark.parametrize("field", ["title", "type"])
def test_explicit_null_for_required_field_should_be_a_client_error(world, field):
    t = world.a.ticket()
    r = world.a.c.patch(f"/api/tickets/{t['id']}", json={field: None})
    assert 400 <= r.status_code < 500
    assert get(world, t["id"])[field] is not None


# =================================================================== TICKET-09
@pytest.mark.plan("TICKET-09")
def test_move_between_columns_persists_and_logs_history(world):
    t = world.a.ticket()
    moved = world.a.move(t["id"], "In Progress")
    assert moved["column"]["name"] == "In Progress" and moved["closed_at"] is None
    assert get(world, t["id"], "reporter")["column_id"] == world.a.columns["In Progress"]
    assert [(h["old_value"], h["new_value"]) for h in history(world, t["id"], "column")] == [
        (None, "Open"), ("Open", "In Progress")]


@pytest.mark.plan("TICKET-09")
def test_move_to_same_column_is_noop(world):
    t = world.a.ticket()
    before = get(world, t["id"])
    after = world.a.move(t["id"], "Open")
    assert len(after["history"]) == len(before["history"])


@pytest.mark.plan("TICKET-09")
def test_move_to_invalid_foreign_or_unknown_column_is_400(world):
    t = world.a.ticket()
    for cid in (987654321, world.b.columns["Open"]):
        assert world.a.c.patch(f"/api/tickets/{t['id']}/column", json={"column_id": cid}).status_code == 400
    assert world.a.c.patch(f"/api/tickets/{t['id']}/column", json={}).status_code == 422
    assert get(world, t["id"])["column_id"] == world.a.columns["Open"]


@pytest.mark.plan("TICKET-09")
def test_closed_at_is_set_cleared_and_set_again(world):
    t = world.a.ticket()
    done = world.a.move(t["id"], "Done")
    first = done["closed_at"]
    assert first is not None
    reopened = world.a.move(t["id"], "In Progress")
    assert reopened["closed_at"] is None
    again = world.a.move(t["id"], "Done")
    assert again["closed_at"] is not None and again["closed_at"] >= first
    assert [h["new_value"] for h in history(world, t["id"], "column")] == ["Open", "Done", "In Progress", "Done"]
    assert world.a.stats()["tickets_done"] == 1


@pytest.mark.plan("TICKET-09")
def test_moves_between_open_columns_never_set_closed_at(world):
    t = world.a.ticket()
    for col in ("ToDo", "Testing", "Deployed"):
        assert world.a.move(t["id"], col)["closed_at"] is None


@pytest.mark.plan("TICKET-09")
def test_closed_at_is_untouched_when_other_fields_change_in_done_column(world):
    t = world.a.ticket()
    closed = world.a.move(t["id"], "Done")["closed_at"]
    again = ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "edited while done"})).json()
    assert again["closed_at"] == closed


# =================================================================== TICKET-10
@pytest.mark.plan("TICKET-10")
def test_history_records_actor_and_old_new_values_for_each_field(world):
    editor, admin = world.roles.editor, world.roles.admin
    m = world.a.milestone(title="Rel 1")
    parent = world.a.ticket(type="Epic")
    t = world.a.ticket(title="v1", description="d1")
    ed = editor.client
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"title": "v2"}))
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"description": "d2"}))
    ok(admin.client.patch(f"/api/tickets/{t['id']}", json={"type": "Bug"}))
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"assignee_id": editor.id}))
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"tester_id": world.roles.reporter.id}))
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"parent_id": parent["id"]}))
    ok(ed.patch(f"/api/tickets/{t['id']}", json={"milestone_id": m["id"]}))
    ok(ed.patch(f"/api/tickets/{t['id']}/column", json={"column_id": world.a.columns["Testing"]}))
    h = {x["field_changed"]: x for x in history(world, t["id"]) if x["field_changed"] != "column" or x["old_value"]}
    assert (h["title"]["old_value"], h["title"]["new_value"], h["title"]["user_id"]) == ("v1", "v2", editor.id)
    assert (h["description"]["old_value"], h["description"]["new_value"]) == ("d1", "d2")
    assert (h["type"]["old_value"], h["type"]["new_value"], h["type"]["user_id"]) == ("Task", "Bug", admin.id)
    assert (h["assignee_id"]["old_value"], h["assignee_id"]["new_value"]) == (None, str(editor.id))
    assert (h["tester_id"]["old_value"], h["tester_id"]["new_value"]) == (None, str(world.roles.reporter.id))
    assert (h["parent"]["old_value"], h["parent"]["new_value"]) == (None, parent["key"])
    assert (h["milestone"]["old_value"], h["milestone"]["new_value"]) == (None, "Rel 1")
    assert (h["column"]["old_value"], h["column"]["new_value"], h["column"]["user_id"]) == ("Open", "Testing", editor.id)


@pytest.mark.plan("TICKET-10")
def test_unchanged_values_produce_no_history_and_order_is_chronological(world):
    t = world.a.ticket(title="same", description="same d", assignee_id=world.roles.editor.id)
    before = len(get(world, t["id"])["history"])
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "same", "description": "same d",
                                                       "assignee_id": world.roles.editor.id, "type": "Task"}))
    assert len(get(world, t["id"])["history"]) == before
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "a"}))
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "b"}))
    ids = [h["id"] for h in get(world, t["id"])["history"]]
    assert ids == sorted(ids)
    assert [h["new_value"] for h in history(world, t["id"], "title")] == ["a", "b"]


# =================================================================== TICKET-11
def _matrix_tickets(world):
    r = world.roles
    return {
        "own_reported": world.a.ticket(client=r.contributor.client, title="contributor own"),
        "assigned": world.a.ticket(title="assigned", assignee_id=r.contributor.id),
        "tested": world.a.ticket(title="tested", tester_id=r.contributor.id),
        "admin_reported": world.a.ticket(title="admin reported"),
        "reporter_reported": world.a.ticket(client=r.reporter.client, title="reporter reported"),
    }


EDIT_MATRIX = {
    "admin": dict(own_reported=True, assigned=True, tested=True, admin_reported=True, reporter_reported=True),
    "editor": dict(own_reported=True, assigned=True, tested=True, admin_reported=True, reporter_reported=True),
    "contributor": dict(own_reported=True, assigned=True, tested=True, admin_reported=False, reporter_reported=False),
    "reporter": dict(own_reported=False, assigned=False, tested=False, admin_reported=False, reporter_reported=False),
}


@pytest.mark.plan("TICKET-11")
@pytest.mark.parametrize("role", ROLE_NAMES)
def test_edit_permission_matrix(world, role):
    tickets = _matrix_tickets(world)
    c = world.client(role)
    mismatches = []
    for label, allowed in EDIT_MATRIX[role].items():
        t = tickets[label]
        for op, call in (("edit", lambda: c.patch(f"/api/tickets/{t['id']}", json={"title": f"by {role}"})),
                         ("move", lambda: c.patch(f"/api/tickets/{t['id']}/column",
                                                  json={"column_id": world.a.columns["ToDo"]}))):
            code = call().status_code
            expected = 200 if allowed else 403
            if code != expected:
                mismatches.append(f"{role} {op} {label}: got {code}, expected {expected}")
        fresh = get(world, t["id"])
        if not allowed:
            assert fresh["title"] != f"by {role}" and fresh["column"]["name"] == "Open", f"mutation despite 403: {label}"
    assert not mismatches, "\n".join(mismatches)


@pytest.mark.plan("TICKET-11")
def test_reporter_can_create_but_not_edit_own_ticket(world):
    r = world.roles.reporter.client
    t = world.a.ticket(client=r)
    assert r.patch(f"/api/tickets/{t['id']}", json={"title": "x"}).status_code == 403
    assert r.patch(f"/api/tickets/{t['id']}/column", json={"column_id": world.a.columns["Done"]}).status_code == 403


@pytest.mark.plan("TICKET-11", "CLAR")
@pytest.mark.characterization
def test_contributor_edit_eligibility_is_reporter_assignee_or_tester(world):
    """Documents can_edit_ticket for contributors (TEST_PLAN section 11)."""
    tickets = _matrix_tickets(world)
    c = world.roles.contributor.client
    allowed = {k for k, t in tickets.items() if c.patch(f"/api/tickets/{t['id']}", json={"title": "z"}).status_code == 200}
    assert allowed == {"own_reported", "assigned", "tested"}


@pytest.mark.plan("TICKET-11")
def test_non_member_cannot_edit_move_or_delete(world):
    t = world.a.ticket()
    out = world.roles.outsider.client
    assert out.patch(f"/api/tickets/{t['id']}", json={"title": "x"}).status_code == 403
    assert out.patch(f"/api/tickets/{t['id']}/column", json={"column_id": world.a.columns["Done"]}).status_code == 403
    assert out.delete(f"/api/tickets/{t['id']}").status_code == 403
    assert get(world, t["id"])["title"] == t["title"]


# =================================================================== TICKET-12
@pytest.mark.plan("TICKET-12")
@pytest.mark.parametrize("role,code", [("editor", 403), ("contributor", 403), ("reporter", 403), ("admin", 204)])
def test_only_admin_can_delete_tickets(world, role, code):
    t = world.a.ticket(client=world.roles.contributor.client if role == "contributor" else world.a.c)
    assert world.client(role).delete(f"/api/tickets/{t['id']}").status_code == code
    exists = world.a.c.get(f"/api/tickets/{t['id']}").status_code
    assert exists == (404 if code == 204 else 200)


@pytest.mark.plan("TICKET-12")
def test_delete_unknown_and_repeat_delete_are_404(world):
    t = world.a.ticket()
    assert world.a.c.delete("/api/tickets/987654321").status_code == 404
    assert world.a.c.delete(f"/api/tickets/{t['id']}").status_code == 204
    assert world.a.c.delete(f"/api/tickets/{t['id']}").status_code == 404
    assert world.a.c.get(f"/api/tickets/key/{t['key']}").status_code == 404


@pytest.mark.plan("TICKET-12")
def test_delete_parent_detaches_children_and_never_reuses_keys(world):
    epic = world.a.ticket(type="Epic")
    kids = [world.a.ticket(type="Task", parent_id=epic["id"]) for _ in range(2)]
    ok(world.a.c.delete(f"/api/tickets/{epic['id']}"), 204)
    for k in kids:
        fresh = get(world, k["id"])
        assert fresh["parent_id"] is None and fresh["ancestors"] == []
    nxt = world.a.ticket()
    assert seq(nxt["key"]) == seq(kids[-1]["key"]) + 1


@pytest.mark.plan("TICKET-12")
def test_delete_removes_attachments_history_and_dependencies(world, anon):
    t, other = world.a.ticket(), world.a.ticket()
    att = ok(world.a.c.upload("/api/attachments", "f.txt", b"data", "text/plain",
                              params={"project_id": world.a.id, "ticket_id": t["id"]}), 201).json()
    world.a.dependency(t["id"], other["id"], entity="ticket")
    assert len(world.a.roadmap()["dependencies"]) == 1
    ok(world.a.c.delete(f"/api/tickets/{t['id']}"), 204)
    assert anon.get(att["url"], auth=False).status_code == 404
    assert world.a.c.delete(f"/api/attachments/{att['id']}").status_code == 404
    assert world.a.roadmap()["dependencies"] == []
    assert [x["id"] for x in world.a.tickets()] == [other["id"]]


@pytest.mark.plan("TICKET-12")
@pytest.mark.needs_local_server
def test_delete_leaves_no_orphan_rows(world, db):
    t = world.a.ticket()
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "edit"}))
    ok(world.a.c.delete(f"/api/tickets/{t['id']}"), 204)
    assert db("SELECT COUNT(*) FROM ticket_history WHERE ticket_id=?", (t["id"],))[0][0] == 0
    assert db("SELECT COUNT(*) FROM ticket_attachments WHERE ticket_id=?", (t["id"],))[0][0] == 0


@pytest.mark.plan("TICKET-12", "ROAD-11")
def test_delete_recalculates_milestone_progress(world):
    m = world.a.milestone()
    done = world.a.ticket(milestone_id=m["id"])
    pending = world.a.ticket(milestone_id=m["id"])
    world.a.move(done["id"], "Done")
    assert world.a.milestone_row(m["id"])["progress"] == 50
    ok(world.a.c.delete(f"/api/tickets/{pending['id']}"), 204)
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"], row["tickets_total"]) == (100, "done", 1)


# =================================================================== TICKET-13
def _parallel_create(world, n=20):
    base, token, pid = world.a.c.base_url, world.roles.admin.token, world.a.id

    def create(i):
        return Client(base, token).post(f"/api/tickets/project/{pid}", json={"title": f"parallel {i}"})

    with ThreadPoolExecutor(max_workers=10) as pool:
        return list(pool.map(create, range(n)))


@pytest.mark.plan("TICKET-13")
@pytest.mark.concurrency
def test_concurrent_creation_never_duplicates_keys_or_loses_accepted_tickets(world):
    results = _parallel_create(world)
    created = [r.json()["key"] for r in results if r.status_code == 201]
    assert len(set(created)) == len(created), "duplicate ticket keys issued"
    assert sorted(t["key"] for t in world.a.tickets()) == sorted(created)


@pytest.mark.plan("TICKET-13")
@pytest.mark.concurrency
def test_concurrent_creation_yields_unique_monotonic_keys(world):
    n = 20
    base, token, pid = world.a.c.base_url, world.roles.admin.token, world.a.id

    def create(i):
        return Client(base, token).post(f"/api/tickets/project/{pid}", json={"title": f"parallel {i}"})

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(create, range(n)))
    codes = [r.status_code for r in results]
    assert codes == [201] * n, f"status codes: {sorted(set(codes))}"
    keys = [r.json()["key"] for r in results]
    assert len(set(keys)) == n
    assert sorted(seq(k) for k in keys) == list(range(1, n + 1))
    assert len(world.a.tickets()) == n
    nxt = world.a.ticket()
    assert seq(nxt["key"]) == n + 1


# =================================================================== TICKET-14
XSS = ["<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>", "<svg/onload=alert(1)>",
       "javascript:alert(1)", "'; DROP TABLE tickets;--", "{{7*7}}", "<iframe src=//evil></iframe>"]


@pytest.mark.plan("TICKET-14", "UI-07")
@pytest.mark.security
@pytest.mark.parametrize("payload", XSS)
def test_markup_in_title_and_description_is_stored_verbatim_as_json_data(world, payload):
    t = world.a.ticket(title=payload, description=payload)
    r = world.a.c.get(f"/api/tickets/{t['id']}")
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["title"] == payload and r.json()["description"] == payload
    assert "text/html" not in r.headers["content-type"]


@pytest.mark.plan("TICKET-14", "UI-07")
@pytest.mark.security
def test_error_responses_do_not_reflect_markup(world):
    r = world.a.c.get("/api/tickets/key/%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert r.status_code == 404 and "<script>" not in r.text
    assert r.headers["content-type"].startswith("application/json")
