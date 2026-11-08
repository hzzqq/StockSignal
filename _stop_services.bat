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
set "BACKEND_PORT=5050"
set "FRONTEND_PORT=8899"
set "V2_PORT=5173"
set "V2_BACKEND_PORT=5050"
set "KILLED_ANY=0"
set "SEEN=,"

if exist "%PROJECT_DIR%logs\active_ports.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).backend" 2^>nul`) do set "BACKEND_PORT=%%j"
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).frontend" 2^>nul`) do set "FRONTEND_PORT=%%j"
    echo   Read v1 ports from logs\active_ports.json
)

if exist "%PROJECT_DIR%logs\active_ports_v2.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports_v2.json' -Raw | ConvertFrom-Json).v2" 2^>nul`) do set "V2_PORT=%%j"
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports_v2.json' -Raw | ConvertFrom-Json).backend" 2^>nul`) do set "V2_BACKEND_PORT=%%j"
    echo   Read v2 ports from logs\active_ports_v2.json
)

echo Stage 1: Kill StockSignal processes by TCP LISTENING port (never blanket-kills python.exe)
echo   Backend v1  = %BACKEND_PORT%
call :kill_port %BACKEND_PORT%
echo   Frontend v1 = %FRONTEND_PORT%
call :kill_port %FRONTEND_PORT%
echo   Backend v2  = %V2_BACKEND_PORT%
call :kill_port %V2_BACKEND_PORT%
echo   Frontend v2 = %V2_PORT%
call :kill_port %V2_PORT%

echo.
echo Stage 2: Waiting for ports to release...
timeout /t 2 /nobreak >nul 2>&1

echo.
echo Stage 3: Verify ports are free...
call :check_port %BACKEND_PORT%
call :check_port %FRONTEND_PORT%
call :check_port %V2_BACKEND_PORT%
call :check_port %V2_PORT%

echo.
if "%KILLED_ANY%"=="1" (
    echo   Done: StockSignal services stopped
) else (
    echo   Info: no running StockSignal service found on those ports
)
echo.
timeout /t 2 >nul
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
