"""Section 1 rule: every protected route must reject missing / malformed tokens and deactivated users
without leaking data or mutating state (AUTH-06/07 across the whole API inventory)."""
import pytest

from framework.client import Client
from framework.factory import PNG_BYTES, deactivate, ok

pytestmark = [pytest.mark.api, pytest.mark.security]

# (method, path, kind) - kind: json | multipart | none
PROTECTED = [
    ("GET", "/api/auth/me", "none"),
    ("GET", "/api/auth/users", "none"),
    ("DELETE", "/api/auth/users/1", "none"),
    ("GET", "/api/users", "none"),
    ("PATCH", "/api/users/me", "json"),
    ("POST", "/api/users/me/avatar", "multipart"),
    ("DELETE", "/api/users/me/avatar", "none"),
    ("GET", "/api/users/1", "none"),
    ("DELETE", "/api/users/1", "none"),
    ("POST", "/api/users/1/deactivate", "none"),
    ("GET", "/api/projects", "none"),
    ("POST", "/api/projects", "json"),
    ("GET", "/api/projects/dashboard", "none"),
    ("GET", "/api/projects/1", "none"),
    ("PATCH", "/api/projects/1", "json"),
    ("DELETE", "/api/projects/1", "none"),
    ("GET", "/api/projects/1/members", "none"),
    ("POST", "/api/projects/1/members", "json"),
    ("PATCH", "/api/projects/1/members/1", "json"),
    ("DELETE", "/api/projects/1/members/1", "none"),
    ("GET", "/api/projects/1/columns", "none"),
    ("POST", "/api/projects/1/columns", "json"),
    ("PATCH", "/api/projects/1/columns/1", "json"),
    ("DELETE", "/api/projects/1/columns/1", "none"),
    ("GET", "/api/projects/1/stats", "none"),
    ("POST", "/api/tickets/project/1", "json"),
    ("GET", "/api/tickets/project/1", "none"),
    ("GET", "/api/tickets/key/ABC-1", "none"),
    ("GET", "/api/tickets/1", "none"),
    ("PATCH", "/api/tickets/1/column", "json"),
    ("PATCH", "/api/tickets/1", "json"),
    ("DELETE", "/api/tickets/1", "none"),
    ("POST", "/api/attachments?project_id=1", "multipart"),
    ("DELETE", "/api/attachments/1", "none"),
    ("GET", "/api/roadmap/project/1", "none"),
    ("POST", "/api/roadmap/project/1/milestones", "json"),
    ("PATCH", "/api/roadmap/milestones/1", "json"),
    ("DELETE", "/api/roadmap/milestones/1", "none"),
    ("POST", "/api/roadmap/project/1/dependencies", "json"),
    ("PATCH", "/api/roadmap/dependencies/1", "json"),
    ("DELETE", "/api/roadmap/dependencies/1", "none"),
    ("PUT", "/api/roadmap/project/1/layout", "json"),
]
IDS = [f"{m} {p}" for m, p, _ in PROTECTED]


def _send(client: Client, method, path, kind, headers=None, auth=True):
    kw = {}
    if kind == "json":
        kw["json"] = {}
    elif kind == "multipart":
        kw["files"] = {"file": ("a.png", PNG_BYTES, "image/png")}
    return client.request(method, path, headers=headers, auth=auth, **kw)


@pytest.mark.plan("AUTH-06", "API-INV")
@pytest.mark.parametrize("method,path,kind", PROTECTED, ids=IDS)
def test_protected_route_rejects_anonymous_request(anon, method, path, kind):
    r = _send(anon, method, path, kind, auth=False)
    assert r.status_code == 401, r.text


@pytest.mark.plan("AUTH-06", "API-INV")
@pytest.mark.parametrize("method,path,kind", PROTECTED, ids=IDS)
def test_protected_route_rejects_malformed_token(anon, method, path, kind):
    r = _send(anon, method, path, kind, auth=False, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401, r.text


@pytest.mark.plan("AUTH-07", "API-INV")
@pytest.mark.parametrize("method,path,kind", PROTECTED[:12] + PROTECTED[25:30], ids=IDS[:12] + IDS[25:30])
def test_protected_route_rejects_deactivated_account(make_user, method, path, kind):
    u = make_user(tag="dead_")
    deactivate(u)
    r = _send(u.client, method, path, kind)
    assert r.status_code == 403, r.text
