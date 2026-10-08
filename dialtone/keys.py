"""Key symbol helpers: pretty-printing, recording, and matching outputs to key events."""
from __future__ import annotations

import json
import os
from pathlib import Path

MODIFIERS = ("Control_L", "Shift_L", "Alt_L", "Super_L")
MODIFIER_KEYVALS = {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
                    "Super_L", "Super_R", "Meta_L", "Meta_R", "ISO_Level3_Shift",
                    "Caps_Lock", "Num_Lock"}

_ALIAS = {
    "prior": "pageup", "next": "pagedown", "pgup": "pageup", "pgdn": "pagedown",
    "controll": "ctrl", "controlr": "ctrl", "control": "ctrl", "leftctrl": "ctrl",
    "rightctrl": "ctrl", "shiftl": "shift", "shiftr": "shift", "leftshift": "shift",
    "rightshift": "shift", "altl": "alt", "altr": "alt", "leftalt": "alt", "rightalt": "alt",
    "superl": "super", "superr": "super", "leftmeta": "super", "rightmeta": "super",
    "return": "enter", "escape": "esc", "backspace": "backspace",
    "xf86audioraisevolume": "volumeup", "xf86audiolowervolume": "volumedown",
    "xf86audiomute": "mute", "xf86audioplay": "playpause", "xf86audionext": "nextsong",
    "xf86audioprev": "previoussong",
}
_MODS = {"ctrl", "shift", "alt", "super"}
_PRETTY = {
    "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Super",
    "pageup": "PgUp", "pagedown": "PgDn", "left": "\u2190", "right": "\u2192",
    "up": "\u2191", "down": "\u2193", "space": "Space", "delete": "Del", "enter": "Enter",
    "esc": "Esc", "home": "Home", "end": "End", "tab": "Tab", "backspace": "Bksp",
    "volumeup": "Vol+", "volumedown": "Vol\u2212", "mute": "Mute", "playpause": "Play",
    "nextsong": "Next", "previoussong": "Prev",
}


def norm(token: str) -> str:
    t = token.strip().lower()
    if t.startswith("key_"):
        t = t[4:]
    t = t.replace("_", "")
    return _ALIAS.get(t, t)


def is_macro(output: str) -> bool:
    return "(" in output and ")" in output


def parse(output: str) -> tuple[frozenset[str], str] | None:
    """'Control_L + Prior' -> ({'ctrl'}, 'pageup'). None for macros/empty."""
    if not output.strip() or is_macro(output):
        return None
    toks = [norm(t) for t in output.split("+") if t.strip()]
    mods = frozenset(t for t in toks if t in _MODS)
    rest = [t for t in toks if t not in _MODS]
    if len(rest) != 1:
        return None
    return mods, rest[0]


def pretty(output: str) -> str:
    if not output.strip():
        return ""
    if is_macro(output):
        return "macro"
    parts = [norm(t) for t in output.split("+") if t.strip()]
    return "+".join(_PRETTY.get(p, p.upper() if len(p) == 1 else p.capitalize()) for p in parts)


def known_symbols() -> set[str]:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    try:
        return set(json.loads((base / "input-remapper-2" / "xmodmap.json").read_text()))
    except (OSError, ValueError):
        return set()


def evdev_name(code: int) -> str | None:
    try:
        from evdev import ecodes
    except ImportError:
        return None
    name = ecodes.KEY.get(code)
    if isinstance(name, list):
        name = name[0]
    return name


def compose(mods: list[str], keyval_name: str | None, evcode: int,
            known: set[str] | None = None) -> str:
    """Build an input-remapper output symbol from a recorded key press."""
    known = known_symbols() if known is None else known
    if keyval_name and (keyval_name in known or not known):
        key = keyval_name
    else:
        key = evdev_name(evcode) or keyval_name or f"KEY_{evcode}"
    return " + ".join([*mods, key])


def matches(output: str, mods: set[str], candidates: set[str]) -> bool:
    parsed = parse(output)
    if parsed is None:
        return False
    want_mods, key = parsed
    return want_mods == frozenset(mods) and key in {norm(c) for c in candidates if c}
