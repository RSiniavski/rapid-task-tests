"""Section 2 - authentication and account lifecycle (API / backend)."""
import time

import pytest

from framework import config
from framework.client import Client
from framework.factory import (create_project, deactivate, decode_jwt_payload, make_jwt, ok, register_user, unique_email)

pytestmark = pytest.mark.api

PASSWORD = config.PASSWORD
SECRET_FIELDS = {"password", "hashed_password", "password_hash", "hash"}


def payload(**kw):
    d = {"email": unique_email(), "password": PASSWORD, "full_name": "QA Registration"}
    d.update(kw)
    return d


def all_users(roles):
    return ok(roles.admin.client.get("/api/users")).json()


def count_email(roles, email, ci=False):
    f = (lambda s: s.lower()) if ci else (lambda s: s)
    return sum(1 for u in all_users(roles) if f(u["email"]) == f(email))


# ------------------------------------------------------------------ AUTH-01
@pytest.mark.plan("AUTH-01")
def test_register_valid_user_returns_safe_user(anon):
    """201 + safe body, password never echoed."""
    p = payload()
    r = ok(anon.post("/api/auth/register", json=p), 201)
    body = r.json()
    assert body["email"] == p["email"] and body["full_name"] == p["full_name"]
    assert isinstance(body["id"], int)
    assert body["is_active"] is True and body["position"] is None and body["avatar_url"] is None
    assert not (SECRET_FIELDS & set(body))
    assert p["password"] not in r.text


@pytest.mark.plan("AUTH-01")
@pytest.mark.needs_local_server
def test_register_stores_verifiable_bcrypt_hash(anon, db):
    """Password is stored as a bcrypt hash, not plain text."""
    p = payload()
    ok(anon.post("/api/auth/register", json=p), 201)
    stored = db("SELECT hashed_password FROM users WHERE email=?", (p["email"],))[0][0]
    assert stored != p["password"] and stored.startswith(("$2a$", "$2b$", "$2y$"))
    try:
        import bcrypt
    except ImportError:
        return
    assert bcrypt.checkpw(p["password"].encode(), stored.encode())


@pytest.mark.plan("AUTH-01")
def test_register_then_login_roundtrip(anon):
    p = payload()
    ok(anon.post("/api/auth/register", json=p), 201)
    assert ok(anon.login_form(p["email"], p["password"])).json()["access_token"]


# ------------------------------------------------------------------ AUTH-02
@pytest.mark.plan("AUTH-02")
def test_duplicate_email_rejected_without_second_user(anon, roles):
    p = payload()
    ok(anon.post("/api/auth/register", json=p), 201)
    r = anon.post("/api/auth/register", json=p)
    assert r.status_code == 400 and "already" in r.json()["detail"].lower()
    assert count_email(roles, p["email"]) == 1


@pytest.mark.plan("AUTH-02", "CLAR")
@pytest.mark.characterization
def test_email_case_variant_is_consistent_with_normalization_contract(anon, roles):
    """Current contract: local-part case is NOT normalized (domain is lower-cased by the validator).
    The test accepts either contract but enforces that behaviour is self-consistent."""
    p = payload()
    first = ok(anon.post("/api/auth/register", json=p), 201).json()
    variant = p["email"].upper()
    r = anon.post("/api/auth/register", json={**p, "email": variant})
    assert r.status_code in (201, 400)
    if r.status_code == 400:  # case-insensitive contract
        assert count_email(roles, p["email"], ci=True) == 1
    else:                     # case-sensitive contract: two distinct, individually usable accounts
        second = r.json()
        assert second["id"] != first["id"]
        assert ok(anon.login_form(second["email"], PASSWORD)).json()["access_token"]
        assert ok(anon.login_form(first["email"], PASSWORD)).json()["access_token"]


@pytest.mark.plan("AUTH-02", "CLAR")
@pytest.mark.characterization
def test_email_surrounding_whitespace_never_creates_duplicate(anon, roles):
    p = payload()
    ok(anon.post("/api/auth/register", json=p), 201)
    r = anon.post("/api/auth/register", json={**p, "email": f"  {p['email']}  "})
    assert r.status_code in (400, 422) or r.json()["email"] != p["email"]
    assert count_email(roles, p["email"]) == 1


# ------------------------------------------------------------------ AUTH-03
BAD_REGISTRATIONS = {
    "missing_email": lambda: {"password": PASSWORD, "full_name": "X"},
    "blank_email": lambda: payload(email=""),
    "malformed_email": lambda: payload(email="not-an-email"),
    "email_no_domain_dot": lambda: payload(email="a@b"),
    "missing_name": lambda: {"email": unique_email(), "password": PASSWORD},
    "missing_password": lambda: {"email": unique_email(), "full_name": "X"},
    "password_over_72": lambda: payload(password="p" * 73),
    "email_wrong_type": lambda: payload(email=12345),
    "password_wrong_type": lambda: payload(password=12345678),
    "name_wrong_type": lambda: payload(full_name=["x"]),
    "null_email": lambda: payload(email=None),
    "empty_object": lambda: {},
}


@pytest.mark.plan("AUTH-03")
@pytest.mark.parametrize("case", sorted(BAD_REGISTRATIONS))
def test_invalid_registration_payload_returns_422_and_creates_no_row(anon, roles, case):
    before = len(all_users(roles))
    r = anon.post("/api/auth/register", json=BAD_REGISTRATIONS[case]())
    assert r.status_code == 422, r.text
    assert len(all_users(roles)) == before


@pytest.mark.plan("AUTH-03")
def test_non_json_registration_body_is_422(anon):
    assert anon.post("/api/auth/register", data="email=a@b.com", headers={"Content-Type": "text/plain"}).status_code == 422


@pytest.mark.plan("AUTH-03")
def test_blank_full_name_should_be_rejected(anon):
    assert anon.post("/api/auth/register", json=payload(full_name="")).status_code == 422


@pytest.mark.plan("AUTH-03")
def test_empty_password_should_be_rejected(anon):
    assert anon.post("/api/auth/register", json=payload(password="")).status_code == 422


# ------------------------------------------------------------------ AUTH-04
@pytest.mark.plan("AUTH-04")
def test_login_returns_bearer_token_identifying_user(anon):
    u = register_user(anon.base_url)
    body = ok(anon.login_form(u.email, PASSWORD)).json()
    assert body["token_type"] == "bearer"
    claims = decode_jwt_payload(body["access_token"])
    assert claims["sub"] == str(u.id)
    assert claims["exp"] > time.time()
    me = ok(Client(anon.base_url, body["access_token"]).get("/api/auth/me")).json()
    assert me["id"] == u.id and me["email"] == u.email


@pytest.mark.plan("AUTH-04")
@pytest.mark.needs_local_server
def test_token_expires_after_configured_lifetime(anon, local_server):
    u = register_user(anon.base_url)
    exp = decode_jwt_payload(u.token)["exp"]
    assert 7 * 86400 - 300 <= exp - time.time() <= 7 * 86400 + 300


# ------------------------------------------------------------------ AUTH-05
@pytest.mark.plan("AUTH-05")
@pytest.mark.parametrize("case", ["wrong_password", "unknown_email", "empty_password"])
def test_bad_credentials_are_rejected_without_token(anon, case):
    u = register_user(anon.base_url)
    username, pw = {"wrong_password": (u.email, "WrongPass123"),
                    "unknown_email": (unique_email("nouser_"), PASSWORD),
                    "empty_password": (u.email, "")}[case]
    r = anon.login_form(username, pw)
    if case == "empty_password":                       # empty required form field -> framework validation
        assert r.status_code in (400, 422)
    else:
        assert r.status_code == 400 and r.json()["detail"] == "Incorrect email or password"
    assert "access_token" not in r.text


@pytest.mark.plan("AUTH-05")
@pytest.mark.parametrize("form", [{"password": "x"}, {"username": "a@b.com"}, {}])
def test_login_missing_form_fields_is_422(anon, form):
    assert anon.post("/api/auth/login", auth=False, data=form).status_code == 422


@pytest.mark.plan("AUTH-05")
def test_login_with_json_instead_of_form_is_422(anon):
    u = register_user(anon.base_url)
    r = anon.post("/api/auth/login", auth=False, json={"username": u.email, "password": PASSWORD})
    assert r.status_code == 422 and "access_token" not in r.text


# ------------------------------------------------------------------ AUTH-06
@pytest.fixture
def victim(base_url):
    return register_user(base_url)


def _me(base_url, token=None, scheme="Bearer"):
    h = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return Client(base_url).get("/api/auth/me", auth=False, headers=h)


@pytest.mark.plan("AUTH-06")
@pytest.mark.parametrize("case", ["no_header", "garbage", "basic_scheme", "empty_bearer"])
def test_missing_or_malformed_authorization_is_401(base_url, case):
    r = {"no_header": lambda: _me(base_url),
         "garbage": lambda: _me(base_url, "abc.def.ghi"),
         "basic_scheme": lambda: _me(base_url, "dXNlcjpwYXNz", scheme="Basic"),
         "empty_bearer": lambda: _me(base_url, "")}[case]()
    assert r.status_code == 401
    assert not (SECRET_FIELDS & set(r.json()))


@pytest.mark.plan("AUTH-06")
def test_token_signed_with_wrong_key_is_rejected(base_url, victim):
    bad = make_jwt({"sub": str(victim.id), "exp": int(time.time()) + 3600}, "some-other-secret")
    assert _me(base_url, bad).status_code == 401


@pytest.mark.plan("AUTH-06")
def test_unsigned_alg_none_token_is_rejected(base_url, victim):
    bad = make_jwt({"sub": str(victim.id), "exp": int(time.time()) + 3600}, "", alg="none")
    assert _me(base_url, bad).status_code == 401


@pytest.mark.plan("AUTH-06")
def test_expired_token_is_rejected(base_url, victim, secret_key):
    tok = make_jwt({"sub": str(victim.id), "exp": int(time.time()) - 60}, secret_key)
    assert _me(base_url, tok).status_code == 401
    good = make_jwt({"sub": str(victim.id), "exp": int(time.time()) + 600}, secret_key)
    assert _me(base_url, good).status_code == 200  # control: same forging code, valid expiry


@pytest.mark.plan("AUTH-06")
def test_token_without_subject_is_rejected(base_url, secret_key):
    tok = make_jwt({"exp": int(time.time()) + 600}, secret_key)
    assert _me(base_url, tok).status_code == 401


@pytest.mark.plan("AUTH-06")
def test_token_for_unknown_user_is_rejected(base_url, secret_key):
    tok = make_jwt({"sub": "987654321", "exp": int(time.time()) + 600}, secret_key)
    assert _me(base_url, tok).status_code == 401


@pytest.mark.plan("AUTH-06")
@pytest.mark.parametrize("sub", ["abc", "", "1.5", "0", "-1", "99999999999999999999", 10 ** 30, [1], {"id": 1}, None],
                         ids=["text", "empty", "decimal", "zero", "negative", "huge-text", "huge-int", "list",
                              "object", "null"])
def test_token_with_invalid_subject_is_401_not_500(base_url, secret_key, sub):
    tok = make_jwt({"sub": sub, "exp": int(time.time()) + 600}, secret_key)
    assert _me(base_url, tok).status_code == 401


# ------------------------------------------------------------------ AUTH-07
@pytest.mark.plan("AUTH-07")
def test_deactivated_user_cannot_login_or_use_existing_token(base_url, roles, make_user):
    u = make_user(tag="deact_")
    r = deactivate(u)
    assert r.json()["is_active"] is False and r.json()["full_name"].endswith("(Deactivated)")

    login = Client(base_url).login_form(u.email, PASSWORD)
    assert login.status_code == 403 and "deactivated" in login.json()["detail"].lower()
    assert "access_token" not in login.text

    for method, path in (("get", "/api/auth/me"), ("get", "/api/projects"), ("get", "/api/users")):
        assert getattr(u.client, method)(path).status_code == 403, path
    assert u.client.post("/api/projects", json={"name": "X", "key": "ZZ"}).status_code == 403


@pytest.mark.plan("AUTH-07")
def test_deactivated_user_with_wrong_password_gets_credentials_error_first(base_url, roles, make_user):
    u = make_user(tag="deact2_")
    deactivate(u)
    assert Client(base_url).login_form(u.email, "bad-password").status_code == 400


# ------------------------------------------------------------------ AUTH-08
@pytest.mark.plan("AUTH-08")
def test_me_returns_current_user_without_secrets(roles):
    r = ok(roles.editor.client.get("/api/auth/me"))
    assert r.json()["id"] == roles.editor.id and not (SECRET_FIELDS & set(r.json()))


@pytest.mark.plan("AUTH-08")
@pytest.mark.parametrize("path", ["/api/users", "/api/auth/users"])
def test_user_lists_contain_users_without_secrets(roles, path):
    r = ok(roles.reporter.client.get(path))
    users = r.json()
    ids = {u["id"] for u in users}
    assert {roles.admin.id, roles.editor.id, roles.reporter.id} <= ids
    for u in users:
        assert not (SECRET_FIELDS & set(u)), u
    assert "$2b$" not in r.text


@pytest.mark.plan("AUTH-08")
def test_user_detail_known_and_unknown(roles):
    r = ok(roles.reporter.client.get(f"/api/users/{roles.admin.id}"))
    assert r.json()["email"] == roles.admin.email and not (SECRET_FIELDS & set(r.json()))
    assert roles.reporter.client.get("/api/users/987654321").status_code == 404
    assert roles.reporter.client.get("/api/users/not-a-number").status_code == 422


# ------------------------------------------------------------------ AUTH-09
@pytest.mark.plan("AUTH-09")
@pytest.mark.parametrize("path_tpl", ["/api/auth/users/{id}", "/api/users/{id}"])
def test_soft_delete_deactivates_and_keeps_user(roles, make_user, path_tpl):
    u = make_user(tag="soft_")
    assert u.client.delete(path_tpl.format(id=u.id)).status_code == 204
    again = ok(roles.admin.client.get(f"/api/users/{u.id}")).json()
    assert again["is_active"] is False


@pytest.mark.plan("AUTH-09")
@pytest.mark.parametrize("path_tpl", ["/api/auth/users/{id}", "/api/users/{id}"])
def test_acting_on_another_or_unknown_account_is_403(roles, path_tpl):
    c = roles.admin.client
    assert c.delete(path_tpl.format(id=987654321)).status_code == 403
    assert c.delete(path_tpl.format(id=987654321), params={"hard_delete": "true"}).status_code == 403
    assert c.post("/api/users/987654321/deactivate").status_code == 403


@pytest.mark.plan("AUTH-09")
def test_deactivation_clears_assignments_and_cannot_be_repeated(roles, make_user, world):
    u = make_user(tag="assg_")
    world.a.add_member(u, "contributor")
    t = world.a.ticket(assignee_id=u.id, tester_id=u.id)
    deactivate(u)
    assert u.client.post(f"/api/users/{u.id}/deactivate").status_code == 403    # token is dead now
    name = ok(roles.admin.client.get(f"/api/users/{u.id}")).json()["full_name"]
    assert name.count("(Deactivated)") == 1
    fresh = ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()
    assert fresh["assignee"] is None and fresh["tester"] is None


@pytest.mark.plan("AUTH-09")
def test_user_can_deactivate_self_and_loses_access(make_user):
    u = make_user(tag="self_")
    assert u.client.delete(f"/api/users/{u.id}").status_code == 204
    assert u.client.get("/api/auth/me").status_code == 403


@pytest.mark.plan("AUTH-09")
def test_hard_delete_removes_user_and_blocks_login(base_url, roles, make_user):
    u = make_user(tag="hard_")
    assert u.client.delete(f"/api/users/{u.id}", params={"hard_delete": "true"}).status_code == 204
    assert roles.admin.client.get(f"/api/users/{u.id}").status_code == 404
    assert Client(base_url).login_form(u.email, PASSWORD).status_code == 400
    assert u.client.get("/api/auth/me").status_code == 401  # token for a vanished user
    assert u.client.delete(f"/api/users/{u.id}", params={"hard_delete": "true"}).status_code == 401


@pytest.mark.plan("AUTH-09")
def test_hard_delete_cascades_without_orphans(roles, make_user, world):
    victim = make_user(tag="casc_")
    # victim is a member who reported a ticket in project A
    world.a.add_member(victim, "contributor")
    theirs = world.a.ticket(client=victim.client, title="victim ticket")
    mine = world.a.ticket(title="kept ticket", assignee_id=victim.id)
    # victim also owns a project with another member
    owned = create_project(victim)
    owned.add_member(roles.editor, "editor")
    owned.ticket(title="inside owned project")

    ok(victim.client.delete(f"/api/users/{victim.id}", params={"hard_delete": "true"}), 204)

    assert roles.admin.client.get(f"/api/tickets/{theirs['id']}").status_code == 404     # reporter's ticket gone
    kept = ok(roles.admin.client.get(f"/api/tickets/{mine['id']}")).json()
    assert kept["assignee"] is None                                                       # assignment cleared
    member_ids = {m["user"]["id"] for m in ok(world.a.c.get(f"/api/projects/{world.a.id}/members")).json()}
    assert victim.id not in member_ids
    assert roles.editor.client.get(f"/api/projects/{owned.id}").status_code == 404        # owned project removed
    assert ok(world.a.c.get(f"/api/roadmap/project/{world.a.id}")).status_code == 200     # others stay consistent


@pytest.mark.plan("AUTH-09")
@pytest.mark.security
@pytest.mark.parametrize("attempt", ["deactivate", "soft_delete", "hard_delete", "legacy_soft_delete", "legacy_hard_delete"])
def test_user_cannot_deactivate_or_delete_another_account(roles, make_user, base_url, attempt):
    victim = make_user(tag="vict_")
    c = roles.outsider.client
    r = {
        "deactivate": lambda: c.post(f"/api/users/{victim.id}/deactivate"),
        "soft_delete": lambda: c.delete(f"/api/users/{victim.id}"),
        "hard_delete": lambda: c.delete(f"/api/users/{victim.id}", params={"hard_delete": "true"}),
        "legacy_soft_delete": lambda: c.delete(f"/api/auth/users/{victim.id}"),
        "legacy_hard_delete": lambda: c.delete(f"/api/auth/users/{victim.id}", params={"hard_delete": "true"}),
    }[attempt]()
    assert r.status_code == 403
    still = ok(victim.client.get("/api/auth/me")).json()          # victim keeps full access
    assert still["is_active"] is True and not still["full_name"].endswith("(Deactivated)")
    assert Client(base_url).login_form(victim.email, PASSWORD).status_code == 200


# ------------------------------------------------------------------ AUTH-10
@pytest.mark.plan("AUTH-10")
@pytest.mark.parametrize("name", ["Іван Петренко-Коваль", "Zoë Müller 🚀", "<b>bold</b> & \"quotes\"", "日本語 テスト", "مرحبا بالعالم"])
def test_unicode_and_markup_names_round_trip(anon, name):
    p = payload(full_name=name)
    created = ok(anon.post("/api/auth/register", json=p), 201).json()
    assert created["full_name"] == name
    token = ok(anon.login_form(p["email"], PASSWORD)).json()["access_token"]
    me = ok(Client(anon.base_url, token).get("/api/auth/me")).json()
    assert me["full_name"] == name


@pytest.mark.plan("AUTH-10")
def test_unicode_password_works_for_login(anon):
    p = payload(password="Пароль🔑-тест-123")
    ok(anon.post("/api/auth/register", json=p), 201)
    assert anon.login_form(p["email"], p["password"]).status_code == 200
    assert anon.login_form(p["email"], "Пароль🔑-тест-124").status_code == 400
