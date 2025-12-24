@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM jp2subs - One-click setup + run (Windows)
REM - Creates a venv in .venv
REM - Installs dependencies (GUI + ASR)
REM - Tries to find ffmpeg (PATH or bundled ffmpeg\bin\ffmpeg.exe)
REM - Launches the desktop UI
REM ============================================================

title jp2subs - Setup and Run
cd /d "%~dp0"

echo.
echo ============================================================
echo   jp2subs - Setup and Run
echo ============================================================
echo   Folder: %CD%
echo.

REM ---- Log file
set "LOG=%CD%\install.log"
echo [START] %DATE% %TIME% > "%LOG%"

REM ---- 1) Check Python launcher
where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher "py" not found. >> "%LOG%"
  echo.
  echo ERROR: Python is not installed (or "py" is missing).
  echo Install Python 3.11+ from:
  echo   https://www.python.org/downloads/windows/
  echo Then run this file again.
  echo.
  pause
  exit /b 1
)

REM ---- 2) Check Python version (needs 3.11+)
py -c "import sys; raise SystemExit^(0 if sys.version_info[:2] >= ^(3,11^) else 1^)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python version is below 3.11. >> "%LOG%"
  echo.
  echo ERROR: Python 3.11+ is required.
  echo Your current Python (py) is too old.
  echo Install Python 3.11+ and run again.
  echo.
  pause
  exit /b 1
)

REM ---- 3) Create venv (if missing)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  echo [INFO] Creating venv... >> "%LOG%"
  py -m venv .venv >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] Failed to create venv. >> "%LOG%"
    echo.
    echo ERROR: Failed to create the virtual environment.
    echo See install.log for details.
    echo.
    pause
    exit /b 1
  )
) else (
  echo Virtual environment already exists. Reusing it.
  echo [INFO] Reusing existing venv. >> "%LOG%"
)

REM ---- 4) Activate venv
call ".venv\Scripts\activate.bat"

REM ---- 5) Upgrade pip
echo Upgrading pip...
echo [INFO] Upgrading pip... >> "%LOG%"
python -m pip install --upgrade pip >> "%LOG%" 2>&1

REM ---- 6) Install project (editable) with extras
REM If you packaged a source folder, this installs from current directory.
echo Installing jp2subs (GUI + ASR)...
echo [INFO] Installing jp2subs extras [gui,asr]... >> "%LOG%"
pip install -e ".[gui,asr]" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] pip install failed. >> "%LOG%"
  echo.
  echo ERROR: Dependency installation failed.
  echo See install.log for details.
  echo.
  pause
  exit /b 1
)

REM ---- 7) ffmpeg detection: prefer bundled ffmpeg if present
set "BUNDLED_FFMPEG=%CD%\ffmpeg\bin\ffmpeg.exe"
if exist "%BUNDLED_FFMPEG%" (
  echo Found bundled ffmpeg: %BUNDLED_FFMPEG%
  echo [INFO] Using bundled ffmpeg. >> "%LOG%"
  set "JP2SUBS_FFMPEG=%BUNDLED_FFMPEG%"
) else (
  where ffmpeg >nul 2>nul
  if errorlevel 1 (
    echo [WARN] ffmpeg not found in PATH and no bundled ffmpeg\bin\ffmpeg.exe. >> "%LOG%"
    echo.
    echo WARNING: ffmpeg was not found.
    echo jp2subs needs ffmpeg to extract audio from videos.
    echo You can:
    echo   - Install ffmpeg and add it to PATH, OR
    echo   - Include ffmpeg in this folder at: ffmpeg\bin\ffmpeg.exe
    echo.
    echo Download ffmpeg:
    echo   https://www.gyan.dev/ffmpeg/builds/
    echo.
    pause
  ) else (
    echo ffmpeg found in PATH.
    echo [INFO] ffmpeg found in PATH. >> "%LOG%"
  )
)

REM ---- 8) Launch UI
echo.
echo Launching jp2subs UI...
echo [INFO] Launching UI... >> "%LOG%"
jp2subs ui >> "%LOG%" 2>&1

echo.
echo jp2subs exited. See install.log for details if needed.
echo [END] %DATE% %TIME% >> "%LOG%"
pause
endlocal
