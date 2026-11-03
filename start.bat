@echo off
rem Grandma Buddy: double-click to start.
rem Makes the Python environment the first time, installs the packages, puts
rem the made-up demo week in when the database is empty, starts the server,
rem and opens the app in your browser as soon as the server answers. Close
rem this window to stop Buddy.
setlocal
cd /d "%~dp0"
if "%~1"=="--wait" goto :wait
title Grandma Buddy

rem The port: 8000, or the one given (start.bat 8001).
set PORT=%1
if "%PORT%"=="" set PORT=8000

rem Already running (start.bat double-clicked twice)? Just open it.
where curl >nul 2>nul
if not errorlevel 1 (
  curl -s -f -o nul http://localhost:%PORT%/api/ping 2>nul && goto :running
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.12 or newer from python.org,
  echo tick "Add python.exe to PATH" in its installer, then double-click start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Making the Python environment ^(once^)...
  python -m venv .venv || goto :failed
)

echo Checking the packages...
.venv\Scripts\python -m pip install -q -r requirements.txt || goto :failed

if not exist ".env" (
  copy .env.example .env >nul
  echo.
  echo A new .env file was made. Put your Meta Model API key on its MODEL_API_KEY= line
  echo ^(it opens in Notepad now^), save it, then double-click start.bat again.
  echo Without a key, Buddy still opens, but its AI features say they need one.
  start "" notepad .env
  pause
  exit /b 0
)

rem Buddy's natural voice (Kokoro, Apache-2.0): the kokoro-onnx package, then the
rem voice model, about 354 MB, once. Without them Buddy speaks with the browser's voice.
.venv\Scripts\python -c "import kokoro_onnx" >nul 2>nul || (
  echo Adding Buddy's natural voice ^(once^)...
  .venv\Scripts\python -m pip install -q kokoro-onnx==0.6.1 --no-deps --ignore-requires-python
)
if not exist "models\kokoro-v1.0.onnx" (
  echo Downloading Buddy's voice, about 354 MB ^(once^). Buddy uses the browser's voice until it is here.
  .venv\Scripts\python scripts\get_voice.py || echo The voice download didn't finish. Buddy will use the browser's voice; run scripts\get_voice.py later.
)

rem The very first start (no database yet): Rose's made-up demo week, or a real
rem person? The answer is kept in data\start-choice, so it is never asked again.
rem Later, Settings, Her data has "Reset the demo week" and "Start fresh for a real person".
if exist "data\grandma_buddy.db" goto :chosen
if exist "data\start-choice" goto :chosen
echo.
choice /C DF /N /M "Load the made-up demo week for Rose (D), or start fresh for a real person (F)? [D/F] "
if "%ERRORLEVEL%"=="2" goto :fresh
if "%ERRORLEVEL%"=="1" goto :demo
goto :chosen
:fresh
if not exist "data" mkdir data
echo F> data\start-choice
echo Starting fresh: Buddy will ask her name on its first screen.
goto :chosen
:demo
if not exist "data" mkdir data
echo D> data\start-choice
:chosen

rem The made-up demo week for "Rose", only when chosen and nothing is in the database yet
rem (scripts/seed_demo.py reads data\start-choice and does nothing after an F).
.venv\Scripts\python scripts\seed_demo.py --no-paint >nul 2>nul

echo Starting Grandma Buddy at http://localhost:%PORT% ...
rem A small hidden helper (this same file, run with --wait) opens the browser
rem once the server answers, instead of guessing how long the start takes.
start "" /min cmd /c call "%~f0" --wait %PORT%
.venv\Scripts\python -m uvicorn app.main:app --port %PORT%
goto :eof

:running
echo Buddy is already running at http://localhost:%PORT% - opening it in your browser.
start "" http://localhost:%PORT%
%SystemRoot%\System32\timeout.exe /t 3 >nul
exit /b 0

:wait
rem The helper: ask the server every second for up to two minutes, then open
rem the browser. Without curl (a very old Windows), wait four seconds instead.
rem timeout.exe is named in full because Git's Unix tools, when they are on
rem the PATH, bring a different "timeout" that doesn't take /t.
set PORT=%2
where curl >nul 2>nul || (%SystemRoot%\System32\timeout.exe /t 4 /nobreak >nul & goto :open)
for /l %%i in (1,1,120) do (
  curl -s -f -o nul http://localhost:%PORT%/api/ping 2>nul && goto :open
  %SystemRoot%\System32\timeout.exe /t 1 /nobreak >nul
)
exit /b 0

:open
start "" http://localhost:%PORT%
exit /b 0

:failed
echo.
echo Something went wrong while setting up. Please check the lines above, then try again.
pause
exit /b 1
