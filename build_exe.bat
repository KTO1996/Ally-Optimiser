@echo off
REM Build AllyOptimizer.exe on Windows (run this on the ROG Xbox Ally or any
REM Windows PC with Python 3.10+ installed). Produces a standalone exe you can
REM double-click - no Python needed on the target afterwards.

echo Installing dependencies...
python -m pip install -r requirements.txt pyinstaller || goto :error

echo Building AllyOptimizer.exe...
pyinstaller --noconfirm AllyOptimizer.spec || goto :error

echo.
echo Done. Your app is at:  dist\AllyOptimizer\AllyOptimizer.exe
echo Put ryzenadj.exe in that same folder (or set its path in the app), then
echo create a Desktop / Start shortcut to AllyOptimizer.exe.
echo.
pause
exit /b 0

:error
echo.
echo Build failed - see the messages above.
pause
exit /b 1
