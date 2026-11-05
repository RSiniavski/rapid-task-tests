"""Platform admin tool: the Overview - GET /api/platform/overview (PLT-26, PLT-27).
PLT-26: who may read it, the shape, the periods. PLT-27: the numbers follow what happens in the application.
The shared test server has other data, so the numbers are compared as differences (before / after)."""
from datetime import datetime, timedelta, timezone

import pytest

from framework import config
from framework.client import Client
from framework.factory import create_project, deactivate, ok, register_user, uid
from framework.platform_api import P, audit, login_client

pytestmark = pytest.mark.api

O = f"{P}/overview"
TYPES = ["Idea", "Epic", "Task", "Subtask", "Bug", "Incident"]


def overview(client, days=None):
    return ok(client.get(O, params={"days": days} if days else None)).json()


def total(o, series):
    return sum(o["series"][series])


def today():
    return datetime.now(timezone.utc).date()


def person(make_user, tag="ov"):
    return make_user(tag=f"{tag}_", full_name=f"QA {uid(8)} {tag}")


# ---------------------------------------------------------------- PLT-26 who, shape, periods
@pytest.mark.plan("PLT-26")
def test_overview_needs_a_platform_token(anon, make_user):
    assert anon.get(O).status_code == 401
    assert make_user(tag="plt_").client.get(O).status_code == 401                    # an app token is no good


@pytest.mark.plan("PLT-26")
def test_the_analytics_permission_is_needed(proot, padmin):
    plain = padmin("noa")
    others = padmin("otha", can_view_system_health=True, can_manage_users=True, can_manage_projects=True, can_view_audit_logs=True)
    allowed = padmin("yesa", can_view_analytics=True)
    assert plain.client.get(O).status_code == 403
    assert others.client.get(O).status_code == 403
    assert allowed.client.get(O).status_code == 200
    assert proot.get(O).status_code == 200                                           # root has it always
    ok(proot.patch(f"{P}/admins/{allowed.id}", json={"is_active": False}))
    assert allowed.client.get(O).status_code == 403                                  # a blocked admin loses it at once


@pytest.mark.plan("PLT-26")
def test_the_answer_has_exactly_the_documented_fields(proot):
    o = overview(proot)
    assert set(o) == {"period", "users", "projects", "tickets", "activity", "series", "activity_since",
                      "tickets_by_status", "tickets_by_type"}
    assert set(o["period"]) == {"days", "first_day", "last_day"}
    assert set(o["users"]) == {"total", "active", "blocked", "deactivated", "deleted", "new"}
    assert set(o["projects"]) == {"total", "new", "with_activity"}
    assert set(o["tickets"]) == {"total", "open", "created", "done"}
    assert set(o["activity"]) == {"comments", "attachments"}
    assert set(o["series"]) == {"days", "new_users", "new_projects", "new_tickets", "active_users"}
    assert all(set(x) == {"name", "count", "is_done"} for x in o["tickets_by_status"])
    assert all(set(x) == {"type", "count"} for x in o["tickets_by_type"])


@pytest.mark.plan("PLT-26")
@pytest.mark.parametrize("days", [None, 7, 30, 90])
def test_the_period_gives_that_many_days_ending_today(proot, days):
    o = overview(proot, days)
    n = days or 30
    s = o["series"]
    assert o["period"]["days"] == n and len(s["days"]) == n
    for key in ("new_users", "new_projects", "new_tickets", "active_users"):
        assert len(s[key]) == n and all(isinstance(v, int) and v >= 0 for v in s[key])
    assert s["days"][-1] == today().isoformat() == o["period"]["last_day"]
    assert s["days"][0] == (today() - timedelta(days=n - 1)).isoformat() == o["period"]["first_day"]
    assert s["days"] == [(today() - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]      # every day, in order


@pytest.mark.plan("PLT-26")
@pytest.mark.parametrize("days", ["0", "1", "10", "-7", "365", "abc", ""])
def test_a_period_that_is_not_offered_is_refused(proot, days):
    assert proot.get(O, params={"days": days}).status_code == 422


@pytest.mark.plan("PLT-26")
def test_tickets_by_type_lists_every_type(proot):
    o = overview(proot)
    assert [x["type"] for x in o["tickets_by_type"]] == TYPES
    assert sum(x["count"] for x in o["tickets_by_type"]) == o["tickets"]["total"]


@pytest.mark.plan("PLT-26")
def test_tickets_by_status_adds_up_and_is_sorted(proot, make_user):
    project = create_project(person(make_user))
    project.ticket()
    o = overview(proot)
    counts = [x["count"] for x in o["tickets_by_status"]]
    assert sum(counts) == o["tickets"]["total"]
    body = [x for x in o["tickets_by_status"] if x["name"] != "Other"]
    assert [x["count"] for x in body] == sorted((x["count"] for x in body), reverse=True)
    assert len(o["tickets_by_status"]) <= 9                                           # 8 names + "Other"
    assert all(isinstance(x["is_done"], bool) and x["name"] for x in o["tickets_by_status"])


@pytest.mark.plan("PLT-26")
def test_the_totals_do_not_depend_on_the_period(proot):
    a, b, c = overview(proot, 7), overview(proot, 30), overview(proot, 90)
    for key, field in (("users", "total"), ("projects", "total"), ("tickets", "total"), ("tickets", "open")):
        assert a[key][field] == b[key][field] == c[key][field]
    assert a["users"]["new"] <= b["users"]["new"] <= c["users"]["new"]
    assert a["tickets"]["created"] <= b["tickets"]["created"] <= c["tickets"]["created"]


@pytest.mark.plan("PLT-26")
def test_reading_the_overview_writes_no_audit_line(proot):
    before = audit(proot)["total"]
    for days in (7, 30, 90):
        overview(proot, days)
    assert audit(proot)["total"] == before


# ---------------------------------------------------------------- PLT-27 the numbers follow the application
@pytest.mark.plan("PLT-27")
def test_user_numbers_follow_register_block_deactivate_and_delete(proot, make_user):
    before = overview(proot)
    a, b, c, d = (person(make_user, t) for t in ("u1", "u2", "u3", "u4"))
    o = overview(proot)
    assert o["users"]["total"] == before["users"]["total"] + 4 and o["users"]["active"] == before["users"]["active"] + 4
    assert o["users"]["new"] == before["users"]["new"] + 4
    assert total(o, "new_users") == total(before, "new_users") + 4
    ok(proot.post(f"{P}/users/{b.id}/block"))
    deactivate(c)
    ok(proot.delete(f"{P}/users/{d.id}"))
    o = overview(proot)
    u, u0 = o["users"], before["users"]
    assert u["active"] == u0["active"] + 1 and u["blocked"] == u0["blocked"] + 1
    assert u["deactivated"] == u0["deactivated"] + 1 and u["deleted"] == u0["deleted"] + 1
    assert u["total"] == u0["total"] + 3                                              # a deleted user is not counted in the total
    assert u["total"] == u["active"] + u["blocked"] + u["deactivated"]


@pytest.mark.plan("PLT-27")
def test_project_and_ticket_numbers(proot, make_user):
    before = overview(proot)
    project = create_project(person(make_user))
    project.ticket()
    project.ticket()
    done = project.ticket()
    project.move(done["id"], "Done")
    o = overview(proot)
    assert o["projects"]["total"] == before["projects"]["total"] + 1 and o["projects"]["new"] == before["projects"]["new"] + 1
    assert o["projects"]["with_activity"] == before["projects"]["with_activity"] + 1
    assert total(o, "new_projects") == total(before, "new_projects") + 1
    t, t0 = o["tickets"], before["tickets"]
    assert t["total"] == t0["total"] + 3 and t["created"] == t0["created"] + 3
    assert t["done"] == t0["done"] + 1                                                # closed in the period
    assert t["open"] == t0["open"] + 2                                                # three new, one of them done
    assert total(o, "new_tickets") == total(before, "new_tickets") + 3


@pytest.mark.plan("PLT-27")
def test_the_status_chart_counts_tickets_per_column(proot, make_user):
    before = {x["name"].lower(): x for x in overview(proot)["tickets_by_status"]}
    project = create_project(person(make_user))
    project.ticket()
    project.ticket()
    project.move(project.ticket()["id"], "Done")
    after = {x["name"].lower(): x for x in overview(proot)["tickets_by_status"]}
    assert after["done"]["is_done"] is True
    assert after["done"]["count"] == before.get("done", {"count": 0})["count"] + 1
    assert sum(x["count"] for x in after.values()) == sum(x["count"] for x in before.values()) + 3


@pytest.mark.plan("PLT-27")
def test_the_type_chart_counts_each_type(proot, make_user):
    before = {x["type"]: x["count"] for x in overview(proot)["tickets_by_type"]}
    project = create_project(person(make_user))
    project.ticket(type="Bug")
    project.ticket(type="Bug")
    project.ticket(type="Epic")
    after = {x["type"]: x["count"] for x in overview(proot)["tickets_by_type"]}
    assert after["Bug"] == before["Bug"] + 2 and after["Epic"] == before["Epic"] + 1
    assert after["Task"] == before["Task"] and after["Incident"] == before["Incident"]


@pytest.mark.plan("PLT-27")
def test_comments_and_files_are_counted(proot, make_user):
    owner = person(make_user)
    project = create_project(owner)
    ticket = project.ticket()
    before = overview(proot)["activity"]
    for text in ("one", "two"):
        ok(owner.client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": text}), 201)
    ok(owner.client.upload("/api/attachments", "note.txt", b"hello", "text/plain",
                           params={"project_id": project.id, "ticket_id": ticket["id"]}), 201)
    after = overview(proot)["activity"]
    assert after["comments"] == before["comments"] + 2 and after["attachments"] == before["attachments"] + 1


@pytest.mark.plan("PLT-27")
def test_an_active_user_is_counted_once_a_day(proot, make_user):
    before = overview(proot)
    u = person(make_user)                                                              # registering also logs in
    assert total(overview(proot), "active_users") == total(before, "active_users") + 1
    for _ in range(3):
        assert u.client.get("/api/auth/me").status_code == 200                         # more calls the same day: still one
    after = overview(proot)
    assert total(after, "active_users") == total(before, "active_users") + 1
    assert after["activity_since"] is not None and after["activity_since"] <= today().isoformat()
    assert after["series"]["active_users"][-1] >= 1


@pytest.mark.plan("PLT-27")
def test_a_blocked_user_is_not_active(proot, make_user, base_url):
    u = person(make_user)
    ok(proot.post(f"{P}/users/{u.id}/block"))
    before = total(overview(proot), "active_users")
    assert u.client.get("/api/auth/me").status_code == 403                             # refused, so not a visit
    assert total(overview(proot), "active_users") == before


@pytest.mark.plan("PLT-27")
@pytest.mark.needs_local_server
def test_the_activity_days_survive_a_restart_without_doubles(plt_server):
    srv = plt_server()
    root = login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)
    u = register_user(srv.base_url, tag="ovr_")
    o = overview(root)
    assert total(o, "active_users") == 1 and o["activity_since"] == today().isoformat()
    srv.restart()
    root = login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)
    assert total(overview(root), "active_users") == 1                                  # the row is still there
    again = Client(srv.base_url, u.token)                                              # a restart gives a new port; the token is still good
    assert again.get("/api/auth/me").status_code == 200                                # the memory is empty, the database says "already saved"
    assert total(overview(root), "active_users") == 1                                  # no second row, no error
    v = register_user(srv.base_url, tag="ovr2_")
    assert total(overview(root), "active_users") == 2


@pytest.mark.plan("PLT-27")
@pytest.mark.needs_local_server
def test_a_fresh_server_shows_zeros_and_no_chart_start(plt_server):
    srv = plt_server()
    root = login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)
    o = overview(root, 90)
    assert o["activity_since"] is None and total(o, "active_users") == 0
    assert (o["users"]["total"], o["projects"]["total"], o["tickets"]["total"]) == (0, 0, 0)
    assert o["tickets_by_status"] == [] and all(x["count"] == 0 for x in o["tickets_by_type"])
    assert o["activity"] == {"comments": 0, "attachments": 0}
