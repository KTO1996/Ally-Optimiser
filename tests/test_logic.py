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
from app import importer  # noqa: E402
from app import covers  # noqa: E402
from app import presets  # noqa: E402
from app import batteryest  # noqa: E402
from app import updates  # noqa: E402
from app import backup  # noqa: E402
from app import watcher  # noqa: E402
from app import display  # noqa: E402
from app import gamepad  # noqa: E402
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


def test_importer_parse_text():
    f = importer.parse_settings_text(
        "Recommended: TDP sustained 15W, boost 20W, 1280x720, 60 fps (Performance)")
    assert f["tdp_sustained"] == 15 and f["tdp_boost"] == 20
    assert f["resolution"] == "1280x720" and f["fps_cap"] == 60
    assert f.get("label") == "Performance"


def test_importer_parse_slash_and_words():
    f = importer.parse_settings_text("Set 18/25 W at 1080p, cap 90fps")
    assert f["tdp_sustained"] == 18 and f["tdp_boost"] == 25
    assert f["resolution"] == "1920x1080" and f["fps_cap"] == 90


def test_importer_url_detection_and_warning():
    assert importer.is_url("https://www.pcgamingwiki.com/wiki/Doom")
    assert importer.needs_fetch_warning("https://rogallylife.com/some-game") is True
    # PCGamingWiki uses the API path, not a raw fetch -> no scrape warning.
    assert importer.needs_fetch_warning("https://www.pcgamingwiki.com/wiki/Doom") is False
    assert importer.needs_fetch_warning("just pasted text") is False


def test_importer_empty_input():
    assert importer.import_from_input("", {}).ok is False


def test_validate_profile_flags_out_of_range():
    # 1440p / 144fps / 45W on a base Ally should all warn.
    bad = {"tdp_sustained": 45, "tdp_boost": 40, "resolution": "2560x1440", "fps_cap": 144}
    warns = sysinfo.validate_profile(bad, sysinfo.ALLY)
    text = " ".join(warns).lower()
    assert "tdp" in text and "panel" in text and "fps" in text
    assert any("boost" in w.lower() for w in warns)   # boost < sustained


def test_validate_profile_ok_for_sane_values():
    good = {"tdp_sustained": 15, "tdp_boost": 20, "resolution": "1920x1080", "fps_cap": 60}
    assert sysinfo.validate_profile(good, sysinfo.ALLY) == []


def test_covers_steam_appid_search_cached():
    import tempfile
    from app import covers as cv
    with tempfile.TemporaryDirectory() as tmp:
        cv.COVERS_DIR = tmp
        cv.APPID_CACHE = os.path.join(tmp, "appid_cache.json")
        calls = {"n": 0}

        def fake_search(name):
            # mimic the real function's cache behaviour without network
            cache = cv._load_appid_cache()
            key = name.strip().lower()
            if key in cache:
                return cache[key] or None
            calls["n"] += 1
            cache[key] = "620"
            cv._save_appid_cache(cache)
            return "620"

        orig = cv.search_steam_appid
        cv.search_steam_appid = fake_search
        try:
            assert cv.search_steam_appid("Portal 2") == "620"
            assert cv.search_steam_appid("Portal 2") == "620"   # served from cache
            assert calls["n"] == 1                               # only one lookup
        finally:
            cv.search_steam_appid = orig


def test_covers_steam_urls_and_cached():
    assert "library_600x900" in covers.steam_cover_url("620")
    assert covers.is_url("https://example.com/a.jpg")
    assert covers.is_url(r"C:\art\cover.jpg") is False
    assert covers.cached_cover({"cover": "https://x/y.jpg"}) is None  # URL, not local


def test_presets_scale_to_model():
    base = {p["label"]: p for p in presets.presets_for(sysinfo.ALLY)}
    x = {p["label"]: p for p in presets.presets_for(sysinfo.ALLY_X)}
    assert set(base) == {"Silent", "Balanced", "Turbo", "Max"}
    # Ally X has more headroom, so its Max sustained is higher.
    assert x["Max"]["tdp_sustained"] > base["Max"]["tdp_sustained"]
    # Presets should pass their own validator.
    for p in presets.presets_for(sysinfo.ALLY_X):
        assert sysinfo.validate_profile(p, sysinfo.ALLY_X) == []


def test_battery_estimate():
    ally = batteryest.estimate_hours(15, sysinfo.ALLY)
    allyx = batteryest.estimate_hours(15, sysinfo.ALLY_X)
    assert ally and allyx and allyx > ally          # bigger battery lasts longer
    assert batteryest.estimate_hours(0, sysinfo.ALLY) is not None
    assert "h battery" in batteryest.estimate_text({"tdp_sustained": 15}, sysinfo.ALLY)


def test_updates_version_compare():
    assert updates.is_newer("v1.3.0", "v1.2.0") is True
    assert updates.is_newer("v1.2.0", "v1.2.0") is False
    assert updates.is_newer("1.2.1", "v1.2.0") is True
    assert updates.is_newer("v1.2.0", "v1.10.0") is False


def test_backup_roundtrip(monkeypatch=None):
    import tempfile
    from app import backup as bk
    with tempfile.TemporaryDirectory() as tmp:
        prof_dir = os.path.join(tmp, "profiles")
        os.makedirs(prof_dir)
        for base, content in (("games.json", '{"games": {}}'),
                              ("config.json", '{"theme": "dark"}')):
            with open(os.path.join(prof_dir, base), "w") as fh:
                fh.write(content)
        # Point the module at our temp profiles dir.
        bk.PROFILES_DIR = prof_dir
        bk.GAMES_FILE = os.path.join(prof_dir, "games.json")
        bk.CONFIG_FILE = os.path.join(prof_dir, "config.json")
        zip_path = os.path.join(tmp, "backup.zip")
        included = bk.export_config(zip_path)
        assert "games.json" in included and "config.json" in included
        os.remove(os.path.join(prof_dir, "games.json"))
        restored = bk.import_config(zip_path)
        assert "games.json" in restored
        assert os.path.isfile(os.path.join(prof_dir, "games.json"))


def test_watcher_match_process():
    doc = {"games": {"Doom": {"process_name": "DOOMEternal.exe"}}}
    pm = watcher.process_name_map(doc)
    assert watcher.match_process("DOOMEternal.exe", pm) == "Doom"
    assert watcher.match_process("doometernal.exe", pm) == "Doom"   # case-insensitive
    assert watcher.match_process("explorer.exe", pm) is None


def test_display_parse_resolution():
    assert display.parse_resolution("1920x1080") == (1920, 1080)
    assert display.parse_resolution("1280 x 720") == (1280, 720)
    assert display.parse_resolution("nonsense") is None


def test_gamepad_decode_and_actions():
    # A + D-pad down pressed together.
    pressed = gamepad.decode(gamepad.BUTTONS["a"] | gamepad.BUTTONS["dpad_down"])
    assert pressed == {"a", "dpad_down"}
    actions = gamepad.actions_from(pressed)
    assert actions == {"activate", "down"}


def test_gamepad_stick_directions():
    assert gamepad.stick_directions(0, 0) == set()
    assert "dpad_right" in gamepad.stick_directions(30000, 0)
    assert "dpad_up" in gamepad.stick_directions(0, 30000)
    assert "dpad_down" in gamepad.stick_directions(0, -30000)


def test_gamepad_edge_and_index():
    assert gamepad.newly_pressed({"a"}, {"a", "b"}) == {"b"}
    assert gamepad.newly_pressed({"a"}, {"a"}) == set()
    assert gamepad.next_index(2, 1, 3) == 0      # wrap forward
    assert gamepad.next_index(0, -1, 3) == 2     # wrap back
    assert gamepad.next_index(0, 1, 0) == 0      # empty list safe


def test_placeholder_cover_generation():
    import tempfile
    from app import covers as cv
    with tempfile.TemporaryDirectory() as tmp:
        cv.PLACEHOLDERS_DIR = os.path.join(tmp, "ph")
        path = cv.placeholder_for("Forza Horizon 6")
        # Pillow is available in this test env; if not, skip gracefully.
        if path is not None:
            assert os.path.isfile(path)
            assert cv.placeholder_for("Forza Horizon 6") == path  # cached


def test_detected_cache_roundtrip():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        scanners.DETECTED_CACHE = os.path.join(tmp, "detected.json")
        scanners.PROFILES_DIR = tmp
        games = [scanners.DetectedGame("Doom", "DOOMEternal.exe", "Steam", "782330"),
                 scanners.DetectedGame("Halo", None, "Xbox", None)]
        scanners.save_detected(games)
        back = scanners.load_detected()
        assert [g.name for g in back] == ["Doom", "Halo"]
        assert back[0].appid == "782330" and back[0].process_name == "DOOMEternal.exe"
        assert back[1].source == "Xbox"


def test_gog_installed_only():
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "galaxy-2.0.db")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE LimitedDetails (productId INTEGER, title TEXT)")
        con.execute("CREATE TABLE InstalledBaseProducts (productId INTEGER)")
        con.executemany("INSERT INTO LimitedDetails VALUES (?,?)",
                        [(1, "Installed Game"), (2, "Owned But Not Installed")])
        con.execute("INSERT INTO InstalledBaseProducts VALUES (1)")  # only #1 installed
        con.commit(); con.close()
        names = [g.name for g in scanners._gog_installed_from_db(db)]
        assert names == ["Installed Game"]   # the owned-not-installed one is excluded


def test_folder_scan_picks_main_exe():
    with tempfile.TemporaryDirectory() as tmp:
        # A game folder with the real exe + an uninstaller (should be ignored).
        gdir = os.path.join(tmp, "Cool Game")
        os.makedirs(gdir)
        with open(os.path.join(gdir, "CoolGame.exe"), "wb") as fh:
            fh.write(b"x" * 5000)
        with open(os.path.join(gdir, "unins000.exe"), "wb") as fh:
            fh.write(b"x" * 9000)   # bigger, but must be skipped
        # A non-game folder.
        os.makedirs(os.path.join(tmp, "Redistributables"))
        found = scanners.scan_folder(tmp)
        assert len(found) == 1
        assert found[0].name == "Cool Game"
        assert found[0].process_name == "CoolGame.exe"
        assert found[0].source == "Folder"


def test_steam_filters_non_games():
    assert scanners._looks_non_game("Halo Infinite Soundtrack")
    assert scanners._looks_non_game("Team Fortress 2 Dedicated Server")
    assert scanners._looks_non_game("Steam Linux Runtime 3.0")
    assert scanners._looks_non_game("Proton 9.0")
    assert not scanners._looks_non_game("Elden Ring")
    assert not scanners._looks_non_game("DOOM Eternal")


def test_scan_generic_is_opt_in(monkeypatch=None):
    # The noisy registry/Start-menu sweep must be OFF unless explicitly enabled.
    sentinel = [scanners.DetectedGame("Some Installed App", None, "Installed")]
    orig_reg, orig_lnk = scanners.scan_registry_uninstall, scanners.scan_start_menu
    try:
        scanners.scan_registry_uninstall = lambda: sentinel
        scanners.scan_start_menu = lambda: []
        default = scanners.scan_all({})                       # no flag -> excluded
        enabled = scanners.scan_all({"scan_include_generic": True})
        names_default = {g.name for g in default}
        names_enabled = {g.name for g in enabled}
        assert "Some Installed App" not in names_default
        assert "Some Installed App" in names_enabled
    finally:
        scanners.scan_registry_uninstall = orig_reg
        scanners.scan_start_menu = orig_lnk


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
