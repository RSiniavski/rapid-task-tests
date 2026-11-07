"""Platform admin tool, Pages tab in the browser (PLT-49 .. PLT-58): list, editor, publish, delete, links, security.
The shared test server has other pages, so every test makes its own pages (slug qa-<token>-...) and deletes them."""
import re

import pytest
from playwright.sync_api import expect

from framework.factory import ok, uid
from framework.platform_api import P

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

PAGES = f"{P}/pages"
PUBLIC = "/api/pages"


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def row(page, slug):
    return page.locator(f"[data-testid='page-row'][data-slug='{slug}']")


def nav_ids(page):
    return page.eval_on_selector_all("[data-testid^='nav-']", "els => els.map(e => e.dataset.testid)")


def open_pages(page, plogin_ui, who):
    plogin_ui(who)
    page.goto("/platform.html#/pages")
    expect(tid(page, "pages-page")).to_be_visible()
    expect(tid(page, "pages-loading")).to_have_count(0)


def edit(page, slug):
    row(page, slug).locator("[data-testid='page-edit']").click()
    expect(tid(page, "page-form")).to_be_visible()


def type_into(page, lang, text, replace=False):
    box = tid(page, f"page-editor-{lang}")
    box.click()
    if replace:
        page.keyboard.press("Control+A")
    page.keyboard.type(text)


def full(proot, slug):
    """The whole page (with the texts) from the platform API, or None."""
    for p in ok(proot.get(PAGES)).json():
        if p["slug"] == slug:
            return ok(proot.get(f"{PAGES}/{p['id']}")).json()
    return None


def public(anon, slug):
    return anon.get(f"{PUBLIC}/{slug}", auth=False)


@pytest.fixture
def make_page(proot):
    """make_page(token, label, publish=False, **fields) -> page dict. All pages of the test are deleted after it."""
    slugs = []

    def make(token, label="p", publish=False, **fields):
        body = {"slug": f"qa-{token}-{label}", "title_en": f"QA {label}", "content_en": f"Text of {label}"}
        body.update(fields)
        page = ok(proot.post(PAGES, json=body), 201).json()
        slugs.append(page["slug"])
        if publish:
            page = ok(proot.post(f"{PAGES}/{page['id']}/publish")).json()
        return page

    make.slugs = slugs
    yield make
    for slug in slugs:
        gone = full(proot, slug)
        if gone:
            proot.delete(f"{PAGES}/{gone['id']}")


# ---------------------------------------------------------------- PLT-49 who sees the tab
@pytest.mark.plan("PLT-49")
def test_the_root_sees_the_pages_tab_with_the_system_donate_page(page, plogin_ui, proot):
    open_pages(page, plogin_ui, proot)
    expect(tid(page, "platform-view-title")).to_have_text("Pages")
    expect(tid(page, "nav-pages")).to_have_attribute("aria-current", "page")
    donate = row(page, "donate")
    expect(donate).to_have_count(1)
    expect(donate.locator("[data-testid='page-system']")).to_have_count(1)
    expect(donate.locator("[data-testid='page-delete']")).to_have_count(0)          # a system page is never deleted
    expect(donate.locator("[data-testid='page-edit']")).to_have_count(1)
    assert page.js_errors == []


@pytest.mark.plan("PLT-49")
def test_an_admin_with_only_the_pages_permission_sees_only_this_tab(page, plogin_ui, padmin):
    a = padmin("pu1", can_manage_pages=True)
    open_pages(page, plogin_ui, a)
    assert nav_ids(page) == ["nav-pages"]
    expect(tid(page, "platform-perm-count")).to_contain_text("1 of 6")


@pytest.mark.plan("PLT-49")
def test_without_the_permission_there_is_no_tab_and_the_route_shows_the_account(page, plogin_ui, padmin):
    a = padmin("pu2", can_manage_users=True)
    plogin_ui(a)
    page.goto("/platform.html#/pages")
    expect(tid(page, "platform-view-title")).to_have_text("My account")
    assert tid(page, "nav-pages").count() == 0 and tid(page, "pages-page").count() == 0


# ---------------------------------------------------------------- PLT-50 create, save, publish
@pytest.mark.plan("PLT-50")
def test_create_a_page_in_the_editor_save_it_and_publish_it(page, plogin_ui, proot, anon, make_page):
    token = uid(8)
    slug = f"qa-{token}-new"
    make_page.slugs.append(slug)                                                    # deleted after the test
    open_pages(page, plogin_ui, proot)
    tid(page, "page-new").click()
    expect(tid(page, "page-save")).to_be_disabled()
    tid(page, "page-slug-input").fill(slug)
    tid(page, "page-title-uk").fill("Умови QA")
    tid(page, "page-title-en").fill("QA terms")
    type_into(page, "uk", "# Заголовок")
    page.keyboard.press("Enter")
    page.keyboard.type("Текст **жирний**")
    tid(page, "page-lang-en").click()
    type_into(page, "en", "English text")
    tid(page, "page-in-footer").check()
    expect(tid(page, "page-dirty")).to_be_visible()
    tid(page, "page-save").click()
    expect(tid(page, "page-dirty")).to_have_count(0)
    saved = full(proot, slug)
    assert saved["status"] == "draft" and saved["in_footer"] is True and saved["in_register"] is False
    assert saved["title_uk"] == "Умови QA" and saved["title_en"] == "QA terms"
    assert saved["content_uk"].startswith("# Заголовок") and "**жирний**" in saved["content_uk"]     # saved as Markdown
    assert saved["content_en"].strip() == "English text"
    assert public(anon, slug).status_code == 404                                    # a draft is not public
    tid(page, "page-form-toggle").click()
    expect(tid(page, "page-form-status")).to_have_text("Published")
    got = ok(public(anon, slug)).json()
    assert got["title_en"] == "QA terms" and got["content_en"].strip() == "English text"
    page.goto(f"/p/{slug}")
    expect(tid(page, "page-title")).to_have_text("QA terms")
    expect(tid(page, "page-body")).to_contain_text("English text")


# ---------------------------------------------------------------- PLT-51 a published page changes at once
@pytest.mark.plan("PLT-51")
def test_saving_a_published_page_is_live_at_once_and_unpublish_hides_it(page, plogin_ui, proot, anon, make_page):
    p = make_page(uid(8), "live", publish=True, content_en="Old text")
    open_pages(page, plogin_ui, proot)
    expect(row(page, p["slug"])).to_have_attribute("data-status", "published")
    edit(page, p["slug"])
    tid(page, "page-lang-en").click()
    type_into(page, "en", "New text", replace=True)
    tid(page, "page-save").click()
    expect(tid(page, "page-dirty")).to_have_count(0)
    assert ok(public(anon, p["slug"])).json()["content_en"].strip() == "New text"           # no extra publish step
    expect(tid(page, "page-form-toggle")).to_have_text("Unpublish")
    tid(page, "page-form-toggle").click()
    expect(tid(page, "page-form-status")).to_have_text("Draft")
    assert public(anon, p["slug"]).status_code == 404
    tid(page, "page-back").click()
    expect(row(page, p["slug"])).to_have_attribute("data-status", "draft")


@pytest.mark.plan("PLT-51")
def test_quick_publish_and_unpublish_buttons_in_the_list(page, plogin_ui, proot, anon, make_page):
    p = make_page(uid(8), "quick")
    open_pages(page, plogin_ui, proot)
    row(page, p["slug"]).locator("[data-testid='page-publish']").click()
    expect(row(page, p["slug"])).to_have_attribute("data-status", "published")
    assert public(anon, p["slug"]).status_code == 200
    row(page, p["slug"]).locator("[data-testid='page-unpublish']").click()
    expect(row(page, p["slug"])).to_have_attribute("data-status", "draft")
    assert public(anon, p["slug"]).status_code == 404


# ---------------------------------------------------------------- PLT-52 two languages and the preview
@pytest.mark.plan("PLT-52")
def test_each_language_has_its_own_text_and_the_preview_follows_the_tab(page, plogin_ui, proot, make_page):
    p = make_page(uid(8), "lang", title_uk="Назва", content_uk="Український **текст**", content_en="")
    open_pages(page, plogin_ui, proot)
    expect(row(page, p["slug"]).locator("[data-testid='page-has-uk']")).to_have_class(re.compile(r"\bok\b"))
    expect(row(page, p["slug"]).locator("[data-testid='page-has-en']")).to_have_class(re.compile(r"\bwarn\b"))
    edit(page, p["slug"])
    expect(tid(page, "page-editor-uk")).to_contain_text("Український текст")
    tid(page, "page-lang-en").click()
    expect(tid(page, "page-editor-en")).to_be_visible()
    expect(tid(page, "page-editor-uk")).to_be_hidden()
    expect(tid(page, "page-editor-en")).not_to_contain_text("Український")
    tid(page, "page-lang-uk").click()
    tid(page, "page-preview-toggle").click()
    expect(tid(page, "page-preview")).to_contain_text("Український текст")
    expect(tid(page, "page-preview").locator("strong")).to_have_text("текст")
    tid(page, "page-lang-en").click()
    expect(tid(page, "page-preview")).not_to_contain_text("Український")
    expect(tid(page, "page-editor-en")).to_be_hidden()                              # the preview replaces the editor


@pytest.mark.plan("PLT-52")
def test_an_empty_language_shows_the_other_language_on_the_public_page(page, plogin_ui, proot, make_page):
    p = make_page(uid(8), "fb", publish=True, title_en="Only English", content_en="English **only**")
    plogin_ui(proot)
    page.goto("/")
    page.evaluate("localStorage.setItem('rt_lang', 'uk')")
    page.goto(f"/p/{p['slug']}")
    expect(tid(page, "page-title")).to_have_text("Only English")
    expect(tid(page, "page-body")).to_contain_text("English only")


# ---------------------------------------------------------------- PLT-53 delete
@pytest.mark.plan("PLT-53")
def test_delete_asks_first_cancel_keeps_the_page_confirm_removes_it(page, plogin_ui, proot, anon, make_page):
    p = make_page(uid(8), "del", publish=True)
    open_pages(page, plogin_ui, proot)
    row(page, p["slug"]).locator("[data-testid='page-delete']").click()
    expect(tid(page, "page-target")).to_have_text("QA del")
    tid(page, "page-modal-cancel").click()
    expect(tid(page, "page-modal")).to_have_count(0)
    expect(row(page, p["slug"])).to_have_count(1)
    row(page, p["slug"]).locator("[data-testid='page-delete']").click()
    tid(page, "page-modal-confirm").click()
    expect(row(page, p["slug"])).to_have_count(0)
    assert public(anon, p["slug"]).status_code == 404 and full(proot, p["slug"]) is None


@pytest.mark.plan("PLT-53")
def test_the_delete_dialog_does_not_close_when_the_mouse_is_released_outside(page, plogin_ui, proot, make_page):
    p = make_page(uid(8), "drag")
    open_pages(page, plogin_ui, proot)
    row(page, p["slug"]).locator("[data-testid='page-delete']").click()
    box = tid(page, "page-modal").bounding_box()
    page.mouse.move(box["x"] + 40, box["y"] + 40)
    page.mouse.down()
    page.mouse.move(5, 5)
    page.mouse.up()
    expect(tid(page, "page-modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(tid(page, "page-modal")).to_have_count(0)


@pytest.mark.plan("PLT-53")
def test_a_system_page_has_a_fixed_address_and_no_delete_in_the_editor(page, plogin_ui, proot):
    open_pages(page, plogin_ui, proot)
    edit(page, "donate")
    expect(tid(page, "page-slug-input")).to_be_disabled()
    expect(tid(page, "page-slug-input")).to_have_value("donate")
    expect(tid(page, "page-form-delete")).to_have_count(0)


# ---------------------------------------------------------------- PLT-54 links in the footer and the register form
@pytest.mark.plan("PLT-54")
def test_footer_and_register_links_follow_the_checkboxes(page, plogin_ui, proot, make_page):
    token = uid(8)
    shown = make_page(token, "lnk", publish=True, in_footer=True, in_register=True)
    hidden = make_page(token, "drf", in_footer=True, in_register=True)                # a draft: no links
    plogin_ui(proot)
    page.goto("/")
    footer = lambda slug: page.locator(f"[data-site-links='footer'] a[data-slug='{slug}']")
    expect(footer(shown["slug"])).to_have_count(1)
    expect(footer(hidden["slug"])).to_have_count(0)
    page.locator("[data-open-auth='register']").first.click()
    reg = lambda slug: page.locator(f"#form-register a[data-slug='{slug}']")
    expect(reg(shown["slug"])).to_have_count(1)
    expect(reg(shown["slug"])).to_have_attribute("target", "_blank")                  # the form stays open
    expect(reg(hidden["slug"])).to_have_count(0)
    open_pages(page, plogin_ui, proot)
    edit(page, shown["slug"])
    tid(page, "page-in-footer").uncheck()
    tid(page, "page-in-register").uncheck()
    tid(page, "page-save").click()
    expect(tid(page, "page-dirty")).to_have_count(0)
    page.goto("/")
    expect(page.locator(f"[data-site-links] a[data-slug='{shown['slug']}']")).to_have_count(0)


# ---------------------------------------------------------------- PLT-55 errors and unsaved changes
@pytest.mark.plan("PLT-55")
def test_a_used_address_and_a_bad_address_are_refused(page, plogin_ui, proot, make_page):
    p = make_page(uid(8), "dup")
    open_pages(page, plogin_ui, proot)
    tid(page, "page-new").click()
    tid(page, "page-title-en").fill("Copy")
    tid(page, "page-slug-input").fill("a")
    expect(tid(page, "page-save")).to_be_disabled()                                  # too short
    tid(page, "page-slug-input").fill("Bad Address!")
    expect(tid(page, "page-save")).to_be_disabled()
    tid(page, "page-slug-input").fill(p["slug"])
    tid(page, "page-save").click()
    expect(tid(page, "page-form-error")).to_contain_text("already used")
    expect(tid(page, "page-form")).to_be_visible()


@pytest.mark.plan("PLT-55")
def test_leaving_the_editor_with_unsaved_changes_asks_first(page, plogin_ui, proot, make_page):
    p = make_page(uid(8), "leave")
    open_pages(page, plogin_ui, proot)
    edit(page, p["slug"])
    tid(page, "page-title-en").fill("Changed title")
    expect(tid(page, "page-dirty")).to_be_visible()
    page.dialog_policy = "dismiss"
    tid(page, "page-back").click()
    assert len(page.dialogs) == 1
    expect(tid(page, "page-form")).to_be_visible()                                    # stayed
    page.dialog_policy = "accept"
    tid(page, "page-back").click()
    expect(tid(page, "pages-table")).to_be_visible()
    assert full(proot, p["slug"])["title_en"] == "QA leave"                           # nothing was saved


# ---------------------------------------------------------------- PLT-56 audit log
@pytest.mark.plan("PLT-56")
def test_page_actions_are_readable_in_the_audit_log(page, plogin_ui, proot):
    slug = f"qa-{uid(8)}-aud"
    created = ok(proot.post(PAGES, json={"slug": slug, "title_en": "Audit me", "content_en": "x"}), 201).json()
    ok(proot.patch(f"{PAGES}/{created['id']}", json={"title_en": "Audit me 2"}))
    ok(proot.post(f"{PAGES}/{created['id']}/publish"))
    ok(proot.post(f"{PAGES}/{created['id']}/unpublish"))
    ok(proot.delete(f"{PAGES}/{created['id']}"), 204)
    plogin_ui(proot)
    page.goto("/platform.html#/audit")
    expect(tid(page, "audit-page")).to_be_visible()
    tid(page, "audit-target").fill(slug)
    rows = page.locator("[data-testid='audit-row']")
    expect(rows).to_have_count(5)
    assert page.eval_on_selector_all("[data-testid='audit-row']", "els => els.map(e => e.dataset.action)") == [
        "page_deleted", "page_unpublished", "page_published", "page_updated", "page_created"]
    labels = [rows.nth(i).locator("[data-testid='audit-action-pill']").inner_text() for i in range(5)]
    assert labels == ["Page deleted", "Page unpublished", "Page published", "Page changed", "Page created"]
    expect(rows.nth(4).locator("[data-testid='audit-details']")).to_contain_text("Audit me")


# ---------------------------------------------------------------- PLT-57 text is text
@pytest.mark.plan("PLT-57")
@pytest.mark.security
def test_html_in_titles_and_texts_is_never_run(page, plogin_ui, proot, make_page):
    evil = "<img src=x onerror=window.__x=1>"
    p = make_page(uid(8), "xss", publish=True, title_en=evil,
                  content_en="Hello <script>window.__x=2</script> **bold**\n\n<img src=x onerror=window.__x=3>\n\n[bad](javascript:window.__x=4)")
    open_pages(page, plogin_ui, proot)
    expect(row(page, p["slug"]).locator("[data-testid='page-title']")).to_have_text(evil)
    edit(page, p["slug"])
    tid(page, "page-lang-en").click()                                               # the text is English only
    tid(page, "page-preview-toggle").click()
    expect(tid(page, "page-preview")).to_contain_text("bold")
    assert tid(page, "page-preview").locator("script, img").count() == 0
    page.goto(f"/p/{p['slug']}")
    expect(tid(page, "page-title")).to_have_text(evil)
    expect(tid(page, "page-body")).to_contain_text("bold")
    assert tid(page, "page-body").locator("script, img").count() == 0
    assert tid(page, "page-body").locator("a[href^='javascript']").count() == 0
    assert page.evaluate("window.__x") is None


# ---------------------------------------------------------------- PLT-58 the old Donate page
@pytest.mark.plan("PLT-58")
def test_the_old_donate_address_goes_to_the_new_page_and_the_support_section_follows_the_state(page, anon_ui):
    anon_ui("en")
    page.goto("/donate.html")
    expect(page).to_have_url(re.compile(r"/p/donate$"))
    page.goto("/")
    expect(page.locator("#support")).to_be_hidden()                                  # Donate is a draft: nothing to show


@pytest.mark.plan("PLT-58")
def test_a_published_donate_page_shows_the_support_section_and_the_page(page, anon_ui, donate_live):
    anon_ui("en")
    page.goto("/")
    expect(page.locator("#support")).to_be_visible()
    button = page.locator("#support a[href='/p/donate']")
    expect(button).to_have_attribute("target", "_blank")
    page.goto("/donate.html")
    expect(page).to_have_url(re.compile(r"/p/donate$"))
    expect(tid(page, "page-title")).to_have_text("Donations")
