"""Label management (API): rename and delete tags/components, usage counts, history (LBL-09..11)."""
import pytest

from framework.factory import ok

pytestmark = pytest.mark.api

KINDS = [("tags", "tag_ids"), ("components", "component_ids")]
NOT_ADMIN = ["editor", "contributor", "reporter"]


def base(world, kind, project=None):
    return f"/api/projects/{(project or world.a).id}/{kind}"


def make(world, kind, name, project=None):
    r = (project or world.a).c.post(base(world, kind, project), json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def listing(world, kind, client=None):
    return ok((client or world.client("admin")).get(base(world, kind))).json()


def history(world, ticket_id, field):
    rows = ok(world.client("admin").get(f"/api/tickets/{ticket_id}")).json()["history"]
    return [(h["old_value"], h["new_value"]) for h in rows if h["field_changed"] == field]


# ---------------------------------------------------------------- LBL-09 permissions
@pytest.mark.plan("LBL-09")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_and_delete_require_login(world, anon, kind, field):
    row = make(world, kind, "x1")
    assert anon.patch(f"{base(world, kind)}/{row['id']}", json={"name": "y"}).status_code == 401
    assert anon.delete(f"{base(world, kind)}/{row['id']}").status_code == 401


@pytest.mark.plan("LBL-09")
@pytest.mark.parametrize("kind,field", KINDS)
@pytest.mark.parametrize("role", NOT_ADMIN)
def test_only_admin_can_rename_or_delete(world, kind, field, role):
    row = make(world, kind, "keep")
    c = world.client(role)
    assert c.patch(f"{base(world, kind)}/{row['id']}", json={"name": "new"}).status_code == 403
    assert c.delete(f"{base(world, kind)}/{row['id']}").status_code == 403
    assert [x["name"] for x in listing(world, kind)] == ["keep"]


@pytest.mark.plan("LBL-09")
@pytest.mark.parametrize("kind,field", KINDS)
def test_outsider_is_forbidden(world, kind, field):
    row = make(world, kind, "keep")
    out = world.client("outsider")
    assert out.patch(f"{base(world, kind)}/{row['id']}", json={"name": "new"}).status_code == 403
    assert out.delete(f"{base(world, kind)}/{row['id']}").status_code == 403


@pytest.mark.plan("LBL-09")
@pytest.mark.parametrize("kind,field", KINDS)
def test_label_of_another_project_is_not_found(world, kind, field):
    foreign = make(world, kind, "theirs", project=world.b)
    c = world.client("admin")
    assert c.patch(f"{base(world, kind)}/{foreign['id']}", json={"name": "mine"}).status_code == 404
    assert c.delete(f"{base(world, kind)}/{foreign['id']}").status_code == 404
    assert c.patch(f"{base(world, kind)}/99999999", json={"name": "x"}).status_code == 404
    assert [x["name"] for x in ok(world.b.c.get(base(world, kind, world.b))).json()] == ["theirs"]


# ---------------------------------------------------------------- LBL-10 rename
@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_changes_the_name_everywhere(world, kind, field):
    row = make(world, kind, "old")
    t = world.a.ticket(**{field: [row["id"]]})
    r = world.client("admin").patch(f"{base(world, kind)}/{row['id']}", json={"name": "  fresh  "})
    assert r.status_code == 200 and r.json() == {"id": row["id"], "name": "fresh"}
    got = ok(world.client("admin").get(f"/api/tickets/{t['id']}")).json()
    assert [x["name"] for x in got[kind]] == ["fresh"]


@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_writes_history_on_each_ticket(world, kind, field):
    a = make(world, kind, "alpha")
    b = make(world, kind, "beta")
    t1 = world.a.ticket(**{field: [a["id"], b["id"]]})
    t2 = world.a.ticket(**{field: [a["id"]]})
    other = world.a.ticket(**{field: [b["id"]]})
    ok(world.client("admin").patch(f"{base(world, kind)}/{a['id']}", json={"name": "gamma"}))
    assert history(world, t1["id"], kind) == [("alpha, beta", "gamma, beta")]
    assert history(world, t2["id"], kind) == [("alpha", "gamma")]
    assert history(world, other["id"], kind) == []


@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_to_an_existing_name_is_409_ignoring_case(world, kind, field):
    a = make(world, kind, "Bug")
    make(world, kind, "Other")
    c = world.client("admin")
    for name in ("Other", "other", "OTHER"):
        assert c.patch(f"{base(world, kind)}/{a['id']}", json={"name": name}).status_code == 409
    assert sorted(x["name"] for x in listing(world, kind)) == ["Bug", "Other"]


@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_only_the_letter_case_of_itself_is_allowed(world, kind, field):
    a = make(world, kind, "bug")
    r = world.client("admin").patch(f"{base(world, kind)}/{a['id']}", json={"name": "Bug"})
    assert r.status_code == 200 and r.json()["name"] == "Bug"


@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field", KINDS)
def test_rename_to_the_same_name_changes_nothing(world, kind, field):
    a = make(world, kind, "same")
    t = world.a.ticket(**{field: [a["id"]]})
    assert world.client("admin").patch(f"{base(world, kind)}/{a['id']}", json={"name": "same"}).status_code == 200
    assert history(world, t["id"], kind) == []


@pytest.mark.plan("LBL-10")
@pytest.mark.parametrize("kind,field,limit", [("tags", "tag_ids", 30), ("components", "component_ids", 50)])
def test_rename_validation(world, kind, field, limit):
    a = make(world, kind, "ok")
    c = world.client("admin")
    for bad in ({"name": ""}, {"name": "   "}, {"name": "x" * (limit + 1)}, {}):
        assert c.patch(f"{base(world, kind)}/{a['id']}", json=bad).status_code == 422
    assert c.patch(f"{base(world, kind)}/{a['id']}", json={"name": "x" * limit}).status_code == 200


# ---------------------------------------------------------------- LBL-11 delete + usage
@pytest.mark.plan("LBL-11")
@pytest.mark.parametrize("kind,field", KINDS)
def test_list_returns_ticket_counts(world, kind, field):
    used = make(world, kind, "used")
    make(world, kind, "unused")
    world.a.ticket(**{field: [used["id"]]})
    world.a.ticket(**{field: [used["id"]]})
    world.a.ticket()
    counts = {x["name"]: x["ticket_count"] for x in listing(world, kind)}
    assert counts == {"unused": 0, "used": 2}


@pytest.mark.plan("LBL-11")
@pytest.mark.parametrize("kind,field", KINDS)
def test_delete_removes_the_label_from_its_tickets_and_writes_history(world, kind, field):
    a = make(world, kind, "doomed")
    b = make(world, kind, "stays")
    t1 = world.a.ticket(**{field: [a["id"], b["id"]]})
    t2 = world.a.ticket(**{field: [a["id"]]})
    assert world.client("admin").delete(f"{base(world, kind)}/{a['id']}").status_code == 204
    assert [x["name"] for x in listing(world, kind)] == ["stays"]
    got1 = ok(world.client("admin").get(f"/api/tickets/{t1['id']}")).json()
    got2 = ok(world.client("admin").get(f"/api/tickets/{t2['id']}")).json()
    assert [x["name"] for x in got1[kind]] == ["stays"] and got2[kind] == []
    assert history(world, t1["id"], kind) == [("doomed, stays", "stays")]
    assert history(world, t2["id"], kind) == [("doomed", None)]


@pytest.mark.plan("LBL-11")
@pytest.mark.parametrize("kind,field", KINDS)
def test_deleted_label_is_gone_and_second_delete_is_404(world, kind, field):
    a = make(world, kind, "once")
    c = world.client("admin")
    assert c.delete(f"{base(world, kind)}/{a['id']}").status_code == 204
    assert c.delete(f"{base(world, kind)}/{a['id']}").status_code == 404
    assert c.patch(f"{base(world, kind)}/{a['id']}", json={"name": "x"}).status_code == 404
    bad = world.a.c.post(f"/api/tickets/project/{world.a.id}",
                         json={"title": "x", "type": "Task", field: [a["id"]]})
    assert bad.status_code == 400


@pytest.mark.plan("LBL-11")
@pytest.mark.parametrize("kind,field", KINDS)
def test_name_can_be_reused_after_delete(world, kind, field):
    a = make(world, kind, "again")
    ok(world.client("admin").delete(f"{base(world, kind)}/{a['id']}"), 204)
    assert make(world, kind, "again")["name"] == "again"


@pytest.mark.plan("LBL-11")
def test_deleting_a_tag_does_not_touch_components(world):
    tag = make(world, "tags", "same-name")
    comp = make(world, "components", "same-name")
    t = world.a.ticket(tag_ids=[tag["id"]], component_ids=[comp["id"]])
    ok(world.client("admin").delete(f"{base(world, 'tags')}/{tag['id']}"), 204)
    got = ok(world.client("admin").get(f"/api/tickets/{t['id']}")).json()
    assert got["tags"] == [] and [x["name"] for x in got["components"]] == ["same-name"]
