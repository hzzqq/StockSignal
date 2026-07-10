@echo off
title StockSignal Stop Services

echo ======================================
echo   StockSignal Stop Background Services
echo ======================================
echo.

set BACKEND_PORT=5050
set FRONTEND_PORT=8501
set KILLED_ANY=0

echo Stage 1: Kill processes by port...
echo   Backend port %BACKEND_PORT%
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /C:":%BACKEND_PORT% "') do (
    echo     Killing PID %%a
    taskkill /f /t /pid %%a >nul 2>&1
    if not errorlevel 1 set KILLED_ANY=1
)

echo   Frontend port %FRONTEND_PORT%
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /C:":%FRONTEND_PORT% "') do (
    echo     Killing PID %%a
    taskkill /f /t /pid %%a >nul 2>&1
    if not errorlevel 1 set KILLED_ANY=1
)

echo.
echo Stage 2: Kill Python processes by image name...
taskkill /f /im python.exe >nul 2>&1
if not errorlevel 1 (
    echo   python.exe terminated
    set KILLED_ANY=1
)
taskkill /f /im pythonw.exe >nul 2>&1
if not errorlevel 1 (
    echo   pythonw.exe terminated
    set KILLED_ANY=1
)

echo.
echo Waiting for ports to release...
timeout /t 2 /nobreak >nul 2>&1

echo.
echo Stage 3: Verify ports are free...
netstat -aon 2^>nul ^| findstr /C:":%BACKEND_PORT% " >nul 2>&1
if errorlevel 1 (
    echo   [OK] Port %BACKEND_PORT% is free
) else (
    echo   [WARN] Port %BACKEND_PORT% is still in use
)

netstat -aon 2^>nul ^| findstr /C:":%FRONTEND_PORT% " >nul 2>&1
if errorlevel 1 (
    echo   [OK] Port %FRONTEND_PORT% is free
) else (
    echo   [WARN] Port %FRONTEND_PORT% is still in use
)

echo.
if "%KILLED_ANY%"=="1" (
    echo   Done: services stopped
) else (
    echo   Info: no running services detected
)
echo.
timeout /t 2 >nul
