"""Platform admin tool: site pages - Donate, Terms, Privacy ... (PLT-43 .. PLT-48).
Platform side: /api/platform/pages (permission can_manage_pages, root has it always).
Public side: GET /api/pages/{slug} and GET /api/pages/links (no login, published pages only).
The shared test server has other pages, so every test uses its own pages (slug prefix qa-<token>)."""
import pytest

from framework.factory import ok, uid
from framework.platform_api import ADMIN_PASSWORD, P, audit, create_admin

pytestmark = pytest.mark.api

PAGES = f"{P}/pages"
PUBLIC = "/api/pages"
PERM = "can_manage_pages"
OTHER_PERMS = {"can_view_system_health": True, "can_view_analytics": True, "can_manage_users": True,
               "can_manage_projects": True, "can_view_audit_logs": True}
LIST_KEYS = {"id", "slug", "title_uk", "title_en", "status", "in_footer", "in_register", "sort_order", "is_system",
             "has_uk", "has_en", "updated_at", "updated_by"}
PUBLIC_KEYS = {"slug", "title_uk", "title_en", "content_uk", "content_en", "updated_at"}


@pytest.fixture
def make_page(proot):
    """make_page(token, label, **fields) -> page dict (a draft). The pages are deleted after the test."""
    made = []

    def make(token, label="p", **fields):
        body = {"slug": f"qa-{token}-{label}", "title_en": f"QA {label}", "content_en": f"Text of {label}"}
        body.update(fields)
        page = ok(proot.post(PAGES, json=body), 201).json()
        made.append(page["id"])
        return page

    yield make
    for page_id in made:
        proot.delete(f"{PAGES}/{page_id}")


def publish(proot, page):
    return ok(proot.post(f"{PAGES}/{page['id']}/publish")).json()


def unpublish(proot, page):
    return ok(proot.post(f"{PAGES}/{page['id']}/unpublish")).json()


def public(anon, slug):
    return anon.get(f"{PUBLIC}/{slug}", auth=False)


def link_slugs(anon, token):
    rows = ok(anon.get(f"{PUBLIC}/links", auth=False)).json()
    return [r["slug"] for r in rows if f"qa-{token}-" in r["slug"]]


# ---------------------------------------------------------------- PLT-43 who may manage pages
@pytest.mark.plan("PLT-43")
def test_the_root_admin_has_the_permission_and_new_admins_do_not(proot, padmin):
    root_row = ok(proot.get(f"{P}/admins")).json()[0]
    assert root_row["is_root"] is True and root_row[PERM] is True
    a = padmin("pg0")
    assert a.data[PERM] is False
    b = padmin("pg0b", **{PERM: True})
    assert b.data[PERM] is True
    got = ok(proot.patch(f"{P}/admins/{a.id}", json={PERM: True})).json()           # the root can give it later
    assert got[PERM] is True
    got = ok(proot.patch(f"{P}/admins/{a.id}", json={PERM: False})).json()
    assert got[PERM] is False


@pytest.mark.plan("PLT-43")
def test_without_the_permission_every_page_endpoint_is_forbidden(proot, padmin, make_page, anon):
    page = make_page(uid(8), "x")
    plain = padmin("pg1", **OTHER_PERMS)                                              # all other permissions, not this one
    c = plain.client
    calls = [("get", PAGES, None), ("get", f"{PAGES}/{page['id']}", None),
             ("post", PAGES, {"slug": f"qa-{uid(8)}-n", "title_en": "N"}),
             ("patch", f"{PAGES}/{page['id']}", {"title_en": "Changed"}),
             ("post", f"{PAGES}/{page['id']}/publish", None), ("post", f"{PAGES}/{page['id']}/unpublish", None),
             ("delete", f"{PAGES}/{page['id']}", None)]
    for method, url, body in calls:
        r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
        assert r.status_code == 403, (method, url, r.status_code)
        r = getattr(anon, method)(url, json=body, auth=False) if body is not None else getattr(anon, method)(url, auth=False)
        assert r.status_code == 401, (method, url, r.status_code)
    assert ok(proot.get(f"{PAGES}/{page['id']}")).json()["title_en"] == "QA x"       # nothing changed


@pytest.mark.plan("PLT-43")
def test_an_admin_with_the_permission_can_do_everything(proot, padmin):
    a = padmin("pg2", **{PERM: True})
    token = uid(8)
    made = ok(a.client.post(PAGES, json={"slug": f"qa-{token}-a", "title_en": "A", "content_en": "text"}), 201).json()
    ok(a.client.patch(f"{PAGES}/{made['id']}", json={"title_en": "A2"}))
    publish(a.client, made)
    assert ok(a.client.get(PAGES)).json()
    unpublish(a.client, made)
    ok(a.client.delete(f"{PAGES}/{made['id']}"), 204)
    row = audit(proot, action="page_created", actor=a.username)["items"][0]
    assert row["actor_name"] == a.username                                            # the log names the admin


@pytest.mark.plan("PLT-43")
def test_a_blocked_admin_cannot_manage_pages(proot, padmin):
    a = padmin("pg3", **{PERM: True})
    ok(proot.patch(f"{P}/admins/{a.id}", json={"is_active": False}))
    assert a.client.get(PAGES).status_code == 403                                       # an old token does not help


# ---------------------------------------------------------------- PLT-44 create and edit
@pytest.mark.plan("PLT-44")
def test_create_a_page_it_is_a_draft(proot, make_page, anon):
    token = uid(8)
    p = make_page(token, "terms", title_uk="Умови", title_en="Terms", content_uk="Текст", content_en="Text",
                  in_footer=True, in_register=True, sort_order=7)
    assert p["slug"] == f"qa-{token}-terms" and p["status"] == "draft" and p["is_system"] is False
    assert (p["title_uk"], p["title_en"], p["content_uk"], p["content_en"]) == ("Умови", "Terms", "Текст", "Text")
    assert p["in_footer"] is True and p["in_register"] is True and p["sort_order"] == 7
    assert p["has_uk"] is True and p["has_en"] is True and p["updated_by"] and p["updated_at"] and p["created_at"]
    assert public(anon, p["slug"]).status_code == 404                                 # a draft is not public
    row = ok(proot.get(PAGES)).json()
    mine = next(x for x in row if x["id"] == p["id"])
    assert set(mine) == LIST_KEYS                                                     # the list has no page text


@pytest.mark.plan("PLT-44")
def test_defaults_and_trimming(proot, make_page):
    token = uid(8)
    p = ok(proot.post(PAGES, json={"slug": f"  QA-{token}-Mixed  ", "title_en": "  Only English  "}), 201).json()
    try:
        assert p["slug"] == f"qa-{token}-mixed" and p["title_en"] == "Only English" and p["title_uk"] == ""
        assert p["in_footer"] is False and p["in_register"] is False and p["sort_order"] == 0
        assert p["has_uk"] is False and p["has_en"] is False and p["content_uk"] == "" and p["content_en"] == ""
    finally:
        proot.delete(f"{PAGES}/{p['id']}")


@pytest.mark.plan("PLT-44")
@pytest.mark.parametrize("slug", ["a", "", "has space", "-start", "end-", "double--dash", "UPPER_case", "under_score",
                                  "slash/inside", "ü-umlaut", "x" * 61, "dot.dot"])
def test_a_bad_address_is_refused(proot, slug):
    assert proot.post(PAGES, json={"slug": slug, "title_en": "T"}).status_code == 422


@pytest.mark.plan("PLT-44")
@pytest.mark.parametrize("shape", ["letters-digits", "with-dash", "starts-with-digits", "longest-60"])
def test_good_addresses_are_accepted(proot, shape):
    token = uid(8)
    slug = {"letters-digits": f"qa{token}", "with-dash": f"qa-{token}-x-y", "starts-with-digits": f"2026-{token}",
            "longest-60": "q" * 52 + token}[shape]
    assert 2 <= len(slug) <= 60
    page = ok(proot.post(PAGES, json={"slug": slug, "title_en": "T"}), 201).json()
    try:
        assert page["slug"] == slug
    finally:
        proot.delete(f"{PAGES}/{page['id']}")


@pytest.mark.plan("PLT-44")
def test_the_page_needs_a_title_and_unknown_fields_are_refused(proot):
    token = uid(8)
    assert proot.post(PAGES, json={"slug": f"qa-{token}-1"}).status_code == 422
    assert proot.post(PAGES, json={"slug": f"qa-{token}-1", "title_en": "   ", "title_uk": ""}).status_code == 422
    for extra in ({"status": "published"}, {"is_system": True}, {"id": 5}, {"updated_by": "x"}):
        r = proot.post(PAGES, json={"slug": f"qa-{token}-2", "title_en": "T", **extra})
        assert r.status_code == 422, extra
    assert proot.post(PAGES, json={"slug": f"qa-{token}-3", "title_en": "T" * 121}).status_code == 422
    assert proot.post(PAGES, json={"slug": f"qa-{token}-4", "title_en": "T", "content_en": "x" * 200_001}).status_code == 422
    assert proot.post(PAGES, json={"slug": f"qa-{token}-5", "title_en": "T", "sort_order": -1}).status_code == 422
    assert not [x for x in ok(proot.get(PAGES)).json() if f"qa-{token}-" in x["slug"]]    # nothing was created


@pytest.mark.plan("PLT-44")
def test_a_used_address_is_refused_also_in_other_letters(proot, make_page):
    token = uid(8)
    make_page(token, "dup")
    r = proot.post(PAGES, json={"slug": f"QA-{token}-DUP", "title_en": "Again"})
    assert r.status_code == 409 and "already" in r.json()["detail"]


@pytest.mark.plan("PLT-44")
def test_edit_one_field_the_rest_stays(proot, make_page):
    token = uid(8)
    p = make_page(token, "ed", title_uk="Заголовок", content_uk="Текст", in_footer=True, sort_order=5)
    got = ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_en": "New English text"})).json()
    assert got["content_en"] == "New English text"
    assert (got["title_uk"], got["content_uk"], got["in_footer"], got["sort_order"], got["slug"]) == \
        ("Заголовок", "Текст", True, 5, p["slug"])
    got = ok(proot.patch(f"{PAGES}/{p['id']}", json={"in_footer": False, "sort_order": 0})).json()   # false and 0 are real values
    assert got["in_footer"] is False and got["sort_order"] == 0
    got = ok(proot.patch(f"{PAGES}/{p['id']}", json={"title_uk": ""})).json()                           # one title may go
    assert got["title_uk"] == "" and got["title_en"] == "QA ed"
    assert got["status"] == "draft"                                                                     # edit never publishes


@pytest.mark.plan("PLT-44")
def test_edit_rules(proot, make_page):
    token = uid(8)
    a = make_page(token, "a")
    b = make_page(token, "b")
    r = proot.patch(f"{PAGES}/{a['id']}", json={"title_en": "", "title_uk": ""})
    assert r.status_code == 422
    assert ok(proot.get(f"{PAGES}/{a['id']}")).json()["title_en"] == "QA a"             # the failed edit changed nothing
    assert proot.patch(f"{PAGES}/{a['id']}", json={"slug": b["slug"]}).status_code == 409
    assert proot.patch(f"{PAGES}/{a['id']}", json={"slug": "Bad Slug"}).status_code == 422
    assert proot.patch(f"{PAGES}/{a['id']}", json={"status": "published"}).status_code == 422
    assert proot.patch(f"{PAGES}/{a['id']}", json={"is_system": True}).status_code == 422
    assert proot.patch(f"{PAGES}/999999", json={"title_en": "x"}).status_code == 404
    moved = ok(proot.patch(f"{PAGES}/{a['id']}", json={"slug": f"QA-{token}-Moved"})).json()
    assert moved["slug"] == f"qa-{token}-moved"
    assert proot.get(f"{PAGES}/999999").status_code == 404


@pytest.mark.plan("PLT-44")
def test_every_change_is_in_the_audit_log(proot, make_page):
    token = uid(8)
    p = make_page(token, "log", title_en="Logged")
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_en": "x", "in_footer": True}))
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"slug": f"qa-{token}-renamed"}))
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"in_footer": True}))                    # no change: no log line
    created = audit(proot, action="page_created", target=f"qa-{token}-log")["items"]
    assert len(created) == 1 and created[0]["target_type"] == "page" and created[0]["target_id"] == p["id"]
    assert created[0]["details"] == {"title": "Logged"}
    updated = audit(proot, action="page_updated", target=f"qa-{token}-")["items"]
    assert len(updated) == 2
    by_name = {row["target_name"]: row for row in updated}
    assert by_name[f"qa-{token}-log"]["details"] == {"changed": ["content_en", "in_footer"]}
    assert by_name[f"qa-{token}-renamed"]["details"] == {"changed": ["slug"], "old_slug": f"qa-{token}-log"}


# ---------------------------------------------------------------- PLT-45 publish, unpublish, public side
@pytest.mark.plan("PLT-45")
def test_publish_makes_the_page_public_and_unpublish_hides_it(proot, make_page, anon):
    token = uid(8)
    p = make_page(token, "pub", title_uk="Умови", content_uk="Український текст", title_en="Terms", content_en="English text",
                  in_footer=True)
    assert public(anon, p["slug"]).status_code == 404
    assert link_slugs(anon, token) == []
    done = publish(proot, p)
    assert done["status"] == "published"
    r = public(anon, p["slug"])
    assert r.status_code == 200
    body = r.json()
    assert set(body) == PUBLIC_KEYS                                                   # no status, no admin names
    assert (body["title_uk"], body["title_en"], body["content_uk"], body["content_en"]) == \
        ("Умови", "Terms", "Український текст", "English text")
    assert link_slugs(anon, token) == [p["slug"]]
    assert public(anon, p["slug"].upper()).status_code == 200                         # the address is not case sensitive
    assert unpublish(proot, p)["status"] == "draft"
    assert public(anon, p["slug"]).status_code == 404
    assert link_slugs(anon, token) == []
    publish(proot, p)                                                                 # and back again
    assert public(anon, p["slug"]).status_code == 200


@pytest.mark.plan("PLT-45")
def test_publish_and_unpublish_in_the_wrong_state_are_refused(proot, make_page):
    p = make_page(uid(8), "st")
    assert proot.post(f"{PAGES}/{p['id']}/unpublish").status_code == 409              # a draft is not published
    publish(proot, p)
    r = proot.post(f"{PAGES}/{p['id']}/publish")
    assert r.status_code == 409 and "already" in r.json()["detail"]
    assert proot.post(f"{PAGES}/999999/publish").status_code == 404
    assert proot.post(f"{PAGES}/999999/unpublish").status_code == 404


@pytest.mark.plan("PLT-45")
def test_a_page_without_text_cannot_be_published(proot, make_page, anon):
    token = uid(8)
    p = make_page(token, "empty", content_en="")
    r = proot.post(f"{PAGES}/{p['id']}/publish")
    assert r.status_code == 422 and "text" in r.json()["detail"]
    assert public(anon, p["slug"]).status_code == 404
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_uk": "  \n  "}))              # spaces are no text
    assert proot.post(f"{PAGES}/{p['id']}/publish").status_code == 422
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_uk": "Тільки українською"}))
    assert publish(proot, p)["status"] == "published"                                 # one language is enough
    assert public(anon, p["slug"]).json()["content_uk"] == "Тільки українською"


@pytest.mark.plan("PLT-45")
def test_editing_a_published_page_is_live_at_once(proot, make_page, anon):
    p = make_page(uid(8), "live")
    publish(proot, p)
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_en": "Fresh text", "title_en": "Fresh title"}))
    body = public(anon, p["slug"]).json()
    assert body["content_en"] == "Fresh text" and body["title_en"] == "Fresh title"
    assert ok(proot.get(f"{PAGES}/{p['id']}")).json()["status"] == "published"        # still published


@pytest.mark.plan("PLT-45")
def test_a_live_page_cannot_be_emptied(proot, make_page, anon):
    p = make_page(uid(8), "keep")
    publish(proot, p)
    r = proot.patch(f"{PAGES}/{p['id']}", json={"content_en": ""})
    assert r.status_code == 422 and "Unpublish" in r.json()["detail"]
    assert public(anon, p["slug"]).json()["content_en"] == "Text of keep"             # the text is still there
    unpublish(proot, p)
    assert ok(proot.patch(f"{PAGES}/{p['id']}", json={"content_en": ""})).json()["has_en"] is False   # a draft may be empty


@pytest.mark.plan("PLT-45")
def test_a_new_address_moves_the_public_page(proot, make_page, anon):
    token = uid(8)
    p = make_page(token, "old")
    publish(proot, p)
    new = f"qa-{token}-new"
    ok(proot.patch(f"{PAGES}/{p['id']}", json={"slug": new}))
    assert public(anon, p["slug"]).status_code == 404
    assert public(anon, new).status_code == 200


@pytest.mark.plan("PLT-45")
@pytest.mark.parametrize("slug", ["no-such-page-" + "z" * 8, "x", "../etc/passwd", "links-not", "%00"])
def test_unknown_public_addresses_are_404(anon, slug):
    assert anon.get(f"{PUBLIC}/{slug}", auth=False).status_code == 404


@pytest.mark.plan("PLT-45")
def test_the_public_side_works_with_a_bad_token_too(proot, make_page, anon):
    p = make_page(uid(8), "tok")
    publish(proot, p)
    r = anon.get(f"{PUBLIC}/{p['slug']}", headers={"Authorization": "Bearer not-a-token"}, auth=False)
    assert r.status_code == 200                                                       # public means public
    assert anon.get(f"{PUBLIC}/links", headers={"Authorization": "Bearer not-a-token"}, auth=False).status_code == 200


# ---------------------------------------------------------------- PLT-46 the footer and register-form links
@pytest.mark.plan("PLT-46")
def test_links_hold_only_published_pages_with_a_flag_in_menu_order(proot, make_page, anon):
    token = uid(8)
    third = make_page(token, "c", in_footer=True, sort_order=30)
    first = make_page(token, "a", in_footer=True, in_register=True, sort_order=10)
    second = make_page(token, "b", in_register=True, sort_order=20)
    plain = make_page(token, "d")                                                      # no flag: no link
    draft = make_page(token, "e", in_footer=True, sort_order=5)                        # never published
    same = make_page(token, "f", in_footer=True, sort_order=30)                        # same order number: older first
    for p in (third, first, second, plain, same):
        publish(proot, p)
    assert link_slugs(anon, token) == [first["slug"], second["slug"], third["slug"], same["slug"]]
    rows = {r["slug"]: r for r in ok(anon.get(f"{PUBLIC}/links", auth=False)).json() if f"qa-{token}-" in r["slug"]}
    assert set(rows[first["slug"]]) == {"slug", "title_uk", "title_en", "in_footer", "in_register"}
    assert (rows[first["slug"]]["in_footer"], rows[first["slug"]]["in_register"]) == (True, True)
    assert (rows[second["slug"]]["in_footer"], rows[second["slug"]]["in_register"]) == (False, True)
    assert (rows[third["slug"]]["in_footer"], rows[third["slug"]]["in_register"]) == (True, False)
    assert draft["slug"] not in rows and plain["slug"] not in rows


@pytest.mark.plan("PLT-46")
def test_a_changed_flag_or_order_changes_the_links_at_once(proot, make_page, anon):
    token = uid(8)
    a = make_page(token, "a", in_footer=True, sort_order=1)
    b = make_page(token, "b", in_footer=True, sort_order=2)
    publish(proot, a)
    publish(proot, b)
    assert link_slugs(anon, token) == [a["slug"], b["slug"]]
    ok(proot.patch(f"{PAGES}/{a['id']}", json={"sort_order": 9}))
    assert link_slugs(anon, token) == [b["slug"], a["slug"]]
    ok(proot.patch(f"{PAGES}/{b['id']}", json={"in_footer": False}))
    assert link_slugs(anon, token) == [a["slug"]]
    ok(proot.patch(f"{PAGES}/{a['id']}", json={"in_footer": False}))
    assert link_slugs(anon, token) == []                                                # the page is public, but has no link
    assert public(anon, a["slug"]).status_code == 200


# ---------------------------------------------------------------- PLT-47 the Donate page
@pytest.fixture
def donate(proot):
    """The system Donate page. Its text and state are put back after the test."""
    row = next(p for p in ok(proot.get(PAGES)).json() if p["slug"] == "donate")
    full = ok(proot.get(f"{PAGES}/{row['id']}")).json()
    yield full
    now = ok(proot.get(f"{PAGES}/{full['id']}")).json()
    if now["status"] == "published":
        proot.post(f"{PAGES}/{full['id']}/unpublish")
    back = {k: full[k] for k in ("title_uk", "title_en", "content_uk", "content_en", "in_footer", "in_register", "sort_order")}
    proot.patch(f"{PAGES}/{full['id']}", json=back)


@pytest.mark.plan("PLT-47")
def test_the_donate_page_exists_as_a_draft_with_the_old_text(donate, anon):
    assert donate["is_system"] is True and donate["status"] == "draft"
    assert donate["title_en"] == "Donations" and donate["title_uk"] == "Донат"
    assert donate["has_uk"] and donate["has_en"]
    for text in (donate["content_uk"], donate["content_en"]):
        assert "paypal.me" in text and "payoneer" in text.lower() and "monobank" in text.lower()
        assert "Small teams. Big things." in text
    assert public(anon, "donate").status_code == 404                                    # off until the admin publishes it


@pytest.mark.plan("PLT-47")
def test_the_donate_page_cannot_be_deleted_or_moved_but_can_be_edited_and_switched(proot, donate, anon):
    r = proot.delete(f"{PAGES}/{donate['id']}")
    assert r.status_code == 409 and "system" in r.json()["detail"].lower()
    assert proot.patch(f"{PAGES}/{donate['id']}", json={"slug": "support-us"}).status_code == 409
    ok(proot.patch(f"{PAGES}/{donate['id']}", json={"slug": "donate", "title_en": "Support us"}))   # the same address is no change
    publish(proot, donate)
    assert public(anon, "donate").json()["title_en"] == "Support us"
    assert "donate" in [r["slug"] for r in ok(anon.get(f"{PUBLIC}/links", auth=False)).json()]        # footer link is on by default
    unpublish(proot, donate)
    assert public(anon, "donate").status_code == 404
    assert ok(proot.get(f"{PAGES}/{donate['id']}")).json()["is_system"] is True


# ---------------------------------------------------------------- PLT-48 delete
@pytest.mark.plan("PLT-48")
def test_delete_removes_the_page_everywhere(proot, anon):
    token = uid(8)
    p = ok(proot.post(PAGES, json={"slug": f"qa-{token}-gone", "title_en": "Gone", "content_en": "bye", "in_footer": True}), 201).json()
    publish(proot, p)
    assert link_slugs(anon, token) == [p["slug"]]
    ok(proot.delete(f"{PAGES}/{p['id']}"), 204)
    assert proot.get(f"{PAGES}/{p['id']}").status_code == 404
    assert public(anon, p["slug"]).status_code == 404
    assert link_slugs(anon, token) == []
    assert proot.delete(f"{PAGES}/{p['id']}").status_code == 404                        # twice
    row = audit(proot, action="page_deleted", target=p["slug"])["items"][0]
    assert row["target_type"] == "page" and row["target_name"] == p["slug"]
    assert row["details"] == {"title": "Gone", "was_published": True}


@pytest.mark.plan("PLT-48")
def test_the_address_can_be_used_again_after_a_delete(proot):
    token = uid(8)
    slug = f"qa-{token}-again"
    first = ok(proot.post(PAGES, json={"slug": slug, "title_en": "One"}), 201).json()
    ok(proot.delete(f"{PAGES}/{first['id']}"), 204)
    second = ok(proot.post(PAGES, json={"slug": slug, "title_en": "Two"}), 201).json()
    try:
        assert second["title_en"] == "Two" and second["status"] == "draft"
    finally:
        proot.delete(f"{PAGES}/{second['id']}")


@pytest.mark.plan("PLT-48")
def test_publish_and_unpublish_are_in_the_audit_log(proot, make_page):
    token = uid(8)
    p = make_page(token, "aud")
    publish(proot, p)
    unpublish(proot, p)
    for action in ("page_published", "page_unpublished"):
        rows = audit(proot, action=action, target=p["slug"])["items"]
        assert len(rows) == 1 and rows[0]["target_type"] == "page" and rows[0]["target_id"] == p["id"]
        assert rows[0]["actor_name"] and rows[0]["details"] is None
