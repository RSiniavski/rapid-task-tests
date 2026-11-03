"""Platform (admin tool) API: login, tokens, lock, admins, audit log, platform.db (PLT-01..05, PLT-07)."""
import sqlite3
import time

import pytest

from framework import config
from framework.client import Client
from framework.factory import make_jwt, ok, uid
from framework.platform_api import ADMIN_PASSWORD, P, PERMS, audit, login_client, login_resp

pytestmark = pytest.mark.api

ROOT = config.PLATFORM_ROOT_USERNAME
LOCK_SECONDS = config.PLATFORM_LOCK_MINUTES * 60


def me(client):
    return ok(client.get(f"{P}/auth/me")).json()


def all_flags(value=True):
    return {f: value for f in PERMS}


def codes(base_url, username, n, password="wrong-Passw0rd"):
    return [login_resp(base_url, username, password).status_code for _ in range(n)]


def forge(sub, key, scope="platform", exp=600):
    payload = {"sub": sub, "exp": int(time.time()) + exp}
    if scope is not None:
        payload["scope"] = scope
    return make_jwt(payload, key)


# ---------------------------------------------------------------- PLT-01 login and status
@pytest.mark.plan("PLT-01")
def test_status_is_public_and_shows_only_two_flags(anon, proot):
    body = ok(anon.get(f"{P}/status")).json()
    assert body == {"has_admins": True, "root_configured": True}


@pytest.mark.plan("PLT-01")
def test_root_logs_in_with_all_permissions(proot, base_url):
    resp = ok(login_resp(base_url, ROOT, config.PLATFORM_ROOT_PASSWORD))
    body = resp.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    admin = body["admin"]
    assert admin["username"] == ROOT and admin["is_root"] is True and admin["is_active"] is True
    assert all(admin[f] is True for f in PERMS)
    assert "hashed_password" not in resp.text and "password" not in admin


@pytest.mark.plan("PLT-01")
def test_login_ignores_case_and_surrounding_spaces(proot, base_url):
    ok(login_resp(base_url, f"  {ROOT.upper()} ", config.PLATFORM_ROOT_PASSWORD))


@pytest.mark.plan("PLT-01")
def test_wrong_password_and_unknown_name_look_the_same(padmin, base_url):
    a = padmin("same")
    wrong = login_resp(base_url, a.username, "bad-Passw0rd-1")
    unknown = login_resp(base_url, f"nobody_{uid()}", "bad-Passw0rd-1")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


@pytest.mark.plan("PLT-01")
@pytest.mark.parametrize("body", [
    {}, {"username": "x"}, {"password": "x"}, {"username": "", "password": "x"}, {"username": "x", "password": ""},
    {"username": "u" * 61, "password": "x"}, {"username": "x", "password": "p" * 129},
])
def test_login_body_is_validated(anon, body):
    assert anon.post(f"{P}/auth/login", json=body, auth=False).status_code == 422


@pytest.mark.plan("PLT-01")
def test_login_form_data_is_not_accepted(anon):
    r = anon.post(f"{P}/auth/login", data={"username": ROOT, "password": config.PLATFORM_ROOT_PASSWORD}, auth=False)
    assert r.status_code == 422


@pytest.mark.plan("PLT-01")
def test_me_returns_the_logged_in_admin(proot, padmin):
    a = padmin("me", can_manage_users=True)
    assert me(proot)["username"] == ROOT and me(proot)["is_root"] is True
    got = me(a.client)
    assert got["username"] == a.username and got["is_root"] is False
    assert got["can_manage_users"] is True and got["can_view_audit_logs"] is False


@pytest.mark.plan("PLT-01")
def test_last_login_is_saved(proot, padmin):
    a = padmin("last")
    row = next(r for r in ok(proot.get(f"{P}/admins")).json() if r["id"] == a.id)
    assert row["last_login_at"] is not None


# ---------------------------------------------------------------- PLT-02 tokens
@pytest.mark.plan("PLT-02")
@pytest.mark.parametrize("path", ["/auth/me", "/admins", "/audit", "/audit/actions"])
def test_platform_endpoints_need_a_token(anon, path):
    assert anon.get(f"{P}{path}").status_code == 401


@pytest.mark.plan("PLT-02")
def test_garbage_tokens_are_refused(base_url):
    for token in ("garbage", "a.b.c", "", "null"):
        assert Client(base_url, token or None).get(f"{P}/auth/me").status_code == 401, token


@pytest.mark.plan("PLT-02")
def test_an_app_user_token_does_not_open_the_platform(make_user):
    u = make_user(tag="plt_")
    for path in ("/auth/me", "/admins", "/audit"):
        assert u.client.get(f"{P}{path}").status_code == 401, path


@pytest.mark.plan("PLT-02")
def test_a_platform_token_does_not_open_the_app(proot):
    for path in ("/api/auth/me", "/api/themes"):
        assert proot.get(path).status_code == 401, path


@pytest.mark.plan("PLT-02")
def test_a_correctly_signed_token_is_accepted(proot, base_url, secret_key):
    """Control for the next test: the forging helper itself builds a token the server accepts."""
    token = forge(f"padmin:{me(proot)['id']}", secret_key + ":platform")
    assert Client(base_url, token).get(f"{P}/auth/me").status_code == 200


@pytest.mark.plan("PLT-02")
@pytest.mark.security
def test_forged_tokens_are_refused(proot, base_url, secret_key):
    rid, key = me(proot)["id"], secret_key + ":platform"
    cases = {
        "signed with the app key": forge(f"padmin:{rid}", secret_key),
        "signed with a foreign key": forge(f"padmin:{rid}", "some-other-secret"),
        "no scope": forge(f"padmin:{rid}", key, scope=None),
        "app scope": forge(f"padmin:{rid}", key, scope="app"),
        "subject without the prefix": forge(str(rid), key),
        "text id": forge("padmin:abc", key),
        "zero id": forge("padmin:0", key),
        "huge id": forge("padmin:99999999999999999999", key),
        "unknown id": forge("padmin:987654321", key),
        "expired": forge(f"padmin:{rid}", key, exp=-60),
        "alg none": make_jwt({"sub": f"padmin:{rid}", "scope": "platform", "exp": int(time.time()) + 600}, "", alg="none"),
    }
    bad = {name: r.status_code for name, tok in cases.items()
           if (r := Client(base_url, tok).get(f"{P}/auth/me")).status_code != 401}
    assert not bad, bad


# ---------------------------------------------------------------- PLT-03 login lock
@pytest.mark.plan("PLT-03")
def test_five_wrong_passwords_lock_the_name(padmin, base_url):
    a = padmin("lock")
    assert codes(base_url, a.username, 4) == [401, 401, 401, 401]
    fifth = login_resp(base_url, a.username, "wrong-Passw0rd")
    assert fifth.status_code == 429 and fifth.headers["Retry-After"] == str(LOCK_SECONDS)
    assert str(config.PLATFORM_LOCK_MINUTES) in fifth.json()["detail"]
    again = login_resp(base_url, a.username, a.password)                 # the right password does not help while locked
    assert again.status_code == 429


@pytest.mark.plan("PLT-03")
def test_unknown_names_are_locked_like_real_ones(base_url):
    name = f"nobody_{uid()}"
    assert codes(base_url, name, 6) == [401, 401, 401, 401, 429, 429]


@pytest.mark.plan("PLT-03")
def test_the_lock_is_per_name_and_ignores_case(padmin, base_url):
    a, b = padmin("lka"), padmin("lkb")
    assert codes(base_url, a.username, 3) == [401, 401, 401]
    assert codes(base_url, a.username.upper(), 2) == [401, 429]          # the same name in capitals shares the counter
    ok(login_resp(base_url, b.username, b.password))                     # another admin is not affected


@pytest.mark.plan("PLT-03")
def test_a_good_login_resets_the_counter(padmin, base_url):
    a = padmin("reset")
    assert codes(base_url, a.username, 4) == [401] * 4
    ok(login_resp(base_url, a.username, a.password))
    assert codes(base_url, a.username, 4) == [401] * 4                   # a new count: still not locked


@pytest.mark.plan("PLT-03")
def test_root_password_reset_removes_the_lock(proot, padmin, base_url):
    a = padmin("unlock")
    codes(base_url, a.username, 5)
    assert login_resp(base_url, a.username, a.password).status_code == 429
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": "N3w-Passw0rd-x"}))
    ok(login_resp(base_url, a.username, "N3w-Passw0rd-x"))


@pytest.mark.plan("PLT-03")
def test_failed_and_blocked_logins_are_in_the_audit_log(proot, padmin, base_url):
    a = padmin("lklog")
    codes(base_url, a.username, 5)
    login_resp(base_url, a.username, a.password)                         # blocked
    rows = audit(proot, actor=a.username)["items"]
    failed = [r for r in rows if r["action"] == "login_failed"]
    blocked = [r for r in rows if r["action"] == "login_blocked"]
    assert len(failed) == 5 and len(blocked) == 1
    assert sum(1 for r in failed if r["details"] and r["details"].get("locked") is True) == 1
    assert all(r["ip"] for r in failed + blocked)


# ---------------------------------------------------------------- PLT-04 admin management
@pytest.mark.plan("PLT-04")
def test_root_creates_an_admin(proot):
    name = f"QA_Create_{uid(6)}"
    r = ok(proot.post(f"{P}/admins", json={"username": f" {name} ", "display_name": "  Anna K  ",
                                          "password": ADMIN_PASSWORD, "can_manage_users": True}), 201)
    a = r.json()
    try:
        assert a["username"] == name.lower() and a["display_name"] == "Anna K"
        assert a["is_root"] is False and a["is_active"] is True and a["created_at"]
        assert a["can_manage_users"] is True
        assert [f for f in PERMS if a[f]] == ["can_manage_users"]
        assert "hashed_password" not in r.text and ADMIN_PASSWORD not in r.text
    finally:
        proot.delete(f"{P}/admins/{a['id']}")


@pytest.mark.plan("PLT-04")
def test_duplicate_names_are_refused_in_any_case(proot, padmin):
    a = padmin("dup")
    body = {"display_name": "Copy", "password": ADMIN_PASSWORD}
    assert proot.post(f"{P}/admins", json={**body, "username": a.username.upper()}).status_code == 409
    assert proot.post(f"{P}/admins", json={**body, "username": ROOT}).status_code == 409


@pytest.mark.plan("PLT-04")
@pytest.mark.parametrize("override", [
    {"username": "ab"}, {"username": "an na"}, {"username": "анна"}, {"username": "_abc"}, {"username": "a" * 41},
    {"display_name": "A"}, {"display_name": "   "}, {"password": "short"}, {"password": "я" * 37},
    {"is_root": True}, {"unknown_field": 1},
])
def test_create_validation(proot, override):
    body = {"username": f"qa_val_{uid(6)}", "display_name": "Valid Name", "password": ADMIN_PASSWORD}
    body.update(override)
    assert proot.post(f"{P}/admins", json=body).status_code == 422


@pytest.mark.plan("PLT-04")
def test_only_root_manages_admins(anon, padmin):
    full = padmin("full", **all_flags())             # every permission, but not root
    victim = padmin("victim")
    base = f"{P}/admins"
    new = {"username": f"qa_x_{uid(6)}", "display_name": "Nope", "password": ADMIN_PASSWORD}
    assert full.client.get(base).status_code == 403
    assert full.client.post(base, json=new).status_code == 403
    assert full.client.patch(f"{base}/{victim.id}", json={"can_manage_users": True}).status_code == 403
    assert full.client.post(f"{base}/{victim.id}/password", json={"password": ADMIN_PASSWORD}).status_code == 403
    assert full.client.delete(f"{base}/{victim.id}").status_code == 403
    for call in (anon.get(base), anon.post(base, json=new), anon.delete(f"{base}/{victim.id}")):
        assert call.status_code == 401


@pytest.mark.plan("PLT-04")
def test_list_shows_root_first_and_never_a_password(proot, padmin):
    a = padmin("list")
    resp = ok(proot.get(f"{P}/admins"))
    rows = resp.json()
    assert rows[0]["is_root"] is True and rows[0]["username"] == ROOT
    assert a.id in [r["id"] for r in rows]
    assert len({r["id"] for r in rows}) == len(rows)
    assert "hashed_password" not in resp.text and "$2" not in resp.text


@pytest.mark.plan("PLT-04")
def test_update_changes_only_what_was_sent(proot, padmin):
    a = padmin("upd", can_view_analytics=True)
    got = ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_users": True, "display_name": " New Name "})).json()
    assert got["display_name"] == "New Name" and got["can_manage_users"] is True
    assert got["can_view_analytics"] is True and got["can_view_audit_logs"] is False and got["is_active"] is True
    listed = next(r for r in ok(proot.get(f"{P}/admins")).json() if r["id"] == a.id)
    assert listed == got


@pytest.mark.plan("PLT-04")
@pytest.mark.parametrize("body", [{}, {"is_root": True}, {"display_name": "x"}, {"username": "other_name"},
                                  {"can_manage_users": "maybe"}])
def test_update_validation(proot, padmin, body):
    a = padmin("updv")
    assert proot.patch(f"{P}/admins/{a.id}", json=body).status_code == 422


@pytest.mark.plan("PLT-04")
def test_unknown_admin_is_404(proot):
    assert proot.patch(f"{P}/admins/999999999", json={"can_manage_users": True}).status_code == 404
    assert proot.post(f"{P}/admins/999999999/password", json={"password": ADMIN_PASSWORD}).status_code == 404
    assert proot.delete(f"{P}/admins/999999999").status_code == 404
    assert proot.patch(f"{P}/admins/abc", json={"can_manage_users": True}).status_code == 422


@pytest.mark.plan("PLT-04")
def test_a_change_that_changes_nothing_writes_no_audit_row(proot, padmin):
    a = padmin("noop")
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_users": True}))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_users": True}))
    rows = audit(proot, target=a.username, action="admin_updated")
    assert rows["total"] == 1


@pytest.mark.plan("PLT-04")
def test_a_blocked_admin_loses_access_at_once(proot, padmin, base_url):
    a = padmin("block", can_view_audit_logs=True)
    assert a.client.get(f"{P}/audit").status_code == 200
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    assert a.client.get(f"{P}/auth/me").status_code == 403                # the old token stops working
    assert a.client.get(f"{P}/audit").status_code == 403
    assert login_resp(base_url, a.username, a.password).status_code == 403
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": True}))
    assert a.client.get(f"{P}/audit").status_code == 200                  # and works again
    ok(login_resp(base_url, a.username, a.password))


@pytest.mark.plan("PLT-04")
def test_permission_changes_work_with_the_old_token(proot, padmin):
    a = padmin("perm")
    assert a.client.get(f"{P}/audit").status_code == 403
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_view_audit_logs": True}))
    assert a.client.get(f"{P}/audit").status_code == 200
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_view_audit_logs": False}))
    assert a.client.get(f"{P}/audit").status_code == 403


@pytest.mark.plan("PLT-04")
def test_root_cannot_be_changed_blocked_or_deleted(proot):
    rid = me(proot)["id"]
    assert proot.patch(f"{P}/admins/{rid}", json={"is_active": False}).status_code == 403
    assert proot.patch(f"{P}/admins/{rid}", json={"can_manage_users": False}).status_code == 403
    assert proot.patch(f"{P}/admins/{rid}", json={"display_name": "Boss"}).status_code == 403
    assert proot.post(f"{P}/admins/{rid}/password", json={"password": ADMIN_PASSWORD}).status_code == 403
    assert proot.delete(f"{P}/admins/{rid}").status_code == 403
    got = me(proot)
    assert got["is_active"] is True and all(got[f] for f in PERMS)


@pytest.mark.plan("PLT-04")
def test_password_reset(proot, padmin, base_url):
    a = padmin("pw")
    resp = ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": "Fresh-Passw0rd-9"}))
    assert "hashed_password" not in resp.text and "Fresh-Passw0rd-9" not in resp.text
    assert login_resp(base_url, a.username, a.password).status_code == 401
    ok(login_resp(base_url, a.username, "Fresh-Passw0rd-9"))
    assert proot.post(f"{P}/admins/{a.id}/password", json={"password": "short"}).status_code == 422
    assert proot.post(f"{P}/admins/{a.id}/password", json={"password": "я" * 37}).status_code == 422


@pytest.mark.plan("PLT-04")
def test_delete_an_admin(proot, padmin, base_url):
    a = padmin("del")
    assert proot.delete(f"{P}/admins/{a.id}").status_code == 204
    assert login_resp(base_url, a.username, a.password).status_code == 401
    assert a.client.get(f"{P}/auth/me").status_code == 401                # an old token of a deleted admin
    assert proot.delete(f"{P}/admins/{a.id}").status_code == 404
    assert a.id not in [r["id"] for r in ok(proot.get(f"{P}/admins")).json()]
    rows = audit(proot, actor=a.username)["items"]                         # the log still shows what the admin did
    assert any(r["action"] == "login_ok" for r in rows)
    assert audit(proot, target=a.username, action="admin_deleted")["total"] == 1


# ---------------------------------------------------------------- PLT-05 audit log
@pytest.mark.plan("PLT-05")
def test_audit_needs_the_permission(proot, anon, padmin):
    plain = padmin("noaud")
    others = padmin("others", **{f: True for f in PERMS if f != "can_view_audit_logs"})
    viewer = padmin("viewer", can_view_audit_logs=True)
    for path in ("/audit", "/audit/actions"):
        assert anon.get(f"{P}{path}").status_code == 401
        assert plain.client.get(f"{P}{path}").status_code == 403
        assert others.client.get(f"{P}{path}").status_code == 403
        assert viewer.client.get(f"{P}{path}").status_code == 200
        assert proot.get(f"{P}{path}").status_code == 200


@pytest.mark.plan("PLT-05")
def test_management_actions_are_logged_with_details(proot, padmin):
    a = padmin("log", can_view_audit_logs=True)
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_users": True}))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": True}))
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": "Fresh-Passw0rd-9"}))
    assert proot.delete(f"{P}/admins/{a.id}").status_code == 204
    page = audit(proot, target=a.username)
    rows = page["items"]
    assert [r["action"] for r in rows] == ["admin_deleted", "admin_password_reset", "admin_enabled",
                                           "admin_disabled", "admin_updated", "admin_created"]
    by = {r["action"]: r for r in rows}
    root_id = me(proot)["id"]
    for r in rows:
        assert r["actor_id"] == root_id and r["actor_name"] == ROOT
        assert r["target_type"] == "admin" and r["target_id"] == a.id and r["target_name"] == a.username
        assert r["ip"] and r["created_at"]
    assert by["admin_created"]["details"] == {"display_name": "QA log", "permissions": ["can_view_audit_logs"]}
    assert by["admin_updated"]["details"] == {"changed": {"can_manage_users": [False, True]}}
    assert by["admin_disabled"]["details"] == {"changed": {"is_active": [True, False]}}
    assert by["admin_enabled"]["details"] == {"changed": {"is_active": [False, True]}}


@pytest.mark.plan("PLT-05")
def test_passwords_never_reach_the_log(proot, padmin, base_url):
    first, second, wrong = "Secr3t-First-Pass!", "Secr3t-Second-Pass!", "Secr3t-Wrong-Pass!"
    a = padmin("sec", password=first)
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": second}))
    login_resp(base_url, a.username, wrong)
    text = "".join(ok(proot.get(f"{P}/audit", params=p)).text
                   for p in ({"target": a.username}, {"actor": a.username}, {"page_size": 100}))
    for secret in (first, second, wrong):
        assert secret not in text


@pytest.mark.plan("PLT-05")
def test_filters(proot, padmin):
    a, b = padmin("adm"), padmin("adm")
    one = audit(proot, action="admin_created", target=a.username)
    assert one["total"] == 1 and one["items"][0]["target_name"] == a.username
    assert audit(proot, target=a.username.upper())["total"] >= 1          # case does not matter
    mine = audit(proot, actor=a.username[:-2])["items"]
    assert mine and all(a.username[:-2] in r["actor_name"] for r in mine)
    assert audit(proot, action="no_such_action") == {"items": [], "total": 0, "page": 1, "page_size": 100}
    assert audit(proot, target="%")["total"] == 0                          # % and _ are plain characters
    assert audit(proot, target="qa_a_m")["total"] == 0                     # would match "qa_adm" if _ were a wildcard
    assert audit(proot, target="adm")["total"] >= 2
    assert audit(proot, actor="   ")["total"] >= 2                         # a blank filter is ignored
    assert b.username != a.username


@pytest.mark.plan("PLT-05")
def test_pagination_and_order(proot, padmin):
    a = padmin("page")
    for n in range(1, 7):
        ok(proot.patch(f"{P}/admins/{a.id}", json={"display_name": f"N{n}"}))
    everything = audit(proot, target=a.username)
    assert everything["total"] == 7 and len(everything["items"]) == 7
    ids = [r["id"] for r in everything["items"]]
    assert ids == sorted(ids, reverse=True)                                # newest first
    seen = []
    for page, size in ((1, 3), (2, 3), (3, 3)):
        part = audit(proot, target=a.username, page=page, page_size=size)
        assert part["total"] == 7 and part["page"] == page and part["page_size"] == size
        seen += [r["id"] for r in part["items"]]
    assert seen == ids
    assert audit(proot, target=a.username, page=4, page_size=3)["items"] == []
    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}):
        assert proot.get(f"{P}/audit", params=bad).status_code == 422


@pytest.mark.plan("PLT-05")
def test_action_names_for_the_filter(proot, padmin):
    padmin("act")
    names = ok(proot.get(f"{P}/audit/actions")).json()
    assert names == sorted(set(names))
    assert {"login_ok", "admin_created"} <= set(names)


@pytest.mark.plan("PLT-05")
def test_login_events_have_the_name_and_the_address(proot, padmin, base_url):
    a = padmin("evt")
    ghost = f"Ghost_{uid(6)}"
    login_resp(base_url, ghost, "bad-Passw0rd-1")
    ok_row = audit(proot, actor=a.username)["items"][-1]
    assert ok_row["action"] == "login_ok" and ok_row["actor_id"] == a.id and ok_row["ip"]
    bad_row = audit(proot, actor=ghost.lower())["items"][0]
    assert bad_row["action"] == "login_failed" and bad_row["actor_name"] == ghost.lower()
    assert bad_row["actor_id"] is None and bad_row["ip"]


@pytest.mark.plan("PLT-05")
@pytest.mark.needs_local_server
def test_the_root_account_creation_is_logged_by_the_system(proot, local_server):
    rows = audit(proot, action="root_created", target=ROOT)["items"]
    assert rows and rows[-1]["actor_name"] == "system" and rows[-1]["actor_id"] is None


# ---------------------------------------------------------------- PLT-07 platform.db
def table_names(path):
    con = sqlite3.connect(str(path))
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


@pytest.mark.plan("PLT-07")
@pytest.mark.needs_local_server
def test_platform_db_is_a_separate_file(proot, local_server):
    plat, main = table_names(local_server.platform_db_path), table_names(local_server.db_path)
    assert {"platform_admins", "platform_login_locks", "platform_audit_log"} <= plat
    assert not {"users", "tickets", "projects"} & plat
    assert not [t for t in main if t.startswith("platform")]


@pytest.mark.plan("PLT-07")
@pytest.mark.needs_local_server
def test_passwords_are_stored_as_hashes(proot, padmin, local_server):
    padmin("hash")
    con = sqlite3.connect(str(local_server.platform_db_path))
    try:
        hashes = [r[0] for r in con.execute("SELECT hashed_password FROM platform_admins")]
    finally:
        con.close()
    assert len(hashes) >= 2 and all(h.startswith("$2") and len(h) == 60 for h in hashes)
    raw = local_server.platform_db_path.read_bytes()
    for plain in (config.PLATFORM_ROOT_PASSWORD, ADMIN_PASSWORD):
        assert plain.encode() not in raw


@pytest.mark.plan("PLT-07")
def test_app_accounts_and_platform_accounts_are_separate(proot, padmin, make_user, base_url):
    u = make_user(tag="plt2_")
    a = padmin("sep")
    assert login_resp(base_url, u.email, u.password).status_code == 401           # an app user is no platform admin
    assert login_resp(base_url, u.email.split("@")[0], u.password).status_code == 401
    assert Client(base_url).login_form(a.username, a.password).status_code in (400, 401, 422)   # and the other way
