"""Images and files pasted into comments (IMG-01 .. IMG-03).
Upload: POST /api/attachments?project_id=..&ticket_id=..&purpose=comment - any project member, any file (same size limit).
The file is a normal ticket attachment (it shows in the Attachments and in the History)."""
import pytest

from framework.factory import GIF_BYTES, PNG_BYTES, ok
from tests.api.test_files import attach

pytestmark = pytest.mark.api

ROLES = ["admin", "editor", "contributor", "reporter"]


def paste(client, project_id, ticket_id, name="image.png", data=PNG_BYTES, ctype="image/png", purpose="comment"):
    params = {"project_id": project_id, "ticket_id": ticket_id}
    if purpose is not None:
        params["purpose"] = purpose
    return client.upload("/api/attachments", name, data, ctype, params=params)


@pytest.fixture
def ticket(world):
    return world.a.ticket(title="Ticket with comment images")          # made by the admin: contributor and reporter can not edit it


def full(world, ticket):
    return ok(world.client("admin").get(f"/api/tickets/{ticket['id']}")).json()


# ---------------------------------------------------------------- IMG-01 who may add an image from a comment
@pytest.mark.plan("IMG-01")
@pytest.mark.parametrize("role", ROLES)
def test_every_member_can_add_an_image_from_a_comment(world, ticket, anon, role):
    user = world.roles.by_name(role)
    a = ok(paste(user.client, world.a.id, ticket["id"]), 201).json()
    assert a["ticket_id"] == ticket["id"] and a["kind"] == "image" and a["uploader_id"] == user.id
    assert a["filename"] == "image.png" and a["url"].startswith("/uploads/") and a["size"] == len(PNG_BYTES)
    assert anon.get(a["url"], auth=False).status_code == 200                       # the file can be shown
    t = full(world, ticket)
    assert a["id"] in [x["id"] for x in t["attachments"]]                          # it is a normal ticket attachment
    assert ("attachment_added", None, "image.png") in [(h["field_changed"], h["old_value"], h["new_value"]) for h in t["history"]]


@pytest.mark.plan("IMG-01")
def test_the_image_can_be_used_in_a_comment(world, ticket):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"]), 201).json()
    body = f"look:\n\n![image.png]({a['url']})"
    c = ok(world.roles.reporter.client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": body}), 201).json()
    assert c["body"] == body


@pytest.mark.plan("IMG-01")
@pytest.mark.parametrize("name,data,ctype", [("shot.jpg", PNG_BYTES, "image/jpeg"), ("anim.gif", GIF_BYTES, "image/gif"),
                                             ("p.webp", PNG_BYTES, "image/webp"), ("UPPER.PNG", PNG_BYTES, "image/png")])
def test_the_allowed_image_types(world, ticket, name, data, ctype):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"], name, data, ctype), 201).json()
    assert a["kind"] == "image" and a["filename"] == name


@pytest.mark.plan("IMG-01")
def test_the_old_rule_is_the_same_without_the_purpose(world, ticket):
    for role in ("contributor", "reporter"):                                       # they can not edit this ticket
        assert paste(world.client(role), world.a.id, ticket["id"], purpose=None).status_code == 403
    assert paste(world.client("editor"), world.a.id, ticket["id"], purpose=None).status_code == 201


# ---------------------------------------------------------------- IMG-02 other files, and how they are served
@pytest.mark.plan("IMG-02")
@pytest.mark.parametrize("name,data,ctype,kind", [
    ("run.log", b"2026-11-06 10:00 ERROR something failed\n", "text/plain", "file"),
    ("report.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf", "file"),
    ("data.zip", b"PK\x03\x04 not really a zip", "application/zip", "file"),
    ("notes.txt", b"hello", "text/plain", "file"),
    ("video.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4", "video"),
    ("noext", b"some bytes", "application/octet-stream", "file"),
    ("page.html", b"<script>alert(1)</script>", "text/html", "file"),
    ("pic.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml", "file"),
], ids=["log", "pdf", "zip", "txt", "video", "no-extension", "html", "svg"])
def test_any_file_can_be_added_from_a_comment(world, ticket, name, data, ctype, kind):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"], name, data, ctype), 201).json()
    assert a["ticket_id"] == ticket["id"] and a["filename"] == name and a["kind"] == kind, a
    assert a["url"].startswith("/uploads/") and a["size"] == len(data)
    assert a["id"] in [x["id"] for x in full(world, ticket)["attachments"]]


@pytest.mark.plan("IMG-02")
@pytest.mark.parametrize("name,data,ctype", [
    ("page.html", b"<script>alert(1)</script>", "text/html"),
    ("pic.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
    ("run.log", b"log line", "text/plain"),
], ids=["html", "svg", "log"])
def test_files_that_can_run_are_only_downloaded(world, ticket, anon, name, data, ctype):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"], name, data, ctype), 201).json()
    r = anon.get(a["url"], auth=False)
    assert r.status_code == 200
    assert r.headers["Content-Disposition"].startswith("attachment")                # never shown in our origin
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Content-Type"].startswith("application/octet-stream")
    assert r.content == data


@pytest.mark.plan("IMG-02")
def test_wrong_requests_are_refused(world, ticket, anon):
    c = world.roles.reporter.client
    no_ticket = c.upload("/api/attachments", "image.png", PNG_BYTES, "image/png",
                         params={"project_id": world.a.id, "purpose": "comment"})
    assert no_ticket.status_code == 422                                            # a comment image needs a ticket
    other = world.b.ticket()
    assert paste(c, world.a.id, other["id"]).status_code == 404                    # the ticket is in another project
    assert paste(c, world.a.id, 999999).status_code == 404
    assert paste(c, world.a.id, ticket["id"], purpose="avatar").status_code == 422  # only "comment" is known
    assert paste(world.roles.outsider.client, world.a.id, ticket["id"]).status_code == 403   # not a member
    r = anon.upload("/api/attachments", "image.png", PNG_BYTES, "image/png", auth=False,
                    params={"project_id": world.a.id, "ticket_id": ticket["id"], "purpose": "comment"})
    assert r.status_code == 401
    assert full(world, ticket)["attachments"] == []


# ---------------------------------------------------------------- IMG-03 the image after the comment
@pytest.mark.plan("IMG-03")
def test_deleting_the_comment_keeps_the_image_in_the_attachments(world, ticket, anon):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"]), 201).json()
    c = ok(world.roles.reporter.client.post(f"/api/tickets/{ticket['id']}/comments",
                                            json={"body": f"![image.png]({a['url']})"}), 201).json()
    ok(world.roles.reporter.client.delete(f"/api/comments/{c['id']}"), 204)
    assert a["id"] in [x["id"] for x in full(world, ticket)["attachments"]]
    assert anon.get(a["url"], auth=False).status_code == 200


@pytest.mark.plan("IMG-03")
def test_who_can_remove_the_image(world, ticket, anon):
    a = ok(paste(world.roles.reporter.client, world.a.id, ticket["id"]), 201).json()
    assert world.roles.reporter.client.delete(f"/api/attachments/{a['id']}").status_code == 403     # the old rule: not the ticket editor
    assert world.roles.contributor.client.delete(f"/api/attachments/{a['id']}").status_code == 403
    ok(world.roles.editor.client.delete(f"/api/attachments/{a['id']}"), 204)
    assert anon.get(a["url"], auth=False).status_code == 404
    assert full(world, ticket)["attachments"] == []


@pytest.mark.plan("IMG-03")
def test_deleting_the_ticket_removes_the_comment_images(world, anon):
    t = world.a.ticket(title="To delete")
    a = ok(paste(world.roles.reporter.client, world.a.id, t["id"]), 201).json()
    ok(world.client("admin").delete(f"/api/tickets/{t['id']}"), 204)
    assert anon.get(a["url"], auth=False).status_code == 404
