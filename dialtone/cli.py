"""dialtone CLI: list / export / apply / stop / hash."""
from __future__ import annotations

import argparse
import sys

from . import hashing, remapper
from .model import load_devices, load_profiles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dialtone")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list devices and profiles")
    sub.add_parser("hash", help="show evdev nodes and their input-remapper origin_hash")
    for name in ("export", "apply"):
        p = sub.add_parser(name, help=f"{name} a profile to input-remapper")
        p.add_argument("profile")
        p.add_argument("--autoload", action="store_true",
                       help="load this preset at login (apply always does)")
    p = sub.add_parser("stop", help="stop injection for a device")
    p.add_argument("--device", default="ulanzi-d100h")
    sub.add_parser("gui", help="launch the GTK app")
    args = ap.parse_args(argv)

    devices, profiles = load_devices(), load_profiles()

    if args.cmd == "list":
        for d in devices.values():
            print(f"device  {d.id:16} {d.name}")
        for p in profiles.values():
            print(f"profile {p.name:16} [{p.device}] {p.description}")
        return 0
    if args.cmd == "hash":
        for n in hashing.scan():
            print(f"{n.event:8} {n.vendor}:{n.product} {n.origin_hash}  {n.name}")
        return 0
    if args.cmd == "gui":
        from .gui import run
        return run()
    if args.cmd == "stop":
        r = remapper.stop(devices[args.device])
        print(r.stdout or r.stderr, end="")
        return r.returncode

    profile = profiles.get(args.profile)
    if profile is None:
        print(f"unknown profile {args.profile!r}; try: dialtone list", file=sys.stderr)
        return 2
    device = devices[profile.device]
    path = remapper.write_preset(device, profile, remapper.resolve_hashes(device))
    print(f"wrote {path}")
    if args.autoload:
        remapper.set_autoload(device, profile)
        print(f"autoload: {device.group} -> {profile.name}")
    if args.cmd == "apply":
        r = remapper.start(device, profile)
        print(r.stdout or r.stderr, end="")
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
