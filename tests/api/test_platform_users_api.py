"""Platform admin tool: the app's users - list, search, block, unblock, soft delete (PLT-15 .. PLT-18)."""
import pytest

from framework.client import Client
from framework.factory import create_project, deactivate, ok, register_user, uid, unique_email
from framework.platform_api import P, audit, find_user, users
from framework import config

pytestmark = pytest.mark.api


def person(make_user, tag="pu", token=None, **kw):
    """An app user whose name is unique (so the platform list can find it)."""
    token = token or uid(8)
    return make_user(tag=f"{tag}_", full_name=f"QA {token} {tag}", **kw)


def app_login(base_url, user, password=None):
    return Client(base_url).login_form(user.email, password or user.password)


def block(root, user):
    return ok(root.post(f"{P}/users/{user.id}/block")).json()


def unblock(root, user):
    return ok(root.post(f"{P}/users/{user.id}/unblock")).json()


def soft_delete(root, user):
    return ok(root.delete(f"{P}/users/{user.id}")).json()


# ---------------------------------------------------------------- PLT-15 list, search, filters, sort, pages
@pytest.mark.plan("PLT-15")
def test_a_list_row_has_the_fields_and_no_secrets(proot, make_user):
    u = person(make_user, "f1")
    resp = ok(proot.get(f"{P}/users", params={"q": u.full_name}))
    row = next(r for r in resp.json()["items"] if r["id"] == u.id)
    assert set(row) == {"id", "email", "full_name", "position", "avatar_url", "status", "created_at", "last_login_at",
                        "deleted_at", "projects_count", "assigned_open_count", "reported_count"}
    assert row["email"] == u.email and row["full_name"] == u.full_name and row["status"] == "active"
    assert row["created_at"] and row["last_login_at"]                                   # make_user logs in once
    assert row["deleted_at"] is None
    assert (row["projects_count"], row["assigned_open_count"], row["reported_count"]) == (0, 0, 0)
    assert "password" not in resp.text and "hashed" not in resp.text and "is_blocked" not in resp.text


@pytest.mark.plan("PLT-15")
def test_search_by_name_and_by_email_ignores_case(proot, make_user):
    u = person(make_user, "s1")
    assert [r["id"] for r in users(proot, q=u.full_name.upper())["items"]] == [u.id]
    assert [r["id"] for r in users(proot, q=f"  {u.email.upper()}  ")["items"]] == [u.id]
    assert users(proot, q="no_such_person_" + uid(10))["total"] == 0
    assert users(proot, q="%")["total"] == 0                       # % is a plain character, not a wildcard
    assert users(proot, q="   ")["total"] == users(proot)["total"]        # a blank search is ignored


@pytest.mark.plan("PLT-15")
def test_status_filter_and_counters(proot, make_user):
    token = uid(8)
    active = person(make_user, "a", token)
    blocked = person(make_user, "b", token)
    gone_himself = person(make_user, "c", token)
    deleted = person(make_user, "d", token)
    block(proot, blocked)
    deactivate(gone_himself)
    soft_delete(proot, deleted)
    page = users(proot, q=token)
    assert page["total"] == 4
    assert page["counts"] == {"all": 4, "active": 1, "blocked": 1, "deactivated": 1, "deleted": 1}
    want = {"active": active, "blocked": blocked, "deactivated": gone_himself, "deleted": deleted}
    for status, u in want.items():
        part = users(proot, q=token, status=status)
        assert [r["id"] for r in part["items"]] == [u.id], status
        assert part["total"] == 1 and part["items"][0]["status"] == status
        assert part["counts"]["all"] == 4                           # the counters ignore the status filter
    assert proot.get(f"{P}/users", params={"status": "nonsense"}).status_code == 422


@pytest.mark.plan("PLT-15")
def test_sorting(proot, make_user, base_url):
    token = uid(8)
    bravo, alpha, charlie = (make_user(tag="o_", full_name=f"QA {token} {n}") for n in ("bravo", "Alpha", "charlie"))
    anon = Client(base_url)
    never = ok(anon.post("/api/auth/register", json={"email": unique_email("never_"), "password": config.PASSWORD,
                                                      "full_name": f"QA {token} never"}), 201).json()
    ids = lambda **p: [r["id"] for r in users(proot, q=token, **p)["items"]]
    assert ids() == [never["id"], charlie.id, alpha.id, bravo.id]                       # newest first (default)
    assert ids(sort="created") == ids()
    assert ids(sort="name") == [alpha.id, bravo.id, charlie.id, never["id"]]            # a-z, case does not matter
    ok(app_login(base_url, bravo))                                                       # bravo logs in again: newest login
    assert ids(sort="last_login") == [bravo.id, charlie.id, alpha.id, never["id"]]      # people who never logged in: last
    assert proot.get(f"{P}/users", params={"sort": "email"}).status_code == 422


@pytest.mark.plan("PLT-15")
def test_pages(proot, make_user):
    token = uid(8)
    made = [person(make_user, f"p{n}", token) for n in range(5)]
    everything = [r["id"] for r in users(proot, q=token)["items"]]
    assert sorted(everything) == sorted(u.id for u in made)
    seen = []
    for page in (1, 2, 3):
        part = users(proot, q=token, page=page, page_size=2)
        assert part["total"] == 5 and part["page"] == page and part["page_size"] == 2
        seen += [r["id"] for r in part["items"]]
    assert seen == everything
    assert users(proot, q=token, page=4, page_size=2)["items"] == []
    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}):
        assert proot.get(f"{P}/users", params=bad).status_code == 422, bad


@pytest.mark.plan("PLT-15")
def test_project_and_ticket_counters(proot, make_user):
    owner, u = person(make_user, "own"), person(make_user, "cnt")
    p1, p2 = create_project(owner), create_project(owner)
    p1.add_member(u, "editor")
    p2.add_member(u, "editor")
    p1.ticket(client=u.client, assignee_id=u.id)                    # open, made by u
    done = p1.ticket(client=u.client, assignee_id=u.id)             # made by u ...
    p1.move(done["id"], "Done")                                     # ... and finished: not "open" any more
    p2.ticket(assignee_id=u.id)                                      # open, made by the owner
    row = find_user(proot, u)
    assert (row["projects_count"], row["assigned_open_count"], row["reported_count"]) == (2, 2, 2)
    owner_row = find_user(proot, owner)
    assert owner_row["projects_count"] == 2 and owner_row["reported_count"] == 1 and owner_row["assigned_open_count"] == 0


# ---------------------------------------------------------------- PLT-16 who may use it, and the audit log
@pytest.mark.plan("PLT-16")
@pytest.mark.parametrize("method, path", [("get", ""), ("post", "/1/block"), ("post", "/1/unblock"), ("delete", "/1")])
def test_users_endpoints_need_a_platform_token(anon, make_user, method, path):
    assert getattr(anon, method)(f"{P}/users{path}").status_code == 401
    assert getattr(make_user(tag="plt_").client, method)(f"{P}/users{path}").status_code == 401     # an app token is no good


@pytest.mark.plan("PLT-16")
def test_the_manage_users_permission_is_needed(proot, padmin, make_user):
    u = person(make_user, "perm")
    plain = padmin("nou")
    others = padmin("others", can_view_audit_logs=True, can_view_analytics=True, can_manage_projects=True)
    allowed = padmin("yes", can_manage_users=True)
    for admin in (plain, others):
        assert admin.client.get(f"{P}/users").status_code == 403
        assert admin.client.post(f"{P}/users/{u.id}/block").status_code == 403
        assert admin.client.post(f"{P}/users/{u.id}/unblock").status_code == 403
        assert admin.client.delete(f"{P}/users/{u.id}").status_code == 403
    assert find_user(proot, u)["status"] == "active"                # nothing happened
    assert allowed.client.get(f"{P}/users", params={"q": u.full_name}).status_code == 200
    assert allowed.client.post(f"{P}/users/{u.id}/block").status_code == 200
    assert find_user(proot, u)["status"] == "blocked"


@pytest.mark.plan("PLT-16")
def test_every_change_is_in_the_audit_log_with_the_admin_who_did_it(proot, padmin, make_user):
    u = person(make_user, "aud")
    admin = padmin("auditor", can_manage_users=True)
    ok(admin.client.post(f"{P}/users/{u.id}/block"))
    ok(admin.client.post(f"{P}/users/{u.id}/unblock"))
    ok(admin.client.delete(f"{P}/users/{u.id}"))
    rows = audit(proot, target=u.email)["items"]                     # the log keeps the ORIGINAL address
    assert [r["action"] for r in rows] == ["user_deleted", "user_unblocked", "user_blocked"]
    for r in rows:
        assert r["actor_id"] == admin.id and r["actor_name"] == admin.username
        assert r["target_type"] == "user" and r["target_id"] == u.id and r["target_name"] == u.email
        assert r["details"] == {"full_name": u.full_name} and r["ip"]
    text = str(rows)
    assert u.password not in text and "hashed" not in text


@pytest.mark.plan("PLT-16")
def test_a_refused_action_writes_no_log_line(proot, make_user):
    u = person(make_user, "nolog")
    assert proot.post(f"{P}/users/{u.id}/unblock").status_code == 409        # not blocked
    assert proot.post(f"{P}/users/99999999/block").status_code == 404
    assert audit(proot, target=u.email)["total"] == 0


@pytest.mark.plan("PLT-16")
def test_unknown_users_and_bad_ids(proot):
    assert proot.post(f"{P}/users/99999999/block").status_code == 404
    assert proot.post(f"{P}/users/99999999/unblock").status_code == 404
    assert proot.delete(f"{P}/users/99999999").status_code == 404
    assert proot.delete(f"{P}/users/abc").status_code == 422


# ---------------------------------------------------------------- PLT-17 block and unblock
@pytest.mark.plan("PLT-17")
def test_a_blocked_user_cannot_log_in_and_the_old_token_stops_at_once(proot, make_user, base_url):
    u = person(make_user, "blk")
    assert u.client.get("/api/auth/me").status_code == 200
    row = block(proot, u)
    assert row["status"] == "blocked" and row["id"] == u.id
    r = app_login(base_url, u)
    assert r.status_code == 403 and r.json()["detail"] == "User account is blocked"
    for path in ("/api/auth/me", "/api/projects", "/api/users"):
        resp = u.client.get(path)
        assert resp.status_code == 403 and resp.json()["detail"] == "User account is blocked", path


@pytest.mark.plan("PLT-17")
def test_a_wrong_password_never_tells_that_the_account_is_blocked(proot, make_user, base_url):
    u = person(make_user, "blk2")
    block(proot, u)
    r = app_login(base_url, u, "Wrong-Passw0rd-1")
    assert r.status_code == 400 and "blocked" not in r.text.lower()


@pytest.mark.plan("PLT-17")
def test_unblock_gives_the_account_back_with_the_same_token(proot, make_user, base_url):
    u = person(make_user, "unb")
    block(proot, u)
    assert unblock(proot, u)["status"] == "active"
    ok(app_login(base_url, u))
    assert u.client.get("/api/auth/me").status_code == 200           # the token from before the block works again


@pytest.mark.plan("PLT-17")
def test_blocking_keeps_the_data_and_the_assignments(proot, make_user):
    owner, u = person(make_user, "own2"), person(make_user, "blk3")
    p = create_project(owner)
    p.add_member(u, "editor")
    t = p.ticket(assignee_id=u.id)
    ok(u.client.post(f"/api/tickets/{t['id']}/comments", json={"body": "before the block"}), 201)
    block(proot, u)
    got = ok(owner.client.get(f"/api/tickets/{t['id']}")).json()
    assert got["assignee"]["id"] == u.id and got["assignee"]["is_active"] is True          # still a normal assignee
    members = ok(owner.client.get(f"/api/projects/{p.id}/members")).json()
    assert u.id in [m["user"]["id"] for m in members]
    assert [c["body"] for c in ok(owner.client.get(f"/api/tickets/{t['id']}/comments")).json()] == ["before the block"]


@pytest.mark.plan("PLT-17")
def test_double_block_and_unblock_of_the_wrong_state_are_refused(proot, make_user):
    u = person(make_user, "dbl")
    assert proot.post(f"{P}/users/{u.id}/unblock").status_code == 409
    block(proot, u)
    r = proot.post(f"{P}/users/{u.id}/block")
    assert r.status_code == 409 and "already blocked" in r.json()["detail"]
    unblock(proot, u)
    assert proot.post(f"{P}/users/{u.id}/unblock").status_code == 409


@pytest.mark.plan("PLT-17")
def test_only_active_users_can_be_blocked(proot, make_user):
    closed, removed = person(make_user, "cls"), person(make_user, "rem")
    deactivate(closed)
    soft_delete(proot, removed)
    for u in (closed, removed):
        r = proot.post(f"{P}/users/{u.id}/block")
        assert r.status_code == 409 and "Only active" in r.json()["detail"]
    assert find_user(proot, closed)["status"] == "deactivated" and find_user(proot, removed)["status"] == "deleted"


@pytest.mark.plan("PLT-17")
def test_last_login_is_saved_by_a_good_login_only(proot, make_user, base_url):
    u = person(make_user, "ll")
    first = find_user(proot, u)["last_login_at"]
    assert first
    app_login(base_url, u, "Wrong-Passw0rd-1")                       # a failed login changes nothing
    assert find_user(proot, u)["last_login_at"] == first
    ok(app_login(base_url, u))
    assert find_user(proot, u)["last_login_at"] >= first
    block(proot, u)
    before = find_user(proot, u)["last_login_at"]
    assert app_login(base_url, u).status_code == 403                 # a refused login (blocked) changes nothing either
    assert find_user(proot, u)["last_login_at"] == before


@pytest.mark.plan("PLT-17")
def test_the_app_never_shows_the_platform_fields(make_user, roles):
    u = person(make_user, "hid")
    hidden = {"is_blocked", "deleted_at", "last_login_at", "hashed_password"}
    assert hidden.isdisjoint(ok(u.client.get("/api/auth/me")).json())
    for row in ok(u.client.get("/api/auth/users")).json()[:20]:
        assert hidden.isdisjoint(row)
    for row in ok(roles.admin.client.get("/api/users")).json()[:20]:
        assert hidden.isdisjoint(row)


# ---------------------------------------------------------------- PLT-18 soft delete
@pytest.mark.plan("PLT-18")
def test_soft_delete_changes_the_address_and_keeps_the_name(proot, make_user, base_url):
    u = person(make_user, "del")
    row = soft_delete(proot, u)
    assert row["status"] == "deleted" and row["deleted_at"]
    assert row["email"] == f"deleted_{u.id}_{u.email}"
    assert row["full_name"] == u.full_name                           # the name stays: "(deactivated)" is added by the screens
    assert find_user(proot, u)["status"] == "deleted"
    r = app_login(base_url, u)                                       # the old address is not known any more
    assert r.status_code == 400 and r.json()["detail"] == "Incorrect email or password"
    assert u.client.get("/api/auth/me").status_code == 403           # the old token stops at once
    assert Client(base_url).login_form(row["email"], u.password).status_code == 400      # the new address has no usable password


@pytest.mark.plan("PLT-18")
def test_the_real_address_can_be_registered_again(proot, make_user, base_url):
    u = person(make_user, "again")
    soft_delete(proot, u)
    fresh = register_user(base_url, email=u.email, full_name=f"QA again {uid(6)}")
    assert fresh.id != u.id and fresh.email == u.email
    assert ok(fresh.client.get("/api/auth/me")).json()["id"] == fresh.id
    assert find_user(proot, u)["status"] == "deleted"                # the old account is still listed


@pytest.mark.plan("PLT-18")
def test_work_stays_after_a_soft_delete(proot, make_user):
    owner, u = person(make_user, "own3"), person(make_user, "del2")
    p = create_project(owner)
    p.add_member(u, "editor")
    mine = p.ticket(client=u.client, assignee_id=u.id, tester_id=u.id)
    ok(u.client.post(f"/api/tickets/{mine['id']}/comments", json={"body": "my comment"}), 201)
    soft_delete(proot, u)
    got = ok(owner.client.get(f"/api/tickets/{mine['id']}")).json()
    for who in ("assignee", "reporter"):
        assert got[who]["id"] == u.id and got[who]["is_active"] is False and got[who]["full_name"] == u.full_name
    assert got["tester"]["id"] == u.id                                # nothing was cleared (the old deactivate cleared these)
    comments = ok(owner.client.get(f"/api/tickets/{mine['id']}/comments")).json()
    assert [(c["body"], c["author_id"]) for c in comments] == [("my comment", u.id)]
    members = {m["user"]["id"]: m["user"] for m in ok(owner.client.get(f"/api/projects/{p.id}/members")).json()}
    assert members[u.id]["is_active"] is False and members[u.id]["full_name"] == u.full_name
    assert any(h["user_id"] == u.id for h in got["history"]), "the history of the user stays"


@pytest.mark.plan("PLT-18")
def test_a_deleted_user_cannot_get_new_work(proot, make_user):
    owner, u = person(make_user, "own4"), person(make_user, "del3")
    p = create_project(owner)
    p.add_member(u, "editor")
    soft_delete(proot, u)
    t = p.ticket()
    assert owner.client.patch(f"/api/tickets/{t['id']}", json={"assignee_id": u.id}).status_code == 400
    assert owner.client.post(f"/api/tickets/project/{p.id}", json={"title": "x", "type": "Task", "assignee_id": u.id}).status_code == 400


@pytest.mark.plan("PLT-18")
def test_the_mention_list_marks_the_user_as_not_active(proot, make_user):
    owner, u = person(make_user, "own5"), person(make_user, "del4")
    p = create_project(owner)
    p.add_member(u, "editor")
    soft_delete(proot, u)
    rows = {r["id"]: r for r in ok(owner.client.get("/api/auth/users")).json()}
    assert rows[u.id]["is_active"] is False


@pytest.mark.plan("PLT-18")
def test_delete_twice_and_other_actions_on_a_deleted_user_are_refused(proot, make_user):
    u = person(make_user, "del5")
    soft_delete(proot, u)
    r = proot.delete(f"{P}/users/{u.id}")
    assert r.status_code == 409 and "already deleted" in r.json()["detail"]
    assert proot.post(f"{P}/users/{u.id}/block").status_code == 409
    assert proot.post(f"{P}/users/{u.id}/unblock").status_code == 409


@pytest.mark.plan("PLT-18")
def test_blocked_and_self_closed_accounts_can_be_deleted(proot, make_user):
    blocked, closed = person(make_user, "bd"), person(make_user, "cd")
    block(proot, blocked)
    deactivate(closed)
    assert soft_delete(proot, blocked)["status"] == "deleted"
    row = soft_delete(proot, closed)
    assert row["status"] == "deleted" and row["full_name"].endswith("(Deactivated)")      # the old mark stays, no second one


@pytest.mark.plan("PLT-18")
def test_a_very_long_address_still_gives_a_valid_deleted_address(proot, make_user, base_url, roles):
    email = f"{'l' * 55}{uid(8)}@{config.EMAIL_DOMAIN}"                 # 63 characters before the @
    u = person(make_user, "long", email=email)
    row = soft_delete(proot, u)
    local, _, domain = row["email"].rpartition("@")
    assert len(local) <= 64 and local.startswith(f"deleted_{u.id}_") and domain == config.EMAIL_DOMAIN
    assert ok(roles.admin.client.get("/api/users")).status_code == 200          # the app lists still work (valid address)
    assert ok(roles.admin.client.get("/api/auth/users")).status_code == 200
    assert audit(proot, target=email)["items"][0]["target_name"] == email          # the log keeps the full original address
