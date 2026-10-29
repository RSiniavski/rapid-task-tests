"""STATIC, UI-06/07 (HTTP part), API inventory vs OpenAPI, CORS, token transport, and Section 11 characterization."""
import re

import pytest

from framework.factory import PNG_BYTES, ok, unique_email
from framework.config import PASSWORD

pytestmark = pytest.mark.api

PAGES = ["/", "/index.html", "/dashboard.html", "/board.html", "/backlog.html", "/ticket.html",
         "/roadmap.html", "/donate.html"]
ASSET_RE = re.compile(r'(?:src|href)="(/[^"#?]+\.(?:js|css|svg|png|ico))')


@pytest.mark.plan("STATIC")
@pytest.mark.parametrize("path", PAGES)
def test_html_pages_are_served(anon, path):
    r = anon.get(path, auth=False)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "<html" in r.text.lower()


@pytest.mark.plan("STATIC")
@pytest.mark.parametrize("path,needle", [("/docs", "swagger"), ("/redoc", "redoc"), ("/openapi.json", "openapi")])
def test_documentation_endpoints(anon, path, needle):
    r = anon.get(path, auth=False)
    assert r.status_code == 200 and needle in r.text.lower()


@pytest.mark.plan("STATIC", "UI-06")
def test_every_local_asset_referenced_by_pages_exists(anon):
    seen = set()
    for page in PAGES:
        seen |= set(ASSET_RE.findall(anon.get(page, auth=False).text))
    assert "/css/theme.css" in seen and "/resources/favico.svg" in seen
    for asset in sorted(seen):
        r = anon.get(asset, auth=False)
        assert r.status_code == 200, f"{asset} -> {r.status_code}"


@pytest.mark.plan("STATIC")
def test_unknown_static_path_is_404_not_500(anon):
    for p in ("/nope.html", "/js/missing.js", "/resources/missing.svg", "/uploads/nope.png", "/api/unknown"):
        assert anon.get(p, auth=False).status_code == 404


@pytest.mark.plan("STATIC", "API-INV")
def test_openapi_inventory_matches_expected_routes(anon):
    spec = anon.get("/openapi.json", auth=False).json()
    got = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops if m in ("get", "post", "patch", "put", "delete")}
    expected = {
        ("POST", "/api/auth/register"), ("POST", "/api/auth/login"), ("GET", "/api/auth/me"),
        ("GET", "/api/auth/users"), ("DELETE", "/api/auth/users/{user_id}"),
        ("GET", "/api/users"), ("PATCH", "/api/users/me"), ("POST", "/api/users/me/avatar"),
        ("DELETE", "/api/users/me/avatar"), ("GET", "/api/users/{user_id}"), ("DELETE", "/api/users/{user_id}"),
        ("POST", "/api/users/{user_id}/deactivate"),
        ("GET", "/api/projects"), ("POST", "/api/projects"), ("GET", "/api/projects/dashboard"),
        ("GET", "/api/projects/{project_id}"), ("PATCH", "/api/projects/{project_id}"),
        ("DELETE", "/api/projects/{project_id}"), ("GET", "/api/projects/{project_id}/stats"),
        ("POST", "/api/attachments"), ("DELETE", "/api/attachments/{attachment_id}"),
        ("GET", "/api/roadmap/project/{project_id}"), ("PUT", "/api/roadmap/project/{project_id}/layout"),
    }
    missing = {e for e in expected if e not in got}
    assert not missing, f"documented routes missing from OpenAPI: {sorted(missing)}"
    assert len([1 for _, p in got if p.startswith("/api/")]) >= 40


# ---------------------------------------------------------------- UI-07 HTTP-level
@pytest.mark.plan("UI-07")
@pytest.mark.security
def test_cors_preflight_policy_is_characterized(anon):
    r = anon.request("OPTIONS", "/api/auth/me", auth=False, headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200
    # current behaviour: wildcard policy. Recorded explicitly so a tightening is a conscious change.
    assert r.headers.get("access-control-allow-origin") in ("*", "https://evil.example")


@pytest.mark.plan("UI-07")
@pytest.mark.security
def test_cors_headers_do_not_enable_cookie_authentication(roles, anon):
    token = roles.admin.token
    r = anon.get("/api/auth/me", auth=False, headers={"Cookie": f"access_token={token}",
                                                      "Origin": "https://evil.example"})
    assert r.status_code == 401                        # token only accepted via Authorization header


@pytest.mark.plan("UI-07")
@pytest.mark.security
@pytest.mark.parametrize("scheme", ["Basic", "Token", "bearer-ish"])
def test_non_bearer_authorization_schemes_rejected(roles, anon, scheme):
    r = anon.get("/api/auth/me", auth=False, headers={"Authorization": f"{scheme} {roles.admin.token}"})
    assert r.status_code == 401


@pytest.mark.plan("UI-07", "FILE-05")
@pytest.mark.security
def test_upload_response_headers_are_safe(world):
    att = ok(world.a.c.upload(f"/api/attachments?project_id={world.a.id}", "x.png", PNG_BYTES, "image/png"), 201).json()
    url = att.get("url") or att.get("download_url") or f"/uploads/{att['stored_name']}"
    r = world.a.c.get(url, auth=False)
    assert r.status_code == 200 and r.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.plan("UI-07")
@pytest.mark.security
def test_api_error_bodies_do_not_leak_internals(anon):
    for r in (anon.post("/api/auth/login", data={"username": "a", "password": "b"}, auth=False),
              anon.get("/api/projects/999999999", auth=False),
              anon.get("/api/tickets/key/%27%20OR%201%3D1", auth=False)):
        assert r.status_code in (400, 401, 404, 422)
        assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()


# ---------------------------------------------------------------- Section 11 characterization
@pytest.mark.plan("CLAR")
@pytest.mark.characterization
def test_clar_email_case_sensitivity_is_documented(anon):
    email = unique_email()
    ok(anon.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Case"}, auth=False), 201)
    upper = anon.login_form(email.upper(), PASSWORD)
    dup = anon.post("/api/auth/register", json={"email": email.upper(), "password": PASSWORD, "full_name": "Case2"}, auth=False)
    # Whatever the product decides, login and duplicate-registration must be consistent with each other.
    assert (upper.status_code == 200) == (dup.status_code in (400, 409)), (upper.status_code, dup.status_code)


@pytest.mark.plan("CLAR")
@pytest.mark.characterization
def test_clar_multiple_done_columns_behaviour(world):
    new = ok(world.a.c.post(f"/api/projects/{world.a.id}/columns", json={"name": "Shipped"}), 201).json()
    r = world.a.c.patch(f"/api/projects/{world.a.id}/columns/{new['id']}", json={"is_done": True})
    assert r.status_code in (200, 400, 409, 422)
    if r.status_code == 200:                            # if a 2nd done column is allowed, both count as done
        world.a.refresh_columns()
        t = world.a.ticket()
        world.a.move(t["id"], "Shipped")
        assert world.a.stats()["tickets_done"] >= 1


@pytest.mark.plan("CLAR")
@pytest.mark.characterization
def test_clar_patch_null_vs_omitted(world):
    t = world.a.ticket(description="keep me")
    ok(world.a.c.patch(f"/api/tickets/{t['id']}", json={"title": "Only title"}))
    assert ok(world.a.c.get(f"/api/tickets/{t['id']}")).json()["description"] == "keep me"      # omitted = unchanged
    r = world.a.c.patch(f"/api/tickets/{t['id']}", json={"description": None})
    assert r.status_code in (200, 422)
