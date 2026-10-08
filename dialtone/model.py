"""Device definitions and mapping profiles (Dialtone's own JSON format)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_DEVICES = PKG_ROOT / "devices"
BUILTIN_PROFILES = PKG_ROOT / "profiles"
BUILTIN_ACTIONS = PKG_ROOT / "actions"


@dataclass
class Control:
    id: str
    label: str
    default: str
    subdevice: str
    codes: list[int]


@dataclass
class Device:
    id: str
    name: str
    vendor: str
    product: str
    group: str
    subdevices: dict[str, str]
    controls: list[Control]

    @classmethod
    def load(cls, path: Path) -> "Device":
        raw = json.loads(path.read_text())
        return cls(
            id=raw["id"], name=raw["name"],
            vendor=raw["usb"]["vendor"], product=raw["usb"]["product"],
            group=raw["input_remapper_group"],
            subdevices={k: v["name"] for k, v in raw["subdevices"].items()},
            controls=[Control(**c) for c in raw["controls"]],
        )

    def control(self, control_id: str) -> Control:
        for c in self.controls:
            if c.id == control_id:
                return c
        raise KeyError(control_id)


@dataclass
class Binding:
    output: str
    label: str = ""


@dataclass
class Profile:
    name: str
    device: str
    app: str = ""
    description: str = ""
    controls: dict[str, Binding] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "Profile":
        raw = json.loads(path.read_text())
        if raw.get("schema") != 1:
            raise ValueError(f"{path}: unsupported schema {raw.get('schema')!r}")
        return cls(
            name=raw["name"], device=raw["device"], app=raw.get("app", ""),
            description=raw.get("description", ""),
            controls={k: Binding(**v) for k, v in raw.get("controls", {}).items()},
            path=path,
        )

    def to_json(self) -> str:
        data = {
            "schema": 1, "name": self.name, "device": self.device,
            "app": self.app, "description": self.description,
            "controls": {k: {"output": b.output, "label": b.label}
                         for k, b in self.controls.items() if b.output},
        }
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    def copy(self, name: str) -> "Profile":
        return Profile(name=name, device=self.device, app=self.app,
                       description=self.description,
                       controls={k: Binding(b.output, b.label) for k, b in self.controls.items()})

    def is_user(self) -> bool:
        return self.path is not None and user_profile_dir() in self.path.parents

    def default_path(self) -> Path:
        if self.is_user():
            return self.path
        slug = "".join(ch if ch.isalnum() else "-" for ch in self.name.lower()).strip("-")
        return user_profile_dir() / f"{slug or 'profile'}.json"

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path for profile")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json())
        self.path = target
        return target


def user_profile_dir() -> Path:
    from os import environ
    base = Path(environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "dialtone" / "profiles"


@dataclass
class Action:
    label: str
    output: str


@dataclass
class Catalog:
    name: str
    match: str
    groups: list[tuple[str, list[Action]]]

    def applies_to(self, app: str) -> bool:
        return bool(self.match) and self.match.lower() in app.lower()


def load_catalogs(folder: Path = BUILTIN_ACTIONS) -> list[Catalog]:
    out = []
    for path in sorted(folder.glob("*.json")):
        raw = json.loads(path.read_text())
        out.append(Catalog(raw["name"], raw.get("match", ""),
                           [(g["name"], [Action(**a) for a in g["actions"]]) for g in raw["groups"]]))
    return out


def load_devices() -> dict[str, Device]:
    return {d.id: d for d in (Device.load(p) for p in sorted(BUILTIN_DEVICES.glob("*.json")))}


def load_profiles() -> dict[str, Profile]:
    """User profiles override built-ins with the same name."""
    profiles: dict[str, Profile] = {}
    for folder in (BUILTIN_PROFILES, user_profile_dir()):
        for p in sorted(folder.glob("*.json")) if folder.exists() else []:
            prof = Profile.load(p)
            profiles[prof.name] = prof
    return profiles
