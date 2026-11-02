"""The six presets added from the reference images: listed, valid, readable (THEME-09..10)."""
import pytest

from framework.factory import ok

pytestmark = pytest.mark.api

OLD_KEYS = ["rapid_task_dark_pastel", "rapid_task_light_pastel", "solarized_dark", "solarized_light",
            "one_dark", "nord"]
NEW = {
    "lavender_light": ("Lavender Light", False),
    "violet_pop_light": ("Violet Pop Light", False),
    "navy_orange_light": ("Navy Orange Light", False),
    "mint_night": ("Mint Night", True),
    "midnight_neon": ("Midnight Neon", True),
    "fresh_lime_light": ("Fresh Lime Light", False),
}


def presets(client):
    return [t for t in ok(client.get("/api/themes")).json() if t["is_preset"]]


def rgb(hexc):
    h = hexc.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ratio(a, b):
    hi, lo = sorted((lum(rgb(a)), lum(rgb(b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------- THEME-09 listed and valid
@pytest.mark.plan("THEME-09")
def test_twelve_presets_with_unique_keys_and_names(make_user):
    rows = presets(make_user(tag="thp1_").client)
    keys = [t["key"] for t in rows]
    assert len(rows) == 12 and len(set(keys)) == 12
    assert len({t["name"] for t in rows}) == 12
    assert set(keys) == set(OLD_KEYS) | set(NEW)


@pytest.mark.plan("THEME-09")
@pytest.mark.parametrize("key", list(NEW))
def test_new_preset_has_the_expected_name_and_full_color_set(make_user, key):
    u = make_user(tag="thp2_")
    t = next(x for x in presets(u.client) if x["key"] == key)
    assert t["name"] == NEW[key][0] and t["created_by"] is None
    old = next(x for x in presets(u.client) if x["key"] == "nord")
    assert set(t["colors"]) == set(old["colors"])                     # no missing or extra color field
    assert set(t["shadows"]) == set(old["shadows"]) and t["typography"] == old["typography"]


@pytest.mark.plan("THEME-09")
@pytest.mark.parametrize("key", list(NEW))
def test_new_preset_exports_and_imports_back(make_user, key):
    u = make_user(tag="thp3_")
    t = next(x for x in presets(u.client) if x["key"] == key)
    body = ok(u.client.get(f"/api/themes/{t['id']}/export")).json()
    body["name"] = f"Copy of {key}"
    copy = ok(u.client.post("/api/themes/import", json=body), 201).json()      # passes the strict validation
    assert copy["is_preset"] is False and copy["colors"] == t["colors"]


@pytest.mark.plan("THEME-09")
def test_new_presets_cannot_be_deleted(make_user):
    u = make_user(tag="thp4_")
    for key in NEW:
        t = next(x for x in presets(u.client) if x["key"] == key)
        assert u.client.delete(f"/api/themes/{t['id']}").status_code == 403


# ---------------------------------------------------------------- THEME-10 contrast
@pytest.mark.plan("THEME-10")
@pytest.mark.parametrize("key", list(NEW))
def test_new_preset_is_readable(make_user, key):
    c = next(x for x in presets(make_user(tag="thp5_").client) if x["key"] == key)["colors"]
    on_accent = "#16131f" if lum(rgb(c["accent"])) > 0.4 else "#ffffff"       # the engine's own rule
    rules = [
        ("text on page", c["text_primary"], c["background"], 7),
        ("text on cards", c["text_primary"], c["bg_1"], 7),
        ("secondary text on cards", c["text_secondary"], c["bg_1"], 4.5),
        ("secondary text on raised surface", c["text_secondary"], c["bg_3"], 4.5),
        ("muted text on cards", c["text_muted"], c["bg_1"], 3),
        ("muted text on page", c["text_muted"], c["background"], 3),
        ("accent text on cards", c["accent"], c["bg_1"], 4.5),
        ("accent text on page", c["accent"], c["background"], 4.5),
        ("button text on accent", on_accent, c["accent"], 4.5),
        ("second accent on cards", c["accent_secondary"], c["bg_1"], 3),
        ("danger on cards", c["danger"], c["bg_1"], 3),
        ("warning on cards", c["warning"], c["bg_1"], 3),
    ]
    failed = [f"{n}: {ratio(a, b):.2f} < {m}" for n, a, b, m in rules if ratio(a, b) < m]
    assert not failed, failed


@pytest.mark.plan("THEME-10")
@pytest.mark.parametrize("key,dark", [(k, v[1]) for k, v in NEW.items()])
def test_dark_and_light_presets_are_what_the_name_says(make_user, key, dark):
    c = next(x for x in presets(make_user(tag="thp6_").client) if x["key"] == key)["colors"]
    assert (lum(rgb(c["background"])) < 0.4) is dark
    assert (lum(rgb(c["text_primary"])) > 0.4) is dark                  # light text on dark, dark text on light
