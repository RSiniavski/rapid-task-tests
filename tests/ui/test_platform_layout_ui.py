"""Platform admin tool: movable and resizable tiles on Overview and System Health (PLT-30 .. PLT-33).

The layout is kept in this browser only (localStorage), so no API is involved here."""
import json

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.ui, pytest.mark.needs_vue]

OVERVIEW_ITEMS = ["tile-users", "tile-projects", "tile-tickets", "tile-activity", "chart-new-users", "chart-active-users",
                  "chart-new-projects", "chart-new-tickets", "chart-status", "chart-type"]
HEALTH_ITEMS = ["server", "databases", "disk", "counts", "load", "errors"]
KEY = {"overview": "rt_platform_layout_overview", "health": "rt_platform_layout_health"}


def tid(page, name):
    return page.locator(f"[data-testid='{name}']")


def item(page, name):
    return tid(page, f"item-{name}")


def open_page(page, plogin_ui, who, route="overview", width=1280, height=1000):
    plogin_ui(who)
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"/platform.html#/{route}")
    expect(tid(page, f"{route}-page")).to_be_visible()
    first = OVERVIEW_ITEMS[0] if route == "overview" else HEALTH_ITEMS[0]
    expect(item(page, first)).to_be_visible()


def order(page):
    return page.evaluate("() => [...document.querySelectorAll('.pl-item')]"
                         ".sort((a, b) => Number(a.dataset.order) - Number(b.dataset.order)).map(e => e.dataset.item)")


def saved(page, route="overview"):
    raw = page.evaluate("k => localStorage.getItem(k)", KEY[route])
    return json.loads(raw) if raw else None


def width_pct(page, name):
    return float(item(page, name).get_attribute("data-width"))


def board_width(page):
    return page.evaluate("document.querySelector('.pl-board').clientWidth")


def drag(page, handle, dx, dy, steps=10):
    handle.scroll_into_view_if_needed()
    b = handle.bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=steps)
    page.mouse.up()


def mover(page, name):
    return item(page, name).locator("[data-testid='item-move']")


def resizer(page, name):
    return item(page, name).locator("[data-testid='item-resize']")


# ---------------------------------------------------------------- PLT-30 the default look and moving
@pytest.mark.plan("PLT-30")
def test_default_layout_has_handles_and_reset_is_disabled(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    assert order(page) == OVERVIEW_ITEMS
    for name in OVERVIEW_ITEMS:
        expect(mover(page, name)).to_have_count(1)
        expect(resizer(page, name)).to_have_count(1)
    expect(tid(page, "layout-reset")).to_be_disabled()
    assert saved(page) is None
    # the four tiles are in one row, the charts two in a row
    ys = {round(item(page, t).bounding_box()["y"]) for t in OVERVIEW_ITEMS[:4]}
    assert len(ys) == 1
    a, b = item(page, "chart-new-users").bounding_box(), item(page, "chart-active-users").bounding_box()
    assert abs(a["y"] - b["y"]) < 2 and b["x"] > a["x"]


@pytest.mark.plan("PLT-30")
def test_move_with_the_keyboard(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    handle = mover(page, "chart-type")
    handle.scroll_into_view_if_needed()
    handle.focus()
    page.keyboard.press("ArrowLeft")
    expect(item(page, "chart-type")).to_have_attribute("data-order", "8")
    page.keyboard.press("Home")
    expect(item(page, "chart-type")).to_have_attribute("data-order", "0")
    assert order(page)[0] == "chart-type"
    page.keyboard.press("End")
    expect(item(page, "chart-type")).to_have_attribute("data-order", "9")
    page.keyboard.press("ArrowRight")                       # already last: nothing happens
    expect(item(page, "chart-type")).to_have_attribute("data-order", "9")
    assert page.evaluate("document.activeElement.dataset.testid") == "item-move"   # the focus stays on the handle
    expect(tid(page, "layout-reset")).to_be_enabled()


@pytest.mark.plan("PLT-30")
def test_move_by_dragging_the_handle(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    target = item(page, "tile-tickets").bounding_box()
    handle = mover(page, "tile-users").bounding_box()
    drag(page, mover(page, "tile-users"), target["x"] + target["width"] / 2 - (handle["x"] + handle["width"] / 2), 60)
    page.wait_for_function("() => Number(document.querySelector('[data-item=tile-users]').dataset.order) >= 2")
    got = order(page)
    assert got.index("tile-users") >= 2 and got[:4] != OVERVIEW_ITEMS[:4]
    assert sorted(got) == sorted(OVERVIEW_ITEMS)             # nothing lost
    assert "tile-users" in saved(page)["order"]


@pytest.mark.plan("PLT-30")
def test_layout_survives_reload_and_reset_brings_the_default_back(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    mover(page, "chart-type").focus()
    page.keyboard.press("Home")
    resizer(page, "tile-projects").focus()
    page.keyboard.press("ArrowRight")
    expect(item(page, "tile-projects")).not_to_have_attribute("data-width", "25")
    changed = order(page)
    wide = width_pct(page, "tile-projects")
    page.reload()
    expect(item(page, "tile-users")).to_be_visible()
    assert order(page) == changed
    assert width_pct(page, "tile-projects") == wide
    tid(page, "overview-period-7").click()                   # a new period reloads the data, not the layout
    expect(tid(page, "overview-period-7")).to_have_attribute("aria-checked", "true")
    assert order(page) == changed
    tid(page, "layout-reset").click()
    expect(item(page, "chart-type")).to_have_attribute("data-order", "9")
    expect(item(page, "tile-projects")).to_have_attribute("data-width", "25")
    expect(tid(page, "layout-reset")).to_be_disabled()
    assert saved(page) is None


@pytest.mark.plan("PLT-30")
def test_broken_or_odd_saved_data_is_cleaned(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    page.evaluate("k => localStorage.setItem(k, '{not json')", KEY["overview"])
    page.reload()
    expect(item(page, "tile-users")).to_be_visible()
    assert order(page) == OVERVIEW_ITEMS
    page.evaluate("k => localStorage.setItem(k, JSON.stringify({order: ['nope', 'chart-type'], sizes: {'tile-users': {w: 9999, h: 5}, 'x': 3}}))",
                  KEY["overview"])
    page.reload()
    expect(item(page, "tile-users")).to_be_visible()
    assert order(page)[0] == "chart-type" and "nope" not in order(page)
    expect(item(page, "tile-users")).to_have_attribute("data-width", "100")      # limit
    assert float(item(page, "tile-users").get_attribute("data-height")) >= 80    # limit


@pytest.mark.plan("PLT-30")
def test_system_health_has_its_own_layout(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot, route="health")
    assert order(page) == HEALTH_ITEMS
    handle = mover(page, "load")
    handle.focus()
    page.keyboard.press("Home")
    expect(item(page, "load")).to_have_attribute("data-order", "0")
    assert saved(page, "health") is not None and saved(page, "overview") is None
    tid(page, "health-refresh").click()                       # a refresh keeps the layout
    expect(tid(page, "health-updated")).to_be_visible()
    assert order(page)[0] == "load"
    page.goto("/platform.html#/overview")                     # the other page is not touched
    expect(item(page, "tile-users")).to_be_visible()
    assert order(page) == OVERVIEW_ITEMS
    page.goto("/platform.html#/health")
    expect(item(page, "load")).to_have_attribute("data-order", "0")
    tid(page, "layout-reset").click()
    expect(item(page, "server")).to_have_attribute("data-order", "0")
    assert saved(page, "health") is None


# ---------------------------------------------------------------- PLT-31 resizing
@pytest.mark.plan("PLT-31")
def test_resize_with_the_keyboard_and_its_limits(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    handle = resizer(page, "chart-new-users")
    handle.scroll_into_view_if_needed()
    handle.focus()
    start = width_pct(page, "chart-new-users")
    page.keyboard.press("ArrowLeft")
    expect(item(page, "chart-new-users")).to_have_attribute("data-width", f"{start - 5:g}")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    expect(item(page, "chart-new-users")).to_have_attribute("data-width", f"{start + 5:g}")
    assert item(page, "chart-new-users").get_attribute("data-height") == ""      # width only: the height stays automatic
    page.keyboard.press("ArrowDown")
    assert float(item(page, "chart-new-users").get_attribute("data-height")) > 0
    for _ in range(30):
        page.keyboard.press("ArrowLeft")
    # a chart is never narrower than 300 px
    page.wait_for_function("() => document.querySelector('[data-item=chart-new-users]').getBoundingClientRect().width >= 299")
    px = width_pct(page, "chart-new-users") / 100 * board_width(page)
    assert 297 <= px <= 303
    for _ in range(40):
        page.keyboard.press("ArrowRight")
    expect(item(page, "chart-new-users")).to_have_attribute("data-width", "100")


@pytest.mark.plan("PLT-31")
def test_resize_by_dragging_the_corner(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    before = item(page, "chart-new-tickets").bounding_box()
    drag(page, resizer(page, "chart-new-tickets"), -200, 120)
    page.wait_for_function("() => document.querySelector('[data-item=chart-new-tickets]').dataset.height !== ''")
    after = item(page, "chart-new-tickets").bounding_box()
    assert after["width"] < before["width"] - 120 and after["height"] > before["height"] + 60
    got = saved(page)["sizes"]["chart-new-tickets"]
    assert 15 <= got["w"] < 50 and got["h"] > 0


@pytest.mark.plan("PLT-31")
def test_a_sideways_drag_keeps_the_automatic_height(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    handle = resizer(page, "chart-status")
    handle.scroll_into_view_if_needed()
    b = handle.bounding_box()
    y = b["y"] + b["height"] / 2
    page.mouse.move(b["x"] + 10, y)
    page.mouse.down()
    page.mouse.move(b["x"] - 100, y, steps=8)
    page.mouse.up()
    page.wait_for_function("() => Number(document.querySelector('[data-item=chart-status]').dataset.width) < 50")
    assert item(page, "chart-status").get_attribute("data-height") == ""
    assert "h" not in saved(page)["sizes"]["chart-status"]


@pytest.mark.plan("PLT-31")
def test_a_tile_is_never_smaller_than_its_content(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    drag(page, resizer(page, "tile-users"), -500, -400)       # try to make it tiny
    page.wait_for_function("() => document.querySelector('[data-item=tile-users]').dataset.width !== '25'")
    box = item(page, "tile-users").bounding_box()
    assert box["width"] >= 209
    cut = page.evaluate("() => { const c = document.querySelector('[data-testid=tile-users]'); return c.scrollHeight - c.clientHeight; }")
    assert cut <= 1                                           # nothing is cut off
    assert width_pct(page, "tile-users") / 100 * board_width(page) >= 209     # and the saved size obeys the same limit
    handle = resizer(page, "tile-users")
    handle.focus()
    for _ in range(30):
        page.keyboard.press("ArrowUp")
    cut = page.evaluate("() => { const c = document.querySelector('[data-testid=tile-users]'); return c.scrollHeight - c.clientHeight; }")
    assert cut <= 1
    for text in ("Active", "Blocked", "Deactivated"):
        expect(tid(page, "tile-users")).to_contain_text(text)
    drag(page, resizer(page, "chart-status"), -700, -400)
    box = item(page, "chart-status").bounding_box()
    assert box["width"] >= 299
    cut = page.evaluate("() => { const c = document.querySelector('[data-testid=chart-status]'); return c.scrollHeight - c.clientHeight; }")
    assert cut <= 1


# ---------------------------------------------------------------- PLT-32 charts follow the size of the tile
def chart_area(page, chart):
    return page.evaluate("""c => {
        const body = document.querySelector(`[data-testid=${c}] .pl-chart-body`).getBoundingClientRect();
        const svg = document.querySelector(`[data-testid=${c}-svg]`);
        const r = svg.getBoundingClientRect();
        return { w: Math.round(body.width), h: Math.round(body.height), sw: Math.round(r.width), sh: Math.round(r.height), vb: svg.getAttribute('viewBox') };
    }""", chart)


def settled(page, chart):
    """The chart is drawn again a moment after its tile changed: wait until the viewBox has the real size."""
    page.wait_for_function(
        f"() => {{ const s = document.querySelector('[data-testid={chart}-svg]'); const r = s.getBoundingClientRect();"
        " return s.getAttribute('viewBox') === '0 0 ' + Math.round(r.width) + ' ' + Math.round(r.height); }")
    return chart_area(page, chart)


@pytest.mark.plan("PLT-32")
def test_a_line_chart_is_drawn_to_the_size_of_its_tile(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    chart = "chart-new-users"
    svg = tid(page, f"{chart}-svg")
    svg.scroll_into_view_if_needed()
    a = chart_area(page, chart)
    assert (a["sw"], a["sh"]) == (a["w"], a["h"]) and a["vb"] == f"0 0 {a['w']} {a['h']}"
    handle = resizer(page, "chart-new-users")
    handle.focus()
    for _ in range(8):
        page.keyboard.press("ArrowDown")
    page.wait_for_function(f"() => document.querySelector('[data-testid={chart}-svg]').getBoundingClientRect().height > {a['h'] + 100}")
    b = settled(page, chart)
    assert b["h"] > a["h"] + 100 and b["sh"] == b["h"]
    assert b["vb"] == f"0 0 {b['w']} {b['h']}"                # the data is drawn again for the new size, not stretched
    size = page.evaluate("c => getComputedStyle(document.querySelector(`[data-testid=${c}-svg] .pl-axis-text`)).fontSize", chart)
    assert size == "12px"                                     # the text keeps its size
    for _ in range(4):
        page.keyboard.press("ArrowRight")
    page.wait_for_function(f"() => document.querySelector('[data-testid={chart}-svg]').getBoundingClientRect().width > {a['w'] + 50}")
    c = settled(page, chart)
    assert c["vb"] == f"0 0 {c['w']} {c['h']}"
    # the chart still works after the table view
    tid(page, f"{chart}-toggle").click()
    expect(tid(page, f"{chart}-table")).to_be_visible()
    tid(page, f"{chart}-toggle").click()
    expect(svg).to_be_visible()
    page.wait_for_function(f"() => {{ const s = document.querySelector('[data-testid={chart}-svg]'); return s.getAttribute('viewBox') === '0 0 ' + Math.round(s.getBoundingClientRect().width) + ' ' + Math.round(s.getBoundingClientRect().height); }}")


@pytest.mark.plan("PLT-32")
def test_the_bar_charts_use_the_height_of_their_tile(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    rows = tid(page, "chart-type-row")
    expect(rows).to_have_count(6)
    first = rows.first.bounding_box()
    last = rows.last.bounding_box()
    span = last["y"] + last["height"] - first["y"]
    handle = resizer(page, "chart-type")
    handle.scroll_into_view_if_needed()
    handle.focus()
    for _ in range(10):
        page.keyboard.press("ArrowDown")
    page.wait_for_function("() => { const r = document.querySelectorAll('[data-testid=chart-type-row]'); const a = r[0].getBoundingClientRect(), b = r[r.length - 1].getBoundingClientRect(); return b.bottom - a.top > " + str(span + 40) + "; }")
    for i in range(6):                                        # every bar is still there and no bar is thicker than 24 px
        bar = rows.nth(i).locator("[data-testid='bar']")
        if rows.nth(i).get_attribute("data-value") != "0":
            assert bar.bounding_box()["height"] <= 24


# ---------------------------------------------------------------- PLT-33 fit to the neighbours, narrow screens
@pytest.mark.plan("PLT-33")
def test_the_right_edge_jumps_to_the_edge_of_a_neighbour(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    users = item(page, "tile-users").bounding_box()
    tickets = item(page, "tile-tickets").bounding_box()
    target = tickets["x"] + tickets["width"]
    handle = resizer(page, "tile-users").bounding_box()
    sx, sy = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    stop = sx + (target - (users["x"] + users["width"])) - 7     # 7 px before the neighbour's edge
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(stop, sy, steps=8)
    expect(page.locator(".pl-guide-v:not([hidden])")).to_have_count(1)      # the guide line is shown while it fits
    page.mouse.up()
    got = item(page, "tile-users").bounding_box()
    assert abs(got["x"] + got["width"] - target) <= 1.5
    expect(page.locator(".pl-guide")).to_have_count(0)                      # and removed at the end


@pytest.mark.plan("PLT-33")
def test_no_jump_when_the_edge_is_far_from_the_neighbours(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    before = item(page, "tile-users").bounding_box()
    drag(page, resizer(page, "tile-users"), 40, 0)
    page.wait_for_function("() => document.querySelector('[data-item=tile-users]').dataset.width !== '25'")
    got = item(page, "tile-users").bounding_box()
    assert abs(got["width"] - (before["width"] + 40)) <= 2


@pytest.mark.plan("PLT-33")
def test_the_bottom_edge_jumps_to_the_edge_of_a_neighbour(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot)
    tall = resizer(page, "chart-active-users")
    tall.scroll_into_view_if_needed()
    tall.focus()
    for _ in range(5):
        page.keyboard.press("ArrowDown")
    expect(item(page, "chart-active-users")).not_to_have_attribute("data-height", "")
    neighbour = item(page, "chart-new-users")
    neighbour.scroll_into_view_if_needed()
    a = item(page, "chart-active-users").bounding_box()
    me = neighbour.bounding_box()
    target = a["y"] + a["height"]
    handle = resizer(page, "chart-new-users").bounding_box()
    sx, sy = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    stop = sy + (target - (me["y"] + me["height"])) - 6
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx, stop, steps=8)
    page.mouse.up()
    got = neighbour.bounding_box()
    assert abs(got["y"] + got["height"] - target) <= 1.5


@pytest.mark.plan("PLT-33")
def test_on_a_narrow_screen_every_tile_uses_the_full_width(page, plogin_ui, proot):
    open_page(page, plogin_ui, proot, width=700, height=900)
    page.evaluate("k => localStorage.setItem(k, JSON.stringify({sizes: {'tile-users': {w: 30}}}))", KEY["overview"])
    page.reload()
    expect(item(page, "tile-users")).to_be_visible()
    box = item(page, "tile-users").bounding_box()
    assert box["width"] >= board_width(page) - 2
