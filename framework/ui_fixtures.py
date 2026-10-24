"""Playwright fixtures (sync API). Imported as a plugin from the root conftest; Playwright is only
imported lazily so API-only runs never need a browser."""
import json
import re
import urllib.request

import pytest

from framework import config, report

CDN_RE = re.compile(r"^https://(unpkg\.com|cdnjs\.cloudflare\.com)/.*")
VENDOR_FILES = {"vue.global.prod.js": "vue.global.prod.js", "Sortable.min.js": "Sortable.min.js"}


def vendor_ready() -> bool:
    return all((config.VENDOR_DIR / f).is_file() for f in VENDOR_FILES.values())


def _cdn_reachable() -> bool:
    try:
        urllib.request.urlopen("https://unpkg.com/vue@3.4.21/package.json", timeout=5)  # noqa: S310
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def vue_available():
    """True when Vue/Sortable can be served (vendor/ copies, or the real CDN is reachable)."""
    return vendor_ready() or _cdn_reachable()


@pytest.fixture(autouse=True)
def _skip_without_vue(request):
    if request.node.get_closest_marker("needs_vue") and not request.getfixturevalue("vue_available"):
        pytest.skip("Vue/Sortable not available offline: run `python tools/fetch_vendor.py` once "
                    "(or allow access to unpkg.com / cdnjs.cloudflare.com)")


@pytest.fixture(scope="session")
def _playwright():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_playwright):
    b = _playwright.chromium.launch(headless=config.HEADLESS, slow_mo=config.SLOW_MO,
                                    args=["--disable-dev-shm-usage"])
    yield b
    b.close()


def _cdn_handler(route):
    name = route.request.url.split("?")[0].rsplit("/", 1)[-1]
    local = VENDOR_FILES.get(name)
    if local and (config.VENDOR_DIR / local).is_file():
        route.fulfill(status=200, body=(config.VENDOR_DIR / local).read_bytes(),
                      headers={"content-type": "application/javascript; charset=utf-8",
                               "access-control-allow-origin": "*"})
    else:
        route.continue_()


@pytest.fixture
def context(browser, base_url, request):
    ctx = browser.new_context(base_url=base_url, viewport={"width": 1366, "height": 850},
                              locale="en-US", accept_downloads=True)
    ctx.set_default_timeout(config.UI_TIMEOUT_MS)
    ctx.route(CDN_RE, _cdn_handler)
    ctx.tracing.start(screenshots=True, snapshots=True)
    yield ctx
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        trace = config.REPORT_DIR / "traces" / (re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)[:150] + ".zip")
        trace.parent.mkdir(parents=True, exist_ok=True)
        ctx.tracing.stop(path=str(trace))
        report.attach(request.node.nodeid, "playwright trace (npx playwright show-trace)", f"traces/{trace.name}")
    else:
        ctx.tracing.stop()
    ctx.close()


def _track(page):
    page.js_errors = []        # uncaught exceptions in the page
    page.console_errors = []   # console.error messages
    page.dialogs = []          # confirm()/alert() messages seen
    page.dialog_policy = "accept"

    def on_dialog(d):
        page.dialogs.append(d.message)
        d.accept() if page.dialog_policy == "accept" else d.dismiss()

    page.on("pageerror", lambda e: page.js_errors.append(str(e)))
    page.on("console", lambda m: page.console_errors.append(m.text) if m.type == "error" else None)
    page.on("dialog", on_dialog)
    return page


@pytest.fixture
def page(context):
    return _track(context.new_page())


def seed_session(context, token=None, lang="en", extra_local=None):
    """Seed localStorage once per tab (guarded by sessionStorage so logout/redirect tests behave)."""
    items = {"rt_lang": lang}
    if token:
        items["rt_token"] = token
    items.update(extra_local or {})
    script = ("(()=>{try{if(sessionStorage.getItem('__seeded'))return;sessionStorage.setItem('__seeded','1');"
              f"const o={json.dumps(items)};for(const k in o)localStorage.setItem(k,o[k]);}}catch(e){{}}}})();")
    context.add_init_script(script)


@pytest.fixture
def login_ui(context):
    """login_ui(user, lang='en') -> seeds the browser session so pages open authenticated."""
    def _login(user, lang="en", **extra):
        seed_session(context, user.token, lang, **extra)
    return _login


@pytest.fixture
def anon_ui(context):
    """Anonymous browser session with a fixed UI language."""
    def _anon(lang="en"):
        seed_session(context, None, lang)
    return _anon
