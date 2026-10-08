"""Dialtone GTK4 / libadwaita app: Studio-style dial editor."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import hashing, keys, remapper, skin  # noqa: E402
from .model import (Action, Binding, Profile, load_catalogs, load_devices,  # noqa: E402
                    load_profiles)

CSS = """
:root { --accent-bg-color: #ffb000; --accent-fg-color: #141414; --accent-color: #ffb000; }
@define-color accent_bg_color #ffb000;
@define-color accent_fg_color #141414;
@define-color accent_color #ffb000;
window, .dt-center { background-color: #101114; }
.dt-sidebar, .dt-inspector { background-color: #16171b; }
.dt-caption { font-family: monospace; font-size: 8pt; font-weight: 700;
              letter-spacing: 1.5px; color: alpha(#ffffff, 0.45); }
.dt-title { font-size: 20pt; font-weight: 800; }
.dt-status { font-family: monospace; font-size: 8.5pt; color: alpha(#ffffff, 0.55); }
.dt-ok { color: #7bd88f; }
.dt-bad { color: #ff6b6b; }
.dt-kbd { font-family: monospace; font-size: 8.5pt; padding: 2px 6px; border-radius: 5px;
          background-color: alpha(#ffffff, 0.08); color: alpha(#ffffff, 0.75); }
.dt-recording { background-color: #ff4f4f; color: white; }
"""

GDK_MODS = ((Gdk.ModifierType.CONTROL_MASK, "Control_L"), (Gdk.ModifierType.SHIFT_MASK, "Shift_L"),
            (Gdk.ModifierType.ALT_MASK, "Alt_L"), (Gdk.ModifierType.SUPER_MASK, "Super_L"))


def _clear(box: Gtk.Widget) -> None:
    while (child := box.get_first_child()) is not None:
        box.remove(child)


class DialCanvas(Gtk.Widget):
    def __init__(self, on_select):
        super().__init__(hexpand=True, vexpand=True)
        self.set_size_request(720, 560)
        self.state = skin.State()
        self.painter = skin.Painter(self, skin.load_textures())
        self.on_select = on_select
        self._target = 0.0
        self._tick = None
        click = Gtk.GestureClick()
        click.connect("pressed", self._pressed)
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _c, x, y: self._hover(skin.hit(x, y, self.get_width(), self.get_height())))
        motion.connect("leave", lambda _c: self._hover(None))
        self.add_controller(motion)

    def do_snapshot(self, snapshot):
        if self.get_width() < 50 or self.get_height() < 50:
            return
        self.painter.paint(snapshot, self.get_width(), self.get_height(), self.state)

    def _pressed(self, _g, _n, x, y):
        cid = skin.hit(x, y, self.get_width(), self.get_height())
        if cid:
            self.on_select(cid)
            if cid in ("dial_cw", "dial_ccw"):
                self.spin(30 if cid == "dial_cw" else -30)

    def _hover(self, cid):
        if cid != self.state.hover:
            self.state.hover = cid
            self.set_cursor_from_name("pointer" if cid else None)
            self.queue_draw()

    def select(self, cid):
        self.state.selected = cid
        self.queue_draw()

    def flash(self, ids):
        ids = set(ids)
        self.state.lit |= ids
        self.queue_draw()

        def off():
            self.state.lit -= ids
            self.queue_draw()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(200, off)

    def spin(self, deg):
        self._target += deg
        if self._tick is None:
            self._tick = self.add_tick_callback(self._animate)

    def _animate(self, _w, _clock):
        diff = self._target - self.state.knob_angle
        if abs(diff) < 0.3:
            self.state.knob_angle = self._target
            self._tick = None
            self.queue_draw()
            return GLib.SOURCE_REMOVE
        self.state.knob_angle += diff * 0.22
        self.queue_draw()
        return GLib.SOURCE_CONTINUE


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Dialtone", default_width=1360, default_height=800)
        self.device = load_devices()["ulanzi-d100h"]
        self.catalogs = load_catalogs()
        self.profiles: list[Profile] = list(load_profiles().values())
        if not self.profiles:
            self.profiles = [Profile("New profile", self.device.id)]
        active = remapper.active_preset(self.device)
        self.profile = next((p for p in self.profiles if p.name == active), self.profiles[0])
        self.dirty: set[int] = set()
        self.selected = "dial_cw"
        self.recording = False
        self._loading = False

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(self._header())
        body = Gtk.Box()
        body.append(self._sidebar())
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self._center())
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self._inspector())
        view.set_content(body)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        keyc = Gtk.EventControllerKey()
        keyc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyc.connect("key-pressed", self._key)
        self.add_controller(keyc)

        self._fill_profiles()
        self._show_profile()
        self._refresh_status()
        GLib.timeout_add_seconds(3, self._refresh_status)

    # ---------- layout ----------
    def _header(self):
        hb = Adw.HeaderBar()
        self.wtitle = Adw.WindowTitle(title="Dialtone")
        hb.set_title_widget(self.wtitle)
        apply = Gtk.Button(label="Apply to dial", tooltip_text="Save, write the input-remapper preset and activate it")
        apply.add_css_class("suggested-action")
        apply.connect("clicked", self._apply)
        save = Gtk.Button(label="Save")
        save.connect("clicked", lambda *_: self._save())
        stop = Gtk.Button(icon_name="media-playback-stop-symbolic",
                          tooltip_text="Release the dial (factory volume/media keys)")
        stop.connect("clicked", self._stop)
        hb.pack_end(apply)
        hb.pack_end(save)
        hb.pack_start(stop)
        return hb

    def _sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=230, spacing=6)
        box.add_css_class("dt-sidebar")
        cap = Gtk.Label(label="PROFILES", xalign=0, margin_start=16, margin_top=14)
        cap.add_css_class("dt-caption")
        box.append(cap)
        self.plist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.plist.add_css_class("navigation-sidebar")
        self.plist.connect("row-selected", self._profile_selected)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.plist)
        box.append(sc)
        btns = Gtk.Box(spacing=6, margin_start=10, margin_end=10, margin_bottom=10, homogeneous=True)
        dup = Gtk.Button(label="Duplicate")
        dup.connect("clicked", lambda *_: self._new_profile(copy=True))
        new = Gtk.Button(label="New")
        new.connect("clicked", lambda *_: self._new_profile(copy=False))
        btns.append(dup)
        btns.append(new)
        box.append(btns)
        return box

    def _center(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        box.add_css_class("dt-center")
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=24, margin_end=24, margin_top=16, spacing=2)
        self.name_edit = Gtk.EditableLabel(xalign=0)
        self.name_edit.add_css_class("dt-title")
        self.name_edit.connect("notify::editing", self._renamed)
        self.desc = Gtk.Label(xalign=0, wrap=True)
        self.desc.add_css_class("dim-label")
        head.append(self.name_edit)
        head.append(self.desc)
        box.append(head)
        self.canvas = DialCanvas(self._select)
        box.append(self.canvas)
        bar = Gtk.Box(spacing=16, margin_start=24, margin_end=24, margin_bottom=12, margin_top=4)
        self.dev_status = Gtk.Label(xalign=0)
        self.dev_status.add_css_class("dt-status")
        hint = Gtk.Label(label="click a control to edit  \u00b7  press the real dial here to test", hexpand=True, xalign=1)
        hint.add_css_class("dt-status")
        bar.append(self.dev_status)
        bar.append(hint)
        box.append(bar)
        return box

    def _inspector(self):
        outer = Gtk.ScrolledWindow(width_request=380, hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.add_css_class("dt-inspector")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                      margin_start=18, margin_end=18, margin_top=16, margin_bottom=18)
        cap = Gtk.Label(label="CONTROL", xalign=0)
        cap.add_css_class("dt-caption")
        self.ctl_title = Gtk.Label(xalign=0)
        self.ctl_title.add_css_class("title-2")
        self.ctl_default = Gtk.Label(xalign=0, wrap=True)
        self.ctl_default.add_css_class("dim-label")
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for w in (cap, self.ctl_title, self.ctl_default):
            head.append(w)
        box.append(head)

        grp = Adw.PreferencesGroup(title="Mapping")
        clear = Gtk.Button(icon_name="edit-clear-all-symbolic", tooltip_text="Unassign", valign=Gtk.Align.CENTER)
        clear.add_css_class("flat")
        clear.connect("clicked", lambda *_: self._assign(Action("", "")))
        grp.set_header_suffix(clear)
        self.row_label = Adw.EntryRow(title="Overlay name")
        self.row_output = Adw.EntryRow(title="Sends (input-remapper syntax)")
        for r in (self.row_label, self.row_output):
            r.connect("changed", self._edited)
            grp.add(r)
        rec = Adw.ActionRow(title="Record shortcut", subtitle="Press the keys this control should send")
        self.rec_btn = Gtk.ToggleButton(label="Record", valign=Gtk.Align.CENTER)
        self.rec_btn.connect("toggled", self._toggle_record)
        rec.add_suffix(self.rec_btn)
        grp.add(rec)
        box.append(grp)

        lib_cap = Gtk.Label(label="ACTION LIBRARY", xalign=0)
        lib_cap.add_css_class("dt-caption")
        self.search = Gtk.SearchEntry(placeholder_text="Search actions")
        self.search.connect("search-changed", lambda *_: self._build_library())
        self.lib = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.append(lib_cap)
        box.append(self.search)
        box.append(self.lib)
        outer.set_child(box)
        return outer

    # ---------- state ----------
    def _fill_profiles(self):
        _clear(self.plist)
        for p in self.profiles:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=4, margin_bottom=4)
            name = Gtk.Label(label=p.name + ("  \u2022" if id(p) in self.dirty else ""), xalign=0)
            name.add_css_class("heading")
            sub = Gtk.Label(label=(p.app or "custom") + ("" if not p.is_user() else "  \u00b7  yours"), xalign=0)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            row.append(name)
            row.append(sub)
            self.plist.append(row)
        self.plist.select_row(self.plist.get_row_at_index(self.profiles.index(self.profile)))

    def _profile_selected(self, _lb, row):
        if row is None:
            return
        p = self.profiles[row.get_index()]
        if p is not self.profile:
            self.profile = p
            self._show_profile()

    def _show_profile(self):
        p = self.profile
        self.name_edit.set_text(p.name)
        self.desc.set_text(" \u2014 ".join(x for x in (p.app, p.description) if x) or "No description")
        self._refresh_callouts()
        self._select(self.selected)
        self._update_title()

    def _update_title(self):
        dirty = id(self.profile) in self.dirty
        self.wtitle.set_subtitle(self.profile.name + ("  \u2022 unsaved" if dirty else ""))

    def _mark_dirty(self):
        if id(self.profile) not in self.dirty:
            self.dirty.add(id(self.profile))
            self._fill_profiles()
        self._update_title()

    def _refresh_callouts(self):
        out = {}
        for cid in skin.CONTROLS:
            b = self.profile.controls.get(cid)
            if b and b.output.strip():
                out[cid] = skin.Callout(skin.SHORT[cid], b.label or keys.pretty(b.output),
                                        keys.pretty(b.output) if b.label else "")
            else:
                out[cid] = skin.Callout(skin.SHORT[cid], "+ assign", mapped=False)
        self.canvas.state.callouts = out
        self.canvas.queue_draw()

    def _select(self, cid):
        self.selected = cid
        self.canvas.select(cid)
        c = self.device.control(cid)
        self.ctl_title.set_text(c.label)
        self.ctl_default.set_text(f"Factory default: {c.default}")
        b = self.profile.controls.get(cid) or Binding("")
        self._loading = True
        self.row_label.set_text(b.label)
        self.row_output.set_text(b.output)
        self._loading = False
        self._build_library()

    def _edited(self, *_):
        if self._loading:
            return
        self.profile.controls[self.selected] = Binding(self.row_output.get_text().strip(),
                                                       self.row_label.get_text().strip())
        self._mark_dirty()
        self._refresh_callouts()

    def _assign(self, action: Action):
        self._loading = True
        self.row_output.set_text(action.output)
        self.row_label.set_text(action.label)
        self._loading = False
        self._edited()
        self._build_library()

    def _build_library(self):
        _clear(self.lib)
        q = self.search.get_text().strip().lower()
        current = (self.profile.controls.get(self.selected) or Binding("")).output
        cats = sorted(self.catalogs, key=lambda c: not c.applies_to(self.profile.app))
        for cat in cats:
            for gname, actions in cat.groups:
                hits = [a for a in actions if not q or q in a.label.lower() or q in a.output.lower()]
                if not hits:
                    continue
                grp = Adw.PreferencesGroup(title=f"{cat.name} \u00b7 {gname}")
                for a in hits:
                    row = Adw.ActionRow(title=a.label, activatable=True)
                    kbd = Gtk.Label(label=keys.pretty(a.output), valign=Gtk.Align.CENTER)
                    kbd.add_css_class("dt-kbd")
                    row.add_suffix(kbd)
                    if a.output == current:
                        row.add_prefix(Gtk.Image(icon_name="object-select-symbolic"))
                    row.connect("activated", lambda _r, a=a: self._assign(a))
                    grp.add(row)
                self.lib.append(grp)

    # ---------- keys ----------
    def _toggle_record(self, btn):
        self.recording = btn.get_active()
        btn.set_label("Press keys\u2026" if self.recording else "Record")
        (btn.add_css_class if self.recording else btn.remove_css_class)("dt-recording")

    def _key(self, _c, keyval, keycode, state):
        name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval))
        if name in keys.MODIFIER_KEYVALS:
            return False
        mods = [sym for mask, sym in GDK_MODS if state & mask]
        evcode = keycode - 8
        if self.recording:
            if name == "Escape" and not mods:
                self.rec_btn.set_active(False)
                return True
            out = keys.compose(mods, name, evcode)
            self.row_output.set_text(out)
            if not self.row_label.get_text():
                self.row_label.set_text(keys.pretty(out))
            self.rec_btn.set_active(False)
            return True
        cands = {name, Gdk.keyval_name(keyval), keys.evdev_name(evcode)}
        normmods = {keys.norm(m) for m in mods}
        hits = [cid for cid, b in self.profile.controls.items()
                if keys.matches(b.output, normmods, cands)]
        if hits:
            self.canvas.flash(hits)
            if "dial_cw" in hits:
                self.canvas.spin(15)
            if "dial_ccw" in hits:
                self.canvas.spin(-15)
        return False

    # ---------- actions ----------
    def _new_profile(self, copy: bool):
        base = f"{self.profile.name} copy" if copy else "New profile"
        name, n = base, 2
        while any(p.name == name for p in self.profiles):
            name, n = f"{base} {n}", n + 1
        p = self.profile.copy(name) if copy else Profile(name, self.device.id, app=self.profile.app)
        self.profiles.append(p)
        self.profile = p
        self.dirty.add(id(p))
        self._fill_profiles()
        self._show_profile()

    def _renamed(self, *_):
        if self.name_edit.get_editing():
            return
        new = self.name_edit.get_text().strip()
        if not new or new == self.profile.name:
            self.name_edit.set_text(self.profile.name)
            return
        if any(p.name == new for p in self.profiles):
            self._toast(f"A profile named \u201c{new}\u201d already exists")
            self.name_edit.set_text(self.profile.name)
            return
        self.profile.name = new
        if not self.profile.is_user():
            self.profile.path = None
        self._mark_dirty()
        self._fill_profiles()

    def _save(self) -> bool:
        p = self.profile
        try:
            path = p.save(p.default_path())
        except OSError as exc:
            self._toast(f"Save failed: {exc}")
            return False
        self.dirty.discard(id(p))
        self._fill_profiles()
        self._update_title()
        self._toast(f"Saved {path.name}")
        return True

    def _apply(self, *_):
        if not self._save():
            return
        p = self.profile
        try:
            remapper.write_preset(self.device, p, remapper.resolve_hashes(self.device))
            r = remapper.start(self.device, p)
        except (LookupError, FileNotFoundError) as exc:
            self._toast(str(exc))
            return
        self._toast(f"\u201c{p.name}\u201d is live on the dial" if r.returncode == 0
                    else f"input-remapper: {(r.stderr or r.stdout).strip()[-200:]}")
        self._refresh_status()

    def _stop(self, *_):
        r = remapper.stop(self.device)
        self._toast("Dial released \u2014 factory keys restored" if r.returncode == 0 else r.stderr.strip())
        self._refresh_status()

    def _toast(self, msg):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(msg), timeout=4))

    def _refresh_status(self):
        nodes = hashing.find(self.device.subdevices["keyboard"], self.device.vendor, self.device.product)
        active = remapper.active_preset(self.device) or "none"
        conn = "\u25cf connected" if nodes else "\u25cb not connected"
        self.dev_status.set_text(f"{self.device.name.split(' Dial')[0]}  {conn}   \u00b7   live preset: {active}")
        for cls in ("dt-ok", "dt-bad"):
            self.dev_status.remove_css_class(cls)
        self.dev_status.add_css_class("dt-ok" if nodes else "dt-bad")
        return GLib.SOURCE_CONTINUE


def _screenshot(win: Gtk.Window, path: str, app: Adw.Application) -> bool:
    w, h = win.get_width(), win.get_height()
    paintable = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    if node is not None:
        win.get_renderer().render_texture(node, None).save_to_png(path)
    app.quit()
    return GLib.SOURCE_REMOVE


def run() -> int:
    app = Adw.Application(application_id="io.github.gunnoej5.Dialtone")

    def activate(a):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = a.get_active_window() or Window(a)
        win.present()
        shot = os.environ.get("DIALTONE_SCREENSHOT")
        if shot:
            GLib.timeout_add(1500, _screenshot, win, shot, a)

    app.connect("activate", activate)
    return app.run(None)
