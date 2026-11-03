"""Platform start-up: the root account comes from .env; the app also starts without it (PLT-06).
Every test starts its own isolated application (own databases) and restarts it on the same databases."""
import pytest

from framework.client import Client
from framework.factory import ok, register_user
from framework.platform_api import ADMIN_PASSWORD, P, audit, create_admin, login_client, login_resp

pytestmark = [pytest.mark.api, pytest.mark.needs_local_server]

USER, PWD = "boot_root", "Boot!Root-12345"
ROOT_ENV = {"PLATFORM_ROOT_USERNAME": USER, "PLATFORM_ROOT_PASSWORD": PWD}
NO_ROOT = {"PLATFORM_ROOT_USERNAME": None, "PLATFORM_ROOT_PASSWORD": None}
NOTICE = "There are no platform admins here"


def status(srv):
    return ok(Client(srv.base_url).get(f"{P}/status", auth=False)).json()


def root(srv, password=PWD, username=USER):
    return login_client(srv.base_url, username, password)


@pytest.mark.plan("PLT-06")
def test_without_a_root_the_app_starts_and_says_so(plt_server):
    srv = plt_server(NO_ROOT)
    assert status(srv) == {"has_admins": False, "root_configured": False}
    assert NOTICE in srv.log_text() and "PLATFORM_ROOT_USERNAME" in srv.log_text()
    register_user(srv.base_url)                                           # the main application works as usual
    assert login_resp(srv.base_url, USER, PWD).status_code == 401


@pytest.mark.plan("PLT-06")
def test_the_root_is_created_from_the_env_values(plt_server):
    srv = plt_server(ROOT_ENV)
    assert status(srv) == {"has_admins": True, "root_configured": True}
    assert NOTICE not in srv.log_text()
    admin = ok(login_resp(srv.base_url, USER, PWD)).json()["admin"]
    assert admin["is_root"] is True and all(admin[f] for f in admin if f.startswith("can_"))
    rows = audit(root(srv), action="root_created")["items"]
    assert len(rows) == 1 and rows[0]["actor_name"] == "system"


@pytest.mark.plan("PLT-06")
def test_a_changed_env_updates_the_same_root_account(plt_server):
    srv = plt_server(ROOT_ENV)
    root_id = ok(login_resp(srv.base_url, USER, PWD)).json()["admin"]["id"]
    srv.restart({**ROOT_ENV, "PLATFORM_ROOT_PASSWORD": "Boot!Root-67890"})              # a new password
    assert login_resp(srv.base_url, USER, PWD).status_code == 401
    assert ok(login_resp(srv.base_url, USER, "Boot!Root-67890")).json()["admin"]["id"] == root_id
    srv.restart({"PLATFORM_ROOT_USERNAME": "boot_root2", "PLATFORM_ROOT_PASSWORD": "Boot!Root-67890"})   # a new name
    assert login_resp(srv.base_url, USER, "Boot!Root-67890").status_code == 401
    assert ok(login_resp(srv.base_url, "boot_root2", "Boot!Root-67890")).json()["admin"]["id"] == root_id
    changed = [c for r in audit(root(srv, "Boot!Root-67890", "boot_root2"), action="root_updated")["items"]
               for c in r["details"]["changed"]]
    assert "password" in changed and "username" in changed


@pytest.mark.plan("PLT-06")
def test_without_the_env_the_root_is_off_but_other_admins_keep_working(plt_server):
    srv = plt_server(ROOT_ENV)
    helper = create_admin(root(srv), srv.base_url, "keep", can_view_audit_logs=True)
    srv.restart(NO_ROOT)
    assert status(srv) == {"has_admins": True, "root_configured": False}      # an admin exists: all is fine
    assert NOTICE not in srv.log_text()
    ok(login_resp(srv.base_url, helper.username, helper.password))
    assert login_resp(srv.base_url, USER, PWD).status_code == 403                # the root is switched off
    srv.restart(ROOT_ENV)                                                       # the root can be set at any time
    assert status(srv) == {"has_admins": True, "root_configured": True}
    actions = [r["action"] for r in audit(root(srv))["items"]]
    assert "root_disabled" in actions and "root_updated" in actions


@pytest.mark.plan("PLT-06")
def test_without_the_env_and_without_other_admins_the_notice_is_printed(plt_server):
    srv = plt_server(ROOT_ENV)
    assert NOTICE not in srv.log_text()
    srv.restart(NO_ROOT)
    assert status(srv) == {"has_admins": False, "root_configured": False}
    assert NOTICE in srv.log_text()


@pytest.mark.plan("PLT-06")
def test_invalid_env_values_are_reported_and_change_nothing(plt_server):
    srv = plt_server({**ROOT_ENV, "PLATFORM_ROOT_PASSWORD": "short"})          # too short from the start
    assert "PLATFORM_ROOT_PASSWORD must be" in srv.log_text()
    assert status(srv)["has_admins"] is False
    srv.restart({"PLATFORM_ROOT_USERNAME": "bad name!", "PLATFORM_ROOT_PASSWORD": PWD})
    assert "PLATFORM_ROOT_USERNAME must be" in srv.log_text()
    assert status(srv)["has_admins"] is False
    srv.restart(ROOT_ENV)                                                       # good values: the root appears
    ok(login_resp(srv.base_url, USER, PWD))
    srv.restart({**ROOT_ENV, "PLATFORM_ROOT_PASSWORD": "short"})               # bad values later: the root stays as it was
    assert "PLATFORM_ROOT_PASSWORD must be" in srv.log_text()
    ok(login_resp(srv.base_url, USER, PWD))


@pytest.mark.plan("PLT-06")
def test_a_root_name_used_by_another_admin_is_refused(plt_server):
    srv = plt_server(ROOT_ENV)
    other = create_admin(root(srv), srv.base_url, "taken")
    srv.restart({"PLATFORM_ROOT_USERNAME": other.username, "PLATFORM_ROOT_PASSWORD": PWD})
    assert "already used by another platform admin" in srv.log_text()
    ok(login_resp(srv.base_url, USER, PWD))                                      # the root is unchanged
    assert login_resp(srv.base_url, other.username, PWD).status_code == 401     # the other admin was not taken over
    ok(login_resp(srv.base_url, other.username, ADMIN_PASSWORD))
