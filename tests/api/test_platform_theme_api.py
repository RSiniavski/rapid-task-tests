"""Platform theme: every admin picks the look of the admin tool, saved on the server (PLT-08)."""
import pytest

from framework.client import Client
from framework.factory import ok
from framework.platform_api import P, audit, login_client

pytestmark = pytest.mark.api


def me(client):
    return ok(client.get(f"{P}/auth/me")).json()


def put_theme(client, key):
    return client.put(f"{P}/auth/me/theme", json={"theme_key": key})


@pytest.mark.plan("PLT-08")
def test_a_new_admin_has_the_default_look(padmin):
    a = padmin("th0")
    assert a.data["theme_key"] is None
    assert me(a.client)["theme_key"] is None


@pytest.mark.plan("PLT-08")
def test_the_choice_is_saved_and_comes_back_after_a_new_login(proot, padmin, base_url):
    a = padmin("th1")
    body = ok(put_theme(a.client, "nord")).json()
    assert body["theme_key"] == "nord" and body["username"] == a.username
    assert "password" not in str(body)
    assert me(a.client)["theme_key"] == "nord"
    again = login_client(base_url, a.username, a.password)                 # a new token, same account
    assert me(again)["theme_key"] == "nord"
    row = next(r for r in ok(proot.get(f"{P}/admins")).json() if r["id"] == a.id)
    assert row["theme_key"] == "nord"


@pytest.mark.plan("PLT-08")
def test_every_preset_of_the_app_can_be_chosen(padmin, make_user):
    keys = [t["key"] for t in ok(make_user(tag="plth_").client.get("/api/themes")).json()]
    assert len(keys) >= 12
    a = padmin("th2")
    for key in keys:
        ok(put_theme(a.client, key))
        assert me(a.client)["theme_key"] == key, key


@pytest.mark.plan("PLT-08")
def test_null_goes_back_to_the_default_look(padmin):
    a = padmin("th3")
    ok(put_theme(a.client, "mint_night"))
    assert ok(put_theme(a.client, None)).json()["theme_key"] is None
    assert me(a.client)["theme_key"] is None


@pytest.mark.plan("PLT-08")
@pytest.mark.parametrize("body", [
    {"theme_key": "no_such_theme"},
    {"theme_key": ""},
    {"theme_key": "x" * 100},
    {"theme_key": 5},
    {"theme_key": ["nord"]},
    {"theme_key": "nord", "is_root": True},
    {"theme_key": "nord", "can_manage_users": True},
], ids=["unknown", "empty", "too-long", "number", "list", "extra-is_root", "extra-permission"])
def test_bad_values_are_refused_and_the_old_choice_stays(padmin, body):
    a = padmin("th4")
    ok(put_theme(a.client, "nord"))
    assert a.client.put(f"{P}/auth/me/theme", json=body).status_code == 422
    got = me(a.client)
    assert got["theme_key"] == "nord"
    assert got["is_root"] is False and got["can_manage_users"] is False


@pytest.mark.plan("PLT-08")
def test_the_endpoint_needs_a_platform_token(base_url, make_user):
    assert Client(base_url).put(f"{P}/auth/me/theme", json={"theme_key": "nord"}).status_code == 401
    assert put_theme(make_user(tag="plth2_").client, "nord").status_code == 401        # an app token is no good


@pytest.mark.plan("PLT-08")
def test_every_admin_has_his_own_look(proot, padmin):
    a, b = padmin("th5"), padmin("th6")
    root_before = me(proot)["theme_key"]
    ok(put_theme(a.client, "midnight_neon"))
    assert me(a.client)["theme_key"] == "midnight_neon"
    assert me(b.client)["theme_key"] is None
    assert me(proot)["theme_key"] == root_before


@pytest.mark.plan("PLT-08")
def test_a_blocked_admin_cannot_change_the_look(proot, padmin):
    a = padmin("th7")
    ok(put_theme(a.client, "nord"))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    assert put_theme(a.client, "mint_night").status_code == 403
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": True}))
    assert me(a.client)["theme_key"] == "nord"


@pytest.mark.plan("PLT-08")
def test_changing_the_look_is_not_an_audit_event(proot, padmin):
    a = padmin("th8")
    before = audit(proot, actor=a.username)["total"]
    ok(put_theme(a.client, "nord"))
    ok(put_theme(a.client, None))
    assert audit(proot, actor=a.username)["total"] == before
    assert audit(proot, target=a.username, action="admin_updated")["total"] == 0


@pytest.mark.plan("PLT-08")
def test_the_look_survives_a_permission_change_and_a_password_reset(proot, padmin):
    a = padmin("th9")
    ok(put_theme(a.client, "nord"))
    ok(proot.patch(f"{P}/admins/{a.id}", json={"can_manage_users": True, "display_name": "Renamed"}))
    ok(proot.post(f"{P}/admins/{a.id}/password", json={"password": "Fresh-Passw0rd-9"}))
    assert me(a.client)["theme_key"] == "nord"
