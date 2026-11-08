@echo off
rem StockSignal stop-services helper.
rem
rem Run from cmd.exe (double-click). Do NOT run from Git Bash / MSYS:
rem in cmd ">nul" is the null device, but Git Bash treats it as a filename and
rem creates an undeletable 0-byte "nul" file (Windows reserved device name).
rem
rem IMPORTANT: this file is intentionally ASCII-only so it parses correctly under
rem ANY console codepage. Adding non-ASCII text here corrupts command parsing when
rem the console codepage no longer matches the file encoding (UTF-8 bytes read as
rem GBK swallow following characters) -- see tests/test_bat_encoding.py.
rem
rem v2 note: start_v2_detached.py writes logs\active_ports_v2.json with the REAL
rem ports. Read it too; otherwise custom ports (and even the default 5050 backend)
rem are never stopped. Only TCP LISTENING rows whose LOCAL address owns the port
rem are used -- Foreign Address / TIME_WAIT / UDP rows must never kill a process.
title StockSignal Stop Services
setlocal EnableExtensions

echo ======================================
echo   StockSignal Stop Background Services
echo ======================================
echo.

set "PROJECT_DIR=%~dp0"
set "KILLED_ANY=0"
set "SEEN=,"
set "V1_BACKEND="
set "V1_FRONTEND="
set "V2_BACKEND_PORT="
set "V2_FRONTEND="

if exist "%PROJECT_DIR%logs\active_ports.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).backend" 2^>nul`) do set "V1_BACKEND=%%j"
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).frontend" 2^>nul`) do set "V1_FRONTEND=%%j"
    echo   Read v1 ports from logs\active_ports.json
)

if exist "%PROJECT_DIR%logs\active_ports_v2.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports_v2.json' -Raw | ConvertFrom-Json).v2" 2^>nul`) do set "V2_FRONTEND=%%j"
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports_v2.json' -Raw | ConvertFrom-Json).backend" 2^>nul`) do set "V2_BACKEND_PORT=%%j"
    echo   Read v2 ports from logs\active_ports_v2.json
)

echo Stage 1: Kill StockSignal processes by TCP LISTENING port (never blanket-kills python.exe)
echo   Only ports recorded by the launchers are stopped. A port with no state file
echo   is skipped, so an unrelated service on any other port is never touched.
echo   Backend v1  = %V1_BACKEND%
call :maybe_kill "StockSignal v1 backend" "%V1_BACKEND%"
echo   Frontend v1 = %V1_FRONTEND%
call :maybe_kill "StockSignal v1 frontend" "%V1_FRONTEND%"
echo   Backend v2  = %V2_BACKEND_PORT%
call :maybe_kill "StockSignal v2 backend" "%V2_BACKEND_PORT%"
echo   Frontend v2 = %V2_FRONTEND%
call :maybe_kill "StockSignal v2 frontend" "%V2_FRONTEND%"

echo.
echo Stage 2: Waiting for ports to release...
timeout /t 2 /nobreak >nul 2>&1

echo.
echo Stage 3: Verify ports are free...
call :maybe_check "StockSignal v1 backend" "%V1_BACKEND%"
call :maybe_check "StockSignal v1 frontend" "%V1_FRONTEND%"
call :maybe_check "StockSignal v2 backend" "%V2_BACKEND_PORT%"
call :maybe_check "StockSignal v2 frontend" "%V2_FRONTEND%"

echo.
if "%KILLED_ANY%"=="1" (
    echo   Done: StockSignal services stopped
) else (
    echo   Info: no running StockSignal service found on those ports
)
echo.
timeout /t 2 >nul
exit /b 0


:maybe_kill
rem %~1 = friendly label, %~2 = port (may be empty). Skip empty (no state file)
rem and NEVER kill 8899: 8899 is reserved and is NOT a StockSignal port (the
rem launchers always pick a free port and record it), so an unrelated service
rem listening on 8899 must never be killed (see PLAN red line).
set "MK_LABEL=%~1"
set "MK_PORT=%~2"
if "%MK_PORT%"=="" (
    echo     [skip] %MK_LABEL%: no port recorded (launcher state file absent)
    exit /b 0
)
if "%MK_PORT%"=="8899" (
    echo     [SKIP]  %MK_LABEL%: 8899 reserved, never killed
    exit /b 0
)
call :kill_port %MK_PORT%
exit /b 0


:maybe_check
set "MC_LABEL=%~1"
set "MC_PORT=%~2"
if "%MC_PORT%"=="" exit /b 0
if "%MC_PORT%"=="8899" exit /b 0
call :check_port %MC_PORT%
exit /b 0


:kill_port
rem Only TCP LISTENING rows whose LOCAL address owns the port are used.
rem A bare ":port " match also hits Foreign Address / TIME_WAIT / UDP rows and
rem would taskkill an unrelated browser or trading app.
for /f "tokens=5" %%a in ('netstat -aon -p tcp 2^>nul ^| findstr /R /C:"^  TCP .*:%~1 .* LISTENING"') do call :kill_pid %%a
exit /b 0


:kill_pid
set "PID=%~1"
if "%PID%"=="" exit /b 0
if "%PID%"=="0" exit /b 0
echo %PID%|findstr /R "[^0-9]" >nul 2>&1
if not errorlevel 1 exit /b 0
echo %SEEN%|findstr /C:",%PID%," >nul 2>&1
if not errorlevel 1 exit /b 0
set "SEEN=%SEEN%%PID%,"
echo     Killing PID %PID%
taskkill /f /t /pid %PID% >nul 2>&1
if not errorlevel 1 set "KILLED_ANY=1"
exit /b 0


:check_port
netstat -aon -p tcp 2>nul | findstr /R /C:"^  TCP .*:%~1 .* LISTENING" >nul 2>&1
if errorlevel 1 (
    echo   [OK]   Port %~1 is free
) else (
    echo   [WARN] Port %~1 is still in use
)
exit /b 0
