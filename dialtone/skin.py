"""Draw the D100H with Studio-style mapping callouts and hit-test it.

Layout and hit-testing are pure Python (unit-tested). Painting uses GTK's
scene graph (Gtk.Snapshot / GSK), so no cairo bindings are needed. Photo layers
and key geometry come from brendanwelsh/ulanzi-d100h-homebrew (MIT) - see
assets/dial-skin/LICENSE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


ASSETS = Path(__file__).resolve().parent / "assets" / "dial-skin"
BASE_W, BASE_H = 528, 583
KNOB = (50.95, 61.58, 57.95)          # cx %, cy % of base; diameter % of width
KEYS = {                              # control id -> (skin file, cx, cy, w, h) in % of base
    "left_lower":  ("1", 3.0, 62.6, 7.5, 21.8),
    "left_upper":  ("2", 3.0, 39.0, 7.5, 22.0),
    "top_left":    ("3", 16.4, 11.0, 29.2, 22.1),
    "top_center":  ("4", 47.8, 11.0, 32.6, 22.1),
    "top_right":   ("5", 81.3, 10.9, 33.3, 22.0),
    "right_upper": ("6", 97.0, 39.0, 7.5, 22.0),
    "right_lower": ("7", 97.0, 63.3, 7.5, 23.2),
}
DIAL = ("dial_ccw", "dial_press", "dial_cw")
CONTROLS = (*KEYS, *DIAL)
SHORT = {
    "top_left": "Top left", "top_center": "Top center", "top_right": "Top right",
    "left_upper": "Left upper", "left_lower": "Left lower",
    "right_upper": "Right upper", "right_lower": "Right lower",
    "dial_ccw": "Dial \u21ba", "dial_cw": "Dial \u21bb", "dial_press": "Dial press",
}

BG = (0.063, 0.067, 0.078)
AMBER = (1.0, 0.69, 0.0)
INK = (0.08, 0.08, 0.09)
PW, PH, GAP = 176, 50, 30


@dataclass
class Callout:
    title: str
    text: str
    keys: str = ""
    mapped: bool = True


@dataclass
class State:
    callouts: dict[str, Callout] = field(default_factory=dict)
    selected: str | None = None
    hover: str | None = None
    lit: set[str] = field(default_factory=set)
    knob_angle: float = 0.0


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def contains(self, px: float, py: float, pad: float = 0) -> bool:
        return (self.x - pad <= px <= self.x + self.w + pad
                and self.y - pad <= py <= self.y + self.h + pad)


@dataclass
class Layout:
    ix: float
    iy: float
    iw: float
    ih: float
    keys: dict[str, Rect]
    knob: tuple[float, float, float]
    pills: dict[str, Rect]
    leaders: dict[str, tuple[tuple[float, float], tuple[float, float]]]

    @property
    def scale(self) -> float:
        return self.iw / BASE_W


def compute_layout(w: float, h: float) -> Layout:
    side = PW + GAP + 10
    top = bottom = PH + GAP
    aw, ah = max(w - 2 * side, 120), max(h - top - bottom, 120)
    s = min(aw / BASE_W, ah / BASE_H)
    iw, ih = BASE_W * s, BASE_H * s
    ix, iy = side + (aw - iw) / 2, top + (ah - ih) / 2

    keys = {cid: Rect(ix + (cx - kw / 2) / 100 * iw, iy + (cy - kh / 2) / 100 * ih,
                      kw / 100 * iw, kh / 100 * ih)
            for cid, (_f, cx, cy, kw, kh) in KEYS.items()}
    kcx, kcy, r = ix + KNOB[0] / 100 * iw, iy + KNOB[1] / 100 * ih, KNOB[2] / 200 * iw

    lx, rx = ix - GAP - PW, ix + iw + GAP

    def at(x: float, y: float) -> Rect:
        return Rect(x, y - PH / 2, PW, PH)

    pills = {
        "top_left": at(lx, keys["top_left"].cy),
        "left_upper": at(lx, keys["left_upper"].cy),
        "left_lower": at(lx, keys["left_lower"].cy),
        "dial_ccw": at(lx, kcy + r * 0.82),
        "top_right": at(rx, keys["top_right"].cy),
        "right_upper": at(rx, keys["right_upper"].cy),
        "right_lower": at(rx, keys["right_lower"].cy),
        "dial_cw": at(rx, kcy + r * 0.82),
        "top_center": Rect(keys["top_center"].cx - PW / 2, iy - GAP * 0.55 - PH, PW, PH),
        "dial_press": Rect(kcx - PW / 2, iy + ih + GAP * 0.55, PW, PH),
    }

    def knob_pt(deg: float) -> tuple[float, float]:
        a = math.radians(deg)
        return kcx + r * math.cos(a), kcy + r * math.sin(a)

    k = keys
    anchors = {
        "top_left": (k["top_left"].x + k["top_left"].w * 0.22, k["top_left"].cy),
        "top_right": (k["top_right"].x + k["top_right"].w * 0.78, k["top_right"].cy),
        "top_center": (k["top_center"].cx, k["top_center"].y + k["top_center"].h * 0.3),
        "left_upper": (k["left_upper"].cx, k["left_upper"].cy),
        "left_lower": (k["left_lower"].cx, k["left_lower"].cy),
        "right_upper": (k["right_upper"].cx, k["right_upper"].cy),
        "right_lower": (k["right_lower"].cx, k["right_lower"].cy),
        "dial_ccw": knob_pt(150),
        "dial_cw": knob_pt(30),
        "dial_press": (kcx, kcy),
    }
    leaders = {}
    for cid, p in pills.items():
        if cid == "top_center":
            start = (p.cx, p.y + p.h)
        elif cid == "dial_press":
            start = (p.cx, p.y)
        elif p.x < ix:
            start = (p.x + p.w, p.cy)
        else:
            start = (p.x, p.cy)
        leaders[cid] = (start, anchors[cid])
    return Layout(ix, iy, iw, ih, keys, (kcx, kcy, r), pills, leaders)


def hit(x: float, y: float, w: float, h: float) -> str | None:
    lay = compute_layout(w, h)
    for cid, p in lay.pills.items():
        if p.contains(x, y):
            return cid
    for cid, k in lay.keys.items():
        if k.contains(x, y, pad=4):
            return cid
    kcx, kcy, r = lay.knob
    d = math.hypot(x - kcx, y - kcy)
    if d <= r * 1.08:
        if d <= r * 0.38:
            return "dial_press"
        return "dial_ccw" if x < kcx else "dial_cw"
    return None


def load_textures(assets: Path = ASSETS) -> dict:
    from gi.repository import Gdk
    tex = {"base": Gdk.Texture.new_from_filename(str(assets / "ulanzi-dial.png")),
           "knob": Gdk.Texture.new_from_filename(str(assets / "ulanzi-knob.png"))}
    for f, *_ in KEYS.values():
        tex[f"white-{f}"] = Gdk.Texture.new_from_filename(str(assets / f"white-{f}.png"))
    return tex


class Painter:
    """Paints a State into a Gtk.Snapshot. Needs the widget for Pango layouts."""

    def __init__(self, widget, textures: dict):
        import gi
        gi.require_version("Gsk", "4.0")
        gi.require_version("Graphene", "1.0")
        from gi.repository import Gdk, GLib, Graphene, Gsk, Pango
        self.Gdk, self.GLib, self.Graphene, self.Gsk, self.Pango = Gdk, GLib, Graphene, Gsk, Pango
        self.widget = widget
        self.tex = textures

    # -- primitives --
    def rgba(self, r, g, b, a=1.0):
        c = self.Gdk.RGBA()
        c.red, c.green, c.blue, c.alpha = r, g, b, a
        return c

    def rect(self, x, y, w, h):
        return self.Graphene.Rect().init(x, y, w, h)

    def point(self, x, y):
        return self.Graphene.Point().init(x, y)

    def rounded_path(self, r: Rect, rad: float):
        """Rounded rectangle path built from quads (RoundedRect boxing is unreliable in PyGObject)."""
        x0, y0, x1, y1 = r.x, r.y, r.x + r.w, r.y + r.h
        rad = min(rad, r.w / 2, r.h / 2)
        pb = self.Gsk.PathBuilder.new()
        pb.move_to(x0 + rad, y0)
        pb.line_to(x1 - rad, y0)
        pb.quad_to(x1, y0, x1, y0 + rad)
        pb.line_to(x1, y1 - rad)
        pb.quad_to(x1, y1, x1 - rad, y1)
        pb.line_to(x0 + rad, y1)
        pb.quad_to(x0, y1, x0, y1 - rad)
        pb.line_to(x0, y0 + rad)
        pb.quad_to(x0, y0, x0 + rad, y0)
        pb.close()
        return pb.to_path()

    def stroke(self, snap, path, width, color, dash=None):
        st = self.Gsk.Stroke.new(width)
        st.set_line_cap(self.Gsk.LineCap.ROUND)
        if dash:
            st.set_dash(dash)
        snap.append_stroke(path, st, color)

    def fill(self, snap, path, color):
        snap.append_fill(path, self.Gsk.FillRule.WINDING, color)

    def text(self, snap, markup, font, x, y, width, color, right=False) -> float:
        lay = self.widget.create_pango_layout(None)
        lay.set_font_description(self.Pango.FontDescription.from_string(font))
        lay.set_markup(markup, -1)
        lay.set_width(int(max(width, 1) * self.Pango.SCALE))
        lay.set_ellipsize(self.Pango.EllipsizeMode.END)
        if right:
            lay.set_alignment(self.Pango.Alignment.RIGHT)
        snap.save()
        snap.translate(self.point(x, y))
        snap.append_layout(lay, color)
        snap.restore()
        return lay.get_pixel_extents()[1].width

    def tinted(self, snap, texture, bounds, color):
        snap.push_mask(self.Gsk.MaskMode.ALPHA)
        snap.append_texture(texture, bounds)
        snap.pop()
        snap.append_color(color, bounds)
        snap.pop()

    def arc_arrow(self, snap, cx, cy, r, a0, a1, color, width):
        pb = self.Gsk.PathBuilder.new()
        steps = 24
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]
        pb.move_to(*pts[0])
        for p in pts[1:]:
            pb.line_to(*p)
        self.stroke(snap, pb.to_path(), width, color)
        t = math.radians(a1)
        ex, ey = cx + r * math.cos(t), cy + r * math.sin(t)
        sign = 1 if a1 > a0 else -1
        dx, dy = -math.sin(t) * sign, math.cos(t) * sign
        nx, ny = -dy, dx
        hb = self.Gsk.PathBuilder.new()
        hb.move_to(ex + dx * 9, ey + dy * 9)
        hb.line_to(ex + nx * 5, ey + ny * 5)
        hb.line_to(ex - nx * 5, ey - ny * 5)
        hb.close()
        self.fill(snap, hb.to_path(), color)

    # -- scene --
    def paint(self, snap, w: float, h: float, state: State) -> None:
        lay = compute_layout(w, h)
        kcx, kcy, r = lay.knob
        bg = self.rgba(*BG)
        snap.append_color(bg, self.rect(0, 0, w, h))
        try:
            stops = []
            for off, col in ((0.0, self.rgba(0.22, 0.23, 0.27)), (1.0, bg)):
                s = self.Gsk.ColorStop()
                s.offset, s.color = off, col
                stops.append(s)
            rad = max(lay.iw, lay.ih) * 0.95
            snap.append_radial_gradient(self.rect(0, 0, w, h), self.point(kcx, kcy),
                                        rad, rad, 0.0, 1.0, stops)
        except (TypeError, AttributeError):
            pass

        img = self.rect(lay.ix, lay.iy, lay.iw, lay.ih)
        snap.append_texture(self.tex["base"], img)
        for cid, (f, *_rest) in KEYS.items():
            if cid in state.lit:
                col = self.rgba(1, 1, 1, 1)
            elif cid == state.selected:
                col = self.rgba(*AMBER, 0.9)
            elif cid == state.hover:
                col = self.rgba(1, 1, 1, 0.35)
            else:
                continue
            self.tinted(snap, self.tex[f"white-{f}"], img, col)

        snap.save()
        snap.translate(self.point(kcx, kcy))
        snap.rotate(state.knob_angle)
        snap.append_texture(self.tex["knob"], self.rect(-r, -r, 2 * r, 2 * r))
        snap.restore()

        for cid in DIAL:
            hot = cid == state.selected
            col = (self.rgba(1, 1, 1, 1) if cid in state.lit else self.rgba(*AMBER) if hot
                   else self.rgba(1, 1, 1, 0.55) if cid == state.hover else self.rgba(1, 1, 1, 0.16))
            wdt = 3 if hot else 2
            if cid == "dial_ccw":
                self.arc_arrow(snap, kcx, kcy, r * 1.09, 235, 125, col, wdt)
            elif cid == "dial_cw":
                self.arc_arrow(snap, kcx, kcy, r * 1.09, -55, 55, col, wdt)
            else:
                pb = self.Gsk.PathBuilder.new()
                pb.add_circle(self.point(kcx, kcy), r * 0.3)
                self.stroke(snap, pb.to_path(), wdt, col)

        for cid, ((sx, sy), (ax, ay)) in lay.leaders.items():
            hot = cid == state.selected
            col = self.rgba(*AMBER, 0.95) if hot else self.rgba(1, 1, 1, 0.26)
            pb = self.Gsk.PathBuilder.new()
            pb.move_to(sx, sy)
            pb.line_to(ax, ay)
            self.stroke(snap, pb.to_path(), 1.6 if hot else 1.0, col)
            db = self.Gsk.PathBuilder.new()
            db.add_circle(self.point(ax, ay), 3.2 if hot else 2.4)
            self.fill(snap, db.to_path(), col)

        for cid, p in lay.pills.items():
            self.pill(snap, p, cid, state)

    def pill(self, snap, p: Rect, cid: str, state: State) -> None:
        c = state.callouts.get(cid) or Callout(SHORT[cid], "+ assign", mapped=False)
        sel, hov = cid == state.selected, cid == state.hover
        path = self.rounded_path(p, 10)
        self.fill(snap, path, self.rgba(*AMBER) if sel else self.rgba(0.105, 0.113, 0.133, 0.94))
        if cid in state.lit:
            self.fill(snap, path, self.rgba(1, 1, 1, 0.35))
        if not sel:
            border = self.rgba(*AMBER, 0.9) if hov else self.rgba(1, 1, 1, 0.14)
            self.stroke(snap, path, 1.0, border, dash=None if c.mapped else [4, 3])
        if c.mapped and not sel:
            self.fill(snap, self.rounded_path(Rect(p.x + 7, p.y + 11, 3, p.h - 22), 1.5),
                      self.rgba(*AMBER, 0.85))

        title = self.rgba(*INK, 0.72) if sel else self.rgba(0.56, 0.59, 0.66)
        body = self.rgba(*INK) if sel else self.rgba(0.93, 0.94, 0.96) if c.mapped else self.rgba(0.56, 0.59, 0.66)
        esc = self.GLib.markup_escape_text
        pad, used = 18, 0
        if c.keys:
            used = self.text(snap, esc(c.keys), "Monospace 7.5", p.x + pad, p.y + 8,
                             p.w - pad - 10, title, right=True)
        self.text(snap, f'<span letter_spacing="1100">{esc(c.title.upper())}</span>',
                  "Monospace Bold 7", p.x + pad, p.y + 9, p.w - pad - 14 - used, title)
        self.text(snap, esc(c.text), "Sans Bold 10.5" if c.mapped else "Sans Italic 10",
                  p.x + pad, p.y + 24, p.w - pad - 10, body)
