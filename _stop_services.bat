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
title StockSignal Stop Services
setlocal EnableExtensions

echo ======================================
echo   StockSignal Stop Background Services
echo ======================================
echo.

set "PROJECT_DIR=%~dp0"
set "BACKEND_PORT=5050"
set "FRONTEND_PORT=8899"
set "KILLED_ANY=0"
set "SEEN=,"

if exist "%PROJECT_DIR%logs\active_ports.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).backend" 2^>nul`) do set "BACKEND_PORT=%%j"
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PROJECT_DIR%logs\active_ports.json' -Raw | ConvertFrom-Json).frontend" 2^>nul`) do set "FRONTEND_PORT=%%j"
    echo   Read ports from logs\active_ports.json
)

echo Stage 1: Kill StockSignal processes by port (never blanket-kills python.exe)
echo   Backend port  = %BACKEND_PORT%
call :kill_port %BACKEND_PORT%
echo   Frontend port = %FRONTEND_PORT%
call :kill_port %FRONTEND_PORT%

echo.
echo Stage 2: Waiting for ports to release...
timeout /t 2 /nobreak >nul 2>&1

echo.
echo Stage 3: Verify ports are free...
call :check_port %BACKEND_PORT%
call :check_port %FRONTEND_PORT%

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
rem Kill every owner of port %~1. Reject empty / non-numeric / pid 0, and dedupe
rem (netstat lists the same PID on both the IPv4 and IPv6 listen rows).
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /C:":%~1 "') do call :kill_pid %%a
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
netstat -aon 2^>nul | findstr /C:":%~1 " >nul 2>&1
if errorlevel 1 (
    echo   [OK]   Port %~1 is free
) else (
    echo   [WARN] Port %~1 is still in use
)
exit /b 0
