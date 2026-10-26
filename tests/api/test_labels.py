"""Tags and components (API): CRUD, ticket fields, pending names, atomicity, clean-up, parent_id bound."""
import pytest

from framework.factory import ok, uid

pytestmark = pytest.mark.api

KINDS = [("tags", 30), ("components", 50)]
ROLES = ["admin", "editor", "contributor", "reporter"]


def url(world, kind, project=None):
    return f"/api/projects/{(project or world.a).id}/{kind}"


def create(client, world, kind, name, project=None, expect=201):
    r = client.post(url(world, kind, project), json={"name": name})
    assert r.status_code == expect, f"{r.status_code}: {r.text}"
    return r.json() if expect == 201 else r


def names(client, world, kind, project=None):
    return [x["name"] for x in ok(client.get(url(world, kind, project))).json()]


def admin(world):
    return world.client("admin")


def patch(world, ticket_id, expect=200, client=None, **body):
    r = (client or admin(world)).patch(f"/api/tickets/{ticket_id}", json=body)
    assert r.status_code == expect, f"{r.status_code}: {r.text}"
    return r.json()


def label_names(ticket, kind):
    return [x["name"] for x in ticket[kind]]


# =================================================================== LBL-01
@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_labels_require_auth(world, anon, kind, limit):
    assert anon.get(url(world, kind)).status_code == 401
    assert anon.post(url(world, kind), json={"name": "x"}).status_code == 401


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_labels_are_forbidden_for_non_members(world, kind, limit):
    out = world.client("outsider")
    assert out.get(url(world, kind)).status_code == 403
    assert out.post(url(world, kind), json={"name": "x"}).status_code == 403


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_labels_unknown_project_is_404(world, kind, limit):
    assert admin(world).get(f"/api/projects/99999999/{kind}").status_code == 404
    assert admin(world).post(f"/api/projects/99999999/{kind}", json={"name": "x"}).status_code == 404


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
@pytest.mark.parametrize("role", ROLES)
def test_every_member_role_can_create_and_list_labels(world, kind, limit, role):
    name = f"n{uid(6)}"
    body = create(world.client(role), world, kind, name)
    assert body["name"] == name and isinstance(body["id"], int)
    for other in ROLES:
        assert name in names(world.client(other), world, kind)


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_duplicate_name_is_409_in_any_letter_case(world, kind, limit):
    create(admin(world), world, kind, "Backend")
    for dup in ("Backend", "backend", "BACKEND"):
        assert create(admin(world), world, kind, dup, expect=409).status_code == 409
    assert names(admin(world), world, kind) == ["Backend"]


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_same_name_is_allowed_in_another_project(world, kind, limit):
    create(admin(world), world, kind, "shared")
    create(world.client("outsider"), world, kind, "shared", project=world.b)
    assert names(world.client("outsider"), world, kind, project=world.b) == ["shared"]


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_label_name_is_trimmed(world, kind, limit):
    assert create(admin(world), world, kind, "  spaced  ")["name"] == "spaced"


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_label_name_length_limit(world, kind, limit):
    assert create(admin(world), world, kind, "a" * limit)["name"] == "a" * limit
    assert create(admin(world), world, kind, "b" * (limit + 1), expect=422).status_code == 422


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"name": None}, {"name": 123}, {}],
                         ids=["empty", "blank", "null", "number", "missing"])
def test_invalid_label_body_is_422(world, kind, limit, body):
    assert admin(world).post(url(world, kind), json=body).status_code == 422
    assert names(admin(world), world, kind) == []


@pytest.mark.plan("LBL-01")
@pytest.mark.parametrize("kind,limit", KINDS)
def test_labels_are_listed_alphabetically_ignoring_case(world, kind, limit):
    for n in ("beta", "Alpha", "charlie"):
        create(admin(world), world, kind, n)
    assert names(admin(world), world, kind) == ["Alpha", "beta", "charlie"]


# =================================================================== LBL-02
@pytest.mark.plan("LBL-02")
def test_new_ticket_has_empty_labels(world):
    t = world.a.ticket()
    assert t["tags"] == [] and t["components"] == []
    listed = world.a.tickets()[0]
    assert listed["tags"] == [] and listed["components"] == []


@pytest.mark.plan("LBL-02")
def test_ticket_is_created_with_labels_sorted_by_name(world):
    b = create(admin(world), world, "tags", "beta")
    a = create(admin(world), world, "tags", "Alpha")
    c = create(admin(world), world, "components", "Auth")
    t = world.a.ticket(tag_ids=[b["id"], a["id"]], component_ids=[c["id"]])
    assert label_names(t, "tags") == ["Alpha", "beta"]
    assert label_names(t, "components") == ["Auth"]
    assert label_names(world.a.tickets()[0], "tags") == ["Alpha", "beta"]


@pytest.mark.plan("LBL-02")
def test_update_replaces_keeps_and_clears_labels(world):
    a = create(admin(world), world, "tags", "a")
    b = create(admin(world), world, "tags", "b")
    c = create(admin(world), world, "components", "c")
    t = world.a.ticket(tag_ids=[a["id"], b["id"]], component_ids=[c["id"]])
    assert label_names(patch(world, t["id"], tag_ids=[b["id"]]), "tags") == ["b"]
    kept = patch(world, t["id"], title="renamed")                      # field omitted -> no change
    assert label_names(kept, "tags") == ["b"] and label_names(kept, "components") == ["c"]
    cleared = patch(world, t["id"], tag_ids=[])
    assert cleared["tags"] == [] and label_names(cleared, "components") == ["c"]


@pytest.mark.plan("LBL-02")
@pytest.mark.parametrize("field", ["tag_ids", "component_ids", "new_tags", "new_components"])
def test_null_label_fields_are_rejected(world, field):
    t = world.a.ticket()
    patch(world, t["id"], expect=422, **{field: None})


@pytest.mark.plan("LBL-02")
def test_unknown_label_ids_are_400(world):
    t = world.a.ticket()
    patch(world, t["id"], expect=400, tag_ids=[99999999])
    patch(world, t["id"], expect=400, component_ids=[99999999])
    r = admin(world).post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "tag_ids": [99999999]})
    assert r.status_code == 400


@pytest.mark.plan("LBL-02")
def test_label_of_another_project_is_400(world):
    foreign = create(world.client("outsider"), world, "tags", "foreign", project=world.b)
    t = world.a.ticket()
    patch(world, t["id"], expect=400, tag_ids=[foreign["id"]])


@pytest.mark.plan("LBL-02")
def test_more_than_ten_ids_is_422(world):
    t = world.a.ticket()
    patch(world, t["id"], expect=422, tag_ids=list(range(1, 12)))
    patch(world, t["id"], expect=422, component_ids=list(range(1, 12)))


@pytest.mark.plan("LBL-02")
def test_duplicate_ids_are_deduplicated(world):
    a = create(admin(world), world, "tags", "a")
    t = world.a.ticket(tag_ids=[a["id"], a["id"]])
    assert label_names(t, "tags") == ["a"]


@pytest.mark.plan("LBL-02")
def test_label_changes_are_written_to_history(world):
    a = create(admin(world), world, "tags", "alpha")
    b = create(admin(world), world, "tags", "beta")
    c = create(admin(world), world, "components", "core")
    t = world.a.ticket()

    def changes(ticket, field):
        return [(h["old_value"], h["new_value"]) for h in ticket["history"] if h["field_changed"] == field]

    after = patch(world, t["id"], tag_ids=[b["id"], a["id"]], component_ids=[c["id"]])
    assert changes(after, "tags") == [(None, "alpha, beta")]
    assert changes(after, "components") == [(None, "core")]
    same = patch(world, t["id"], tag_ids=[a["id"], b["id"]], component_ids=[c["id"]])
    assert changes(same, "tags") == [(None, "alpha, beta")]            # nothing new was logged
    removed = patch(world, t["id"], tag_ids=[a["id"]])
    assert changes(removed, "tags")[-1] == ("alpha, beta", "alpha")


@pytest.mark.plan("LBL-02")
def test_editor_can_change_labels_of_foreign_ticket(world):
    a = create(admin(world), world, "tags", "a")
    t = world.a.ticket()
    done = patch(world, t["id"], client=world.client("editor"), tag_ids=[a["id"]])
    assert label_names(done, "tags") == ["a"]


@pytest.mark.plan("LBL-02")
def test_reporter_can_create_ticket_with_labels(world):
    a = create(world.client("reporter"), world, "tags", "from-reporter")
    t = world.a.ticket(client=world.client("reporter"), tag_ids=[a["id"]])
    assert label_names(t, "tags") == ["from-reporter"]


# =================================================================== LBL-03
@pytest.mark.plan("LBL-03")
def test_new_names_are_created_together_with_the_ticket(world):
    t = world.a.ticket(new_tags=["Fresh", "fresh"], new_components=["Billing"])
    assert label_names(t, "tags") == ["Fresh"] and label_names(t, "components") == ["Billing"]
    assert names(admin(world), world, "tags") == ["Fresh"]
    assert names(admin(world), world, "components") == ["Billing"]


@pytest.mark.plan("LBL-03")
def test_new_name_reuses_existing_label_in_any_case(world):
    old = create(admin(world), world, "tags", "Beta")
    t = world.a.ticket(new_tags=["BETA"])
    assert [x["id"] for x in t["tags"]] == [old["id"]]
    assert names(admin(world), world, "tags") == ["Beta"]


@pytest.mark.plan("LBL-03")
def test_ids_and_new_names_are_combined(world):
    a = create(admin(world), world, "tags", "old")
    t = world.a.ticket(tag_ids=[a["id"]], new_tags=["new"])
    assert label_names(t, "tags") == ["new", "old"]


@pytest.mark.plan("LBL-03")
def test_failed_create_does_not_leave_new_labels_behind(world):
    r = admin(world).post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "will fail", "column_id": 99999999,
                                "new_tags": ["ghost"], "new_components": ["phantom"]})
    assert r.status_code == 400
    assert names(admin(world), world, "tags") == []
    assert names(admin(world), world, "components") == []
    assert world.a.tickets() == []


@pytest.mark.plan("LBL-03")
def test_failed_update_does_not_leave_new_labels_behind(world):
    t = world.a.ticket()
    patch(world, t["id"], expect=400, column_id=99999999, new_tags=["ghost"])
    assert names(admin(world), world, "tags") == []


@pytest.mark.plan("LBL-03")
def test_total_label_limit_counts_ids_and_new_names(world):
    ids = [create(admin(world), world, "tags", f"t{i}")["id"] for i in range(9)]
    r = admin(world).post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "too many", "tag_ids": ids, "new_tags": ["x", "y"]})
    assert r.status_code == 400
    assert "ghost" not in names(admin(world), world, "tags") and len(names(admin(world), world, "tags")) == 9
    ok(admin(world).post(f"/api/tickets/project/{world.a.id}",
                         json={"title": "fits", "tag_ids": ids, "new_tags": ["x"]}), 201)


@pytest.mark.plan("LBL-03")
@pytest.mark.parametrize("bad", [[""], ["   "], ["a" * 31], [f"t{i}" for i in range(11)]],
                         ids=["empty", "blank", "too-long", "eleven"])
def test_invalid_new_tag_names_are_422(world, bad):
    r = admin(world).post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "new_tags": bad})
    assert r.status_code == 422


@pytest.mark.plan("LBL-03")
def test_component_new_name_limit_is_50(world):
    ok(admin(world).post(f"/api/tickets/project/{world.a.id}",
                         json={"title": "x", "new_components": ["c" * 50]}), 201)
    r = admin(world).post(f"/api/tickets/project/{world.a.id}",
                          json={"title": "y", "new_components": ["c" * 51]})
    assert r.status_code == 422


@pytest.mark.plan("LBL-03")
def test_update_with_only_new_names_keeps_existing_labels(world):
    a = create(admin(world), world, "tags", "keep")
    t = world.a.ticket(tag_ids=[a["id"]])
    updated = patch(world, t["id"], new_tags=["added"])
    assert label_names(updated, "tags") == ["added", "keep"]


@pytest.mark.plan("LBL-03")
def test_reporter_can_create_ticket_with_new_names(world):
    t = world.a.ticket(client=world.client("reporter"), new_tags=["by-reporter"], new_components=["ui"])
    assert label_names(t, "tags") == ["by-reporter"] and label_names(t, "components") == ["ui"]


# =================================================================== LBL-04
@pytest.mark.plan("LBL-04")
def test_deleting_a_ticket_removes_its_label_links_but_keeps_the_labels(world, db):
    a = create(admin(world), world, "tags", "a")
    c = create(admin(world), world, "components", "c")
    t = world.a.ticket(tag_ids=[a["id"]], component_ids=[c["id"]])
    assert admin(world).delete(f"/api/tickets/{t['id']}").status_code == 204
    assert db("select count(*) from ticket_tags where ticket_id=?", (t["id"],)) == [(0,)]
    assert db("select count(*) from ticket_components where ticket_id=?", (t["id"],)) == [(0,)]
    assert names(admin(world), world, "tags") == ["a"]
    assert names(admin(world), world, "components") == ["c"]


@pytest.mark.plan("LBL-04")
def test_deleting_a_project_removes_its_labels_and_links(world, db):
    a = create(admin(world), world, "tags", "a")
    c = create(admin(world), world, "components", "c")
    t = world.a.ticket(tag_ids=[a["id"]], component_ids=[c["id"]])
    assert world.a.c.delete(f"/api/projects/{world.a.id}").status_code == 204
    assert db("select count(*) from tags where project_id=?", (world.a.id,)) == [(0,)]
    assert db("select count(*) from components where project_id=?", (world.a.id,)) == [(0,)]
    assert db("select count(*) from ticket_tags where ticket_id=?", (t["id"],)) == [(0,)]
    assert db("select count(*) from ticket_components where ticket_id=?", (t["id"],)) == [(0,)]


@pytest.mark.plan("LBL-04")
def test_deleting_one_project_keeps_labels_of_another(world, db):
    create(admin(world), world, "tags", "mine")
    create(world.client("outsider"), world, "tags", "theirs", project=world.b)
    assert world.a.c.delete(f"/api/projects/{world.a.id}").status_code == 204
    assert names(world.client("outsider"), world, "tags", project=world.b) == ["theirs"]


# =================================================================== LBL-05
@pytest.mark.plan("LBL-05")
@pytest.mark.parametrize("bad", [0, -1])
def test_parent_id_below_one_is_422_on_create_and_update(world, bad):
    r = admin(world).post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "parent_id": bad})
    assert r.status_code == 422
    t = world.a.ticket()
    patch(world, t["id"], expect=422, parent_id=bad)


@pytest.mark.plan("LBL-05")
def test_null_parent_id_still_means_no_parent(world):
    t = admin(world).post(f"/api/tickets/project/{world.a.id}", json={"title": "x", "parent_id": None})
    assert t.status_code == 201 and t.json()["parent_id"] is None