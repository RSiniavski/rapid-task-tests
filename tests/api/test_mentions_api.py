"""@mentions: the server keeps them as plain Markdown; the members list feeds the dropdown (MEN-01..02)."""
import pytest

from framework.factory import deactivate, ok

pytestmark = pytest.mark.api


def token(user):
    return f"@[{user.full_name}](user:{user.id})"


@pytest.fixture
def ticket(world):
    return world.a.ticket(title="Mention ticket")


def members(client, world):
    return ok(client.get(f"/api/projects/{world.a.id}/members")).json()


# ---------------------------------------------------------------- MEN-01 stored as Markdown
@pytest.mark.plan("MEN-01")
def test_description_keeps_the_mention_token(world, ticket):
    text = f"Please look {token(world.roles.editor)}, thanks"
    ok(world.a.c.patch(f"/api/tickets/{ticket['id']}", json={"description": text}))
    assert ok(world.a.c.get(f"/api/tickets/{ticket['id']}")).json()["description"] == text


@pytest.mark.plan("MEN-01")
def test_new_ticket_keeps_the_mention_token(world):
    text = f"{token(world.roles.editor)} owns this"
    created = world.a.ticket(title="Born with a mention", description=text)
    assert ok(world.a.c.get(f"/api/tickets/{created['id']}")).json()["description"] == text


@pytest.mark.plan("MEN-01")
def test_comment_keeps_the_mention_token(world, ticket):
    text = f"{token(world.roles.admin)} and {token(world.roles.reporter)} please check"
    c = ok(world.client("editor").post(f"/api/tickets/{ticket['id']}/comments", json={"body": text}), 201).json()
    assert c["body"] == text
    got = ok(world.client("reporter").get(f"/api/tickets/{ticket['id']}/comments")).json()
    assert [x["body"] for x in got] == [text]


@pytest.mark.plan("MEN-01")
def test_mention_of_a_stranger_is_kept_as_text(world, ticket):
    text = f"@[Nobody](user:99999999) {token(world.roles.outsider)}"        # no such user, and a user outside the project
    ok(world.a.c.patch(f"/api/tickets/{ticket['id']}", json={"description": text}))
    assert ok(world.a.c.get(f"/api/tickets/{ticket['id']}")).json()["description"] == text


# ---------------------------------------------------------------- MEN-02 members list
@pytest.mark.plan("MEN-02")
def test_anonymous_and_outsider_cannot_read_members(world, anon):
    assert anon.get(f"/api/projects/{world.a.id}/members").status_code == 401
    assert world.roles.outsider.client.get(f"/api/projects/{world.a.id}/members").status_code == 403


@pytest.mark.plan("MEN-02")
@pytest.mark.parametrize("role", ["admin", "editor", "contributor", "reporter"])
def test_every_member_gets_the_list_with_what_the_dropdown_needs(world, role):
    rows = members(world.client(role), world)
    by_id = {r["user"]["id"]: r["user"] for r in rows}
    for name in ["admin", "editor", "contributor", "reporter"]:
        u = world.roles.by_name(name)
        assert by_id[u.id]["full_name"] == u.full_name
        assert by_id[u.id]["email"] == u.email
        assert by_id[u.id]["is_active"] is True
    assert world.roles.outsider.id not in by_id


@pytest.mark.plan("MEN-02")
def test_removed_member_is_not_in_the_list(world, make_user):
    guest = make_user(tag="guest")
    world.a.add_member(guest, "contributor")
    assert guest.id in {r["user"]["id"] for r in members(world.a.c, world)}
    assert world.a.c.delete(f"/api/projects/{world.a.id}/members/{guest.id}").status_code == 204
    assert guest.id not in {r["user"]["id"] for r in members(world.a.c, world)}


@pytest.mark.plan("MEN-02")
def test_deactivated_member_is_marked_inactive(world, make_user):
    guest = make_user(tag="gone")
    world.a.add_member(guest, "contributor")
    deactivate(guest)
    rows = {r["user"]["id"]: r["user"] for r in members(world.a.c, world)}
    assert guest.id in rows and rows[guest.id]["is_active"] is False
