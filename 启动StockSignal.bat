@echo off
chcp 65001 >nul 2>&1
title StockSignal 启动器
setlocal EnableExtensions

:: 项目目录（本文件所在目录）
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: 优先使用 venv 解释器；其次用 workbuddy 预置环境；最后回退到 PATH
set "PYTHON=%PROJECT_DIR%venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
)
if not exist "%PYTHON%" (
    for /f "tokens=*" %%p in ('where python 2^>nul') do (
        set "PYTHON=%%p"
        goto :python_found
    )
)

:python_found
if not exist "%PYTHON%" (
    echo [错误] 找不到可用的 Python 解释器。
    pause
    exit /b 1
)

:: 启动器：用 Python 完成全部流程（端口清理、DB、Flask、Streamlit、健康探测、浏览器打开）
:: 比 Windows 批处理更可靠：不存在标签解析、重定向被吞、start 失败等问题。
"%PYTHON%" startup_sim.py --keep --pause
exit /b %errorlevel%
