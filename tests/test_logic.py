"""Smoke tests for the pure-Python logic.

These cover the platform-independent pieces so the app can be validated off a
Windows handheld (the GUI, RyzenAdj execution, and Windows scanners can't be
exercised here). Run with: ``python -m pytest`` or ``python tests/test_logic.py``.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import ryzenadj  # noqa: E402
from app import scanners  # noqa: E402
from app import weblinks  # noqa: E402


def test_watts_to_mw():
    assert ryzenadj.watts_to_mw(15) == 15000
    assert ryzenadj.watts_to_mw(12.5) == 12500


def test_clamp_tdp():
    assert ryzenadj.clamp_tdp(3, 5, 40) == 5      # below floor
    assert ryzenadj.clamp_tdp(99, 5, 40) == 40    # above ceiling
    assert ryzenadj.clamp_tdp(20, 5, 40) == 20    # in band


def test_build_command_boost_not_below_sustained():
    cmd = ryzenadj.build_command("ryzenadj.exe", 25, 10, 5, 40)
    # boost (fast-limit) should be clamped up to sustained
    assert "--stapm-limit=25000" in cmd
    assert "--fast-limit=25000" in cmd


def test_build_command_normal():
    cmd = ryzenadj.build_command("ryzenadj.exe", 20, 30, 5, 40)
    assert cmd[0] == "ryzenadj.exe"
    assert "--stapm-limit=20000" in cmd
    assert "--slow-limit=20000" in cmd
    assert "--fast-limit=30000" in cmd


def test_apply_dry_run_when_exe_missing():
    result = ryzenadj.apply_profile(
        {"tdp_sustained": 18, "tdp_boost": 22},
        {"ryzenadj_path": "definitely-not-here.exe", "min_tdp": 5, "max_tdp": 40},
    )
    assert result.dry_run is True
    assert result.ok is False
    assert any("18000" in c for c in result.command)


def test_steam_acf_parse():
    with tempfile.TemporaryDirectory() as tmp:
        common = os.path.join(tmp, "steamapps", "common")
        os.makedirs(common)
        acf = os.path.join(tmp, "steamapps", "appmanifest_550.acf")
        with open(acf, "w", encoding="utf-8") as fh:
            fh.write('"AppState"\n{\n\t"appid"\t"550"\n\t"name"\t"Left 4 Dead 2"\n}\n')
        found = scanners.scan_steam([common])
        assert any(g.name == "Left 4 Dead 2" and g.source == "Steam" for g in found)


def test_steam_acf_skips_redistributables():
    with tempfile.TemporaryDirectory() as tmp:
        common = os.path.join(tmp, "steamapps", "common")
        os.makedirs(common)
        acf = os.path.join(tmp, "steamapps", "appmanifest_228980.acf")
        with open(acf, "w", encoding="utf-8") as fh:
            fh.write('"AppState"\n{\n\t"name"\t"Steamworks Common Redistributables"\n}\n')
        found = scanners.scan_steam([common])
        assert found == []


def test_weblinks_no_scraping_just_urls():
    links = weblinks.build_links("Forza Horizon 6", {})
    labels = [l for l, _ in links]
    assert "ROG Ally Life" in labels and "rogally.games" in labels
    for _, url in links:
        assert url.startswith("http")
        assert "Forza" in url  # game name url-encoded into the query


def test_games_json_seed_is_valid():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "profiles", "games.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert "games" in doc
    assert "Left 4 Dead 2" in doc["games"]


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
