"""FILE-FE (profile/avatar), E2E-09."""
import pytest
from playwright.sync_api import expect

from framework.factory import GIF_BYTES, PNG_BYTES, ok

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]


def open_profile(page):
    page.goto("/dashboard.html")
    page.locator(".cabinet-btn").click()
    return page.locator(".profile-modal")


@pytest.mark.plan("FILE-FE", "E2E-09")
def test_profile_edit_name_and_position_persist(page, login_ui, make_user):
    u = make_user(tag="uiprof_")
    login_ui(u)
    dlg = open_profile(page)
    expect(dlg.locator("input[disabled]")).to_have_value(u.email)
    inputs = dlg.locator("input.input:not([disabled])")
    inputs.nth(0).fill("Renamed User")
    inputs.nth(1).fill("QA Lead")
    dlg.get_by_role("button", name="Save").click()
    expect(dlg.locator(".form-ok")).to_contain_text("Saved")
    me = ok(u.client.get("/api/auth/me")).json()
    assert (me["full_name"], me["position"]) == ("Renamed User", "QA Lead")
    page.reload()
    expect(page.locator(".badge-mint")).to_have_text("Renamed User")


@pytest.mark.plan("FILE-FE")
def test_profile_blank_name_is_rejected_client_side(page, login_ui, make_user):
    u = make_user(tag="uiprof2_")
    login_ui(u)
    dlg = open_profile(page)
    dlg.locator("input.input:not([disabled])").nth(0).fill("   ")
    dlg.get_by_role("button", name="Save").click()
    page.wait_for_timeout(300)
    assert ok(u.client.get("/api/auth/me")).json()["full_name"] == u.full_name


@pytest.mark.plan("FILE-FE", "E2E-09")
def test_avatar_upload_and_removal(page, login_ui, make_user, tmp_path):
    u = make_user(tag="uiava_")
    f = tmp_path / "me.png"
    f.write_bytes(PNG_BYTES)
    login_ui(u)
    dlg = open_profile(page)
    dlg.locator("input[type=file]:not([data-testid=theme-file])").set_input_files(str(f))
    page.wait_for_function("document.querySelector('.profile-modal img') !== null")
    url = ok(u.client.get("/api/auth/me")).json()["avatar_url"]
    assert url and page.request.get(url).status == 200
    dlg.get_by_role("button", name="Remove").click()
    page.wait_for_timeout(600)
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None
    assert page.request.get(url).status == 404


@pytest.mark.plan("FILE-FE")
@pytest.mark.parametrize("name,content", [("note.txt", b"hello"), ("fake.png", b"not an image")])
def test_avatar_invalid_file_shows_error_and_keeps_state(page, login_ui, make_user, tmp_path, name, content):
    u = make_user(tag="uiava2_")
    f = tmp_path / name
    f.write_bytes(content)
    login_ui(u)
    dlg = open_profile(page)
    dlg.locator("input[type=file]:not([data-testid=theme-file])").set_input_files(str(f))
    expect(dlg.locator(".form-error")).to_be_visible()
    assert ok(u.client.get("/api/auth/me")).json()["avatar_url"] is None


@pytest.mark.plan("FILE-FE")
def test_avatar_replacement_removes_old_file(page, login_ui, make_user, tmp_path):
    u = make_user(tag="uiava3_")
    ok(u.client.upload("/api/users/me/avatar", "a.png", PNG_BYTES, "image/png"))
    old = ok(u.client.get("/api/auth/me")).json()["avatar_url"]
    f = tmp_path / "b.gif"
    f.write_bytes(GIF_BYTES)
    login_ui(u)
    dlg = open_profile(page)
    dlg.locator("input[type=file]:not([data-testid=theme-file])").set_input_files(str(f))
    page.wait_for_function("true")
    page.wait_for_timeout(800)
    new = ok(u.client.get("/api/auth/me")).json()["avatar_url"]
    assert new != old and page.request.get(new).status == 200 and page.request.get(old).status == 404
