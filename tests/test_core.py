import json
from pathlib import Path

from dialtone import hashing, remapper
from dialtone.model import Profile, load_devices, BUILTIN_PROFILES

# Capability bitmaps captured from a real D100H keyboard node (sysfs).
D100H_KBD = {
    "ev": "12001f",
    "key": "3f00733fff 0 0 483ffff17aff32d bfd4444600000000 1 130ff38b17d007 "
           "ffff7bfad9415fff ffbeffdfffefffff fffffffffffffffe",
    "rel": "1040", "abs": "100000000", "msc": "10", "led": "1f", "sw": "0",
}
# Hash recorded by the input-remapper 2.2 GUI for that node.
KNOWN_HASH = "80fd316df255f6cc283357cf7e8865f9"


def fake_sysfs(tmp_path: Path) -> Path:
    dev = tmp_path / "event24" / "device"
    (dev / "capabilities").mkdir(parents=True)
    (dev / "id").mkdir()
    (dev / "name").write_text("Ulanzi Dial Keyboard\n")
    (dev / "id" / "vendor").write_text("fff1\n")
    (dev / "id" / "product").write_text("0082\n")
    for k, v in D100H_KBD.items():
        (dev / "capabilities" / k).write_text(v + "\n")
    return tmp_path


def test_hash_matches_input_remapper(tmp_path):
    nodes = hashing.find("Ulanzi Dial Keyboard", "fff1", "0082", fake_sysfs(tmp_path))
    assert [n.origin_hash for n in nodes] == [KNOWN_HASH]


def test_builtin_profiles_cover_known_controls():
    device = load_devices()["ulanzi-d100h"]
    ids = {c.id for c in device.controls}
    for path in BUILTIN_PROFILES.glob("*.json"):
        assert set(Profile.load(path).controls) <= ids, path


def test_preset_shape(tmp_path):
    device = load_devices()["ulanzi-d100h"]
    profile = Profile.load(BUILTIN_PROFILES / "avidemux.json")
    hashes = remapper.resolve_hashes(device, fake_sysfs(tmp_path))
    preset = remapper.build_preset(device, profile, hashes)
    assert len(preset) == 10
    marker_a = next(m for m in preset if m["name"] == "Set marker A")
    assert [e["code"] for e in marker_a["input_combination"]] == [29, 47]
    assert marker_a["output_symbol"] == "Control_L + Prior"
    json.dumps(preset)
