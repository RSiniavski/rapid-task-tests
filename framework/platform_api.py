"""Helpers for the platform (admin tool) API tests."""
from dataclasses import dataclass

from framework.client import Client
from framework.factory import ok, uid

P = "/api/platform"
PERMS = ["can_view_system_health", "can_view_analytics", "can_manage_users", "can_manage_projects",
         "can_view_audit_logs", "can_manage_pages"]
ADMIN_PASSWORD = "Adm!n-Passw0rd-1"


def login_resp(base_url: str, username: str, password: str):
    return Client(base_url).post(f"{P}/auth/login", json={"username": username, "password": password}, auth=False)


def login_client(base_url: str, username: str, password: str) -> Client:
    token = ok(login_resp(base_url, username, password)).json()["access_token"]
    return Client(base_url, token)


@dataclass
class PAdmin:
    id: int
    username: str
    password: str
    client: Client
    data: dict


def create_admin(root: Client, base_url: str, tag: str = "adm", password: str = ADMIN_PASSWORD, **fields) -> PAdmin:
    """Root creates a platform admin (all permissions off unless given) and the admin logs in."""
    username = f"qa_{tag}_{uid(6)}".lower()
    body = {"username": username, "display_name": f"QA {tag}", "password": password}
    body.update(fields)
    data = ok(root.post(f"{P}/admins", json=body), 201).json()
    return PAdmin(id=data["id"], username=data["username"], password=password,
                  client=login_client(base_url, data["username"], password), data=data)


def audit(root: Client, **params) -> dict:
    params.setdefault("page_size", 100)
    return ok(root.get(f"{P}/audit", params=params)).json()


# ---------------------------------------------------------------- the app's users, seen from the platform
def users(client: Client, **params) -> dict:
    params.setdefault("page_size", 100)
    return ok(client.get(f"{P}/users", params=params)).json()


def find_user(client: Client, user) -> dict:
    """The platform row of an app user (found by the unique full name; the e-mail of a deleted user changes)."""
    token = user.full_name.replace(" (Deactivated)", "")
    rows = users(client, q=token)["items"]
    return next(r for r in rows if r["id"] == user.id)


# ---------------------------------------------------------------- the app's projects, seen from the platform (Project Insights)
def insight_projects(client: Client, **params) -> dict:
    params.setdefault("page_size", 100)
    return ok(client.get(f"{P}/insights/projects", params=params)).json()


def find_project(client: Client, project) -> dict:
    """The platform row of a project (found by its unique key)."""
    return next(r for r in insight_projects(client, q=project.key)["items"] if r["id"] == project.id)
