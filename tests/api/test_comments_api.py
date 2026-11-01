"""Ticket comments (API) and the extra history events (CMT-01..05)."""
import pytest

from framework.factory import ok
from tests.api.test_files import attach

pytestmark = pytest.mark.api


@pytest.fixture
def ticket(world):
    return world.a.ticket(title="Commented ticket")


def add(client, ticket, body="hello"):
    return ok(client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": body}), 201).json()


def comments(client, ticket, order=None):
    url = f"/api/tickets/{ticket['id']}/comments" + (f"?order={order}" if order else "")
    return ok(client.get(url)).json()


def history(world, ticket):
    rows = ok(world.client("admin").get(f"/api/tickets/{ticket['id']}")).json()["history"]
    return [(h["field_changed"], h["old_value"], h["new_value"]) for h in rows]


# ---------------------------------------------------------------- CMT-01 access
@pytest.mark.plan("CMT-01")
def test_comments_require_login(world, anon, ticket):
    assert anon.get(f"/api/tickets/{ticket['id']}/comments").status_code == 401
    assert anon.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "x"}).status_code == 401


@pytest.mark.plan("CMT-01")
def test_outsider_cannot_read_or_write_comments(world, ticket):
    outsider = world.roles.outsider.client
    assert outsider.get(f"/api/tickets/{ticket['id']}/comments").status_code == 403
    assert outsider.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "x"}).status_code == 403


@pytest.mark.plan("CMT-01")
@pytest.mark.parametrize("role", ["admin", "editor", "contributor", "reporter"])
def test_every_member_can_comment_and_read(world, ticket, role):
    c = add(world.client(role), ticket, f"from {role}")
    assert c["author_id"] == world.roles.by_name(role).id and c["body"] == f"from {role}"
    assert [x["id"] for x in comments(world.client("reporter"), ticket)] == [c["id"]]


@pytest.mark.plan("CMT-01")
def test_unknown_ticket_and_comment_are_404(world):
    admin = world.client("admin")
    assert admin.get("/api/tickets/99999999/comments").status_code == 404
    assert admin.post("/api/tickets/99999999/comments", json={"body": "x"}).status_code == 404
    assert admin.patch("/api/comments/99999999", json={"body": "x"}).status_code == 404
    assert admin.delete("/api/comments/99999999").status_code == 404


# ---------------------------------------------------------------- CMT-02 content and order
@pytest.mark.plan("CMT-02")
def test_comments_are_sorted_oldest_first_by_default_and_newest_first_on_request(world, ticket):
    admin = world.client("admin")
    ids = [add(admin, ticket, f"c{i}")["id"] for i in range(3)]
    assert [c["id"] for c in comments(admin, ticket)] == ids
    assert [c["id"] for c in comments(admin, ticket, "asc")] == ids
    assert [c["id"] for c in comments(admin, ticket, "desc")] == ids[::-1]
    assert admin.get(f"/api/tickets/{ticket['id']}/comments?order=sideways").status_code == 422


@pytest.mark.plan("CMT-02")
@pytest.mark.parametrize("body", ["", "   ", "\n\n"])
def test_blank_comment_is_rejected(world, ticket, body):
    r = world.client("admin").post(f"/api/tickets/{ticket['id']}/comments", json={"body": body})
    assert r.status_code == 422


@pytest.mark.plan("CMT-02")
def test_comment_length_limit(world, ticket):
    admin = world.client("admin")
    assert admin.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "x" * 20000}).status_code == 201
    assert admin.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "x" * 20001}).status_code == 422


@pytest.mark.plan("CMT-02")
def test_markdown_body_is_stored_as_written(world, ticket):
    body = "**bold**\n\n- [ ] task\n\nsee " + ticket["key"]
    c = add(world.client("editor"), ticket, body)
    assert comments(world.client("admin"), ticket)[0]["body"] == body and c["updated_at"] is None


@pytest.mark.plan("CMT-02")
def test_comments_of_one_ticket_do_not_leak_into_another(world, ticket):
    other = world.a.ticket(title="Other")
    add(world.client("admin"), ticket, "mine")
    assert comments(world.client("admin"), other) == []


# ---------------------------------------------------------------- CMT-03 edit and delete rules
@pytest.mark.plan("CMT-03")
def test_author_edits_own_comment_and_updated_at_is_set(world, ticket):
    reporter = world.client("reporter")
    c = add(reporter, ticket, "first")
    got = ok(reporter.patch(f"/api/comments/{c['id']}", json={"body": "second"})).json()
    assert got["body"] == "second" and got["updated_at"] is not None


@pytest.mark.plan("CMT-03")
@pytest.mark.parametrize("role", ["admin", "editor", "contributor"])
def test_nobody_edits_a_foreign_comment_not_even_admin(world, ticket, role):
    c = add(world.client("reporter"), ticket, "mine")
    assert world.client(role).patch(f"/api/comments/{c['id']}", json={"body": "hacked"}).status_code == 403
    assert comments(world.client("admin"), ticket)[0]["body"] == "mine"


@pytest.mark.plan("CMT-03")
def test_author_deletes_own_comment(world, ticket):
    c = add(world.client("contributor"), ticket)
    assert world.client("contributor").delete(f"/api/comments/{c['id']}").status_code == 204
    assert comments(world.client("admin"), ticket) == []


@pytest.mark.plan("CMT-03")
def test_admin_deletes_any_comment_but_editor_and_contributor_cannot(world, ticket):
    c = add(world.client("reporter"), ticket)
    for role in ("editor", "contributor"):
        assert world.client(role).delete(f"/api/comments/{c['id']}").status_code == 403
    assert len(comments(world.client("admin"), ticket)) == 1
    assert world.client("admin").delete(f"/api/comments/{c['id']}").status_code == 204
    assert comments(world.client("admin"), ticket) == []


@pytest.mark.plan("CMT-03")
def test_outsider_cannot_edit_or_delete(world, ticket):
    c = add(world.client("admin"), ticket)
    outsider = world.roles.outsider.client
    assert outsider.patch(f"/api/comments/{c['id']}", json={"body": "x"}).status_code == 403
    assert outsider.delete(f"/api/comments/{c['id']}").status_code == 403


@pytest.mark.plan("CMT-03")
def test_edit_validates_the_body(world, ticket):
    c = add(world.client("admin"), ticket)
    assert world.client("admin").patch(f"/api/comments/{c['id']}", json={"body": "  "}).status_code == 422


# ---------------------------------------------------------------- CMT-04 history events
@pytest.mark.plan("CMT-04")
def test_comment_events_are_in_the_history(world, ticket):
    reporter = world.client("reporter")
    c = add(reporter, ticket, "one")
    ok(reporter.patch(f"/api/comments/{c['id']}", json={"body": "two"}))
    ok(reporter.patch(f"/api/comments/{c['id']}", json={"body": "two"}))        # no real change: no new event
    ok(reporter.delete(f"/api/comments/{c['id']}"), 204)
    events = [h for h in history(world, ticket) if h[0].startswith("comment_")]
    cid = str(c["id"])
    assert events == [("comment_added", None, cid), ("comment_edited", None, cid), ("comment_deleted", cid, None)]


@pytest.mark.plan("CMT-04")
def test_description_change_keeps_old_and_new_text(world, ticket):
    admin = world.client("admin")
    ok(admin.patch(f"/api/tickets/{ticket['id']}", json={"description": "first text"}))
    ok(admin.patch(f"/api/tickets/{ticket['id']}", json={"description": "second text"}))
    got = [h for h in history(world, ticket) if h[0] == "description"]
    assert got == [("description", None, "first text"), ("description", "first text", "second text")]


@pytest.mark.plan("CMT-04")
def test_attachment_events_are_in_the_history(world, ticket):
    a = ok(attach(world.client("admin"), world.a.id, name="spec.txt", ticket_id=ticket["id"]), 201).json()
    ok(world.client("admin").delete(f"/api/attachments/{a['id']}"), 204)
    got = [h for h in history(world, ticket) if h[0].startswith("attachment_")]
    assert got == [("attachment_added", None, "spec.txt"), ("attachment_removed", "spec.txt", None)]


@pytest.mark.plan("CMT-04")
def test_file_added_while_creating_a_ticket_is_not_a_history_event(world):
    a = ok(attach(world.client("admin"), world.a.id, name="early.txt"), 201).json()
    t = world.a.ticket(title="With early file", attachment_ids=[a["id"]])
    assert [h for h in history(world, t) if h[0].startswith("attachment_")] == []


@pytest.mark.plan("CMT-04")
def test_subticket_events_are_in_the_parent_history(world):
    epic = world.a.ticket(type="Epic", title="Parent")
    child = world.a.ticket(title="Kid", parent_id=epic["id"])
    admin = world.client("admin")
    ok(admin.patch(f"/api/tickets/{child['id']}", json={"parent_id": None}))
    got = [h for h in history(world, epic) if h[0].startswith("subticket_")]
    assert got == [("subticket_added", None, child["key"]), ("subticket_removed", child["key"], None)]
    kid_rows = [h for h in history(world, child) if h[0] == "parent"]
    assert kid_rows == [("parent", epic["key"], None)]


@pytest.mark.plan("CMT-04")
def test_moving_a_ticket_to_another_parent_is_logged_on_both_parents(world):
    p1 = world.a.ticket(type="Epic", title="P1")
    p2 = world.a.ticket(type="Epic", title="P2")
    child = world.a.ticket(title="Kid", parent_id=p1["id"])
    ok(world.client("admin").patch(f"/api/tickets/{child['id']}", json={"parent_id": p2["id"]}))
    assert ("subticket_removed", child["key"], None) in history(world, p1)
    assert ("subticket_added", None, child["key"]) in history(world, p2)


# ---------------------------------------------------------------- CMT-05 clean-up
@pytest.mark.plan("CMT-05")
def test_deleting_a_ticket_removes_its_comments(world):
    t = world.a.ticket(title="To delete")
    add(world.client("admin"), t)
    assert world.client("admin").delete(f"/api/tickets/{t['id']}").status_code == 204
    assert world.client("admin").get(f"/api/tickets/{t['id']}/comments").status_code == 404


@pytest.mark.plan("CMT-05")
def test_comments_survive_a_ticket_edit(world, ticket):
    add(world.client("admin"), ticket, "stays")
    ok(world.client("admin").patch(f"/api/tickets/{ticket['id']}", json={"title": "Renamed"}))
    assert [c["body"] for c in comments(world.client("admin"), ticket)] == ["stays"]
