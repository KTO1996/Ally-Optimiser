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
from app import sysinfo  # noqa: E402
from app import systweaks  # noqa: E402
from app import armoury  # noqa: E402
from app import boost  # noqa: E402
from app import hibernate  # noqa: E402
from app.tweakengine import TweakEngine  # noqa: E402


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


def test_classify_model():
    assert sysinfo.classify_model("RC71L") == sysinfo.ALLY
    assert sysinfo.classify_model("RC72LA") == sysinfo.ALLY_X
    assert sysinfo.classify_model("RC73XA", 24) == sysinfo.ALLY_X   # Z2, lots of RAM
    assert sysinfo.classify_model("RC73", 16) == sysinfo.ALLY        # Z2, base RAM
    assert sysinfo.classify_model("Some Desktop") == sysinfo.UNKNOWN


def test_device_tdp_profile_differs():
    ally = sysinfo.DeviceInfo(model=sysinfo.ALLY)
    allyx = sysinfo.DeviceInfo(model=sysinfo.ALLY_X)
    assert allyx.tdp_profile["max"] > ally.tdp_profile["max"]


def test_tweak_catalogue_integrity():
    tweaks = systweaks.all_tweaks()
    ids = [t.id for t in tweaks]
    assert len(ids) == len(set(ids)), "tweak ids must be unique"
    valid_risk = {systweaks.SAFE, systweaks.AGGRESSIVE, systweaks.EXPERIMENTAL}
    for t in tweaks:
        assert t.risk in valid_risk
        # Every tweak must actually do something.
        assert t.reg or t.apply_cmds
        # Registry tweaks are reversible from captured state; command tweaks
        # must carry an inverse OR be explicitly flagged non-reversible.
        if t.apply_cmds and not t.reg:
            assert t.revert_cmds or not t.reversible


def test_engine_dry_run_apply_revert_roundtrip():
    eng = TweakEngine(dry_run=True)
    tw = next(t for t in systweaks.all_tweaks() if t.id == "game_mode_on")
    applied = eng.apply(tw)
    assert applied.ok and applied.dry_run
    assert eng.state[tw.id]["applied"] is True
    reverted = eng.revert(tw)
    assert reverted.ok and reverted.dry_run
    assert eng.state[tw.id]["applied"] is False


def test_engine_dry_run_writes_no_state_file():
    # Dry-run must never touch the real state file on disk.
    from app import tweakengine
    before = os.path.exists(tweakengine.STATE_FILE)
    eng = TweakEngine(dry_run=True)
    eng.apply(systweaks.all_tweaks()[0])
    assert os.path.exists(tweakengine.STATE_FILE) == before


def test_armoury_checklist_and_links():
    items = armoury.checklist(sysinfo.DeviceInfo(model=sysinfo.ALLY_X))
    assert any("TDP" in i.title for i in items)
    assert any(i.native for i in items)          # some are replicable natively
    links = armoury.deep_links()
    assert any(l.kind == "app" for l in links)    # launch Armoury Crate
    assert any(l.target.startswith("ms-settings:") for l in links)


def test_boost_native_guides():
    guides = boost.native_boost_guides()
    titles = " ".join(g.title for g in guides)
    assert "AFMF" in titles and "RSR" in titles and "FSR" in titles
    assert any(g.native for g in guides)
    assert any(not g.native for g in guides)   # Lossless Scaling is third-party


def test_boost_detect_lossless_scaling(tmp_path=None):
    with tempfile.TemporaryDirectory() as tmp:
        steamapps = os.path.join(tmp, "steamapps")
        common = os.path.join(steamapps, "common")
        os.makedirs(common)
        # Absent first.
        assert boost.detect_lossless_scaling([common]).installed is False
        # Present once the manifest exists.
        open(os.path.join(steamapps, f"appmanifest_{boost.LOSSLESS_SCALING_APPID}.acf"),
             "w").close()
        st = boost.detect_lossless_scaling([common])
        assert st.installed is True and st.path.startswith("steam://")


def test_boost_fse_dry_run():
    res = boost.set_fse(r"C:\Games\game.exe", True, dry_run=True)
    assert res.ok and res.dry_run
    assert any("game.exe" in a for a in res.actions)


def test_hibernate_commands_dry_run():
    assert hibernate.set_enabled(True, dry_run=True).actions == ["powercfg /hibernate on"]
    assert hibernate.set_enabled(False, dry_run=True).actions == ["powercfg /hibernate off"]
    r = hibernate.set_auto_hibernate_timeout(30, dry_run=True)
    assert r.ok and any("30" in a for a in r.actions)
    assert hibernate.hibernate_now(dry_run=True).actions == ["shutdown /h"]
    pb = hibernate.set_power_button_hibernate(dry_run=True)
    # Each button action is set to index 2 (hibernate) via powercfg.
    assert pb.ok and all("powercfg" in a for a in pb.actions)
    assert any(a.endswith(hibernate.ACTION_HIBERNATE) for a in pb.actions)


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
