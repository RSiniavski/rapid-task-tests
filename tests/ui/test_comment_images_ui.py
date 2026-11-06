"""Images and files pasted or dropped into comments and into the description (IMG-04 .. IMG-06)."""
import pytest
from playwright.sync_api import expect

from framework.factory import ok
from pages.base import Board
from tests.api.test_comment_images_api import paste as api_paste

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
NEW = "comment-editor"
EDIT = "comment-edit-editor"
DLG = ".modal-backdrop.open .modal"


def open_ticket_page(page, key):
    page.goto(f"/ticket.html?key={key}")
    page.wait_for_selector(".tk-page-card, [data-testid=ticket-page-error]")
    expect(page.get_by_test_id("ticket-activity")).to_be_visible()


def put(page, testid, files, how="paste"):
    """Paste (or drop) files into an editor. files = [(name, mime)]; every file holds the bytes of a tiny PNG."""
    page.evaluate("""([sel, files, b64, how]) => {
      const el = document.querySelector(sel);
      el.focus();
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const dt = new DataTransfer();
      for (const [name, mime] of files) dt.items.add(new File([bytes], name, {type: mime}));
      const ev = how === "paste"
        ? new ClipboardEvent("paste", {clipboardData: dt, bubbles: true, cancelable: true})
        : new DragEvent("drop", {dataTransfer: dt, bubbles: true, cancelable: true});
      el.dispatchEvent(ev);
    }""", [f"[data-testid={testid}]", files, PNG_B64, how])


def editor(page, testid=NEW):
    return page.locator(f"[data-testid={testid}]")


def ticket_files(world, ticket):
    return ok(world.client("admin").get(f"/api/tickets/{ticket['id']}")).json()["attachments"]


def image_is_shown(page, selector):
    """The picture is really loaded from the server (not a broken image)."""
    page.wait_for_function(f"(() => {{ const i = document.querySelector({selector!r}); return !!i && i.complete && i.naturalWidth > 0; }})()")


@pytest.fixture
def ticket(world, on_board):
    return world.a.ticket(title="Look at the picture")


def comment_with_image(world, ticket, who="reporter"):
    """A comment of `who` that holds an uploaded image (made through the API)."""
    c = world.client(who)
    a = ok(api_paste(c, world.a.id, ticket["id"], "shot.png"), 201).json()
    ok(c.post(f"/api/tickets/{ticket['id']}/comments", json={"body": f"Here:\n\n![shot.png]({a['url']})"}), 201)
    return a


# ---------------------------------------------------------------- IMG-04 paste and drop into a comment
@pytest.mark.plan("IMG-04")
@pytest.mark.parametrize("role", ["admin", "contributor", "reporter"])
def test_a_pasted_image_is_shown_in_the_comment_and_is_a_ticket_attachment(page, login_ui, world, ticket, role):
    login_ui(world.roles.by_name(role))
    open_ticket_page(page, ticket["key"])
    put(page, NEW, [("image.png", "image/png")])
    expect(editor(page).locator("img")).to_have_count(1)
    expect(page.get_by_test_id("comment-uploading")).to_have_count(0)
    expect(page.get_by_test_id("comment-send")).to_be_enabled()
    page.get_by_test_id("comment-send").click()
    body = page.get_by_test_id("comment-body").first
    expect(body.locator("img.desc-media")).to_have_count(1)
    assert body.locator("img.desc-media").get_attribute("src").startswith("/uploads/")
    image_is_shown(page, "[data-testid=comment-body] img.desc-media")
    expect(page.locator(".attach-thumb")).to_have_count(1)                          # also in the ticket Attachments
    files = ticket_files(world, ticket)
    assert len(files) == 1 and files[0]["kind"] == "image" and files[0]["filename"] == "image.png"
    assert files[0]["uploader_id"] == world.roles.by_name(role).id


@pytest.mark.plan("IMG-04")
def test_a_dropped_image_works_like_a_pasted_one(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    put(page, NEW, [("dropped.png", "image/png")], how="drop")
    expect(editor(page).locator("img")).to_have_count(1)
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment-body").first.locator("img.desc-media")).to_have_count(1)
    assert [f["filename"] for f in ticket_files(world, ticket)] == ["dropped.png"]


@pytest.mark.plan("IMG-04")
def test_a_log_file_becomes_a_link_that_downloads(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    put(page, NEW, [("run.log", "text/plain")])
    expect(editor(page).locator("a.desc-file")).to_have_count(1)
    expect(editor(page).locator("img")).to_have_count(0)
    page.get_by_test_id("comment-send").click()
    link = page.get_by_test_id("comment-body").first.locator("a.desc-file")
    expect(link).to_have_count(1)
    assert "run.log" in link.inner_text()
    href = link.get_attribute("href")
    assert href.startswith("/uploads/") and href.endswith(".log")
    r = page.request.get(href)
    assert r.status == 200 and r.headers["content-disposition"].startswith("attachment")
    files = ticket_files(world, ticket)
    assert len(files) == 1 and files[0]["kind"] == "file" and files[0]["filename"] == "run.log"


@pytest.mark.plan("IMG-04")
def test_an_image_and_a_file_together(page, login_ui, world, ticket):
    login_ui(world.roles.editor)
    open_ticket_page(page, ticket["key"])
    put(page, NEW, [("a.png", "image/png"), ("b.pdf", "application/pdf")])
    expect(editor(page).locator("img")).to_have_count(1)
    expect(editor(page).locator("a.desc-file")).to_have_count(1)
    page.get_by_test_id("comment-send").click()
    body = page.get_by_test_id("comment-body").first
    expect(body.locator("img.desc-media")).to_have_count(1)
    expect(body.locator("a.desc-file")).to_have_count(1)
    assert sorted(f["filename"] for f in ticket_files(world, ticket)) == ["a.png", "b.pdf"]


@pytest.mark.plan("IMG-04")
def test_paste_into_the_editor_of_an_edited_comment(page, login_ui, world, ticket):
    me = world.roles.reporter
    ok(me.client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "first"}), 201)
    login_ui(me)
    open_ticket_page(page, ticket["key"])
    page.get_by_test_id("comment-edit").click()
    expect(editor(page, EDIT)).to_be_visible()
    put(page, EDIT, [("later.png", "image/png")])
    expect(editor(page, EDIT).locator("img")).to_have_count(1)
    page.get_by_test_id("comment-edit-save").click()
    body = page.get_by_test_id("comment-body").first
    expect(body.locator("img.desc-media")).to_have_count(1)
    expect(body).to_contain_text("first")
    expect(page.get_by_test_id("comment-edited")).to_be_visible()


# ---------------------------------------------------------------- IMG-05 big view
@pytest.mark.plan("IMG-05")
def test_a_click_on_the_image_opens_the_big_view_and_it_closes_three_ways(page, login_ui, world, ticket):
    a = comment_with_image(world, ticket)
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    img = page.get_by_test_id("comment-body").first.locator("img.desc-media")
    box = page.get_by_test_id("image-lightbox")
    expect(box).to_have_count(0)
    img.click()
    expect(box).to_be_visible()
    assert page.get_by_test_id("image-lightbox-img").get_attribute("src") == a["url"]
    page.keyboard.press("Escape")                                                    # 1: Esc
    expect(box).to_have_count(0)
    img.click()
    expect(box).to_be_visible()
    box.click(position={"x": 8, "y": 8})                                             # 2: a click on the dark background
    expect(box).to_have_count(0)
    img.click()
    page.get_by_test_id("image-lightbox-close").click()                              # 3: the close button
    expect(box).to_have_count(0)
    expect(page.get_by_test_id("ticket-activity")).to_be_visible()


@pytest.mark.plan("IMG-05")
def test_a_picture_in_the_editor_does_not_open_the_big_view(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    put(page, NEW, [("image.png", "image/png")])
    expect(editor(page).locator("img")).to_have_count(1)
    editor(page).locator("img").click()
    page.wait_for_timeout(300)
    expect(page.get_by_test_id("image-lightbox")).to_have_count(0)


@pytest.mark.plan("IMG-05")
def test_escape_closes_only_the_big_view_not_the_ticket_window(page, login_ui, world, ticket):
    comment_with_image(world, ticket)
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_text(ticket["title"]).first.click()
    expect(page.locator(DLG)).to_be_visible()
    page.get_by_test_id("comment-body").first.locator("img.desc-media").click()
    expect(page.get_by_test_id("image-lightbox")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("image-lightbox")).to_have_count(0)
    expect(page.locator(DLG)).to_be_visible()                                         # the ticket window stays open


# ---------------------------------------------------------------- IMG-06 errors and the description
@pytest.mark.plan("IMG-06")
def test_a_refused_upload_shows_the_error_and_the_comment_still_works(page, login_ui, world, ticket):
    login_ui(world.roles.reporter)
    open_ticket_page(page, ticket["key"])
    page.route("**/api/attachments?*", lambda route: route.fulfill(
        status=413, content_type="application/json", body='{"detail": "File is too large (max 25 MB)"}'))
    put(page, NEW, [("huge.png", "image/png")])
    expect(page.get_by_test_id("comment-error")).to_have_text("File is too large (max 25 MB)")
    expect(editor(page).locator("img")).to_have_count(0)
    expect(page.get_by_test_id("comment-uploading")).to_have_count(0)
    page.unroute("**/api/attachments?*")
    editor(page).click()
    page.keyboard.type("only text")
    page.get_by_test_id("comment-send").click()
    expect(page.get_by_test_id("comment-body").first).to_have_text("only text")
    assert ticket_files(world, ticket) == []


@pytest.mark.plan("IMG-06")
def test_a_file_pasted_into_the_description_gets_a_link_and_one_attachment(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.locator(".desc-view").first.click()
    expect(page.get_by_test_id("desc-editor")).to_be_visible()
    put(page, "desc-editor", [("trace.log", "text/plain")])
    expect(page.get_by_test_id("desc-editor").locator("a.desc-file")).to_have_count(1)
    page.wait_for_timeout(500)                                                        # a double upload would be visible by now
    files = ticket_files(world, ticket)
    assert [f["filename"] for f in files] == ["trace.log"]
    expect(page.locator(".attach-thumb")).to_have_count(1)


@pytest.mark.plan("IMG-06")
def test_the_attach_button_does_not_write_into_the_description(page, login_ui, world, ticket):
    login_ui(world.roles.admin)
    open_ticket_page(page, ticket["key"])
    page.locator("input[type=file]").first.set_input_files(
        files=[{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello"}])
    expect(page.locator(".attach-thumb")).to_have_count(1)
    assert ticket_files(world, ticket)[0]["filename"] == "notes.txt"
    expect(page.locator(".desc-view a.desc-file")).to_have_count(0)                   # nothing in the text
