"""Platform admin tool, Overview tab in the browser (PLT-28, PLT-29)."""
import json
import re
from datetime import date, datetime, timezone

import pytest
from playwright.sync_api import expect

from framework import config
from framework.factory import create_project, ok, uid
from framework.platform_api import P, login_client

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

O = f"{P}/overview"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TYPES = ["Idea", "Epic", "Task", "Subtask", "Bug", "Incident"]
LINE_CHARTS = {"chart-new-users": "new_users", "chart-active-users": "active_users",
               "chart-new-projects": "new_projects", "chart-new-tickets": "new_tickets"}


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def api(client, days=30):
    return ok(client.get(O, params={"days": days})).json()


def n(value):
    return f"{value:,}"


def short(iso):
    d = date.fromisoformat(iso)
    return f"{d.day:02d} {MONTHS[d.month - 1]}"


def long(iso):
    return f"{short(iso)} {iso[:4]}"


def open_overview(page, plogin_ui, who, base=""):
    plogin_ui(who)
    page.goto(f"{base}/platform.html#/overview")
    expect(tid(page, "overview-page")).to_be_visible()
    expect(tid(page, "tile-users")).to_be_visible()


def own_server(plt_server):
    srv = plt_server({})
    return srv, login_client(srv.base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)


def person(make_user, tag="ou"):
    return make_user(tag=f"{tag}_", full_name=f"QA {uid(8)} {tag}")


# ---------------------------------------------------------------- PLT-28 what the page shows
@pytest.mark.plan("PLT-28")
def test_the_page_the_menu_item_and_the_default_period(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    expect(tid(page, "platform-view-title")).to_have_text("Platform Overview")
    expect(tid(page, "nav-overview")).to_have_attribute("aria-current", "page")
    expect(tid(page, "overview-period-30")).to_have_attribute("aria-checked", "true")
    expect(tid(page, "overview-period-7")).to_have_attribute("aria-checked", "false")
    expect(tid(page, "overview-updated")).to_have_text(re.compile(r"^Updated \d\d:\d\d:\d\d$"))
    for chart in list(LINE_CHARTS) + ["chart-status", "chart-type"]:
        expect(tid(page, chart)).to_have_count(1)


@pytest.mark.plan("PLT-28")
def test_the_tiles_match_the_api(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    expect(tid(page, "users-total")).to_have_text(n(o["users"]["total"]))
    for key in ("active", "blocked", "deactivated", "new"):
        expect(tid(page, f"users-{key}")).to_have_text(n(o["users"][key]))
    expect(tid(page, "projects-total")).to_have_text(n(o["projects"]["total"]))
    expect(tid(page, "projects-new")).to_have_text(n(o["projects"]["new"]))
    expect(tid(page, "projects-with-activity")).to_have_text(n(o["projects"]["with_activity"]))
    for key in ("total", "open", "created", "done"):
        expect(tid(page, f"tickets-{key}")).to_have_text(n(o["tickets"][key]))
    expect(tid(page, "activity-comments")).to_have_text(n(o["activity"]["comments"]))
    expect(tid(page, "activity-attachments")).to_have_text(n(o["activity"]["attachments"]))
    expect(tid(page, "tile-users")).to_contain_text("last 30 days")


@pytest.mark.plan("PLT-28")
def test_the_tiles_and_charts_follow_what_happens_in_the_app(page, plogin_ui, proot, make_user):
    open_overview(page, plogin_ui, proot)
    owner = person(make_user)
    project = create_project(owner)
    project.ticket(type="Bug")
    ticket = project.ticket(type="Bug")
    project.move(ticket["id"], "Done")
    ok(owner.client.post(f"/api/tickets/{ticket['id']}/comments", json={"body": "hello"}), 201)
    tid(page, "overview-refresh").click()
    o = api(proot)
    expect(tid(page, "users-total")).to_have_text(n(o["users"]["total"]))
    expect(tid(page, "projects-total")).to_have_text(n(o["projects"]["total"]))
    expect(tid(page, "tickets-total")).to_have_text(n(o["tickets"]["total"]))
    expect(tid(page, "tickets-done")).to_have_text(n(o["tickets"]["done"]))
    expect(tid(page, "activity-comments")).to_have_text(n(o["activity"]["comments"]))
    bug = page.locator("[data-testid='chart-type-row'][data-label='Bug']")
    expect(bug).to_have_attribute("data-value", str(next(x["count"] for x in o["tickets_by_type"] if x["type"] == "Bug")))
    expect(tid(page, "chart-active-users-end")).to_have_text(n(o["series"]["active_users"][-1]))


@pytest.mark.plan("PLT-28")
def test_line_charts_have_the_period_summary_and_the_first_and_last_day(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    for chart, key in LINE_CHARTS.items():
        svg = tid(page, f"{chart}-svg")
        expect(svg).to_contain_text(short(o["series"]["days"][0]))
        expect(svg).to_contain_text(short(o["series"]["days"][-1]))
    for chart, key in (("chart-new-users", "new_users"), ("chart-new-projects", "new_projects"), ("chart-new-tickets", "new_tickets")):
        expect(tid(page, f"{chart}-total")).to_have_text(f"{n(sum(o['series'][key]))} in 30 days")
    expect(tid(page, "chart-new-tickets-end")).to_have_text(n(o["series"]["new_tickets"][-1]))
    expect(tid(page, "chart-new-tickets-line")).to_have_count(1)
    assert page.locator("[data-testid='chart-new-users'] .pl-legend").count() == 0          # one series: no legend box


@pytest.mark.plan("PLT-28")
def test_the_bar_charts_show_every_type_and_the_status_columns(page, plogin_ui, proot, make_user):
    project = create_project(person(make_user))
    project.ticket()
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    rows = tid(page, "chart-type-row")
    expect(rows).to_have_count(6)
    assert [r.get_attribute("data-label") for r in rows.all()] == TYPES
    assert [int(r.get_attribute("data-value")) for r in rows.all()] == [x["count"] for x in o["tickets_by_type"]]
    for r in rows.all():
        expect(r.locator("[data-testid='bar-value']")).to_have_text(n(int(r.get_attribute("data-value"))))
    status = tid(page, "chart-status-row")
    assert sum(int(r.get_attribute("data-value")) for r in status.all()) == o["tickets"]["total"]
    expect(tid(page, "chart-status-legend").locator("li")).to_have_count(2)
    expect(tid(page, "chart-status-total")).to_contain_text(f"{n(o['tickets']['total'])} tickets")
    done = [r for r in status.all() if r.get_attribute("data-label").lower() == "done"]
    assert done and "tone-b" in done[0].locator("[data-testid='bar']").get_attribute("class")      # a done column has its own colour


@pytest.mark.plan("PLT-28")
def test_a_bar_is_as_long_as_its_value_and_never_thicker_than_24px(page, plogin_ui, proot, make_user):
    project = create_project(person(make_user))
    for _ in range(3):
        project.ticket(type="Bug")
    project.ticket(type="Epic")
    open_overview(page, plogin_ui, proot)
    bars = {r.get_attribute("data-label"): r.locator("[data-testid='bar']") for r in tid(page, "chart-type-row").all()}
    widths = {k: b.evaluate("e => e.getBoundingClientRect().width") for k, b in bars.items()}
    values = {r.get_attribute("data-label"): int(r.get_attribute("data-value")) for r in tid(page, "chart-type-row").all()}
    top = max(values, key=values.get)
    for name, value in values.items():
        if value == 0:
            assert widths[name] == 0, name                                                     # nothing to draw
        else:
            assert abs(widths[name] / widths[top] - value / values[top]) < 0.03 or widths[name] <= 3.01, name           # a very short bar is kept at 3 px, so it can be seen
    assert all(b.evaluate("e => e.getBoundingClientRect().height") <= 24 for b in bars.values())


@pytest.mark.plan("PLT-28")
def test_the_table_view_shows_every_day_and_goes_back(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    tid(page, "chart-new-tickets-toggle").click()
    expect(tid(page, "chart-new-tickets-svg")).to_have_count(0)
    expect(tid(page, "chart-new-tickets-toggle")).to_have_text("Chart")
    rows = tid(page, "chart-new-tickets-row")
    expect(rows).to_have_count(30)
    first, last = rows.first.locator("td"), rows.last.locator("td")
    expect(first.nth(0)).to_have_text(long(o["series"]["days"][0]))
    expect(last.nth(0)).to_have_text(long(o["series"]["days"][-1]))
    expect(last.nth(1)).to_have_text(n(o["series"]["new_tickets"][-1]))
    assert sum(int(c.replace(",", "")) for c in tid(page, "chart-new-tickets-row").locator("td:nth-child(2)").all_inner_texts()) == sum(o["series"]["new_tickets"])
    tid(page, "chart-new-tickets-toggle").click()
    expect(tid(page, "chart-new-tickets-svg")).to_have_count(1)
    tid(page, "chart-type-toggle").click()
    expect(tid(page, "chart-type-trow")).to_have_count(6)
    expect(tid(page, "chart-type-table")).to_contain_text("%")                                  # a share column


@pytest.mark.plan("PLT-28")
def test_active_users_tell_since_when_they_are_counted(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    since = o["activity_since"]
    assert since is not None                                                                  # the test logins are activity
    note = tid(page, "chart-active-users-note")
    if since > o["series"]["days"][0]:
        expect(note).to_have_text(f"Counted since {long(since)}.")
    else:
        expect(note).to_have_count(0)


@pytest.mark.plan("PLT-28")
def test_a_new_server_has_no_activity_yet_and_the_chart_starts_with_the_first_visit(page, plogin_ui, plt_server):
    srv, root = own_server(plt_server)
    open_overview(page, plogin_ui, root, srv.base_url)
    expect(tid(page, "chart-active-users-note")).to_have_text("No activity is saved yet. The chart fills as people use the app.")
    expect(tid(page, "chart-active-users-line")).to_have_count(0)
    expect(tid(page, "users-total")).to_have_text("0")
    expect(tid(page, "chart-status-row")).to_have_count(0)                                    # no tickets: no bars
    expect(tid(page, "chart-status")).to_contain_text("No tickets yet.")
    from framework.factory import register_user
    register_user(srv.base_url, tag="ovn_")
    tid(page, "overview-refresh").click()
    today = datetime.now(timezone.utc).date().isoformat()
    expect(tid(page, "chart-active-users-note")).to_have_text(f"Counted since {long(today)}.")
    expect(tid(page, "chart-active-users-end")).to_have_text("1")
    expect(tid(page, "users-total")).to_have_text("1")


@pytest.mark.plan("PLT-28")
@pytest.mark.parametrize("days", [7, 30, 90])
def test_the_period_buttons_change_every_number(page, plogin_ui, proot, days):
    open_overview(page, plogin_ui, proot)
    with page.expect_request(lambda r: r.url.endswith(f"/overview?days={days}")):
        if days != 30:
            tid(page, f"overview-period-{days}").click()
        else:
            tid(page, "overview-refresh").click()
    o = api(proot, days)
    expect(tid(page, f"overview-period-{days}")).to_have_attribute("aria-checked", "true")
    expect(tid(page, "tile-users")).to_contain_text(f"last {days} days")
    expect(tid(page, "users-new")).to_have_text(n(o["users"]["new"]))
    expect(tid(page, "tickets-created")).to_have_text(n(o["tickets"]["created"]))
    expect(tid(page, "chart-new-users-total")).to_have_text(f"{n(sum(o['series']['new_users']))} in {days} days")
    tid(page, "chart-new-users-toggle").click()
    expect(tid(page, "chart-new-users-row")).to_have_count(days)


@pytest.mark.plan("PLT-28")
def test_the_chosen_period_is_remembered(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    tid(page, "overview-period-90").click()
    expect(tid(page, "chart-new-users-total")).to_contain_text("in 90 days")
    page.reload()
    expect(tid(page, "overview-period-90")).to_have_attribute("aria-checked", "true")
    expect(tid(page, "chart-new-users-total")).to_contain_text("in 90 days")


# ---------------------------------------------------------------- PLT-29 hover, keyboard, errors, permission
@pytest.mark.plan("PLT-29")
def test_the_tooltip_follows_the_keyboard_and_shows_the_api_values(page, plogin_ui, proot, make_user):
    project = create_project(person(make_user))
    project.ticket()
    open_overview(page, plogin_ui, proot)
    o = api(proot)
    series = o["series"]["new_tickets"]
    svg = tid(page, "chart-new-tickets-svg")
    svg.scroll_into_view_if_needed()
    svg.focus()
    page.keyboard.press("ArrowLeft")                                                           # the last day
    tip = tid(page, "chart-new-tickets-tip")
    expect(tip).to_be_visible()
    expect(tip.locator("[data-testid='tip-value']")).to_have_text(n(series[-1]))
    expect(tip.locator("[data-testid='tip-date']")).to_have_text(long(o["series"]["days"][-1]))
    page.keyboard.press("ArrowLeft")                                                           # the day before
    expect(tip.locator("[data-testid='tip-value']")).to_have_text(n(series[-2]))
    expect(tip.locator("[data-testid='tip-date']")).to_have_text(long(o["series"]["days"][-2]))
    page.keyboard.press("Escape")
    expect(tip).to_have_count(0)


@pytest.mark.plan("PLT-29")
def test_the_tooltip_follows_the_mouse_and_goes_away(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    svg = tid(page, "chart-new-users-svg")
    svg.scroll_into_view_if_needed()
    box = svg.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    tip = tid(page, "chart-new-users-tip")
    expect(tip).to_be_visible()
    expect(tip.locator("[data-testid='tip-value']")).to_have_text(re.compile(r"^[\d,]+$"))
    expect(tip.locator("[data-testid='tip-date']")).to_have_text(re.compile(r"^\d\d \w{3} \d{4}$"))
    expect(svg.locator(".pl-cross")).to_have_count(1)                                          # the crosshair
    page.mouse.move(2, 2)
    expect(tip).to_have_count(0)


@pytest.mark.plan("PLT-29")
def test_a_bar_shows_its_value_name_and_share_on_hover(page, plogin_ui, proot, make_user):
    project = create_project(person(make_user))
    project.ticket(type="Bug")
    open_overview(page, plogin_ui, proot)
    row = page.locator("[data-testid='chart-type-row'][data-label='Bug']")
    row.scroll_into_view_if_needed()
    tip = row.locator("[data-testid='bar-tip']")
    expect(tip).to_be_hidden()
    row.hover()
    expect(tip).to_be_visible()
    expect(tip).to_contain_text("tickets")
    expect(tip).to_contain_text("Bug")
    expect(tip).to_contain_text("%")
    page.mouse.move(2, 2)
    expect(tip).to_be_hidden()


@pytest.mark.plan("PLT-29")
def test_a_failed_refresh_keeps_the_old_numbers_and_says_so(page, plogin_ui, proot):
    open_overview(page, plogin_ui, proot)
    before = tid(page, "users-total").inner_text()
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route("**/api/platform/overview?*", handler)
    tid(page, "overview-refresh").click()
    expect(tid(page, "overview-error")).to_contain_text("Something broke")
    expect(tid(page, "users-total")).to_have_text(before)
    state["fail"] = False
    tid(page, "overview-refresh").click()
    expect(tid(page, "overview-error")).to_have_count(0)


@pytest.mark.plan("PLT-29")
def test_a_first_load_error_has_try_again(page, plogin_ui, proot):
    plogin_ui(proot)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Something broke"}))
        else:
            route.continue_()

    page.route("**/api/platform/overview?*", handler)
    page.goto("/platform.html#/overview")
    expect(tid(page, "overview-error")).to_contain_text("Something broke")
    expect(tid(page, "tile-users")).to_have_count(0)
    state["fail"] = False
    tid(page, "overview-retry").click()
    expect(tid(page, "tile-users")).to_be_visible()


@pytest.mark.plan("PLT-29")
def test_an_admin_with_analytics_works(page, plogin_ui, padmin):
    a = padmin("oa1", can_view_analytics=True)
    open_overview(page, plogin_ui, a)
    assert page.locator("a[data-testid^='nav-']").count() == 1                                 # Overview; Project Insights is not built yet
    expect(tid(page, "nav-overview")).to_be_visible()


@pytest.mark.plan("PLT-29")
def test_an_admin_without_analytics_is_sent_to_my_account(page, plogin_ui, padmin):
    plain = padmin("oa2", can_view_audit_logs=True)
    plogin_ui(plain)
    page.goto("/platform.html#/overview")
    expect(tid(page, "platform-account")).to_be_visible()
    expect(tid(page, "nav-overview")).to_have_count(0)
    expect(tid(page, "overview-page")).to_have_count(0)
