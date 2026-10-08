from dialtone import keys, skin
from dialtone.model import load_catalogs, load_devices


def test_every_control_has_pill_and_leader():
    lay = skin.compute_layout(780, 620)
    ids = {c.id for c in load_devices()["ulanzi-d100h"].controls}
    assert set(lay.pills) == ids == set(skin.CONTROLS)
    assert set(lay.leaders) == ids


def test_pills_do_not_overlap():
    for w, h in ((720, 560), (780, 620), (1200, 900)):
        pills = list(skin.compute_layout(w, h).pills.values())
        for i, a in enumerate(pills):
            for b in pills[i + 1:]:
                assert (a.x + a.w <= b.x or b.x + b.w <= a.x
                        or a.y + a.h <= b.y or b.y + b.h <= a.y), (w, h, a, b)


def test_hit_testing():
    w, h = 780, 620
    lay = skin.compute_layout(w, h)
    for cid, p in lay.pills.items():
        assert skin.hit(p.cx, p.cy, w, h) == cid
    kcx, kcy, r = lay.knob
    assert skin.hit(kcx, kcy, w, h) == "dial_press"
    assert skin.hit(kcx - r * 0.7, kcy, w, h) == "dial_ccw"
    assert skin.hit(kcx + r * 0.7, kcy, w, h) == "dial_cw"
    k = lay.keys["top_center"]
    assert skin.hit(k.cx, k.cy, w, h) == "top_center"
    assert skin.hit(2, 2, w, h) is None


def test_pretty_and_parse():
    assert keys.pretty("Control_L + Prior") == "Ctrl+PgUp"
    assert keys.pretty("Shift_L + Left") == "Shift+\u2190"
    assert keys.pretty("wheel(up, 1)") == "macro"
    assert keys.parse("Control_L + Shift_L + Right") == (frozenset({"ctrl", "shift"}), "right")


def test_matching_event_to_output():
    assert keys.matches("Control_L + Prior", {"ctrl"}, {"Page_Up", "KEY_PAGEUP"})
    assert keys.matches("Next", set(), {"Page_Down"})
    assert not keys.matches("Control_L + Prior", set(), {"Page_Up"})
    assert keys.matches("space", set(), {"space"})


def test_compose_prefers_known_symbols():
    known = {"Prior", "Left", "Control_L"}
    assert keys.compose(["Control_L"], "Left", 105, known) == "Control_L + Left"
    # Page_Up isn't an input-remapper symbol; fall back to evdev name if available
    out = keys.compose([], "Page_Up", 104, known)
    assert out in ("KEY_PAGEUP", "Page_Up")


def test_catalogs_load():
    cats = load_catalogs()
    assert any(c.applies_to("Avidemux 2.8") for c in cats)
    assert all(a.output for c in cats for _g, acts in c.groups for a in acts)
