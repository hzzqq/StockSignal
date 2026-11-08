@echo off
rem StockSignal Frontend v2 launcher (Windows, cmd.exe).
rem Starts the Flask backend (default 5050) and the Vite dev server (default 5173).
rem Vite proxies /api and /webapps to the backend, so the backend must run too.
rem Run by double-click or from cmd.exe. Do NOT run from Git Bash (see .sh for that).
rem NOTE: keep this file pure ASCII + CRLF (see tests/test_bat_encoding.py).

setlocal EnableExtensions
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

rem --- backend port (prefer explicit env, else 5050) ---
if defined STOCKSIGNAL_PORT (
    set "BACKEND_PORT=%STOCKSIGNAL_PORT%"
) else (
    set "BACKEND_PORT=5050"
)

rem --- frontend v2 port (default 5173) ---
if defined STOCKSIGNAL_V2_PORT (
    set "V2_PORT=%STOCKSIGNAL_V2_PORT%"
) else (
    set "V2_PORT=5173"
)

rem --- resolve python for the backend (priority: venv -> workbuddy venv -> PATH) ---
set "PY=%PROJECT_DIR%venv\Scripts\python.exe"
if exist "%PY%" goto :py_ok
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%PY%" goto :py_ok
for %%p in (python.exe) do set "PY=%%~$PATH:p"
if defined PY if exist "%PY%" goto :py_ok
echo [ERROR] python.exe not found (checked venv, workbuddy venv, PATH).
pause
exit /b 1
:py_ok

rem --- resolve npm for the frontend ---
where npm >nul 2>nul
if not errorlevel 1 (
    set "NPM=npm.cmd"
    goto :npm_ok
)
rem workbuddy node binaries (version-agnostic glob)
for /d %%d in ("%USERPROFILE%\.workbuddy\binaries\node\versions\*") do (
    if exist "%%d\npm.cmd" set "NPM=%%d\npm.cmd"
)
if defined NPM if exist "%NPM%" goto :npm_ok
if exist "C:\Program Files\nodejs\npm.cmd" (
    set "NPM=C:\Program Files\nodejs\npm.cmd"
    goto :npm_ok
)
echo [ERROR] npm not found (checked PATH, workbuddy node, Program Files).
pause
exit /b 1
:npm_ok

rem --- data source: this launcher also starts a real backend, so use it ---
rem Set STOCKSIGNAL_USE_MOCKS=1 to force MSW demo data instead.
set "VITE_ENABLE_MOCKS=false"
if "%STOCKSIGNAL_USE_MOCKS%"=="1" set "VITE_ENABLE_MOCKS=true"

rem --- if backend port is not the default 5050, point vite proxy at it ---
if not "%BACKEND_PORT%"=="5050" (
    set "VITE_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%"
)

echo ======================================
echo   StockSignal Frontend v2 Launcher
echo ======================================
echo   Backend  : http://127.0.0.1:%BACKEND_PORT%/api/health
echo   Frontend : http://127.0.0.1:%V2_PORT%/
echo   Data     : real backend (MSW=%VITE_ENABLE_MOCKS%); login demo / Demo@123
echo ======================================
echo.

rem --- start backend (minimized console; maximize to see logs) ---
start "StockSignal Backend :%BACKEND_PORT%" /d "%PROJECT_DIR%" /min "%PY%" -m flask --app backend.app:app run --host 127.0.0.1 --port %BACKEND_PORT%

rem --- start vite dev server (visible console for HMR / errors) ---
start "StockSignal Frontend v2 :%V2_PORT%" /d "%PROJECT_DIR%frontend-v2" "%NPM%" run dev -- --port %V2_PORT%

echo Waiting for services to boot...
timeout /t 4 /nobreak >nul 2>&1

rem --- open browser ---
start "" "http://127.0.0.1:%V2_PORT%/"

echo.
echo Started. Close the "Frontend v2" console to stop the UI.
echo Stop the backend with _stop_services.bat (kills port %BACKEND_PORT%).
echo.
pause
exit /b 0
