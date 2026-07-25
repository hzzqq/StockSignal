@echo off
chcp 936 >nul 2>&1
title StockSignal 启动器
setlocal EnableExtensions

:: 项目目录（本文件所在目录）
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: ── Python 查找策略（按优先级，找到即用）─────────────────────────────
:: ① 项目本地 venv
set "PYTHONW=%PROJECT_DIR%venv\Scripts\pythonw.exe"
if exist "%PYTHONW%" goto :found

:: ② 当前用户的 workbuddy managed venv（动态取用户名，不再硬编码）
set "PYTHONW=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
if exist "%PYTHONW%" goto :found

:: ③ 系统 PATH 里的 pythonw（任何已安装的 Python）
for %%p in (pythonw.exe) do set "PYTHONW=%%~$PATH:p"
if defined PYTHONW if exist "%PYTHONW%" goto :found

:: ④ 降级：用 python.exe 代替 pythonw.exe（功能相同，仅启动时闪一下控制台）
for %%p in (python.exe) do set "PYTHONW=%%~$PATH:p"
if defined PYTHONW if exist "%PYTHONW%" goto :found

:: 全部失败
echo [错误] 找不到可用的 Python（pythonw.exe / python.exe）。
echo 请确认已安装 Python 或在本项目目录下创建 venv。
pause
exit /b 1

:found
:: 使用 pythonw 在后台无窗口启动，关闭此 CMD 窗口不影响项目运行
:: 实际启动逻辑由 start_background.py 完成，负责进程拉起、健康检查、状态记录。
echo 正在后台启动 StockSignal，关闭此窗口不影响项目运行...
echo 停止服务请双击 _stop_services.bat
echo 启动状态请查看 logs\background_startup_status.log

start "" "%PYTHONW%" "%PROJECT_DIR%start_background.py"
timeout /t 2 >nul
exit /b 0
