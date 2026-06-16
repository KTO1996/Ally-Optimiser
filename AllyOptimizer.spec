# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Ally Optimizer.

Build a standalone Windows .exe (run this ON Windows / on the Ally):

    pip install -r requirements.txt pyinstaller
    pyinstaller AllyOptimizer.spec

Output: dist/AllyOptimizer/AllyOptimizer.exe  (one-folder build).
The profiles/ folder is copied next to the exe so games.json / config.json
stay user-editable. RyzenAdj is NOT bundled — point config.json at it, or
drop ryzenadj.exe in the same folder as the built exe.
"""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# CustomTkinter ships its theme JSON / assets as data files that must travel
# with the exe, or the UI fails to load at runtime.
_ctk_datas = collect_data_files("customtkinter")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Ship the seed profiles alongside the exe (kept editable, not embedded)
    # and bundle the icon/screenshot assets used by the window + tray.
    datas=[('profiles', 'profiles'), ('assets', 'assets')] + _ctk_datas,
    # pystray picks a backend at runtime; include the Windows one explicitly.
    hiddenimports=['pystray._win32', 'customtkinter'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AllyOptimizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # windowed app, no console window
    disable_windowed_traceback=False,
    # Request admin in the exe manifest so UAC prompts on launch (RyzenAdj).
    uac_admin=True,
    icon='assets/allyoptimizer.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AllyOptimizer',
)
