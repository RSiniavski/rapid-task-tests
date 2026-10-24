"""Section 6 - roadmap, dependencies, layout and calculations (API / backend)."""
import time

import pytest

from framework.factory import iso, ok

pytestmark = pytest.mark.api

BIG = 987654321


def rm(world, role="admin"):
    return ok(world.client(role).get(f"/api/roadmap/project/{world.a.id}")).json()


def dep_row(world, dep_id):
    return next(d for d in rm(world)["dependencies"] if d["id"] == dep_id)


# =================================================================== ROAD-01
@pytest.mark.plan("ROAD-01")
def test_empty_roadmap_shape(world):
    r = rm(world)
    assert r == {"project_id": world.a.id, "milestones": [], "dependencies": [], "blocked_ticket_ids": []}


@pytest.mark.plan("ROAD-01")
def test_mixed_roadmap_is_project_scoped_and_coherent(world):
    m1 = world.a.milestone(title="Has tickets", start_date=iso(0), due_date=iso(30))
    m2 = world.a.milestone(title="Empty", status="in_progress", progress=40)
    world.b.milestone(title="Other project")
    t_done = world.a.ticket(milestone_id=m1["id"])
    world.a.ticket(milestone_id=m1["id"])
    world.a.move(t_done["id"], "Done")
    dep = world.a.dependency(m1["id"], m2["id"])
    r = rm(world, "reporter")                                 # any member can read
    rows = {m["id"]: m for m in r["milestones"]}
    assert set(rows) == {m1["id"], m2["id"]}
    a, b = rows[m1["id"]], rows[m2["id"]]
    assert (a["tickets_total"], a["tickets_done"], a["progress"], a["status"], a["auto_managed"]) == (2, 1, 50, "in_progress", True)
    assert (b["tickets_total"], b["progress"], b["status"], b["auto_managed"]) == (0, 40, "in_progress", False)
    assert [d["id"] for d in r["dependencies"]] == [dep["id"]]
    for m in r["milestones"]:
        assert m["project_id"] == world.a.id
        assert m["risk_level"] in ("none", "warning", "danger") and isinstance(m["risk_reasons"], list)
        assert isinstance(m["blocked_by"], list) and isinstance(m["downstream_count"], int)


@pytest.mark.plan("ROAD-01", "ROAD-11")
def test_repeated_reads_are_deterministic(world):
    m = world.a.milestone(due_date=iso(2))
    world.a.ticket(milestone_id=m["id"])
    assert rm(world) == rm(world) == rm(world)


# =================================================================== ROAD-02
@pytest.mark.plan("ROAD-02")
def test_roadmap_access_denied_cases(world, anon):
    world.a.milestone(title="private-roadmap-title")
    r = world.roles.outsider.client.get(f"/api/roadmap/project/{world.a.id}")
    assert r.status_code == 403 and "private-roadmap-title" not in r.text
    assert world.a.c.get(f"/api/roadmap/project/{BIG}").status_code == 404
    assert anon.get(f"/api/roadmap/project/{world.a.id}", auth=False).status_code == 401
    assert world.a.c.get("/api/roadmap/project/abc").status_code == 422


# =================================================================== ROAD-03
@pytest.mark.plan("ROAD-03")
def test_create_milestone_minimal_has_defaults(world):
    m = ok(world.a.c.post(f"/api/roadmap/project/{world.a.id}/milestones", json={"title": "  Phase 1  "}), 201).json()
    assert m["title"] == "Phase 1" and m["project_id"] == world.a.id
    assert (m["status"], m["progress"], m["tickets_total"], m["tickets_done"], m["auto_managed"]) == ("planned", 0, 0, 0, False)
    assert (m["risk_level"], m["risk_reasons"], m["blocked_by"], m["is_blocked"]) == ("none", [], [], False)
    assert (m["downstream_count"], m["is_bottleneck"], m["pos_x"], m["pos_y"], m["description"]) == (0, False, None, None, None)


@pytest.mark.plan("ROAD-03")
def test_create_milestone_with_all_fields(world):
    m = world.a.milestone(title="Full", description="Описание 🚀", start_date="2028-02-29", due_date="2028-03-31",
                          status="in_progress", progress=35, pos_x=120.5, pos_y=-40)
    assert (m["description"], m["start_date"], m["due_date"]) == ("Описание 🚀", "2028-02-29", "2028-03-31")
    assert (m["status"], m["progress"], m["pos_x"], m["pos_y"]) == ("in_progress", 35, 120.5, -40.0)
    assert world.a.milestone_row(m["id"]) == m


@pytest.mark.plan("ROAD-03")
def test_done_status_without_progress_defaults_to_100(world):
    assert world.a.milestone(status="done")["progress"] == 100


@pytest.mark.plan("ROAD-03", "ROAD-12")
def test_derived_overdue_risk_on_creation(world):
    m = world.a.milestone(due_date=iso(-3))
    assert m["risk_level"] == "danger" and "overdue" in m["risk_reasons"]


@pytest.mark.plan("ROAD-03", "ROAD-04")
@pytest.mark.parametrize("role", ["editor", "admin"])
def test_planner_roles_can_create(world, role):
    assert ok(world.client(role).post(f"/api/roadmap/project/{world.a.id}/milestones", json={"title": "x"}), 201)


# =================================================================== ROAD-04
BAD_MILESTONES = {
    "blank_title": ({"title": ""}, 422),
    "missing_title": ({"description": "d"}, 422),
    "title_121": ({"title": "t" * 121}, 422),
    "spaces_title": ({"title": "    "}, 400),
    "invalid_status": ({"title": "x", "status": "blocked"}, 422),
    "progress_101": ({"title": "x", "progress": 101}, 422),
    "progress_negative": ({"title": "x", "progress": -1}, 422),
    "progress_text": ({"title": "x", "progress": "half"}, 422),
    "due_before_start": ({"title": "x", "start_date": "2027-05-10", "due_date": "2027-05-09"}, 400),
    "malformed_date": ({"title": "x", "start_date": "2027-13-45"}, 422),
    "date_text": ({"title": "x", "due_date": "tomorrow"}, 422),
    "non_leap_feb_29": ({"title": "x", "due_date": "2027-02-29"}, 422),
    "description_2001": ({"title": "x", "description": "d" * 2001}, 422),
    "pos_text": ({"title": "x", "pos_x": "left"}, 422),
}


@pytest.mark.plan("ROAD-04")
@pytest.mark.parametrize("case", sorted(BAD_MILESTONES))
def test_invalid_milestone_payloads_create_nothing(world, case):
    body, code = BAD_MILESTONES[case]
    assert world.a.c.post(f"/api/roadmap/project/{world.a.id}/milestones", json=body).status_code == code
    assert rm(world)["milestones"] == []


@pytest.mark.plan("ROAD-04")
def test_milestone_creation_denied_for_other_roles_and_projects(world):
    base = f"/api/roadmap/project/{world.a.id}/milestones"
    for role in ("contributor", "reporter"):
        assert world.client(role).post(base, json={"title": "x"}).status_code == 403
    assert world.roles.outsider.client.post(base, json={"title": "x"}).status_code == 403
    assert world.a.c.post(f"/api/roadmap/project/{BIG}/milestones", json={"title": "x"}).status_code == 404
    assert rm(world)["milestones"] == []


# =================================================================== ROAD-05
@pytest.mark.plan("ROAD-05")
def test_update_each_milestone_field(world):
    m = world.a.milestone()
    p = f"/api/roadmap/milestones/{m['id']}"
    c = world.a.c
    assert ok(c.patch(p, json={"title": " Renamed "})).json()["title"] == "Renamed"
    assert ok(c.patch(p, json={"description": "desc"})).json()["description"] == "desc"
    r = ok(c.patch(p, json={"start_date": "2030-01-01", "due_date": "2030-02-01"})).json()
    assert (r["start_date"], r["due_date"]) == ("2030-01-01", "2030-02-01")
    r = ok(c.patch(p, json={"status": "in_progress", "progress": 60})).json()
    assert (r["status"], r["progress"]) == ("in_progress", 60)
    r = ok(c.patch(p, json={"pos_x": 10, "pos_y": 20})).json()
    assert (r["pos_x"], r["pos_y"]) == (10.0, 20.0)
    assert ok(c.patch(p, json={"status": "done"})).json()["progress"] == 100     # done implies 100
    assert world.a.milestone_row(m["id"])["title"] == "Renamed"


@pytest.mark.plan("ROAD-05")
def test_clear_optional_values_and_ignore_null_required_ones(world):
    m = world.a.milestone(title="Keep", description="d", start_date=iso(1), due_date=iso(9))
    p = f"/api/roadmap/milestones/{m['id']}"
    r = ok(world.a.c.patch(p, json={"description": None, "start_date": None, "due_date": None, "title": None})).json()
    assert r["description"] is None and r["start_date"] is None and r["due_date"] is None and r["title"] == "Keep"
    untouched = ok(world.a.c.patch(p, json={})).json()
    assert untouched["title"] == "Keep"


@pytest.mark.plan("ROAD-05")
def test_update_validation_uses_merged_dates(world):
    m = world.a.milestone(start_date=iso(5), due_date=iso(10))
    p = f"/api/roadmap/milestones/{m['id']}"
    assert world.a.c.patch(p, json={"due_date": iso(1)}).status_code == 400
    assert world.a.c.patch(p, json={"start_date": iso(20)}).status_code == 400
    assert world.a.c.patch(p, json={"title": ""}).status_code == 422
    assert world.a.c.patch(p, json={"title": "   "}).status_code == 400
    assert world.a.c.patch(p, json={"progress": 150}).status_code == 422
    row = world.a.milestone_row(m["id"])
    assert (row["start_date"], row["due_date"]) == (iso(5), iso(10))


@pytest.mark.plan("ROAD-05")
def test_update_missing_milestone_and_roles(world):
    m = world.a.milestone(title="Guarded")
    assert world.a.c.patch(f"/api/roadmap/milestones/{BIG}", json={"title": "x"}).status_code == 404
    p = f"/api/roadmap/milestones/{m['id']}"
    for role in ("contributor", "reporter"):
        assert world.client(role).patch(p, json={"title": "HACK"}).status_code == 403
    assert world.roles.outsider.client.patch(p, json={"title": "HACK"}).status_code == 403
    assert ok(world.roles.editor.client.patch(p, json={"title": "By editor"})).json()["title"] == "By editor"


@pytest.mark.plan("ROAD-05", "ROAD-11")
def test_status_and_progress_of_ticket_backed_milestone_are_read_only(world):
    m = world.a.milestone()
    world.a.ticket(milestone_id=m["id"])
    p = f"/api/roadmap/milestones/{m['id']}"
    for body in ({"status": "done"}, {"progress": 50}):
        r = world.a.c.patch(p, json=body)
        assert r.status_code == 400 and "automatically" in r.json()["detail"]
    assert ok(world.a.c.patch(p, json={"title": "titles still editable"})).json()["auto_managed"] is True


@pytest.mark.plan("ROAD-05", "ROAD-12")
def test_update_recalculates_risk(world):
    m = world.a.milestone(due_date=iso(60))
    assert m["risk_level"] == "none"
    r = ok(world.a.c.patch(f"/api/roadmap/milestones/{m['id']}", json={"due_date": iso(-1)})).json()
    assert r["risk_level"] == "danger" and "overdue" in r["risk_reasons"]


# =================================================================== ROAD-06
@pytest.mark.plan("ROAD-06")
def test_delete_empty_milestone(world):
    m = world.a.milestone()
    assert world.a.c.delete(f"/api/roadmap/milestones/{m['id']}").status_code == 204
    assert rm(world)["milestones"] == []
    assert world.a.c.delete(f"/api/roadmap/milestones/{m['id']}").status_code == 404
    assert world.a.c.patch(f"/api/roadmap/milestones/{m['id']}", json={"title": "x"}).status_code == 404


@pytest.mark.plan("ROAD-06")
def test_delete_linked_milestone_detaches_tickets_and_removes_dependencies(world):
    m1, m2, m3 = world.a.milestone(), world.a.milestone(), world.a.milestone()
    t = world.a.ticket(milestone_id=m1["id"])
    world.a.dependency(m1["id"], m2["id"])
    world.a.dependency(m3["id"], m1["id"])
    keep = world.a.dependency(m3["id"], m2["id"])
    ok(world.a.c.delete(f"/api/roadmap/milestones/{m1['id']}"), 204)
    fresh = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert fresh["milestone_id"] is None and fresh["title"] == t["title"]
    r = rm(world)
    assert {m["id"] for m in r["milestones"]} == {m2["id"], m3["id"]}
    assert [d["id"] for d in r["dependencies"]] == [keep["id"]]


@pytest.mark.plan("ROAD-06")
def test_delete_milestone_denied_for_non_planners(world):
    m = world.a.milestone()
    for role in ("contributor", "reporter"):
        assert world.client(role).delete(f"/api/roadmap/milestones/{m['id']}").status_code == 403
    assert world.roles.outsider.client.delete(f"/api/roadmap/milestones/{m['id']}").status_code == 403
    assert world.a.c.delete(f"/api/roadmap/milestones/{BIG}").status_code == 404
    assert len(rm(world)["milestones"]) == 1


# =================================================================== ROAD-07
@pytest.mark.plan("ROAD-07")
@pytest.mark.parametrize("dep_type", ["FS", "SS", "FF", "SF"])
def test_create_milestone_dependency_of_each_type(world, dep_type):
    a, b = world.a.milestone(), world.a.milestone()
    d = world.a.dependency(a["id"], b["id"], type=dep_type)
    assert (d["entity"], d["predecessor_id"], d["successor_id"], d["type"]) == ("milestone", a["id"], b["id"], dep_type)
    assert d["state"] in ("ok", "waiting", "violated") and isinstance(d["schedule_conflict"], bool)
    assert dep_row(world, d["id"]) == d


@pytest.mark.plan("ROAD-07")
def test_dependency_defaults_to_milestone_and_fs(world):
    a, b = world.a.milestone(), world.a.milestone()
    d = ok(world.a.c.post(f"/api/roadmap/project/{world.a.id}/dependencies",
                          json={"predecessor_id": a["id"], "successor_id": b["id"]}), 201).json()
    assert (d["entity"], d["type"], d["state"]) == ("milestone", "FS", "waiting")


@pytest.mark.plan("ROAD-07")
@pytest.mark.parametrize("dep_type", ["FS", "SS", "FF", "SF"])
def test_create_ticket_dependency_of_each_type(world, dep_type):
    t1, t2 = world.a.ticket(), world.a.ticket()
    d = world.a.dependency(t1["id"], t2["id"], type=dep_type, entity="ticket")
    assert (d["entity"], d["predecessor_id"], d["successor_id"], d["type"]) == ("ticket", t1["id"], t2["id"], dep_type)


# =================================================================== ROAD-08
@pytest.mark.plan("ROAD-08")
def test_invalid_milestone_dependencies_are_rejected_and_graph_unchanged(world):
    a, b, c = world.a.milestone(), world.a.milestone(), world.a.milestone()
    foreign = world.b.milestone()
    first = world.a.dependency(a["id"], b["id"])
    cases = [
        (dict(predecessor_id=a["id"], successor_id=a["id"]), 400, "itself"),
        (dict(predecessor_id=a["id"], successor_id=b["id"]), 400, "already exists"),
        (dict(predecessor_id=a["id"], successor_id=b["id"], type="SS"), 400, "already exists"),
        (dict(predecessor_id=b["id"], successor_id=a["id"]), 400, "cycle"),
        (dict(predecessor_id=a["id"], successor_id=BIG), 400, "exist"),
        (dict(predecessor_id=BIG, successor_id=a["id"]), 400, "exist"),
        (dict(predecessor_id=a["id"], successor_id=foreign["id"]), 400, "exist"),
        (dict(predecessor_id=foreign["id"], successor_id=a["id"]), 400, "exist"),
    ]
    for body, code, text in cases:
        r = world.a.c.post(f"/api/roadmap/project/{world.a.id}/dependencies", json=body)
        assert r.status_code == code and text in r.json()["detail"], (body, r.text)
    world.a.dependency(b["id"], c["id"])
    r = world.a.c.post(f"/api/roadmap/project/{world.a.id}/dependencies",
                       json={"predecessor_id": c["id"], "successor_id": a["id"]})
    assert r.status_code == 400 and "cycle" in r.json()["detail"]                # longer cycle
    assert [d["id"] for d in rm(world)["dependencies"]][:1] == [first["id"]]
    assert len(rm(world)["dependencies"]) == 2
    assert rm(world, "admin") and len(ok(world.b.c.get(f"/api/roadmap/project/{world.b.id}")).json()["dependencies"]) == 0


@pytest.mark.plan("ROAD-08")
def test_invalid_enum_values_and_missing_fields_are_422(world):
    a, b = world.a.milestone(), world.a.milestone()
    base = f"/api/roadmap/project/{world.a.id}/dependencies"
    ids = dict(predecessor_id=a["id"], successor_id=b["id"])
    for body in ({**ids, "entity": "project"}, {**ids, "type": "XX"}, {"predecessor_id": a["id"]},
                 {"successor_id": b["id"]}, {**ids, "predecessor_id": "x"}):
        assert world.a.c.post(base, json=body).status_code == 422, body
    assert rm(world)["dependencies"] == []


@pytest.mark.plan("ROAD-08")
def test_ticket_dependency_errors(world):
    t1, t2 = world.a.ticket(), world.a.ticket()
    foreign = world.b.ticket()
    world.a.dependency(t1["id"], t2["id"], entity="ticket")
    base = f"/api/roadmap/project/{world.a.id}/dependencies"
    for body, text in (({"predecessor_id": t2["id"], "successor_id": t1["id"]}, "cycle"),
                       ({"predecessor_id": t1["id"], "successor_id": t1["id"]}, "itself"),
                       ({"predecessor_id": t1["id"], "successor_id": t2["id"]}, "already exists"),
                       ({"predecessor_id": t1["id"], "successor_id": foreign["id"]}, "exist"),
                       ({"predecessor_id": t1["id"], "successor_id": BIG}, "exist")):
        r = world.a.c.post(base, json={"entity": "ticket", **body})
        assert r.status_code == 400 and text in r.json()["detail"], (body, r.text)
    assert len(rm(world)["dependencies"]) == 1


@pytest.mark.plan("ROAD-08")
def test_dependency_for_unknown_project_and_roles(world):
    a, b = world.a.milestone(), world.a.milestone()
    body = {"predecessor_id": a["id"], "successor_id": b["id"]}
    assert world.a.c.post(f"/api/roadmap/project/{BIG}/dependencies", json=body).status_code == 404
    base = f"/api/roadmap/project/{world.a.id}/dependencies"
    for role in ("contributor", "reporter"):
        assert world.client(role).post(base, json=body).status_code == 403
    assert world.roles.outsider.client.post(base, json=body).status_code == 403
    assert rm(world)["dependencies"] == []


# =================================================================== ROAD-09
@pytest.mark.plan("ROAD-09")
def test_update_and_delete_dependency(world):
    a, b = world.a.milestone(), world.a.milestone()
    d = world.a.dependency(a["id"], b["id"])
    p = f"/api/roadmap/dependencies/{d['id']}"
    for tp in ("SS", "FF", "SF", "FS"):
        assert ok(world.a.c.patch(p, json={"type": tp})).json()["type"] == tp
    assert dep_row(world, d["id"])["type"] == "FS"
    assert world.a.c.patch(p, json={"type": "ZZ"}).status_code == 422
    assert world.a.c.patch(p, json={}).status_code == 422
    assert world.a.c.delete(p).status_code == 204
    assert rm(world)["dependencies"] == []
    assert world.a.c.delete(p).status_code == 404
    assert world.a.c.patch(p, json={"type": "SS"}).status_code == 404


@pytest.mark.plan("ROAD-09")
def test_dependency_mutation_roles(world):
    a, b = world.a.milestone(), world.a.milestone()
    d = world.a.dependency(a["id"], b["id"])
    p = f"/api/roadmap/dependencies/{d['id']}"
    for role in ("contributor", "reporter"):
        assert world.client(role).patch(p, json={"type": "SS"}).status_code == 403
        assert world.client(role).delete(p).status_code == 403
    assert world.roles.outsider.client.patch(p, json={"type": "SS"}).status_code == 403
    assert world.roles.outsider.client.delete(p).status_code == 403
    assert dep_row(world, d["id"])["type"] == "FS"
    assert ok(world.roles.editor.client.patch(p, json={"type": "SS"})).json()["type"] == "SS"
    assert world.a.c.patch(f"/api/roadmap/dependencies/{BIG}", json={"type": "SS"}).status_code == 404
    assert world.a.c.delete(f"/api/roadmap/dependencies/{BIG}").status_code == 404


# =================================================================== ROAD-10
def layout(world, items, role="admin"):
    return world.client(role).put(f"/api/roadmap/project/{world.a.id}/layout", json={"items": items})


def pos(world, mid):
    row = world.a.milestone_row(mid)
    return row["pos_x"], row["pos_y"]


@pytest.mark.plan("ROAD-10")
def test_layout_save_empty_full_and_partial(world):
    ms = [world.a.milestone() for _ in range(3)]
    assert ok(layout(world, [])).json() == {"saved": 0}
    full = [{"id": m["id"], "x": 10.0 * i, "y": -5.5 * i} for i, m in enumerate(ms)]
    assert ok(layout(world, full)).json() == {"saved": 3}
    assert [pos(world, m["id"]) for m in ms] == [(0.0, -0.0), (10.0, -5.5), (20.0, -11.0)]
    assert ok(layout(world, [{"id": ms[1]["id"], "x": 99, "y": 98}])).json() == {"saved": 1}
    assert pos(world, ms[1]["id"]) == (99.0, 98.0)
    assert pos(world, ms[0]["id"]) == (0.0, 0.0) and pos(world, ms[2]["id"]) == (20.0, -11.0)   # untouched


@pytest.mark.plan("ROAD-10")
def test_layout_duplicates_unknown_and_foreign_ids(world):
    mine, foreign = world.a.milestone(), world.b.milestone(pos_x=1, pos_y=2)
    items = [{"id": mine["id"], "x": 1, "y": 1}, {"id": mine["id"], "x": 7, "y": 8},
             {"id": BIG, "x": 5, "y": 5}, {"id": foreign["id"], "x": 500, "y": 500}]
    assert ok(layout(world, items)).json()["saved"] >= 1
    assert pos(world, mine["id"]) == (7.0, 8.0)                                  # last duplicate wins
    other = next(m for m in ok(world.b.c.get(f"/api/roadmap/project/{world.b.id}")).json()["milestones"])
    assert (other["pos_x"], other["pos_y"]) == (1.0, 2.0)                        # foreign project untouched


@pytest.mark.plan("ROAD-10")
@pytest.mark.parametrize("x,y", [(1e300, -1e300), (-1e9, 1e9), (0.000001, 123456789.123)])
def test_layout_extreme_coordinates_persist(world, x, y):
    m = world.a.milestone()
    ok(layout(world, [{"id": m["id"], "x": x, "y": y}]))
    assert pos(world, m["id"]) == (x, y)


@pytest.mark.plan("ROAD-10")
def test_malformed_layout_is_rejected_without_partial_overwrite(world):
    m = world.a.milestone(pos_x=3, pos_y=4)
    good = {"id": m["id"], "x": 100, "y": 100}
    bad_payloads = [
        [good, {"id": m["id"], "x": "left", "y": 1}],
        [good, {"id": m["id"], "x": 1}],
        [good, {"x": 1, "y": 1}],
        [good, {"id": "abc", "x": 1, "y": 1}],
        [{"id": m["id"], "x": 1, "y": 1}] * 501,
    ]
    for items in bad_payloads:
        assert layout(world, items).status_code == 422
    assert world.a.c.put(f"/api/roadmap/project/{world.a.id}/layout", json={}).status_code == 422
    assert world.a.c.put(f"/api/roadmap/project/{world.a.id}/layout", json={"items": "x"}).status_code == 422
    assert pos(world, m["id"]) == (3.0, 4.0)


@pytest.mark.plan("ROAD-10")
def test_layout_roles_and_boundaries(world):
    m = world.a.milestone()
    item = [{"id": m["id"], "x": 1, "y": 1}]
    for role in ("contributor", "reporter"):
        assert layout(world, item, role).status_code == 403
    assert layout(world, item, "outsider").status_code == 403
    assert world.a.c.put(f"/api/roadmap/project/{BIG}/layout", json={"items": item}).status_code == 404
    assert ok(layout(world, item, "editor")).json() == {"saved": 1}
    assert ok(layout(world, [{"id": m["id"], "x": 2, "y": 2}] * 500)).json()["saved"] == 500   # max allowed size


# =================================================================== ROAD-11
def make_ms_with_tickets(world, n):
    m = world.a.milestone()
    ts = [world.a.ticket(milestone_id=m["id"]) for _ in range(n)]
    return m, ts


@pytest.mark.plan("ROAD-11")
def test_progress_for_untouched_milestone_is_planned_zero(world):
    m, _ = make_ms_with_tickets(world, 3)
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"], row["tickets_total"], row["tickets_done"]) == (0, "planned", 3, 0)


@pytest.mark.plan("ROAD-11")
def test_movement_outside_first_column_makes_in_progress_with_zero_progress(world):
    m, ts = make_ms_with_tickets(world, 2)
    world.a.move(ts[0]["id"], "In Progress")
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"]) == (0, "in_progress")


@pytest.mark.plan("ROAD-11")
@pytest.mark.parametrize("total,done,progress,status", [(1, 1, 100, "done"), (2, 1, 50, "in_progress"),
                                                        (3, 1, 33, "in_progress"), (3, 2, 67, "in_progress"),
                                                        (4, 4, 100, "done")])
def test_progress_rounding_and_done_status(world, total, done, progress, status):
    m, ts = make_ms_with_tickets(world, total)
    for t in ts[:done]:
        world.a.move(t["id"], "Done")
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"], row["tickets_done"]) == (progress, status, done)


@pytest.mark.plan("ROAD-11")
def test_reopened_ticket_recalculates_progress_and_status(world):
    m, ts = make_ms_with_tickets(world, 2)
    for t in ts:
        world.a.move(t["id"], "Done")
    assert world.a.milestone_row(m["id"])["status"] == "done"
    world.a.move(ts[1]["id"], "Open")
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"]) == (50, "in_progress")
    world.a.move(ts[0]["id"], "Open")
    row = world.a.milestone_row(m["id"])
    assert (row["progress"], row["status"]) == (0, "planned")


@pytest.mark.plan("ROAD-11")
def test_column_done_toggle_and_ticket_milestone_moves_recalculate(world):
    m1, m2 = world.a.milestone(), world.a.milestone()
    t = world.a.ticket(milestone_id=m1["id"])
    ok(world.a.c.patch(f"/api/projects/{world.a.id}/columns/{world.a.columns['Open']}", json={"is_done": True}))
    assert world.a.milestone_row(m1["id"])["status"] == "done"
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"milestone_id": m2["id"]}))
    assert world.a.milestone_row(m1["id"])["tickets_total"] == 0
    assert world.a.milestone_row(m2["id"])["tickets_total"] == 1


@pytest.mark.plan("ROAD-11")
def test_manually_controlled_empty_milestone_keeps_values_across_reads(world):
    m = world.a.milestone(status="in_progress", progress=40)
    other = world.a.milestone()
    world.a.ticket(milestone_id=other["id"])                      # triggers project-wide recalculation
    for _ in range(2):
        row = world.a.milestone_row(m["id"])
        assert (row["status"], row["progress"], row["auto_managed"]) == ("in_progress", 40, False)


@pytest.mark.plan("ROAD-11")
def test_subtasks_inherit_milestone_and_count_towards_progress(world):
    m = world.a.milestone()
    t = world.a.ticket(type="Task", milestone_id=m["id"], subtasks=[{"title": "s1"}, {"title": "s2"}])
    assert world.a.milestone_row(m["id"])["tickets_total"] == 3
    assert t["milestone_id"] == m["id"]


# =================================================================== ROAD-12
STATE_MATRIX = [
    ("FS", "planned", "planned", "waiting"), ("FS", "planned", "in_progress", "violated"),
    ("FS", "in_progress", "planned", "waiting"), ("FS", "in_progress", "done", "violated"),
    ("FS", "done", "planned", "ok"), ("FS", "done", "in_progress", "ok"),
    ("SS", "planned", "planned", "waiting"), ("SS", "planned", "in_progress", "violated"),
    ("SS", "in_progress", "in_progress", "ok"), ("SS", "done", "planned", "ok"),
    ("FF", "planned", "planned", "waiting"), ("FF", "planned", "in_progress", "waiting"),
    ("FF", "planned", "done", "violated"), ("FF", "done", "done", "ok"),
    ("SF", "planned", "planned", "waiting"), ("SF", "planned", "done", "violated"),
    ("SF", "in_progress", "done", "ok"), ("SF", "done", "done", "ok"),
]


@pytest.mark.plan("ROAD-12")
@pytest.mark.parametrize("dep_type,pred,succ,expected", STATE_MATRIX)
def test_dependency_state_matrix(world, dep_type, pred, succ, expected):
    a, b = world.a.milestone(status=pred), world.a.milestone(status=succ)
    d = world.a.dependency(a["id"], b["id"], type=dep_type)
    assert d["state"] == expected
    assert dep_row(world, d["id"])["state"] == expected


@pytest.mark.plan("ROAD-12")
@pytest.mark.parametrize("dep_type,blocks", [("FS", True), ("SS", True), ("FF", False), ("SF", False)])
def test_only_start_dependencies_block_the_successor(world, dep_type, blocks):
    a, b = world.a.milestone(), world.a.milestone()
    world.a.dependency(a["id"], b["id"], type=dep_type)
    row = world.a.milestone_row(b["id"])
    assert row["is_blocked"] is blocks and row["blocked_by"] == ([a["id"]] if blocks else [])


@pytest.mark.plan("ROAD-12")
def test_completing_predecessor_clears_blocking_and_risk(world):
    pred = world.a.milestone(due_date=iso(-2))
    succ = world.a.milestone()
    world.a.dependency(pred["id"], succ["id"])
    before = world.a.milestone_row(succ["id"])
    assert before["is_blocked"] and before["risk_level"] == "warning" and "upstream_risk" in before["risk_reasons"]
    ok(world.a.c.patch(f"/api/roadmap/milestones/{pred['id']}", json={"status": "done"}))
    after = world.a.milestone_row(succ["id"])
    assert (after["is_blocked"], after["blocked_by"], after["risk_level"], after["risk_reasons"]) == (False, [], "none", [])
    assert world.a.milestone_row(pred["id"])["risk_level"] == "none"


@pytest.mark.plan("ROAD-12")
@pytest.mark.parametrize("due,progress,status,level,reason", [
    (-3, 0, "planned", "danger", "overdue"),
    (3, 10, "planned", "warning", "due_soon"),
    (3, 60, "in_progress", "none", None),
    (7, 49, "planned", "warning", "due_soon"),
    (30, 0, "planned", "none", None),
    (None, 0, "planned", "none", None),
    (-10, 100, "done", "none", None),
])
def test_overdue_due_soon_and_no_date_cases(world, due, progress, status, level, reason):
    kw = {"status": status, "progress": progress}
    if due is not None:
        kw["due_date"] = iso(due)
    row = world.a.milestone(**kw)
    assert row["risk_level"] == level
    assert (reason in row["risk_reasons"]) if reason else row["risk_reasons"] == []


@pytest.mark.plan("ROAD-12")
def test_violated_dependency_makes_successor_dangerous(world):
    pred, succ = world.a.milestone(), world.a.milestone(status="in_progress")
    world.a.dependency(pred["id"], succ["id"])
    row = world.a.milestone_row(succ["id"])
    assert row["risk_level"] == "danger" and "violated" in row["risk_reasons"]


@pytest.mark.plan("ROAD-12")
def test_schedule_conflict_is_flagged_until_predecessor_is_done(world):
    pred = world.a.milestone(start_date=iso(0), due_date=iso(20))
    succ = world.a.milestone(start_date=iso(5), due_date=iso(30))
    d = world.a.dependency(pred["id"], succ["id"])
    assert d["schedule_conflict"] is True
    assert "schedule_conflict" in world.a.milestone_row(succ["id"])["risk_reasons"]
    ok(world.a.c.patch(f"/api/roadmap/milestones/{pred['id']}", json={"status": "done"}))
    assert dep_row(world, d["id"])["schedule_conflict"] is False


@pytest.mark.plan("ROAD-12")
def test_risk_propagates_downstream_and_flags_bottleneck(world):
    root = world.a.milestone(due_date=iso(-1))                       # danger
    mid = world.a.milestone()
    leaf1, leaf2 = world.a.milestone(), world.a.milestone()
    world.a.dependency(root["id"], mid["id"])
    world.a.dependency(mid["id"], leaf1["id"])
    world.a.dependency(mid["id"], leaf2["id"])
    rows = {m["id"]: m for m in rm(world)["milestones"]}
    assert rows[root["id"]]["risk_level"] == "danger" and rows[root["id"]]["downstream_count"] == 3
    assert rows[root["id"]]["is_bottleneck"] is True
    for m in (mid, leaf1, leaf2):
        assert rows[m["id"]]["risk_level"] == "warning" and "upstream_risk" in rows[m["id"]]["risk_reasons"]
    assert rows[mid["id"]]["is_bottleneck"] is True and rows[mid["id"]]["downstream_count"] == 2
    assert rows[leaf1["id"]]["is_bottleneck"] is False


@pytest.mark.plan("ROAD-12")
def test_single_dependent_is_not_a_bottleneck(world):
    a, b = world.a.milestone(due_date=iso(-1)), world.a.milestone()
    world.a.dependency(a["id"], b["id"])
    row = world.a.milestone_row(a["id"])
    assert row["downstream_count"] == 1 and row["is_bottleneck"] is False


@pytest.mark.plan("ROAD-12")
def test_ticket_dependency_blocking_follows_columns(world):
    t1, t2 = world.a.ticket(), world.a.ticket()
    d = world.a.dependency(t1["id"], t2["id"], entity="ticket")
    r = rm(world)
    assert r["blocked_ticket_ids"] == [t2["id"]] and dep_row(world, d["id"])["state"] == "waiting"
    world.a.move(t1["id"], "Done")
    r = rm(world)
    assert r["blocked_ticket_ids"] == [] and dep_row(world, d["id"])["state"] == "ok"
    world.a.move(t1["id"], "Open")
    world.a.move(t2["id"], "In Progress")
    assert dep_row(world, d["id"])["state"] == "violated"


# =================================================================== ROAD-13
@pytest.mark.plan("ROAD-13")
@pytest.mark.slow
def test_deep_dependency_chain_is_handled_without_recursion_or_hang(world):
    n = 80
    ms = [world.a.milestone(title=f"chain {i}") for i in range(n)]
    for i in range(n - 1):
        world.a.dependency(ms[i]["id"], ms[i + 1]["id"])
    started = time.time()
    r = rm(world)
    assert time.time() - started < 10
    rows = {m["id"]: m for m in r["milestones"]}
    assert rows[ms[0]["id"]]["downstream_count"] == n - 1
    assert rows[ms[-1]["id"]]["is_blocked"] is True
    closing = world.a.c.post(f"/api/roadmap/project/{world.a.id}/dependencies",
                             json={"predecessor_id": ms[-1]["id"], "successor_id": ms[0]["id"]})
    assert closing.status_code == 400 and "cycle" in closing.json()["detail"]


@pytest.mark.plan("ROAD-13")
@pytest.mark.slow
def test_wide_graph_with_many_milestones_and_tickets(world):
    ms = [world.a.milestone() for _ in range(60)]
    for m in ms[:20]:
        world.a.ticket(milestone_id=m["id"])
    started = time.time()
    r = rm(world)
    assert len(r["milestones"]) == 60 and time.time() - started < 10


@pytest.mark.plan("ROAD-13")
@pytest.mark.needs_local_server
def test_cyclic_legacy_database_data_is_handled_safely(world, db):
    a, b, c = world.a.milestone(), world.a.milestone(), world.a.milestone()
    for pred, succ in ((a, b), (b, c), (c, a)):                      # persisted cycle, bypassing the API
        db("INSERT INTO roadmap_dependencies (project_id, entity, predecessor_id, successor_id, type, created_at) "
           "VALUES (?, 'milestone', ?, ?, 'FS', datetime('now'))", (world.a.id, pred["id"], succ["id"]))
    started = time.time()
    r = rm(world)
    assert time.time() - started < 10
    assert len(r["dependencies"]) == 3 and len(r["milestones"]) == 3
    extra = world.a.milestone()
    assert world.a.c.post(f"/api/roadmap/project/{world.a.id}/dependencies",
                          json={"predecessor_id": extra["id"], "successor_id": a["id"]}).status_code in (201, 400)
    assert world.a.c.get(f"/api/roadmap/project/{world.a.id}").status_code == 200
