@echo off
REM ====================================================================
REM  SBA-Launcher - Start (Windows)
REM  Zentrale GUI fuer die drei SBA-Werkzeuge. Bootstrap 'uv', falls fehlt,
REM  startet dann launcher.py (Tkinter-Fenster).
REM
REM  Erststart? start.bat installiert uv automatisch und legt die Umgebung
REM  an. Die Geschwister-Repos (ausleihe-ausgabe, ausleihe-api, barcode-simple)
REM  werden ueber die Tabs der GUI geklont/gepflegt — nicht von hier.
REM ====================================================================
setlocal
cd /d "%~dp0"

REM 'uv' installiert automatisch eine passende Python-Version (>=3.12) und
REM bringt Tkinter mit dem Windows-Python-Bundle mit. Einzige externe
REM Abhaengigkeit ist 'uv' selbst.
where uv >nul 2>nul
if errorlevel 1 (
  echo [INFO] 'uv' wurde nicht gefunden - installiere automatisch ...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  where uv >nul 2>nul
  if errorlevel 1 (
    echo [FEHLER] Automatische 'uv'-Installation fehlgeschlagen.
    echo   Manuell installieren: https://docs.astral.sh/uv/getting-started/installation/
    echo   z.B. in PowerShell:  irm https://astral.sh/uv/install.ps1 ^| iex
    echo   Danach dieses Fenster schliessen und start.bat erneut ausfuehren.
    echo.
    pause
    exit /b 1
  )
  echo [INFO] 'uv' installiert.
)

REM Abhaengigkeiten (qrcode[pil]) installieren, falls noch nicht geschehen.
call uv sync
if errorlevel 1 ( echo [FEHLER] uv sync fehlgeschlagen. & pause & exit /b 1 )

REM Launcher starten. Beenden im Fenster schliesst die App.
call uv run python launcher.py
if errorlevel 1 (
  echo.
  echo [FEHLER] Launcher lief nicht fehlerfrei. Siehe Meldung oben.
  pause
)
endlocal