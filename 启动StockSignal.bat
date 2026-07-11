@echo off
chcp 65001 >nul 2>&1
title StockSignal 启动器
setlocal EnableExtensions

:: 项目目录（本文件所在目录）
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: 优先使用 venv 中的 pythonw.exe；其次用 workbuddy 预置环境
set "PYTHONW=%PROJECT_DIR%venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
    set "PYTHONW=C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
)
if not exist "%PYTHONW%" (
    echo [错误] 找不到可用的 pythonw.exe。
    echo 请确认 Python 环境已安装。
    pause
    exit /b 1
)

:: 使用 pythonw 在后台无窗口启动，关闭此 CMD 窗口不影响项目运行
:: 实际启动逻辑由 start_background.py 完成，负责进程拉起、健康检查、状态记录。
echo 正在后台启动 StockSignal，关闭此窗口不影响项目运行...
echo 停止服务请双击 _stop_services.bat
echo 启动状态请查看 logs\background_startup_status.log

start "" "%PYTHONW%" "%PROJECT_DIR%start_background.py"
timeout /t 2 >nul
exit /b 0
