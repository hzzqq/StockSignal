@echo off
rem StockSignal Frontend v2 launcher (Windows, cmd.exe).
rem Starts the Flask backend (default 5050) and the Vite dev server (default 5173).
rem
rem The services are started by a HIDDEN worker (start_frontend_v2_hidden.vbs),
rem which runs scripts/start_v2_detached.py. No service shares this visible
rem console, so closing this window can NEVER stop the services.
rem Logs: logs/launcher_v2.log , logs/backend_v2.log , logs/frontend_v2.log
rem Stop: _stop_services.bat (kills by port)
rem Run by double-click or from cmd.exe. Do NOT run from Git Bash (see .sh).
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

rem --- pass resolved values to the detached python launcher ---
set "SS_PY=%PY%"
set "SS_NPM=%NPM%"
set "SS_BACKEND_PORT=%BACKEND_PORT%"
set "SS_V2_PORT=%V2_PORT%"

rem --- worker branch: runs inside the HIDDEN console only ---
if "%~1"=="--worker" goto :worker

echo ======================================
echo   StockSignal Frontend v2 Launcher
echo ======================================
echo   Backend  : http://127.0.0.1:%BACKEND_PORT%/api/health
echo   Frontend : http://127.0.0.1:%V2_PORT%/
echo   Data     : real backend (MSW=%VITE_ENABLE_MOCKS%); login demo / Demo@123
echo ======================================
echo.

if not exist "%PROJECT_DIR%logs" mkdir "%PROJECT_DIR%logs"
if not exist "%PROJECT_DIR%start_frontend_v2_hidden.vbs" (
    echo [ERROR] start_frontend_v2_hidden.vbs is missing.
    pause
    exit /b 1
)
if not exist "%PROJECT_DIR%scripts\start_v2_detached.py" (
    echo [ERROR] scripts\start_v2_detached.py is missing.
    pause
    exit /b 1
)

echo Starting services in a hidden background worker...
wscript.exe //nologo "%PROJECT_DIR%start_frontend_v2_hidden.vbs" "%~f0" "--worker"
if errorlevel 1 (
    echo [ERROR] Failed to launch the hidden worker.
    pause
    exit /b 1
)

set "TRIES=0"
:wait_v2
set /a TRIES+=1
netstat -aon | findstr /C:":%V2_PORT% " >nul 2>&1
if not errorlevel 1 goto :v2_ready
if %TRIES% GEQ 30 goto :v2_timeout
timeout /t 1 /nobreak >nul 2>&1
goto :wait_v2

:v2_ready
timeout /t 1 /nobreak >nul 2>&1
echo   Frontend is ready: http://127.0.0.1:%V2_PORT%/
if not "%SS_NO_BROWSER%"=="1" start "" "http://127.0.0.1:%V2_PORT%/"
goto :done

:v2_timeout
echo [WARN] Frontend was not ready in 30s. Check logs\launcher_v2.log and logs\frontend_v2.log

:done
echo.
echo The services keep running after this window is closed.
echo Stop them with _stop_services.bat (ports %BACKEND_PORT% / %V2_PORT%).
echo Logs are in the logs\ folder. This window is only a status display.
echo.
pause
exit /b 0

:worker
if not exist "%PROJECT_DIR%logs" mkdir "%PROJECT_DIR%logs"
"%PY%" "%PROJECT_DIR%scripts\start_v2_detached.py" > "%PROJECT_DIR%logs\launcher_v2.log" 2>&1
exit /b %errorlevel%
