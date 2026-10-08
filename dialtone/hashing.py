"""Compute input-remapper origin_hash values without root.

input-remapper identifies a source evdev node by
md5(str(device.capabilities(absinfo=False)) + device.name). Reading that via
python-evdev needs read access to /dev/input/eventN (root or the input group).
The same capability bitmaps are world-readable in sysfs, so we rebuild the
exact dict python-evdev would return. Verified against a hash recorded by the
input-remapper GUI for the D100H keyboard node.

python-evdev quirks reproduced here:
  * EV_SYN (0) is listed with the supported event *types* as its codes.
  * EV_REP (20) is omitted (EVIOCGBIT for EV_REP is not a code bitmap).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SYSFS_INPUT = Path("/sys/class/input")
_CAP_FILES = {1: "key", 2: "rel", 3: "abs", 4: "msc", 5: "sw", 17: "led", 18: "snd", 21: "ff"}
EV_SYN, EV_REP = 0, 20


def parse_bitmap(text: str) -> list[int]:
    """Parse a sysfs capability bitmap (space separated hex words, MSW first)."""
    words = text.split()[::-1]
    out: list[int] = []
    for index, word in enumerate(words):
        value = int(word, 16)
        for bit in range(64):
            if value >> bit & 1:
                out.append(index * 64 + bit)
    return out


def capabilities_from_sysfs(cap_dir: Path) -> dict[int, list[int]]:
    ev_types = parse_bitmap((cap_dir / "ev").read_text())
    caps: dict[int, list[int]] = {}
    for ev_type in ev_types:
        if ev_type == EV_SYN:
            caps[EV_SYN] = list(ev_types)
        elif ev_type == EV_REP:
            continue
        elif ev_type in _CAP_FILES:
            path = cap_dir / _CAP_FILES[ev_type]
            caps[ev_type] = parse_bitmap(path.read_text()) if path.exists() else []
    return caps


def origin_hash(name: str, caps: dict[int, list[int]]) -> str:
    return hashlib.md5((str(caps) + name).encode()).hexdigest().lower()


@dataclass(frozen=True)
class EvdevNode:
    event: str          # e.g. "event24"
    name: str
    vendor: str
    product: str
    uniq: str
    origin_hash: str


def scan(sysfs: Path = SYSFS_INPUT) -> list[EvdevNode]:
    nodes = []
    for entry in sorted(sysfs.glob("event*")):
        dev = entry / "device"
        try:
            name = (dev / "name").read_text().strip()
            caps = capabilities_from_sysfs(dev / "capabilities")
            ident = dev / "id"
            vendor = (ident / "vendor").read_text().strip()
            product = (ident / "product").read_text().strip()
            uniq_path = dev / "uniq"
            uniq = uniq_path.read_text().strip() if uniq_path.exists() else ""
        except OSError:
            continue
        nodes.append(EvdevNode(entry.name, name, vendor, product, uniq, origin_hash(name, caps)))
    return nodes


def find(name: str, vendor: str | None = None, product: str | None = None,
         sysfs: Path = SYSFS_INPUT) -> list[EvdevNode]:
    return [n for n in scan(sysfs)
            if n.name == name
            and (vendor is None or n.vendor.lower() == vendor.lower())
            and (product is None or n.product.lower() == product.lower())]
