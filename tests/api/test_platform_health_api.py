"""Platform admin tool: system health - GET /api/platform/health (PLT-22, PLT-23).
PLT-22 runs on the shared test server (shape, permission, counts). PLT-23 starts its own isolated applications
(counters, server errors, limits, restart), because it needs clean counters or special settings."""
from datetime import datetime

import pytest

from framework import config
from framework.client import Client
from framework.factory import create_project, ok, register_user, uid
from framework.platform_api import P, audit, create_admin, login_client

pytestmark = pytest.mark.api

H = f"{P}/health"
RAISE = f"{H}/_raise"
DEBUG = {"PLATFORM_HEALTH_DEBUG": "1"}


def health(client):
    return ok(client.get(H)).json()


def when(text):
    return datetime.fromisoformat(text)


def srv_root(srv):
    return login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)


# ---------------------------------------------------------------- PLT-22 who may see it, shape, counts
@pytest.mark.plan("PLT-22")
def test_health_needs_a_platform_token(anon, make_user):
    assert anon.get(H).status_code == 401
    assert make_user(tag="plt_").client.get(H).status_code == 401                   # an app token is no good


@pytest.mark.plan("PLT-22")
def test_the_system_health_permission_is_needed(proot, padmin):
    plain = padmin("noh")
    others = padmin("oth", can_manage_users=True, can_view_audit_logs=True, can_view_analytics=True, can_manage_projects=True)
    allowed = padmin("yesh", can_view_system_health=True)
    assert plain.client.get(H).status_code == 403
    assert others.client.get(H).status_code == 403
    assert allowed.client.get(H).status_code == 200
    assert proot.get(H).status_code == 200                                           # root has it always
    ok(proot.patch(f"{P}/admins/{allowed.id}", json={"is_active": False}))
    assert allowed.client.get(H).status_code == 403                                  # a blocked admin loses it at once


@pytest.mark.plan("PLT-22")
def test_the_answer_has_exactly_the_documented_fields(proot):
    h = health(proot)
    assert set(h) == {"status", "server", "databases", "disk", "counts", "load", "recent_errors", "limits"}
    assert h["status"] in ("ok", "warning", "critical")
    assert set(h["server"]) == {"app_version", "python_version", "started_at", "now", "uptime_seconds"}
    assert set(h["disk"]) == {"total_bytes", "used_bytes", "free_bytes", "used_percent", "level", "uploads_bytes", "uploads_files"}
    assert set(h["counts"]) == {"users", "projects", "tickets"}
    assert set(h["load"]) == {"requests_last_minute", "requests_total", "errors_last_hour", "errors_total", "errors_level"}
    assert set(h["limits"]) == {"disk_warn_percent", "disk_critical_percent", "errors_warn", "errors_critical"}
    assert [d["name"] for d in h["databases"]] == ["app", "platform"]
    assert all(set(d) == {"name", "file", "ok", "size_bytes", "error"} for d in h["databases"])


@pytest.mark.plan("PLT-22")
def test_server_and_database_values_make_sense(proot):
    h = health(proot)
    s = h["server"]
    assert s["app_version"] and s["python_version"].count(".") >= 1
    assert when(s["started_at"]) <= when(s["now"]) and s["uptime_seconds"] >= 0
    app_db, platform_db = h["databases"]
    assert (app_db["file"], platform_db["file"]) == ("rapid_task.db", "platform.db")
    for d in h["databases"]:
        assert d["ok"] is True and d["error"] is None and d["size_bytes"] > 0
        assert "/" not in d["file"] and "\\" not in d["file"]                       # the file name only, no folders


@pytest.mark.plan("PLT-22")
def test_disk_numbers_and_color_follow_the_limits(proot):
    h = health(proot)
    d, lim = h["disk"], h["limits"]
    assert d["total_bytes"] > 0 and d["used_bytes"] + d["free_bytes"] <= d["total_bytes"] * 1.01
    assert abs(d["used_percent"] - round(d["used_bytes"] * 100 / d["total_bytes"], 1)) < 0.11
    expected = ("critical" if d["used_percent"] >= lim["disk_critical_percent"]
                else "warning" if d["used_percent"] >= lim["disk_warn_percent"] else "ok")
    assert d["level"] == expected
    assert d["uploads_bytes"] >= 0 and d["uploads_files"] >= 0
    assert (lim["disk_warn_percent"], lim["disk_critical_percent"], lim["errors_warn"], lim["errors_critical"]) == (80, 90, 1, 10)


@pytest.mark.plan("PLT-22")
def test_the_overall_status_is_the_worst_level(proot):
    h = health(proot)
    levels = [h["disk"]["level"], h["load"]["errors_level"]] + ["ok" if d["ok"] else "critical" for d in h["databases"]]
    order = ["ok", "warning", "critical"]
    assert h["status"] == max(levels, key=order.index)


@pytest.mark.plan("PLT-22")
def test_counts_follow_users_projects_and_tickets(proot, make_user):
    before = health(proot)["counts"]
    owner = make_user(tag="hc_", full_name=f"QA {uid(8)} hc")
    other = make_user(tag="hc_", full_name=f"QA {uid(8)} hc2")
    project = create_project(owner)
    project.ticket()
    project.ticket()
    now = health(proot)["counts"]
    assert (now["users"] - before["users"], now["projects"] - before["projects"], now["tickets"] - before["tickets"]) == (2, 1, 2)
    ok(proot.post(f"{P}/users/{other.id}/block"))
    assert health(proot)["counts"]["users"] == now["users"]                          # a blocked user is still an account
    ok(proot.delete(f"{P}/users/{other.id}"))
    assert health(proot)["counts"]["users"] == now["users"] - 1                      # a soft-deleted one is not counted


@pytest.mark.plan("PLT-22")
def test_the_answer_has_no_secrets_and_no_paths(proot):
    text = proot.get(H).text
    low = text.lower()
    for word in ("password", "secret", "hash", "token", "sqlite:"):
        assert word not in low, word
    assert config.PLATFORM_ROOT_PASSWORD not in text and config.SECRET_KEY not in text
    assert ":\\" not in text and "/home/" not in text and "\\\\" not in text         # no folder names of the server


@pytest.mark.plan("PLT-22")
def test_reading_the_health_writes_no_audit_line(proot):
    before = audit(proot)["total"]
    for _ in range(3):
        health(proot)
    assert audit(proot)["total"] == before


# ---------------------------------------------------------------- PLT-23 counters, errors, limits, restart
@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_only_api_calls_are_counted_and_health_calls_are_not(plt_server):
    srv = plt_server()
    root = srv_root(srv)
    base = health(root)["load"]
    for _ in range(3):
        health(root)                                                                 # the page refreshes by itself
    assert health(root)["load"]["requests_total"] == base["requests_total"]
    Client(srv.base_url).get("/")                                                    # a static page
    assert health(root)["load"]["requests_total"] == base["requests_total"]
    for _ in range(3):
        ok(root.get(f"{P}/users"))
    load = health(root)["load"]
    assert load["requests_total"] == base["requests_total"] + 3
    assert load["requests_last_minute"] >= 3


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_a_client_error_is_a_request_but_not_a_server_error(plt_server):
    srv = plt_server()
    root = srv_root(srv)
    base = health(root)["load"]
    assert root.get(f"{P}/users/999999999").status_code in (404, 405)
    assert Client(srv.base_url).get(f"{P}/users", auth=False).status_code == 401
    load = health(root)["load"]
    assert load["requests_total"] == base["requests_total"] + 2
    assert load["errors_total"] == 0 and load["errors_last_hour"] == 0 and load["errors_level"] == "ok"


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_a_server_error_is_counted_listed_and_does_not_leak(plt_server):
    srv = plt_server(DEBUG)
    root = srv_root(srv)
    r = root.post(RAISE)
    assert r.status_code == 500 and r.json() == {"detail": "Internal Server Error"}
    assert "raised on purpose" not in r.text and "Traceback" not in r.text
    h = health(root)
    assert (h["load"]["errors_total"], h["load"]["errors_last_hour"]) == (1, 1)
    assert h["load"]["errors_level"] == "warning" and h["status"] in ("warning", "critical")
    err = h["recent_errors"][0]
    assert (err["method"], err["path"], err["status"], err["error"]) == ("POST", RAISE, 500, "RuntimeError")
    assert "raised on purpose" not in str(h)                                         # the class name only, never the message
    assert when(err["at"]) <= when(h["server"]["now"])
    assert health(root)["server"]                                                    # the server still works


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_the_error_list_keeps_the_newest_50_first(plt_server):
    srv = plt_server({**DEBUG, "HEALTH_ERRORS_WARN": "1000", "HEALTH_ERRORS_CRITICAL": "2000"})
    root = srv_root(srv)
    for _ in range(52):
        assert root.post(RAISE).status_code == 500
    h = health(root)
    assert h["load"]["errors_total"] == 52 and len(h["recent_errors"]) == 50
    times = [when(e["at"]) for e in h["recent_errors"]]
    assert times == sorted(times, reverse=True)


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_the_error_color_follows_the_limits(plt_server):
    srv = plt_server({**DEBUG, "HEALTH_ERRORS_WARN": "2", "HEALTH_ERRORS_CRITICAL": "3"})
    root = srv_root(srv)
    seen = []
    for _ in range(3):
        root.post(RAISE)
        seen.append(health(root)["load"]["errors_level"])
    assert seen == ["ok", "warning", "critical"]
    assert health(root)["status"] == "critical"
    assert health(root)["limits"]["errors_warn"] == 2


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_the_debug_route_exists_only_when_it_is_switched_on(plt_server, proot):
    assert proot.post(RAISE).status_code in (404, 405)                               # the normal server has no such route
    srv = plt_server(DEBUG)
    assert Client(srv.base_url).post(RAISE).status_code == 401                       # and with it, a platform token is needed
    plain = create_admin(srv_root(srv), srv.base_url, "dbg")
    assert plain.client.post(RAISE).status_code == 403                               # and the health permission


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
@pytest.mark.parametrize("warn, critical, level", [(0, 100, "warning"), (0, 0, "critical"), (101, 102, "ok")])
def test_the_disk_limits_come_from_the_settings(plt_server, warn, critical, level):
    srv = plt_server({"HEALTH_DISK_WARN_PERCENT": str(warn), "HEALTH_DISK_CRITICAL_PERCENT": str(critical)})
    h = health(srv_root(srv))
    assert h["disk"]["level"] == level
    assert h["status"] == level                                                      # nothing else is wrong on a fresh server
    assert (h["limits"]["disk_warn_percent"], h["limits"]["disk_critical_percent"]) == (warn, critical)


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_the_uploads_folder_is_measured(plt_server):
    srv = plt_server()
    root = srv_root(srv)
    before = health(root)["disk"]
    (srv.uploads_dir / f"health_{uid(6)}.bin").write_bytes(b"x" * 1234)
    after = health(root)["disk"]
    assert after["uploads_bytes"] - before["uploads_bytes"] == 1234
    assert after["uploads_files"] - before["uploads_files"] == 1


@pytest.mark.plan("PLT-23")
@pytest.mark.needs_local_server
def test_a_restart_starts_the_counters_and_the_uptime_again(plt_server):
    srv = plt_server(DEBUG)
    root = srv_root(srv)
    root.post(RAISE)
    old = health(root)
    assert old["load"]["errors_total"] == 1
    srv.restart(DEBUG)
    root = srv_root(srv)
    new = health(root)
    assert new["load"]["errors_total"] == 0 and new["recent_errors"] == [] and new["load"]["errors_level"] == "ok"
    assert when(new["server"]["started_at"]) > when(old["server"]["started_at"])
    assert new["server"]["uptime_seconds"] < old["server"]["uptime_seconds"] + 60
