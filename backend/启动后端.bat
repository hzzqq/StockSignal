@echo off
chcp 936 >nul 2>&1
title StockSignal 后端启动
setlocal EnableExtensions

:: 项目根目录（本文件在 backend/ 下，上一级即项目根）
set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

:: ── Python 查找策略（按优先级，找到即用）─────────────────────────────
:: ① 项目本地 venv
set "PY=%PROJECT_DIR%\venv\Scripts\python.exe"
if exist "%PY%" goto :found

:: ② 当前用户的 workbuddy managed venv（动态取用户名，不硬编码）
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%PY%" goto :found

:: ③ 系统 PATH 里的 python
for %%p in (python.exe) do set "PY=%%~$PATH:p"
if defined PY if exist "%PY%" goto :found

:: 全部失败
echo [错误] 找不到可用的 Python（venv / managed venv / PATH）。
echo 请确认已安装 Python 或在本项目目录下创建 venv。
pause
exit /b 1

:found
echo 使用解释器: %PY%
echo 启动 StockSignal 后端（Ctrl+C 停止）...
"%PY%" backend/run.py %*
exit /b %ERRORLEVEL%
