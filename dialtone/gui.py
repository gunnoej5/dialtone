"""GTK4 / libadwaita editor for Dialtone profiles."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from . import remapper  # noqa: E402
from .model import Binding, Profile, load_devices, load_profiles, user_profile_dir  # noqa: E402

# Physical arrangement of the D100H: (control id, column, row) on a 3x3 grid.
LAYOUT = [
    ("top_left", 0, 0), ("top_center", 1, 0), ("top_right", 2, 0),
    ("left_upper", 0, 1), ("dial_press", 1, 1), ("right_upper", 2, 1),
    ("left_lower", 0, 2), ("dial_ccw", 1, 2), ("right_lower", 2, 2),
    ("dial_cw", 1, 3),
]

COMMON_KEYS = ["space", "Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End",
               "Delete", "Return", "Escape", "Control_L + z", "Control_L + y",
               "Shift_L + Left", "Shift_L + Right"]


class ControlCard(Gtk.Frame):
    def __init__(self, control):
        super().__init__(label=control.label)
        self.control = control
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        hint = Gtk.Label(label=f"default: {control.default}", xalign=0)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        self.output = Gtk.Entry(placeholder_text="output, e.g. Control_L + Prior")
        completion_model = Gtk.StringList.new(COMMON_KEYS)
        self.preset_drop = Gtk.DropDown(model=completion_model)
        self.preset_drop.set_selected(Gtk.INVALID_LIST_POSITION)
        self.preset_drop.connect("notify::selected", self._on_pick)
        self.label = Gtk.Entry(placeholder_text="label (what it does)")
        for w in (hint, self.output, self.preset_drop, self.label):
            box.append(w)
        self.set_child(box)

    def _on_pick(self, drop, _pspec):
        item = drop.get_selected_item()
        if item is not None:
            self.output.set_text(item.get_string())

    def load(self, binding: Binding | None):
        self.output.set_text(binding.output if binding else "")
        self.label.set_text(binding.label if binding else "")

    def dump(self) -> Binding:
        return Binding(self.output.get_text().strip(), self.label.get_text().strip())


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Dialtone", default_width=900, default_height=640)
        self.devices = load_devices()
        self.device = self.devices["ulanzi-d100h"]
        self.profiles = load_profiles()

        self.toast = Adw.ToastOverlay()
        header = Adw.HeaderBar()
        self.picker = Gtk.DropDown(model=Gtk.StringList.new(list(self.profiles)))
        self.picker.connect("notify::selected", lambda *_: self._show_selected())
        header.pack_start(self.picker)
        for text, cb, css in (("Apply", self._apply, "suggested-action"),
                              ("Save", self._save, None), ("Stop", self._stop, None)):
            b = Gtk.Button(label=text)
            if css:
                b.add_css_class(css)
            b.connect("clicked", cb)
            header.pack_end(b)

        self.description = Gtk.Label(xalign=0, wrap=True, margin_start=12, margin_end=12)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_top=12,
                        margin_bottom=12, margin_start=12, margin_end=12,
                        column_homogeneous=True)
        self.cards: dict[str, ControlCard] = {}
        for cid, col, row in LAYOUT:
            card = ControlCard(self.device.control(cid))
            self.cards[cid] = card
            grid.attach(card, col, row, 1, 1)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(header)
        body.append(self.description)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(grid)
        body.append(scroller)
        self.toast.set_child(body)
        self.set_content(self.toast)
        self._show_selected()

    def _current(self) -> Profile:
        return self.profiles[self.picker.get_selected_item().get_string()]

    def _show_selected(self):
        p = self._current()
        self.description.set_text(f"{p.app} — {p.description}" if p.app else p.description)
        for cid, card in self.cards.items():
            card.load(p.controls.get(cid))

    def _collect(self) -> Profile:
        p = self._current()
        p.controls = {cid: card.dump() for cid, card in self.cards.items()}
        return p

    def _notify(self, msg: str):
        self.toast.add_toast(Adw.Toast(title=msg, timeout=4))

    def _save(self, *_):
        p = self._collect()
        target = user_profile_dir() / f"{p.name.lower().replace(' ', '-')}.json"
        p.save(target)
        self._notify(f"Saved {target}")

    def _apply(self, *_):
        p = self._collect()
        try:
            remapper.write_preset(self.device, p, remapper.resolve_hashes(self.device))
            r = remapper.start(self.device, p)
        except (LookupError, FileNotFoundError) as exc:
            self._notify(str(exc))
            return
        self._notify(f"Active: {p.name}" if r.returncode == 0 else f"input-remapper: {r.stderr.strip()}")

    def _stop(self, *_):
        r = remapper.stop(self.device)
        self._notify("Stopped" if r.returncode == 0 else r.stderr.strip())


def run() -> int:
    app = Adw.Application(application_id="io.github.gunnoej5.Dialtone")
    app.connect("activate", lambda a: Window(a).present())
    return app.run(None)
