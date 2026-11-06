"""Platform admin tool: Project Insights - the app's projects, seen by the platform admins (PLT-34 .. PLT-38).
List (permission can_view_analytics); archive / restore / suspend / unsuspend / delete (root admin only).
The shared test server has other projects, so every test finds its own projects by a unique name or key."""
from datetime import datetime, timedelta

import pytest

from framework.factory import create_project, ok, uid
from framework.platform_api import P, audit, find_project, insight_projects

pytestmark = pytest.mark.api

I = f"{P}/insights/projects"
ROW_KEYS = {"id", "name", "key", "owner_name", "owner_email", "status", "status_reason", "status_changed_at", "created_at",
            "members_count", "tickets_total", "tickets_open", "last_activity_at", "inactive", "empty"}


def person(make_user, tag="pi", token=None):
    token = token or uid(8)
    return make_user(tag=f"{tag}_", full_name=f"QA {token} {tag}")


def build(make_user, token, label, members=0, tickets=0, owner=None):
    """A project owned by a new person; `members` more people join; `tickets` tickets are created.
    Returns (owner, project, [people], [tickets])."""
    owner = owner or person(make_user, f"o{label}", token)
    project = create_project(owner, name=f"QA {token} {label}")
    people = [person(make_user, f"m{label}{n}", token) for n in range(members)]
    for u in people:
        project.add_member(u, "editor")
    return owner, project, people, [project.ticket() for _ in range(tickets)]


def act(root, project, action, **body):
    return ok(root.post(f"{I}/{project.id}/{action}", json=body or None)).json()


def when(text):
    return datetime.fromisoformat(text)


def backdate(server, project, days):
    """Make the whole project (and its tickets, history, comments) look `days` days old, like a project nobody touched."""
    old = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S.%f")
    ids = "(SELECT id FROM tickets WHERE project_id = ?)"
    server.sql("UPDATE projects SET created_at = ? WHERE id = ?", (old, project.id))
    server.sql("UPDATE tickets SET created_at = ? WHERE project_id = ?", (old, project.id))
    server.sql(f"UPDATE ticket_history SET created_at = ? WHERE ticket_id IN {ids}", (old, project.id))
    server.sql(f"UPDATE ticket_comments SET created_at = ? WHERE ticket_id IN {ids}", (old, project.id))


# ---------------------------------------------------------------- PLT-34 list, search, filters, counters, sort, pages
@pytest.mark.plan("PLT-34")
def test_a_list_row_has_the_fields(proot, make_user):
    owner, p, _, _ = build(make_user, uid(8), "row")
    row = find_project(proot, p)
    assert set(row) == ROW_KEYS
    assert row["name"] == p.data["name"] and row["key"] == p.key
    assert row["owner_name"] == owner.full_name and row["owner_email"] == owner.email
    assert row["status"] == "active" and row["status_reason"] is None and row["status_changed_at"] is None
    assert row["created_at"] and (row["members_count"], row["tickets_total"], row["tickets_open"]) == (1, 0, 0)
    assert row["last_activity_at"] == row["created_at"]                       # nothing happened yet
    assert "password" not in str(row).lower() and "hashed" not in str(row).lower()


@pytest.mark.plan("PLT-34")
def test_search_by_name_key_and_owner_ignores_case(proot, make_user):
    token = uid(8)
    owner, p, _, _ = build(make_user, token, "srch")
    ids = lambda **kw: [r["id"] for r in insight_projects(proot, **kw)["items"]]
    assert ids(q=p.data["name"].upper()) == [p.id]
    assert ids(q=f"  {p.key.lower()}  ") == [p.id]
    assert ids(q=owner.full_name.upper()) == [p.id]                            # the owner's name
    assert ids(q=owner.email.upper()) == [p.id]                                # the owner's e-mail
    assert insight_projects(proot, q="no_such_project_" + uid(10))["total"] == 0
    assert insight_projects(proot, q="%")["total"] == 0                       # % is a plain character, not a wildcard
    assert insight_projects(proot, q="   ")["total"] == insight_projects(proot)["total"]


@pytest.mark.plan("PLT-34")
def test_status_filter_and_counters(proot, make_user):
    token = uid(8)
    _, active, _, _ = build(make_user, token, "a")
    _, archived, _, _ = build(make_user, token, "b")
    _, suspended, _, _ = build(make_user, token, "c")
    act(proot, archived, "archive")
    act(proot, suspended, "suspend", reason="check")
    page = insight_projects(proot, q=token)
    assert page["total"] == 3 and page["counts"] == {"all": 3, "active": 1, "archived": 1, "suspended": 1}
    for status, p in {"active": active, "archived": archived, "suspended": suspended}.items():
        part = insight_projects(proot, q=token, status=status)
        assert [r["id"] for r in part["items"]] == [p.id] and part["total"] == 1, status
        assert part["items"][0]["status"] == status
        assert part["counts"]["all"] == 3                                      # the counters ignore the status filter
    assert proot.get(I, params={"status": "nonsense"}).status_code == 422
    assert proot.get(I, params={"flag": "nonsense"}).status_code == 422


@pytest.mark.plan("PLT-34")
def test_sorting(proot, make_user):
    token = uid(8)
    _, bravo, _, _ = build(make_user, token, "bravo")
    _, alpha, _, _ = build(make_user, token, "Alpha")
    _, charlie, _, _ = build(make_user, token, "charlie")
    for u in (person(make_user, "x1", token), person(make_user, "x2", token)):
        charlie.add_member(u, "editor")                                         # charlie: 3 members
    bravo.add_member(person(make_user, "x3", token), "editor")                  # bravo: 2 members, alpha: 1
    bravo.ticket(), bravo.ticket()                                              # bravo: 2 tickets
    charlie.ticket()                                                            # charlie: 1 ticket, the newest action
    ids = lambda **kw: [r["id"] for r in insight_projects(proot, q=token, **kw)["items"]]
    assert ids() == [charlie.id, alpha.id, bravo.id]                            # newest project first (default)
    assert ids(sort="created") == ids()
    assert ids(sort="name") == [alpha.id, bravo.id, charlie.id]                 # a-z, case does not matter
    assert ids(sort="tickets") == [bravo.id, charlie.id, alpha.id]
    assert ids(sort="members") == [charlie.id, bravo.id, alpha.id]
    assert ids(sort="activity") == [charlie.id, bravo.id, alpha.id]             # the most recent action first
    assert proot.get(I, params={"sort": "owner"}).status_code == 422


@pytest.mark.plan("PLT-34")
def test_pages(proot, make_user):
    token = uid(8)
    made = [build(make_user, token, f"p{n}")[1] for n in range(5)]
    everything = [r["id"] for r in insight_projects(proot, q=token)["items"]]
    assert sorted(everything) == sorted(p.id for p in made)
    seen = []
    for page in (1, 2, 3):
        part = insight_projects(proot, q=token, page=page, page_size=2)
        assert part["total"] == 5 and part["page"] == page and part["page_size"] == 2
        seen += [r["id"] for r in part["items"]]
    assert seen == everything
    assert insight_projects(proot, q=token, page=4, page_size=2)["items"] == []
    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}):
        assert proot.get(I, params=bad).status_code == 422, bad


# ---------------------------------------------------------------- PLT-35 numbers and warnings
@pytest.mark.plan("PLT-35")
def test_members_and_tickets_are_counted(proot, make_user):
    owner, p, people, tickets = build(make_user, uid(8), "num", members=2, tickets=3)
    p.move(tickets[0]["id"], "Done")                                            # finished: not "open" any more
    row = find_project(proot, p)
    assert (row["members_count"], row["tickets_total"], row["tickets_open"]) == (3, 3, 2)
    ok(owner.client.delete(f"/api/projects/{p.id}/members/{people[0].id}"), 204)
    ok(owner.client.delete(f"/api/tickets/{tickets[1]['id']}"), 204)
    row = find_project(proot, p)
    assert (row["members_count"], row["tickets_total"], row["tickets_open"]) == (2, 2, 1)


@pytest.mark.plan("PLT-35")
def test_last_activity_follows_tickets_comments_and_changes(proot, make_user):
    owner, p, _, tickets = build(make_user, uid(8), "act", members=1, tickets=1)
    t = tickets[0]
    first = when(find_project(proot, p)["last_activity_at"])
    assert first >= when(find_project(proot, p)["created_at"])
    ok(owner.client.post(f"/api/tickets/{t['id']}/comments", json={"body": "hello"}), 201)
    second = when(find_project(proot, p)["last_activity_at"])
    assert second > first                                                       # a comment
    p.move(t["id"], "Done")
    third = when(find_project(proot, p)["last_activity_at"])
    assert third > second                                                       # a change in the history
    p.ticket()
    assert when(find_project(proot, p)["last_activity_at"]) > third             # a new ticket


@pytest.mark.plan("PLT-35")
def test_inactive_means_no_activity_for_30_days(proot, make_user, server):
    token = uid(8)
    owner, p, _, tickets = build(make_user, token, "old", members=1, tickets=1)
    assert find_project(proot, p)["inactive"] is False
    backdate(server, p, 29)
    assert find_project(proot, p)["inactive"] is False                          # 29 days: still fine
    backdate(server, p, 31)
    row = find_project(proot, p)
    assert row["inactive"] is True and row["empty"] is False
    part = insight_projects(proot, q=token, flag="inactive")
    assert [r["id"] for r in part["items"]] == [p.id] and part["flags"] == {"inactive": 1, "empty": 0}
    assert insight_projects(proot, q=token, flag="empty")["total"] == 0
    ok(owner.client.post(f"/api/tickets/{tickets[0]['id']}/comments", json={"body": "back again"}), 201)
    assert find_project(proot, p)["inactive"] is False                          # any activity ends it


@pytest.mark.plan("PLT-35")
def test_a_project_nobody_touched_counts_from_the_day_it_was_created(proot, make_user, server):
    _, p, _, _ = build(make_user, uid(8), "never")
    backdate(server, p, 40)
    row = find_project(proot, p)
    assert row["inactive"] is True and row["empty"] is True
    assert row["last_activity_at"] == row["created_at"]


@pytest.mark.plan("PLT-35")
def test_empty_means_no_tickets_or_one_member(proot, make_user):
    token = uid(8)
    _, no_tickets, _, _ = build(make_user, token, "e1", members=2, tickets=0)
    _, one_member, _, _ = build(make_user, token, "e2", members=0, tickets=1)
    _, fine, _, _ = build(make_user, token, "e3", members=1, tickets=1)
    assert [find_project(proot, p)["empty"] for p in (no_tickets, one_member, fine)] == [True, True, False]
    part = insight_projects(proot, q=token, flag="empty")
    assert sorted(r["id"] for r in part["items"]) == sorted([no_tickets.id, one_member.id])
    assert part["total"] == 2 and part["flags"] == {"inactive": 0, "empty": 2}
    assert part["counts"]["all"] == 3                                           # the counters ignore the flag filter


@pytest.mark.plan("PLT-35")
def test_the_warnings_are_for_working_projects_only(proot, make_user, server):
    token = uid(8)
    _, archived, _, _ = build(make_user, token, "w1")
    _, suspended, _, _ = build(make_user, token, "w2")
    backdate(server, archived, 40)
    backdate(server, suspended, 40)
    assert find_project(proot, archived)["inactive"] is True
    act(proot, archived, "archive")
    act(proot, suspended, "suspend", reason="check")
    for p in (archived, suspended):
        row = find_project(proot, p)
        assert row["inactive"] is False and row["empty"] is False
    assert insight_projects(proot, q=token)["flags"] == {"inactive": 0, "empty": 0}
    act(proot, archived, "restore")
    assert find_project(proot, archived)["inactive"] is True                    # a working project again


# ---------------------------------------------------------------- PLT-36 who may use it
@pytest.mark.plan("PLT-36")
@pytest.mark.parametrize("method, path", [("get", ""), ("post", "/1/archive"), ("post", "/1/restore"),
                                          ("post", "/1/suspend"), ("post", "/1/unsuspend"), ("delete", "/1")])
def test_insights_endpoints_need_a_platform_token(anon, make_user, method, path):
    assert getattr(anon, method)(f"{I}{path}").status_code == 401
    assert getattr(make_user(tag="plt_").client, method)(f"{I}{path}").status_code == 401       # an app token is no good


@pytest.mark.plan("PLT-36")
def test_the_analytics_permission_is_needed_to_read(proot, padmin, make_user):
    _, p, _, _ = build(make_user, uid(8), "perm")
    plain = padmin("noa")
    others = padmin("others", can_manage_users=True, can_manage_projects=True, can_view_system_health=True,
                    can_view_audit_logs=True)
    reader = padmin("yes", can_view_analytics=True)
    for admin in (plain, others):
        assert admin.client.get(I).status_code == 403
    assert reader.client.get(I, params={"q": p.key}).status_code == 200
    assert find_project(reader.client, p)["id"] == p.id


@pytest.mark.plan("PLT-36")
def test_only_the_root_admin_can_change_a_project(proot, padmin, make_user):
    owner, p, _, _ = build(make_user, uid(8), "root")
    boss = padmin("boss", can_view_analytics=True, can_manage_projects=True, can_manage_users=True,
                  can_view_system_health=True, can_view_audit_logs=True)       # every permission, but not the root
    base = f"{I}/{p.id}"
    calls = [lambda: boss.client.post(f"{base}/archive"), lambda: boss.client.post(f"{base}/restore"),
             lambda: boss.client.post(f"{base}/suspend", json={"reason": "x"}),
             lambda: boss.client.post(f"{base}/unsuspend"), lambda: boss.client.delete(base)]
    for call in calls:
        r = call()
        assert r.status_code == 403 and "root" in r.json()["detail"].lower()
    assert find_project(proot, p)["status"] == "active"                       # nothing happened
    assert owner.client.get(f"/api/projects/{p.id}").status_code == 200
    assert audit(proot, target=p.data["name"])["total"] == 0


# ---------------------------------------------------------------- PLT-37 archive, restore, suspend, unsuspend
@pytest.mark.plan("PLT-37")
def test_archive_hides_the_project_from_its_members_and_restore_brings_it_back(proot, make_user):
    owner, p, people, tickets = build(make_user, uid(8), "arc", members=1, tickets=1)
    member = people[0]
    t = tickets[0]
    row = act(proot, p, "archive")
    assert row["status"] == "archived" and row["status_changed_at"] and row["status_reason"] is None
    for u in (owner, member):
        assert p.id not in [x["id"] for x in ok(u.client.get("/api/projects")).json()]            # not in the list
        assert p.id not in [x["project_id"] for x in ok(u.client.get("/api/projects/dashboard")).json()["projects"]]
        for path in (f"/api/projects/{p.id}", f"/api/projects/{p.id}/members", f"/api/tickets/project/{p.id}",
                     f"/api/tickets/{t['id']}", f"/api/tickets/{t['id']}/comments"):
            r = u.client.get(path)
            assert r.status_code == 404 and r.json()["detail"] == "Project not found", path       # like a project that does not exist
    assert owner.client.post(f"/api/tickets/project/{p.id}", json={"title": "x", "type": "Task"}).status_code == 404
    assert owner.client.delete(f"/api/projects/{p.id}").status_code == 404                        # the owner can not delete it either
    assert find_project(proot, p)["status"] == "archived"                                         # the platform still sees it
    back = act(proot, p, "restore")
    assert back["status"] == "active" and back["status_reason"] is None
    assert p.id in [x["id"] for x in ok(owner.client.get("/api/projects")).json()]
    assert ok(member.client.get(f"/api/tickets/{t['id']}")).json()["id"] == t["id"]               # the data is all there


@pytest.mark.plan("PLT-37")
def test_a_suspended_project_blocks_its_members_and_tells_them_why(proot, make_user):
    owner, p, people, tickets = build(make_user, uid(8), "sus", members=1, tickets=1)
    member = people[0]
    t = tickets[0]
    row = act(proot, p, "suspend", reason="  Spam investigation  ")
    assert row["status"] == "suspended" and row["status_reason"] == "Spam investigation" and row["status_changed_at"]
    for u in (owner, member):
        listed = {x["id"]: x for x in ok(u.client.get("/api/projects")).json()}
        assert listed[p.id]["status"] == "suspended" and listed[p.id]["status_reason"] == "Spam investigation"
        assert p.id not in [x["project_id"] for x in ok(u.client.get("/api/projects/dashboard")).json()["projects"]]
        for method, path in (("get", f"/api/projects/{p.id}"), ("get", f"/api/tickets/project/{p.id}"),
                             ("get", f"/api/tickets/{t['id']}"), ("get", f"/api/tickets/{t['id']}/comments"),
                             ("get", f"/api/roadmap/project/{p.id}")):
            r = getattr(u.client, method)(path)
            assert r.status_code == 403, path
            assert r.json() == {"detail": "This project is suspended", "code": "project_suspended",
                                "reason": "Spam investigation"}
        assert u.client.post(f"/api/tickets/{t['id']}/comments", json={"body": "x"}).status_code == 403
        assert u.client.post(f"/api/tickets/project/{p.id}", json={"title": "x", "type": "Task"}).status_code == 403
    assert owner.client.delete(f"/api/projects/{p.id}").status_code == 403                        # no deleting evidence
    assert find_project(proot, p)["status"] == "suspended"
    back = act(proot, p, "unsuspend")
    assert back["status"] == "active" and back["status_reason"] is None
    assert ok(member.client.get(f"/api/tickets/{t['id']}")).json()["id"] == t["id"]
    ok(member.client.post(f"/api/tickets/{t['id']}/comments", json={"body": "working again"}), 201)
    assert ok(owner.client.get("/api/projects")).json()[-1]["status"] == "active"


@pytest.mark.plan("PLT-37")
def test_a_person_outside_the_project_never_sees_the_reason(proot, make_user):
    token = uid(8)
    _, p, _, tickets = build(make_user, token, "priv", tickets=1)
    stranger = person(make_user, "str", token)
    act(proot, p, "suspend", reason="private investigation notes")
    for path in (f"/api/projects/{p.id}", f"/api/tickets/{tickets[0]['id']}", f"/api/tickets/project/{p.id}"):
        r = stranger.client.get(path)
        assert r.status_code in (403, 404) and "investigation" not in r.text and "suspended" not in r.text, path
    assert p.id not in [x["id"] for x in ok(stranger.client.get("/api/projects")).json()]


@pytest.mark.plan("PLT-37")
def test_a_reason_is_required_to_suspend_and_is_optional_to_archive(proot, make_user):
    _, p, _, _ = build(make_user, uid(8), "rsn")
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": None}):
        r = proot.post(f"{I}/{p.id}/suspend", json=body)
        assert r.status_code == 422, body
    assert proot.post(f"{I}/{p.id}/suspend", json={"reason": "x" * 501}).status_code == 422
    assert find_project(proot, p)["status"] == "active"
    assert act(proot, p, "suspend", reason="x" * 500)["status_reason"] == "x" * 500
    act(proot, p, "unsuspend")
    row = act(proot, p, "archive", reason="  abandoned  ")
    assert row["status"] == "archived" and row["status_reason"] == "abandoned"
    assert act(proot, p, "restore")["status_reason"] is None                    # the reason goes with the state


@pytest.mark.plan("PLT-37")
def test_wrong_states_and_unknown_projects_are_refused(proot, make_user):
    _, p, _, _ = build(make_user, uid(8), "st")
    refused = lambda action, **body: proot.post(f"{I}/{p.id}/{action}", json=body or None)
    assert refused("restore").status_code == 409 and refused("unsuspend").status_code == 409       # it is active
    act(proot, p, "archive")
    for action, body in (("archive", {}), ("suspend", {"reason": "x"}), ("unsuspend", {})):
        assert refused(action, **body).status_code == 409, action
    act(proot, p, "restore")
    act(proot, p, "suspend", reason="x")
    for action, body in (("archive", {}), ("suspend", {"reason": "y"}), ("restore", {})):
        assert refused(action, **body).status_code == 409, action
    assert find_project(proot, p)["status_reason"] == "x"                      # a refused call changes nothing
    for action, body in (("archive", {}), ("restore", {}), ("suspend", {"reason": "x"}), ("unsuspend", {})):
        assert proot.post(f"{I}/99999999/{action}", json=body).status_code == 404, action
    assert proot.post(f"{I}/abc/archive", json={}).status_code == 422


@pytest.mark.plan("PLT-37")
def test_every_change_is_in_the_audit_log(proot, make_user):
    owner, p, _, _ = build(make_user, uid(8), "aud")
    name = p.data["name"]
    act(proot, p, "archive")
    act(proot, p, "restore")
    act(proot, p, "suspend", reason="Spam")
    act(proot, p, "unsuspend")
    act(proot, p, "archive", reason="Dead project")
    rows = audit(proot, target=name)["items"]
    assert [r["action"] for r in rows] == ["project_archived", "project_unsuspended", "project_suspended",
                                           "project_restored", "project_archived"]
    for r in rows:
        assert r["actor_name"] and r["target_type"] == "project" and r["target_id"] == p.id and r["target_name"] == name
        assert r["ip"]
    details = [r["details"] for r in rows]
    assert details == [{"key": p.key, "reason": "Dead project"}, {"key": p.key}, {"key": p.key, "reason": "Spam"},
                       {"key": p.key}, {"key": p.key}]


@pytest.mark.plan("PLT-37")
def test_a_refused_change_writes_no_log_line(proot, make_user):
    _, p, _, _ = build(make_user, uid(8), "nolog")
    assert proot.post(f"{I}/{p.id}/restore").status_code == 409
    assert proot.post(f"{I}/{p.id}/suspend", json={"reason": ""}).status_code == 422
    assert audit(proot, target=p.data["name"])["total"] == 0


# ---------------------------------------------------------------- PLT-38 delete
@pytest.mark.plan("PLT-38")
def test_delete_removes_the_project_and_everything_in_it(proot, make_user):
    token = uid(8)
    owner, p, people, tickets = build(make_user, token, "del", members=1, tickets=2)
    _, other, _, other_tickets = build(make_user, token, "keep", tickets=1)
    ok(owner.client.post(f"/api/tickets/{tickets[0]['id']}/comments", json={"body": "bye"}), 201)
    assert proot.delete(f"{I}/{p.id}").status_code == 204
    assert insight_projects(proot, q=p.key)["total"] == 0
    assert owner.client.get(f"/api/projects/{p.id}").status_code == 404
    assert owner.client.get(f"/api/tickets/{tickets[0]['id']}").status_code == 404
    assert p.id not in [x["id"] for x in ok(people[0].client.get("/api/projects")).json()]
    assert find_project(proot, other)["tickets_total"] == 1                     # the other project is not touched
    assert ok(other.owner.client.get(f"/api/tickets/{other_tickets[0]['id']}")).json()["id"] == other_tickets[0]["id"]
    assert proot.delete(f"{I}/{p.id}").status_code == 404                       # it is gone
    row = audit(proot, target=p.data["name"])["items"][0]
    assert row["action"] == "project_deleted" and row["target_id"] == p.id and row["target_name"] == p.data["name"]
    assert row["details"] == {"key": p.key, "tickets": 2}


@pytest.mark.plan("PLT-38")
@pytest.mark.parametrize("state", ["archived", "suspended"])
def test_a_project_can_be_deleted_in_any_state(proot, make_user, state):
    _, p, _, _ = build(make_user, uid(8), "any", tickets=1)
    act(proot, p, "archive") if state == "archived" else act(proot, p, "suspend", reason="check")
    assert proot.delete(f"{I}/{p.id}").status_code == 204
    assert insight_projects(proot, q=p.key)["total"] == 0


@pytest.mark.plan("PLT-38")
def test_the_key_can_be_used_again_after_a_delete(proot, make_user):
    owner, p, _, _ = build(make_user, uid(8), "reuse")
    ok(proot.delete(f"{I}/{p.id}"), 204)
    again = create_project(owner, key=p.key, name="Same key again")
    assert again.key == p.key                                                   # (SQLite may give the freed id again: not checked)
    assert find_project(proot, again)["name"] == "Same key again"
