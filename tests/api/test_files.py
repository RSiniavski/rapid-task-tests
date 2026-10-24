"""Section 3 - profile, avatar and attachments (API / backend)."""
import re

import pytest

from framework import config
from framework.factory import GIF_BYTES, PDF_BYTES, PNG_BYTES, ok

pytestmark = pytest.mark.api

AVATAR_URL = re.compile(r"^/uploads/avatar_[0-9a-f]{32}\.(png|jpg|gif|webp)$")
ATT_URL = re.compile(r"^/uploads/[0-9a-f]{32}\.[a-z0-9]{1,10}$")


def avatar(client, name="me.png", data=PNG_BYTES, ctype="image/png"):
    return client.upload("/api/users/me/avatar", name, data, ctype)


def attach(client, project_id, name="note.txt", data=b"hello world", ctype="text/plain", ticket_id=None):
    params = {"project_id": project_id}
    if ticket_id is not None:
        params["ticket_id"] = ticket_id
    return client.upload("/api/attachments", name, data, ctype, params=params)


# =================================================================== FILE-01
@pytest.mark.plan("FILE-01")
def test_update_each_profile_field_alone_and_both(make_user):
    u = make_user(tag="prof_")
    c = u.client
    assert ok(c.patch("/api/users/me", json={"position": "QA Engineer"})).json()["position"] == "QA Engineer"
    r = ok(c.patch("/api/users/me", json={"full_name": "New Name"})).json()
    assert r["full_name"] == "New Name" and r["position"] == "QA Engineer"      # omitted field unchanged
    r = ok(c.patch("/api/users/me", json={"full_name": "Both A", "position": "Lead"})).json()
    assert (r["full_name"], r["position"]) == ("Both A", "Lead")
    me = ok(c.get("/api/auth/me")).json()                                       # persistence
    assert (me["full_name"], me["position"]) == ("Both A", "Lead")


@pytest.mark.plan("FILE-01")
def test_empty_patch_changes_nothing(make_user):
    u = make_user(tag="prof_")
    before = ok(u.client.get("/api/auth/me")).json()
    assert ok(u.client.patch("/api/users/me", json={})).json() == before


@pytest.mark.plan("FILE-01")
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_or_null_position_clears_it(make_user, blank):
    u = make_user(tag="prof_")
    ok(u.client.patch("/api/users/me", json={"position": "Dev"}))
    assert ok(u.client.patch("/api/users/me", json={"position": blank})).json()["position"] is None


@pytest.mark.plan("FILE-01")
def test_null_full_name_is_ignored(make_user):
    u = make_user(tag="prof_", full_name="Keep Me")
    assert ok(u.client.patch("/api/users/me", json={"full_name": None})).json()["full_name"] == "Keep Me"


@pytest.mark.plan("FILE-01")
@pytest.mark.parametrize("body", [{"full_name": ""}, {"full_name": "x" * 101}, {"position": "p" * 101},
                                  {"full_name": 123}, {"position": ["a"]}])
def test_invalid_profile_values_rejected_and_state_unchanged(make_user, body):
    u = make_user(tag="prof_", full_name="Stable Name")
    assert u.client.patch("/api/users/me", json=body).status_code == 422
    assert ok(u.client.get("/api/auth/me")).json()["full_name"] == "Stable Name"


@pytest.mark.plan("FILE-01")
def test_profile_boundary_lengths_accepted(make_user):
    u = make_user(tag="prof_")
    r = ok(u.client.patch("/api/users/me", json={"full_name": "n" * 100, "position": "p" * 100})).json()
    assert len(r["full_name"]) == 100 and len(r["position"]) == 100


@pytest.mark.plan("FILE-01")
def test_whitespace_only_full_name_should_be_rejected(make_user):
    u = make_user(tag="prof_", full_name="Keep Me")
    assert u.client.patch("/api/users/me", json={"full_name": "     "}).status_code == 422


# =================================================================== FILE-02
@pytest.mark.plan("FILE-02")
def test_avatar_upload_replace_delete_lifecycle(make_user, anon):
    u = make_user(tag="av_")
    c = u.client
    first = ok(avatar(c)).json()
    assert AVATAR_URL.match(first["avatar_url"])
    served = anon.get(first["avatar_url"], auth=False)
    assert served.status_code == 200 and served.headers["content-type"].startswith("image/png")
    assert served.content == PNG_BYTES

    second = ok(avatar(c, "other.gif", GIF_BYTES, "image/gif")).json()
    assert second["avatar_url"] != first["avatar_url"] and second["avatar_url"].endswith(".gif")
    assert anon.get(first["avatar_url"], auth=False).status_code == 404       # replaced file removed
    assert anon.get(second["avatar_url"], auth=False).status_code == 200
    assert ok(c.get("/api/auth/me")).json()["avatar_url"] == second["avatar_url"]

    deleted = ok(c.delete("/api/users/me/avatar")).json()
    assert deleted["avatar_url"] is None
    assert anon.get(second["avatar_url"], auth=False).status_code == 404
    assert ok(c.get("/api/auth/me")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-02")
def test_delete_avatar_when_absent_is_harmless(make_user):
    u = make_user(tag="av_")
    assert ok(u.client.delete("/api/users/me/avatar")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-02")
@pytest.mark.parametrize("name,ctype,ext", [("a.png", "image/png", ".png"), ("a.jpg", "image/jpeg", ".jpg"),
                                            ("a.gif", "image/gif", ".gif"), ("a.webp", "image/webp", ".webp")])
def test_each_allowed_avatar_type_is_accepted(make_user, name, ctype, ext):
    u = make_user(tag="av_")
    assert ok(avatar(u.client, name, PNG_BYTES, ctype)).json()["avatar_url"].endswith(ext)


@pytest.mark.plan("FILE-02")
@pytest.mark.needs_local_server
def test_avatar_files_are_removed_from_disk_on_replace_and_delete(make_user, uploads_dir):
    u = make_user(tag="av_")
    url = ok(avatar(u.client)).json()["avatar_url"]
    stored = uploads_dir / url.rsplit("/", 1)[-1]
    assert stored.is_file()
    ok(u.client.delete("/api/users/me/avatar"))
    assert not stored.exists()


# =================================================================== FILE-03
@pytest.mark.plan("FILE-03")
def test_avatar_upload_without_auth_is_401(anon):
    r = anon.upload("/api/users/me/avatar", "a.png", PNG_BYTES, "image/png", auth=False)
    assert r.status_code == 401


@pytest.mark.plan("FILE-03")
def test_empty_avatar_is_rejected(make_user):
    u = make_user(tag="av_")
    r = avatar(u.client, "a.png", b"", "image/png")
    assert r.status_code == 400 and "empty" in r.json()["detail"].lower()
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-03")
@pytest.mark.slow
def test_oversized_avatar_is_413_and_limit_is_inclusive(make_user):
    u = make_user(tag="av_")
    over = avatar(u.client, "big.png", b"\x00" * (config.MAX_AVATAR_BYTES + 1), "image/png")
    assert over.status_code == 413
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None
    exact_data = PNG_BYTES + b"\x00" * (config.MAX_AVATAR_BYTES - len(PNG_BYTES))
    exact = avatar(u.client, "exact.png", exact_data, "image/png")
    assert exact.status_code == 200


@pytest.mark.plan("FILE-03", "UI-07")
@pytest.mark.security
@pytest.mark.parametrize("name,ctype", [("a.svg", "image/svg+xml"), ("a.txt", "text/plain"),
                                        ("a.html", "text/html"), ("a.pdf", "application/pdf"),
                                        ("a.exe", "application/octet-stream"), ("a.png", "application/octet-stream"),
                                        ("a.bmp", "image/bmp")])
def test_unsupported_avatar_types_are_rejected(make_user, name, ctype):
    u = make_user(tag="av_")
    assert avatar(u.client, name, b"<svg onload=alert(1)>", ctype).status_code == 400
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-03", "UI-07")
@pytest.mark.security
@pytest.mark.parametrize("content", [b"<html><script>alert(1)</script></html>", b"<svg onload=alert(1)/>", b"plain text"],
                         ids=["html", "svg", "text"])
def test_spoofed_avatar_content_is_rejected_and_nothing_is_stored(make_user, content):
    u = make_user(tag="av_")
    r = avatar(u.client, "evil.png", content, "image/png")
    assert r.status_code == 400
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-03", "FILE-08")
@pytest.mark.security
@pytest.mark.parametrize("filename", ["../../evil.png", "..\\..\\evil.png", "a/b/c.png"])
def test_dangerous_avatar_filename_never_influences_stored_name(make_user, filename):
    u = make_user(tag="av_")
    r = avatar(u.client, filename, PNG_BYTES, "image/png")
    if r.status_code == 200:
        assert AVATAR_URL.match(r.json()["avatar_url"])
    else:
        assert r.status_code in (400, 422)


# =================================================================== FILE-04
@pytest.mark.plan("FILE-04")
def test_upload_attachment_to_project_then_bind_to_new_ticket(world, anon):
    c = world.roles.reporter.client
    a = ok(attach(c, world.a.id, "spec.txt", b"payload-123", "text/plain"), 201).json()
    assert a["ticket_id"] is None and a["filename"] == "spec.txt" and a["size"] == len(b"payload-123")
    assert a["content_type"] == "text/plain" and a["kind"] == "file" and ATT_URL.match(a["url"])
    assert anon.get(a["url"], auth=False).content == b"payload-123"
    t = world.a.ticket(client=c, attachment_ids=[a["id"]])
    assert [x["id"] for x in t["attachments"]] == [a["id"]] and t["attachments"][0]["ticket_id"] == t["id"]


@pytest.mark.plan("FILE-04")
def test_upload_attachment_directly_to_ticket_and_list_in_ticket_response(world):
    t = world.a.ticket()
    a = ok(attach(world.a.c, world.a.id, "log.txt", b"abc", ticket_id=t["id"]), 201).json()
    assert a["ticket_id"] == t["id"]
    fresh = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert [x["filename"] for x in fresh["attachments"]] == ["log.txt"]
    by_key = ok(world.a.c.get(f"/api/tickets/key/{t['key']}")).json()
    assert by_key["attachments"][0]["id"] == a["id"]


@pytest.mark.plan("FILE-04")
@pytest.mark.parametrize("name,ctype,kind", [("p.png", "image/png", "image"), ("v.mp4", "video/mp4", "video"),
                                             ("a.mp3", "audio/mpeg", "audio"), ("d.pdf", "application/pdf", "file"),
                                             ("i.svg", "image/svg+xml", "file")])
def test_attachment_kind_is_derived_from_content_type(world, name, ctype, kind):
    assert ok(attach(world.a.c, world.a.id, name, b"x", ctype), 201).json()["kind"] == kind


@pytest.mark.plan("FILE-04")
def test_attachment_content_type_falls_back_to_filename_guess(world):
    a = ok(attach(world.a.c, world.a.id, "pic.png", PNG_BYTES, "application/octet-stream"), 201).json()
    assert a["content_type"] == "image/png" and a["kind"] == "image"


@pytest.mark.plan("FILE-04")
def test_attachment_cannot_be_bound_by_another_user_or_project(world):
    mine = ok(attach(world.roles.editor.client, world.a.id), 201).json()
    t = world.a.ticket(client=world.roles.reporter.client, attachment_ids=[mine["id"]])  # not the uploader
    assert t["attachments"] == []
    other = ok(attach(world.b.c, world.b.id), 201).json()
    t2 = world.a.ticket(attachment_ids=[other["id"]])                                    # other project
    assert t2["attachments"] == []


# =================================================================== FILE-05
@pytest.mark.plan("FILE-05")
def test_attachment_upload_requires_auth(world, anon):
    r = anon.upload("/api/attachments", "a.txt", b"x", "text/plain", params={"project_id": world.a.id}, auth=False)
    assert r.status_code == 401


@pytest.mark.plan("FILE-05")
def test_attachment_upload_non_member_denied_without_leak(world):
    t = world.a.ticket()
    for tid in (None, t["id"]):
        r = attach(world.roles.outsider.client, world.a.id, ticket_id=tid)
        assert r.status_code == 403 and "member" in r.json()["detail"].lower()
    assert world.a.c.get(f"/api/tickets/{t['id']}").json()["attachments"] == []


@pytest.mark.plan("FILE-05")
def test_attachment_upload_invalid_or_mismatched_project_and_ticket(world):
    t_a, t_b = world.a.ticket(), world.b.ticket()
    c = world.a.c
    assert attach(c, 987654321).status_code == 403                               # unknown project -> not a member
    assert attach(c, world.a.id, ticket_id=987654321).status_code == 404        # unknown ticket
    assert attach(c, world.a.id, ticket_id=t_b["id"]).status_code == 404        # ticket of another project
    assert attach(world.b.c, world.b.id, ticket_id=t_a["id"]).status_code == 404
    assert world.a.c.get(f"/api/tickets/{t_a['id']}").json()["attachments"] == []


@pytest.mark.plan("FILE-05")
def test_reporter_and_foreign_contributor_cannot_attach_to_others_tickets(world):
    t = world.a.ticket()
    assert attach(world.roles.reporter.client, world.a.id, ticket_id=t["id"]).status_code == 403
    assert attach(world.roles.contributor.client, world.a.id, ticket_id=t["id"]).status_code == 403
    assert attach(world.roles.editor.client, world.a.id, ticket_id=t["id"]).status_code == 201


@pytest.mark.plan("FILE-05")
def test_attachment_upload_validation_errors(world):
    c = world.a.c
    assert c.post("/api/attachments", params={"project_id": world.a.id}).status_code == 422       # no file
    assert c.upload("/api/attachments", "a.txt", b"x", "text/plain").status_code == 422          # no project_id
    assert c.upload("/api/attachments", "a.txt", b"x", "text/plain",
                    params={"project_id": "abc"}).status_code == 422
    assert attach(c, world.a.id, "empty.txt", b"").status_code == 400                             # empty file


@pytest.mark.plan("FILE-05")
@pytest.mark.slow
def test_oversized_attachment_is_413(world):
    r = attach(world.a.c, world.a.id, "big.bin", b"\x00" * (config.MAX_ATTACHMENT_BYTES + 1), "application/octet-stream")
    assert r.status_code == 413


# =================================================================== FILE-06
@pytest.mark.plan("FILE-06")
def test_uploader_deletes_unbound_attachment_and_file_disappears(world, anon):
    a = ok(attach(world.roles.reporter.client, world.a.id), 201).json()
    assert world.roles.editor.client.delete(f"/api/attachments/{a['id']}").status_code == 403   # unbound: uploader only
    assert world.roles.reporter.client.delete(f"/api/attachments/{a['id']}").status_code == 204
    assert anon.get(a["url"], auth=False).status_code == 404
    assert world.roles.reporter.client.delete(f"/api/attachments/{a['id']}").status_code == 404  # repeat


@pytest.mark.plan("FILE-06")
def test_ticket_attachment_delete_follows_ticket_edit_rights(world):
    t = world.a.ticket(client=world.roles.contributor.client)                      # contributor is reporter
    a = ok(attach(world.roles.contributor.client, world.a.id, ticket_id=t["id"]), 201).json()
    assert world.roles.reporter.client.delete(f"/api/attachments/{a['id']}").status_code == 403
    assert world.roles.outsider.client.delete(f"/api/attachments/{a['id']}").status_code == 403
    assert world.roles.editor.client.delete(f"/api/attachments/{a['id']}").status_code == 204
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["attachments"] == []


@pytest.mark.plan("FILE-06")
def test_delete_unknown_attachment_is_404(world):
    assert world.a.c.delete("/api/attachments/987654321").status_code == 404


@pytest.mark.plan("FILE-06")
@pytest.mark.needs_local_server
def test_attachment_delete_keeps_db_and_disk_consistent(world, db, uploads_dir):
    a = ok(attach(world.a.c, world.a.id), 201).json()
    stored = a["url"].rsplit("/", 1)[-1]
    assert (uploads_dir / stored).is_file()
    ok(world.a.c.delete(f"/api/attachments/{a['id']}"), 204)
    assert not (uploads_dir / stored).exists()
    assert db("SELECT COUNT(*) FROM ticket_attachments WHERE id=?", (a["id"],))[0][0] == 0


# =================================================================== FILE-07
def upload_and_fetch(world, anon, name, ctype, data=b"content"):
    a = ok(attach(world.a.c, world.a.id, name, data, ctype), 201).json()
    return anon.get(a["url"], auth=False)


@pytest.mark.plan("FILE-07", "UI-07")
@pytest.mark.security
@pytest.mark.parametrize("name,ctype,expected", [
    ("pic.png", "image/png", "image/png"), ("pic.jpg", "image/jpeg", "image/jpeg"),
    ("doc.pdf", "application/pdf", "application/pdf"), ("song.mp3", "audio/mpeg", "audio/mpeg"),
    ("clip.mp4", "video/mp4", "video/mp4")])
def test_safe_types_render_inline_with_nosniff(world, anon, name, ctype, expected):
    r = upload_and_fetch(world, anon, name, ctype)
    assert r.status_code == 200 and r.headers["content-type"].startswith(expected)
    assert not r.headers.get("content-disposition", "").lower().startswith("attachment")
    assert "sandbox" not in r.headers.get("content-security-policy", "")
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.plan("FILE-07", "UI-07")
@pytest.mark.security
@pytest.mark.parametrize("name,ctype", [
    ("page.html", "text/html"), ("vector.svg", "image/svg+xml"), ("run.exe", "application/x-msdownload"),
    ("script.js", "application/javascript"), ("archive.zip", "application/zip"),
    ("noext", "application/octet-stream"), ("data.xyz123", "application/octet-stream"),
    ("doc.xhtml", "application/xhtml+xml")])
def test_active_or_unknown_types_download_in_sandbox(world, anon, name, ctype):
    r = upload_and_fetch(world, anon, name, ctype, b"<script>alert(1)</script>")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/octet-stream"), r.headers["content-type"]
    cd = r.headers.get("content-disposition", "")
    assert cd == "" or cd.lower().startswith("attachment")   # see known-issue test below for the header itself
    assert "sandbox" in r.headers.get("content-security-policy", "")
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.plan("FILE-07")
@pytest.mark.security
def test_download_types_carry_explicit_attachment_disposition(world, anon):
    r = upload_and_fetch(world, anon, "page.html", "text/html")
    assert r.headers.get("content-disposition", "").lower().startswith("attachment")


@pytest.mark.plan("FILE-07")
@pytest.mark.security
def test_declared_mime_cannot_force_inline_for_html_file(world, anon):
    r = upload_and_fetch(world, anon, "sneaky.html", "image/png")
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert "sandbox" in r.headers.get("content-security-policy", "")


@pytest.mark.plan("FILE-07")
@pytest.mark.security
@pytest.mark.parametrize("path", ["/uploads/missing.png", "/uploads/..%2f..%2fetc%2fpasswd", "/uploads/%2e%2e/main.py",
                                  "/uploads/..%5c..%5cwindows%5cwin.ini", "/uploads/noext", "/uploads/a.b.c",
                                  "/uploads/%00.png", "/uploads/" + "a" * 300 + ".png"])
def test_traversal_and_missing_upload_names_return_404(anon, path):
    assert anon.get(path, auth=False).status_code == 404


# =================================================================== FILE-08
@pytest.mark.plan("FILE-08", "TICKET-14")
@pytest.mark.security
@pytest.mark.parametrize("filename,expected_name", [
    ("звіт_квартал_🚀.txt", "звіт_квартал_🚀.txt"),
    ("../../etc/passwd.txt", "passwd.txt"),
    ("..\\..\\windows\\win.txt", "win.txt"),
    ("<img src=x onerror=alert(1)>.txt", "<img src=x onerror=alert(1)>.txt"),
    ('quote"semi;colon.txt', None),
])
def test_original_filename_is_kept_for_display_but_never_used_for_storage(world, filename, expected_name):
    r = attach(world.a.c, world.a.id, filename, b"data", "text/plain")
    assert r.status_code == 201, r.text
    a = r.json()
    if expected_name:
        assert a["filename"] == expected_name
    assert "/" not in a["filename"] and "\\" not in a["filename"]
    assert ATT_URL.match(a["url"])


@pytest.mark.plan("FILE-08")
def test_duplicate_filenames_get_distinct_storage_names(world, anon):
    a = ok(attach(world.a.c, world.a.id, "same.txt", b"one"), 201).json()
    b = ok(attach(world.a.c, world.a.id, "same.txt", b"two"), 201).json()
    assert a["url"] != b["url"] and a["id"] != b["id"]
    assert anon.get(a["url"], auth=False).content == b"one" and anon.get(b["url"], auth=False).content == b"two"


@pytest.mark.plan("FILE-08")
def test_very_long_filename_is_truncated_and_stored_safely(world):
    long_name = "n" * 400 + ".txt"
    a = ok(attach(world.a.c, world.a.id, long_name, b"x"), 201).json()
    assert 0 < len(a["filename"]) <= 255
    assert ATT_URL.match(a["url"]) and a["url"].endswith(".txt")


@pytest.mark.plan("FILE-08")
def test_weird_extension_is_normalised_to_safe_suffix(world):
    a = ok(attach(world.a.c, world.a.id, "archive.TAR.GZ", b"x"), 201).json()
    assert ATT_URL.match(a["url"]) and a["url"].endswith(".gz")
    b = ok(attach(world.a.c, world.a.id, "weird.ext!@#", b"x"), 201).json()
    assert b["url"].endswith(".bin")
