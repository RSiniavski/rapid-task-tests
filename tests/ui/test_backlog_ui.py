"""Backlog page: table, search, sorting, row click, by-milestone view; board rule; create buttons."""
import pytest
from playwright.sync_api import expect

from pages.base import Board, pick_milestone

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

DLG = ".modal-backdrop.open .modal"


def open_backlog(page, world):
    page.goto(f"/backlog.html?project={world.a.id}")
    page.wait_for_selector("[data-testid=bl-count]")
    return page


def rows(page):
    return page.locator("tr[data-key]")


def group_keys(page):
    return [s.get_attribute("data-testid").replace("bl-group-", "") for s in page.locator("section.bl-group").all()]


@pytest.fixture
def mixed(world):
    open_m = world.a.milestone(title="Alpha")
    later = world.a.milestone(title="Beta")
    closed_m = world.a.milestone(title="Old")
    a = world.a.ticket(title="Plain ticket")
    b = world.a.ticket(title="Alpha ticket", milestone_id=open_m["id"])
    c = world.a.ticket(title="Old ticket", milestone_id=closed_m["id"])
    world.a.move(c["id"], "Done")
    world.a.close_milestone(closed_m["id"])
    return {"open": open_m, "later": later, "closed": closed_m, "plain": a, "alpha": b, "old": c}


# ---------------------------------------------------------------- board rule
@pytest.mark.plan("BKL-04")
def test_board_shows_only_tickets_of_open_milestones(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    expect(b.ticket("Alpha ticket")).to_be_visible()
    expect(page.locator(".ticket-card", has_text="Plain ticket")).to_have_count(0)
    expect(page.locator(".ticket-card", has_text="Old ticket")).to_have_count(0)
    assert not page.js_errors


@pytest.mark.plan("BKL-04")
def test_board_notice_after_creating_a_ticket_without_milestone(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    Board(page).open(world.a.id)
    page.get_by_role("button", name="＋ New ticket").click()
    dlg = page.locator(DLG)
    dlg.locator("input.input").first.fill("Goes to backlog")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(page.get_by_test_id("board-notice")).to_be_visible()
    expect(page.locator(".ticket-card", has_text="Goes to backlog")).to_have_count(0)


# ---------------------------------------------------------------- list view
@pytest.mark.plan("BKL-05")
def test_backlog_lists_all_tickets_including_closed_milestones(page, login_ui, world, mixed):
    login_ui(world.roles.reporter)
    open_backlog(page, world)
    expect(rows(page)).to_have_count(3)
    expect(page.get_by_test_id("backlog-table")).to_contain_text("Old")
    assert not page.js_errors


@pytest.mark.plan("BKL-05")
def test_empty_project_shows_empty_state(page, login_ui, world):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    expect(page.get_by_test_id("bl-empty")).to_be_visible()


@pytest.mark.plan("BKL-05")
def test_row_click_opens_the_ticket_dialog_on_the_same_page(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    rows(page).filter(has_text="Plain ticket").click()
    expect(page.locator(DLG).locator(".crumb.self")).to_contain_text(mixed["plain"]["key"])
    assert "/backlog.html" in page.url


@pytest.mark.plan("BKL-06")
def test_search_by_title_and_key_and_no_matches(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    search = page.get_by_test_id("bl-search")
    search.fill("alpha")
    expect(rows(page)).to_have_count(1)
    search.fill(mixed["old"]["key"])
    expect(rows(page)).to_have_count(1)
    expect(rows(page).first).to_contain_text("Old ticket")
    search.fill("zzz-nothing")
    expect(page.get_by_test_id("bl-no-matches")).to_be_visible()
    search.fill("")
    expect(rows(page)).to_have_count(3)


@pytest.mark.plan("BKL-06")
def test_sorting_by_title_asc_desc_then_default(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    head = page.locator("th[data-col=title]")
    head.click()
    expect(page.get_by_test_id("bl-sort-title")).to_have_text("▲")
    assert rows(page).first.inner_text().find("Alpha ticket") >= 0
    head.click()
    expect(page.get_by_test_id("bl-sort-title")).to_have_text("▼")
    assert rows(page).first.inner_text().find("Plain ticket") >= 0
    head.click()
    expect(page.get_by_test_id("bl-sort-title")).to_have_count(0)


@pytest.mark.plan("BKL-06")
def test_milestone_filter_and_reset(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-filter-toggle").click()
    pk = page.locator(".label-picker:has(input[data-testid=bl-f-milestones])")
    pk.locator(".lp-input").click()
    pk.locator(".lp-list li", has_text="Alpha").first.click()
    expect(rows(page)).to_have_count(1)
    page.get_by_test_id("bl-filter-reset").click()
    expect(rows(page)).to_have_count(3)


@pytest.mark.plan("BKL-06")
def test_pagination_and_page_size(page, login_ui, world):
    for i in range(27):
        world.a.ticket(title=f"Bulk {i:02d}")
    login_ui(world.roles.admin)
    open_backlog(page, world)
    expect(rows(page)).to_have_count(27)
    expect(page.get_by_test_id("bl-pager")).to_have_count(0)   # one page: no pager
    page.evaluate(
        "id => localStorage.setItem('rt_backlog_state_' + id, JSON.stringify({pageSize: 25}))", world.a.id)
    page.reload()
    page.wait_for_selector("[data-testid=bl-count]")
    expect(page.get_by_test_id("bl-page-size")).to_have_value("25")
    expect(rows(page)).to_have_count(25)
    expect(page.get_by_test_id("bl-page")).to_contain_text("1 / 2")
    page.get_by_test_id("bl-next").click()
    expect(rows(page)).to_have_count(2)
    page.get_by_test_id("bl-page-size").select_option("100")
    expect(rows(page)).to_have_count(27)


@pytest.mark.plan("BKL-06")
def test_column_choice_is_remembered(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    expect(page.locator("th[data-col=milestone]")).to_have_count(1)
    page.get_by_test_id("bl-columns-btn").click()
    page.get_by_test_id("bl-col-milestone").uncheck()
    expect(page.locator("th[data-col=milestone]")).to_have_count(0)
    page.reload()
    page.wait_for_selector("[data-testid=bl-count]")
    expect(page.locator("th[data-col=milestone]")).to_have_count(0)


# ---------------------------------------------------------------- by milestone view
@pytest.mark.plan("BKL-07")
def test_grouped_view_order_and_no_milestone_column(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    keys = group_keys(page)
    assert keys[0] == "none"
    assert keys.index(f"m{mixed['open']['id']}") < keys.index(f"m{mixed['closed']['id']}")
    assert keys[-1] == f"m{mixed['closed']['id']}"
    assert page.locator("th[data-col=milestone]").count() == 0
    expect(page.get_by_test_id("bl-table-none")).to_contain_text("Plain ticket")
    expect(page.get_by_test_id(f"bl-table-m{mixed['open']['id']}")).to_contain_text("Alpha ticket")
    expect(page.get_by_test_id("bl-pager")).to_have_count(0)


@pytest.mark.plan("BKL-07")
def test_grouped_view_plus_creates_a_ticket_in_that_milestone(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    page.get_by_test_id(f"bl-add-m{mixed['later']['id']}").click()
    dlg = page.locator(DLG)
    expect(dlg.get_by_test_id("create-milestone-chip")).to_contain_text("Beta")
    dlg.locator("input.input").first.fill("Made in Beta")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(page.get_by_test_id(f"bl-table-m{mixed['later']['id']}")).to_contain_text("Made in Beta")


@pytest.mark.plan("BKL-07")
def test_closed_milestone_group_has_no_plus_button(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    expect(page.get_by_test_id(f"bl-add-m{mixed['closed']['id']}")).to_have_count(0)
    expect(page.get_by_test_id("bl-add-none")).to_have_count(1)


@pytest.mark.plan("BKL-07")
def test_group_can_be_collapsed_and_view_is_remembered(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    table = page.get_by_test_id("bl-table-none")
    expect(table).to_be_visible()
    page.get_by_test_id("bl-toggle-none").click()
    expect(table).to_be_hidden()
    page.reload()
    page.wait_for_selector("[data-testid=bl-count]")
    expect(page.get_by_test_id("bl-group-none")).to_be_visible()
    expect(page.get_by_test_id("bl-table-none")).to_be_hidden()
    page.get_by_test_id("bl-view-list").click()
    expect(page.get_by_test_id("backlog-table")).to_be_visible()


@pytest.mark.plan("BKL-07")
def test_grouped_view_applies_search_and_hides_empty_groups_while_filtering(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    # an open milestone without tickets is shown while nothing is filtered
    assert f"m{mixed['later']['id']}" in group_keys(page)
    page.get_by_test_id("bl-search").fill("Alpha")
    assert group_keys(page) == [f"m{mixed['open']['id']}"]


@pytest.mark.plan("BKL-07")
def test_grouped_row_click_opens_dialog(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-view-grouped").click()
    page.get_by_test_id("bl-table-none").locator("tr[data-key]").first.click()
    expect(page.locator(DLG).locator(".crumb.self")).to_contain_text(mixed["plain"]["key"])


# ---------------------------------------------------------------- create from everywhere
@pytest.mark.plan("BKL-08")
def test_backlog_new_ticket_button_creates_and_lists_the_ticket(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-new-ticket").click()
    dlg = page.locator(DLG)
    dlg.locator("input.input").first.fill("From backlog")
    pick_milestone(dlg, "Alpha")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(rows(page).filter(has_text="From backlog")).to_have_count(1)


@pytest.mark.plan("BKL-08")
def test_create_dialog_has_no_status_field(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-new-ticket").click()
    expect(page.locator(DLG).get_by_text("Status", exact=True)).to_have_count(0)


@pytest.mark.plan("BKL-08")
def test_new_ticket_starts_in_the_first_column(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_test_id("bl-new-ticket").click()
    dlg = page.locator(DLG)
    dlg.locator("input.input").first.fill("First column")
    dlg.get_by_role("button", name="Create ticket").click()
    expect(rows(page).filter(has_text="First column")).to_have_count(1)
    t = next(x for x in world.a.tickets() if x["title"] == "First column")
    assert t["column_id"] == world.a.columns["Open"]


@pytest.mark.plan("BKL-08")
def test_board_columns_have_no_plus_button(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    b = Board(page).open(world.a.id)
    assert b.column("Open").get_by_role("button", name="＋").count() == 0


@pytest.mark.plan("BKL-08")
def test_roadmap_new_ticket_button_opens_the_create_dialog(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    page.goto(f"/roadmap.html?project={world.a.id}")
    page.wait_for_selector("#rm-viewport")
    page.locator("#rm-new-ticket").click()
    expect(page.locator(DLG).get_by_role("button", name="Create ticket")).to_be_visible()


@pytest.mark.plan("BKL-08")
def test_backlog_page_navigation_links(page, login_ui, world, mixed):
    login_ui(world.roles.admin)
    open_backlog(page, world)
    page.get_by_role("link", name="Board").first.click()
    page.wait_for_url(f"**/board.html?project={world.a.id}")
