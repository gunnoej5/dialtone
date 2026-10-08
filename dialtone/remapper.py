"""Export Dialtone profiles as input-remapper 2.x presets and drive the daemon."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import hashing
from .model import Device, Profile

EV_KEY = 1


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "input-remapper-2"


def resolve_hashes(device: Device, sysfs: Path = hashing.SYSFS_INPUT) -> dict[str, str]:
    """Map subdevice key -> origin_hash for the connected device."""
    out = {}
    for key, name in device.subdevices.items():
        nodes = hashing.find(name, device.vendor, device.product, sysfs)
        hashes = {n.origin_hash for n in nodes}
        if len(hashes) != 1:
            raise LookupError(f"expected one evdev node for {name!r}, found {len(nodes)}"
                              " - is the dial connected?")
        out[key] = hashes.pop()
    return out


def build_preset(device: Device, profile: Profile, hashes: dict[str, str]) -> list[dict]:
    mappings = []
    for control in device.controls:
        binding = profile.controls.get(control.id)
        if binding is None or not binding.output.strip():
            continue
        mappings.append({
            "input_combination": [
                {"type": EV_KEY, "code": code, "origin_hash": hashes[control.subdevice]}
                for code in control.codes
            ],
            "target_uinput": "keyboard",
            "output_symbol": binding.output,
            "name": binding.label or control.label,
            "mapping_type": "key_macro",
        })
    return mappings


def preset_path(device: Device, profile: Profile) -> Path:
    safe = profile.name.replace("/", "-")
    return config_dir() / "presets" / device.group / f"{safe}.json"


def write_preset(device: Device, profile: Profile, hashes: dict[str, str]) -> Path:
    path = preset_path(device, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(build_preset(device, profile, hashes), indent=4) + "\n")
    return path


def set_autoload(device: Device, profile: Profile) -> None:
    """Merge into config.json; never drops other devices' autoload entries."""
    path = config_dir() / "config.json"
    data = json.loads(path.read_text()) if path.exists() else {"version": "2.2.0"}
    data.setdefault("autoload", {})[device.group] = profile.name
    path.write_text(json.dumps(data, indent=4) + "\n")


def _control(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("input-remapper-control")
    if not exe:
        raise FileNotFoundError("input-remapper-control not found; install input-remapper")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)


def start(device: Device, profile: Profile) -> subprocess.CompletedProcess:
    """Activate a preset.

    `--command start --device X` makes the *client* enumerate /dev/input, which fails
    without root or the input group. `autoload` is resolved by the root daemon instead,
    so: point autoload at the profile, stop (autoload skips an unchanged preset name),
    then autoload.
    """
    set_autoload(device, profile)
    stop(device)
    return _control("--command", "autoload")


def stop(device: Device) -> subprocess.CompletedProcess:
    return _control("--command", "stop", "--device", device.group)
