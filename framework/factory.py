"""Test-data factories: users, projects, tickets, milestones, JWTs and tiny binary fixtures."""
import base64
import hashlib
import hmac
import json
import random
import string
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Optional

from framework import config
from framework.client import Client

ROLES = ("admin", "editor", "contributor", "reporter")

# 1x1 PNG / JPEG / GIF so avatar uploads carry plausible content
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def ok(resp, code: int = 200):
    """Assert the status code and return the response (message shows method, url and body)."""
    assert resp.status_code == code, (
        f"{resp.request.method} {resp.url} -> {resp.status_code} (expected {code}): {resp.text[:600]}")
    return resp


def uid(n: int = 10) -> str:
    return uuid.uuid4().hex[:n]


def unique_email(tag: str = "") -> str:
    return f"{config.EMAIL_PREFIX}{tag}{uid(12)}@{config.EMAIL_DOMAIN}"


def unique_key() -> str:
    """Valid, globally unique project key: ^[A-Z][A-Z0-9]*$, 2..10 chars."""
    return "Q" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(payload: dict, key: str, alg: str = "HS256") -> str:
    """Hand-rolled HS256 JWT so tests can forge expired / foreign-signature tokens without extra deps."""
    header = {"alg": alg, "typ": "JWT"}
    signing = b64url(json.dumps(header).encode()) + "." + b64url(json.dumps(payload).encode())
    if alg == "none":
        return signing + "."
    sig = hmac.new(key.encode(), signing.encode(), hashlib.sha256).digest()
    return signing + "." + b64url(sig)


def decode_jwt_payload(token: str) -> dict:
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


@dataclass
class User:
    id: int
    email: str
    password: str
    full_name: str
    token: str
    client: Client
    data: dict = field(default_factory=dict)

    @property
    def headers(self):
        return self.client.headers


def register_user(base_url: str, full_name: Optional[str] = None, email: Optional[str] = None,
                  password: str = config.PASSWORD, tag: str = "") -> User:
    anon = Client(base_url)
    email = email or unique_email(tag)
    full_name = full_name or f"QA {tag or 'User'} {uid(4)}"
    r = ok(anon.post("/api/auth/register", json={"email": email, "password": password, "full_name": full_name}), 201)
    data = r.json()
    tok = ok(anon.login_form(email, password)).json()["access_token"]
    return User(id=data["id"], email=data["email"], password=password, full_name=full_name,
                token=tok, client=Client(base_url, tok), data=data)


# ---------------------------------------------------------------- projects
class Project:
    """Convenience wrapper around a created project owned by `owner`."""

    def __init__(self, owner: User, data: dict):
        self.owner = owner
        self.data = data
        self.id: int = data["id"]
        self.key: str = data["key"]
        self.columns: Dict[str, int] = {c["name"]: c["id"] for c in data["columns"]}

    @property
    def c(self) -> Client:
        return self.owner.client

    def add_member(self, user: User, role: str = "contributor"):
        return ok(self.c.post(f"/api/projects/{self.id}/members", json={"user_id": user.id, "role": role}), 201).json()

    def refresh_columns(self):
        cols = ok(self.c.get(f"/api/projects/{self.id}/columns")).json()
        self.columns = {c["name"]: c["id"] for c in cols}
        return cols

    def ticket(self, client: Optional[Client] = None, **fields) -> dict:
        """Create a ticket (asserting 201). Defaults: Task titled with a random suffix."""
        payload = {"title": f"T {uid(6)}", "type": "Task"}
        payload.update(fields)
        return ok((client or self.c).post(f"/api/tickets/project/{self.id}", json=payload), 201).json()

    def move(self, ticket_id: int, column: str, client: Optional[Client] = None):
        return ok((client or self.c).patch(f"/api/tickets/{ticket_id}/column",
                                           json={"column_id": self.columns[column]})).json()

    def milestone(self, client: Optional[Client] = None, **fields) -> dict:
        payload = {"title": f"M {uid(6)}"}
        payload.update(fields)
        return ok((client or self.c).post(f"/api/roadmap/project/{self.id}/milestones", json=payload), 201).json()

    def dependency(self, pred: int, succ: int, type: str = "FS", entity: str = "milestone",
                   client: Optional[Client] = None, expect: int = 201):
        r = (client or self.c).post(f"/api/roadmap/project/{self.id}/dependencies",
                                    json={"entity": entity, "predecessor_id": pred, "successor_id": succ,
                                          "type": type})
        return ok(r, expect).json() if expect == 201 else r

    def roadmap(self, client: Optional[Client] = None) -> dict:
        return ok((client or self.c).get(f"/api/roadmap/project/{self.id}")).json()

    def milestone_row(self, milestone_id: int, client: Optional[Client] = None) -> dict:
        return next(m for m in self.roadmap(client)["milestones"] if m["id"] == milestone_id)

    def tickets(self, client: Optional[Client] = None) -> list:
        return ok((client or self.c).get(f"/api/tickets/project/{self.id}")).json()

    def stats(self, client: Optional[Client] = None) -> dict:
        return ok((client or self.c).get(f"/api/projects/{self.id}/stats")).json()


def create_project(owner: User, key: Optional[str] = None, name: Optional[str] = None,
                   language: str = "uk") -> Project:
    payload = {"name": name or f"Project {uid(5)}", "key": key or unique_key(), "language": language}
    return Project(owner, ok(owner.client.post("/api/projects", json=payload), 201).json())


@dataclass
class Roles:
    admin: User          # project owner / admin
    editor: User
    contributor: User
    reporter: User
    outsider: User       # not a member of project A, owner of project B

    def by_name(self, name: str) -> User:
        return getattr(self, name)


@dataclass
class World:
    roles: Roles
    a: Project           # Project A: all roles are members
    b: Project           # Project B: separate key / columns / members (owner = outsider)

    def client(self, role: str) -> Client:
        return self.roles.by_name(role).client


def build_world(roles: Roles) -> World:
    a = create_project(roles.admin)
    a.add_member(roles.editor, "editor")
    a.add_member(roles.contributor, "contributor")
    a.add_member(roles.reporter, "reporter")
    b = create_project(roles.outsider)
    return World(roles=roles, a=a, b=b)


def iso(days: int = 0) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def wait_until(fn, timeout: float = 10.0, interval: float = 0.2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last

def deactivate(user):
    """A user closes their own account (the only allowed form after the authorization fix)."""
    return ok(user.client.post(f"/api/users/{user.id}/deactivate"))