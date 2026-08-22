@echo off
title StockSignal Stop Services
chcp 936 >nul 2>&1

echo ======================================
echo   StockSignal Stop Background Services
echo ======================================
echo.

set "PROJECT_DIR=%~dp0"
set BACKEND_PORT=5050
set FRONTEND_PORT=8899
set KILLED_ANY=0

:: 优先读取实际运行端口（startup_sim 写入的 active_ports.json）
if exist "%PROJECT_DIR%logs\active_ports.json" (
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content '%PROJECT_DIR%logs\active_ports.json' | ConvertFrom-Json).backend" 2^>nul`) do set BACKEND_PORT=%%j
    for /f "usebackq tokens=*" %%j in (`powershell -NoProfile -Command "(Get-Content '%PROJECT_DIR%logs\active_ports.json' | ConvertFrom-Json).frontend" 2^>nul`) do set FRONTEND_PORT=%%j
    echo 读取实际运行端口：后端=%BACKEND_PORT% 前端=%FRONTEND_PORT%
)

echo Stage 1: Kill processes by port (only StockSignal ports)...
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
echo Stage 2: 不再无差别 taskkill python.exe（避免误杀量化软件等其他 Python 服务）
echo   如需强制清理，请手动结束对应端口进程。

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
    echo   Info: no running services detected on configured ports
)
echo.
timeout /t 2 >nul
