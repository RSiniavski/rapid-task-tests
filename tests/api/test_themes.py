"""Theme Engine (API): presets, personal theme, import validation, export/delete, project lock."""
import copy

import pytest

from framework.factory import ok

pytestmark = pytest.mark.api

PRESET_KEYS = {"rapid_task_dark_pastel", "rapid_task_light_pastel", "solarized_dark",
               "solarized_light", "one_dark", "nord"}


def themes(client):
    return ok(client.get("/api/themes")).json()


def preset(client, key="nord"):
    return next(t for t in themes(client) if t["key"] == key)


def exported(client, key="nord", name=None):
    """A valid importable theme body (taken from the export of a preset)."""
    body = ok(client.get(f"/api/themes/{preset(client, key)['id']}/export")).json()
    body["name"] = name or "QA theme"
    return body


def import_theme(client, **overrides):
    body = exported(client)
    body.update(overrides)
    return ok(client.post("/api/themes/import", json=body), 201).json()


# =================================================================== THEME-01
@pytest.mark.plan("THEME-01")
def test_theme_list_requires_auth(anon):
    assert anon.get("/api/themes").status_code == 401


@pytest.mark.plan("THEME-01")
def test_presets_are_listed(make_user):
    u = make_user(tag="th1_")
    rows = themes(u.client)
    presets = [t for t in rows if t["is_preset"]]
    assert {t["key"] for t in presets} >= PRESET_KEYS
    for t in presets:
        assert t["created_by"] is None
        assert set(t) >= {"id", "key", "name", "colors", "shadows", "typography"}
        assert t["colors"]["accent"].startswith("#")


@pytest.mark.plan("THEME-01")
def test_custom_theme_is_private_to_its_owner(make_user):
    a, b = make_user(tag="th1a_"), make_user(tag="th1b_")
    mine = import_theme(a.client, name="Private A")
    assert mine["id"] in {t["id"] for t in themes(a.client)}
    assert mine["id"] not in {t["id"] for t in themes(b.client)}


# =================================================================== THEME-02
@pytest.mark.plan("THEME-02")
def test_new_user_has_no_personal_theme(make_user):
    u = make_user(tag="th2_")
    assert ok(u.client.get("/api/auth/me")).json()["theme_id"] is None


@pytest.mark.plan("THEME-02")
def test_set_and_reset_personal_theme(make_user):
    u = make_user(tag="th2b_")
    nord = preset(u.client)["id"]
    r = ok(u.client.put("/api/users/me/theme", json={"theme_id": nord})).json()
    assert r["theme_id"] == nord
    assert ok(u.client.get("/api/auth/me")).json()["theme_id"] == nord
    r = ok(u.client.put("/api/users/me/theme", json={"theme_id": None})).json()
    assert r["theme_id"] is None


@pytest.mark.plan("THEME-02")
def test_personal_theme_unknown_id_is_404(make_user):
    u = make_user(tag="th2c_")
    assert u.client.put("/api/users/me/theme", json={"theme_id": 99999999}).status_code == 404


@pytest.mark.plan("THEME-02")
def test_personal_theme_wrong_type_is_422(make_user):
    u = make_user(tag="th2d_")
    assert u.client.put("/api/users/me/theme", json={"theme_id": "abc"}).status_code == 422


@pytest.mark.plan("THEME-02")
def test_cannot_select_someone_elses_custom_theme(make_user):
    a, b = make_user(tag="th2e_"), make_user(tag="th2f_")
    mine = import_theme(a.client, name="Only mine")
    assert b.client.put("/api/users/me/theme", json={"theme_id": mine["id"]}).status_code == 404
    assert ok(a.client.put("/api/users/me/theme", json={"theme_id": mine["id"]})).json()["theme_id"] == mine["id"]


@pytest.mark.plan("THEME-02")
def test_personal_theme_requires_auth(anon):
    assert anon.put("/api/users/me/theme", json={"theme_id": 1}).status_code == 401


# =================================================================== THEME-03
def _mut(fn):
    def apply(body):
        body = copy.deepcopy(body)
        fn(body)
        return body
    return apply


INVALID = {
    "css-injection-in-color": _mut(lambda b: b["colors"].__setitem__("accent", "red; } body{display:none")),
    "named-color": _mut(lambda b: b["colors"].__setitem__("accent", "red")),
    "color-not-string": _mut(lambda b: b["colors"].__setitem__("accent", 123)),
    "rgb-out-of-range": _mut(lambda b: b["colors"].__setitem__("accent", "rgb(300, 0, 0)")),
    "alpha-out-of-range": _mut(lambda b: b["colors"].__setitem__("accent_soft", "rgba(1, 2, 3, 1.5)")),
    "url-in-color": _mut(lambda b: b["colors"].__setitem__("border", "url(http://evil.example/x)")),
    "missing-color": _mut(lambda b: b["colors"].pop("accent")),
    "unknown-color-key": _mut(lambda b: b["colors"].__setitem__("evil", "#fff")),
    "url-in-shadow": _mut(lambda b: b["shadows"].__setitem__("card", "0 0 0 url(http://evil.example/x)")),
    "semicolon-in-shadow": _mut(lambda b: b["shadows"].__setitem__("card", "0 0 0 #000; color: red")),
    "unknown-shadow-key": _mut(lambda b: b["shadows"].__setitem__("evil", "0 0 1px #000")),
    "font-not-whitelisted": _mut(lambda b: b["typography"].__setitem__("font_family", "Comic Sans MS")),
    "font-injection": _mut(lambda b: b["typography"].__setitem__("font_family", "Arial; background:url(x)")),
    "size-without-unit": _mut(lambda b: b["typography"].__setitem__("base_size", "14")),
    "size-too-small": _mut(lambda b: b["typography"].__setitem__("base_size", "5px")),
    "size-too-big": _mut(lambda b: b["typography"].__setitem__("base_size", "40px")),
    "empty-name": _mut(lambda b: b.__setitem__("name", "   ")),
    "name-too-long": _mut(lambda b: b.__setitem__("name", "N" * 81)),
    "name-with-html": _mut(lambda b: b.__setitem__("name", "<script>alert(1)</script>")),
    "unknown-top-level-key": _mut(lambda b: b.__setitem__("project_id", 1)),
    "missing-section": _mut(lambda b: b.pop("shadows")),
}


@pytest.mark.plan("THEME-03")
@pytest.mark.parametrize("case", sorted(INVALID))
def test_invalid_theme_is_rejected(make_user, case):
    u = make_user(tag="th3_")
    body = INVALID[case](exported(u.client))
    r = u.client.post("/api/themes/import", json=body)
    assert r.status_code == 422, r.text
    assert themes(u.client) == [t for t in themes(u.client) if t["is_preset"]]  # nothing was saved


@pytest.mark.plan("THEME-03")
def test_rejection_names_the_bad_field(make_user):
    u = make_user(tag="th3b_")
    body = INVALID["css-injection-in-color"](exported(u.client))
    r = u.client.post("/api/themes/import", json=body)
    assert any("colors.accent" in e for e in r.json()["detail"]["errors"])


@pytest.mark.plan("THEME-03")
def test_import_body_must_be_an_object(make_user):
    u = make_user(tag="th3c_")
    assert u.client.post("/api/themes/import", json=[1, 2, 3]).status_code == 422
    assert u.client.post("/api/themes/import", json="text").status_code == 422


@pytest.mark.plan("THEME-03")
def test_oversized_import_is_413(make_user):
    u = make_user(tag="th3d_")
    body = exported(u.client)
    body["junk"] = "a" * 25000
    assert u.client.post("/api/themes/import", json=body).status_code == 413


@pytest.mark.plan("THEME-03")
def test_import_requires_auth(anon, make_user):
    u = make_user(tag="th3e_")
    assert anon.post("/api/themes/import", json=exported(u.client)).status_code == 401


@pytest.mark.plan("THEME-03")
def test_valid_import_is_saved_as_private_custom_theme(make_user):
    u = make_user(tag="th3f_")
    created = import_theme(u.client, name="  Padded name  ")
    assert created["name"] == "Padded name"
    assert created["is_preset"] is False and created["key"] is None
    assert created["created_by"] == u.id
    assert created["colors"] == preset(u.client)["colors"]


@pytest.mark.plan("THEME-03")
def test_custom_theme_limit_per_user(make_user):
    u = make_user(tag="th3g_")
    for i in range(20):
        import_theme(u.client, name=f"T{i}")
    r = u.client.post("/api/themes/import", json=exported(u.client, name="One too many"))
    assert r.status_code == 400


# =================================================================== THEME-04
@pytest.mark.plan("THEME-04")
def test_export_import_round_trip(make_user):
    u = make_user(tag="th4_")
    first = import_theme(u.client, name="Round trip")
    body = ok(u.client.get(f"/api/themes/{first['id']}/export")).json()
    assert set(body) == {"name", "colors", "shadows", "typography"}
    body["name"] = "Round trip 2"
    second = ok(u.client.post("/api/themes/import", json=body), 201).json()
    assert second["colors"] == first["colors"] and second["id"] != first["id"]


@pytest.mark.plan("THEME-04")
def test_export_unknown_or_foreign_theme_is_404(make_user):
    a, b = make_user(tag="th4a_"), make_user(tag="th4b_")
    mine = import_theme(a.client)
    assert a.client.get("/api/themes/99999999/export").status_code == 404
    assert b.client.get(f"/api/themes/{mine['id']}/export").status_code == 404


@pytest.mark.plan("THEME-04")
def test_theme_export_and_delete_require_auth(anon):
    assert anon.get("/api/themes/1/export").status_code == 401
    assert anon.delete("/api/themes/1").status_code == 401


@pytest.mark.plan("THEME-04")
def test_preset_cannot_be_deleted(make_user):
    u = make_user(tag="th4c_")
    assert u.client.delete(f"/api/themes/{preset(u.client)['id']}").status_code == 403
    assert preset(u.client)["key"] == "nord"


@pytest.mark.plan("THEME-04")
def test_delete_own_custom_theme_clears_references(world, make_user):
    admin = world.roles.admin
    mine = import_theme(admin.client, name="To delete")
    ok(admin.client.put("/api/users/me/theme", json={"theme_id": mine["id"]}))
    ok(admin.client.put(f"/api/projects/{world.a.id}/theme-settings",
                        json={"theme_id": mine["id"], "is_locked": True}))
    assert admin.client.delete(f"/api/themes/{mine['id']}").status_code == 204
    assert mine["id"] not in {t["id"] for t in themes(admin.client)}
    assert ok(admin.client.get("/api/auth/me")).json()["theme_id"] is None
    s = ok(admin.client.get(f"/api/projects/{world.a.id}/theme-settings")).json()
    assert (s["theme_id"], s["is_locked"], s["theme"]) == (None, False, None)


@pytest.mark.plan("THEME-04")
def test_cannot_delete_someone_elses_theme(make_user):
    a, b = make_user(tag="th4d_"), make_user(tag="th4e_")
    mine = import_theme(a.client)
    assert b.client.delete(f"/api/themes/{mine['id']}").status_code == 404
    assert mine["id"] in {t["id"] for t in themes(a.client)}


# =================================================================== THEME-05
def settings_url(world):
    return f"/api/projects/{world.a.id}/theme-settings"


@pytest.mark.plan("THEME-05")
def test_default_project_theme_settings(world):
    s = ok(world.client("reporter").get(settings_url(world))).json()
    assert s == {"project_id": world.a.id, "theme_id": None, "is_locked": False, "theme": None}


@pytest.mark.plan("THEME-05")
def test_theme_settings_require_auth_and_membership(world, anon):
    assert anon.get(settings_url(world)).status_code == 401
    assert world.client("outsider").get(settings_url(world)).status_code == 403
    assert world.client("outsider").put(settings_url(world), json={"theme_id": None}).status_code == 403


@pytest.mark.plan("THEME-05")
@pytest.mark.parametrize("role", ["editor", "contributor", "reporter"])
def test_only_admin_can_change_project_theme(world, role):
    nord = preset(world.client(role))["id"]
    r = world.client(role).put(settings_url(world), json={"theme_id": nord, "is_locked": False})
    assert r.status_code == 403
    assert ok(world.client("admin").get(settings_url(world))).json()["theme_id"] is None


@pytest.mark.plan("THEME-05")
def test_admin_sets_theme_and_lock_and_members_see_it(world):
    nord = preset(world.client("admin"))
    r = ok(world.client("admin").put(settings_url(world), json={"theme_id": nord["id"], "is_locked": True})).json()
    assert (r["theme_id"], r["is_locked"]) == (nord["id"], True)
    assert r["theme"]["colors"] == nord["colors"]
    for role in ("editor", "contributor", "reporter"):
        s = ok(world.client(role).get(settings_url(world))).json()
        assert (s["theme_id"], s["is_locked"]) == (nord["id"], True)


@pytest.mark.plan("THEME-05")
def test_lock_without_theme_is_400(world):
    r = world.client("admin").put(settings_url(world), json={"theme_id": None, "is_locked": True})
    assert r.status_code == 400


@pytest.mark.plan("THEME-05")
def test_project_theme_unknown_id_is_404(world):
    r = world.client("admin").put(settings_url(world), json={"theme_id": 99999999, "is_locked": False})
    assert r.status_code == 404


@pytest.mark.plan("THEME-05")
def test_admin_can_apply_own_custom_theme_and_members_can_read_it(world):
    admin = world.roles.admin
    mine = import_theme(admin.client, name="Team look")
    ok(admin.client.put(settings_url(world), json={"theme_id": mine["id"], "is_locked": False}))
    s = ok(world.client("reporter").get(settings_url(world))).json()
    assert s["theme"]["name"] == "Team look"
    # ... but the member still cannot see it in his own theme list
    assert mine["id"] not in {t["id"] for t in themes(world.client("reporter"))}


@pytest.mark.plan("THEME-05")
def test_admin_cannot_apply_someone_elses_custom_theme(world, make_user):
    other = make_user(tag="th5_")
    foreign = import_theme(other.client, name="Foreign")
    r = world.client("admin").put(settings_url(world), json={"theme_id": foreign["id"], "is_locked": False})
    assert r.status_code == 404


@pytest.mark.plan("THEME-05")
def test_unlock_and_clear_project_theme(world):
    c = world.client("admin")
    nord = preset(c)["id"]
    ok(c.put(settings_url(world), json={"theme_id": nord, "is_locked": True}))
    ok(c.put(settings_url(world), json={"theme_id": nord, "is_locked": False}))
    assert ok(c.get(settings_url(world))).json()["is_locked"] is False
    ok(c.put(settings_url(world), json={"theme_id": None, "is_locked": False}))
    assert ok(c.get(settings_url(world))).json()["theme"] is None


@pytest.mark.plan("THEME-05")
def test_theme_settings_are_per_project(world):
    nord = preset(world.client("admin"))["id"]
    ok(world.client("admin").put(settings_url(world), json={"theme_id": nord, "is_locked": True}))
    other = ok(world.client("outsider").get(f"/api/projects/{world.b.id}/theme-settings")).json()
    assert other["theme_id"] is None and other["is_locked"] is False


@pytest.mark.plan("THEME-05")
def test_unknown_project_theme_settings_is_404(world):
    assert world.client("admin").get("/api/projects/99999999/theme-settings").status_code == 404
