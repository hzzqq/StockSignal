@echo off
chcp 936 >nul 2>&1
title StockSignal 启动器
setlocal EnableExtensions
set "PROJECT_DIR=%~dp0"
set "LOGS_DIR=%PROJECT_DIR%\logs"
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" >nul 2>&1
set "DIAG=%LOGS_DIR%\launch_diag.log"
:: ── 关键变量：端口 / 监听地址（缺失会导致 Flask/Streamlit 无法绑定端口，启动彻底失败）──
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=5050"
set "FRONTEND_PORT=8501"

:: ── 统一日志：打印到屏幕 且 追加写入 launch_diag.log ──
goto :main

:log
>> "%DIAG%" echo %*
echo %*
goto :eof

:: ════════════════════════════════════════════
::  主流程
:: ════════════════════════════════════════════
:main
>> "%DIAG%" echo ===================================================
>> "%DIAG%" echo [%DATE% %TIME%] === 启动开始 ===

call :log ===================================================
call :log   StockSignal 一键启动
call :log   A股事件驱动投资分析平台
call :log ===================================================

:: ── 0. 解析 Python 解释器（逐个实测，跳过 PATH 中损坏解释器）──
call :log [0/6] 解析 Python 解释器...
call :find_python
if not defined PYTHON (
    call :log   [错误] 找不到可用的 Python。请先创建 venv（StockSignal\venv）或将其加入 PATH。
    goto :finish_fail
)
for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do call :log   [OK] %%v  ^(%PYTHON%^)

:: ── 1. 清理占用端口的旧进程 ──
call :log.
call :log [1/6] 清理占用 %BACKEND_PORT% / %FRONTEND_PORT% 端口的旧进程...
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
ping -n 2 127.0.0.1 >nul 2>&1
call :log   [OK] 端口清理完成

:: ── 2. 检查项目目录 ──
call :log.
call :log [2/6] 检查项目目录...
if not exist "%PROJECT_DIR%\app.py" ( call :log   [错误] 找不到 %PROJECT_DIR%\app.py & goto :finish_fail )
if not exist "%PROJECT_DIR%\backend\app.py" ( call :log   [错误] 找不到 %PROJECT_DIR%\backend\app.py & goto :finish_fail )
call :log   [OK] 项目目录: %PROJECT_DIR%

:: ── 3. 检查 / 初始化数据库 ──
call :log.
call :log [3/6] 检查数据库...
call :db_ok
if errorlevel 1 (
    call :log   数据库缺失或结构不完整，正在初始化...
    cd /d "%PROJECT_DIR%"
    "%PYTHON%" -m backend.scripts.init_db
    if errorlevel 1 ( call :log   [错误] 数据库初始化失败 & goto :finish_fail )
    call :log   导入A股股票数据（约5177只，请稍候）...
    "%PYTHON%" -m backend.scripts.import_stocks
    if errorlevel 1 ( call :log   [警告] 股票数据导入失败（可能无外网），可稍后手动重试 )
    call :log   [OK] 数据库初始化完成
) else (
    call :log   [OK] 数据库已存在且结构完整
)

:: ── 4. 启动 Flask 后端 ──
call :log.
call :log [4/6] 启动 Flask 后端 ^(端口 %BACKEND_PORT%^)...
call :launch "%PYTHON%" "-m flask --app backend.app:app run --host %BACKEND_HOST% --port %BACKEND_PORT%" "backend_run"
if errorlevel 1 ( call :log   [错误] 后端启动进程拉起失败 & goto :finish_fail )
call :log   等待后端就绪 ^(健康检查 /api/health，最多 60 秒^)...
set WAIT_N=0
:wait_be
call :wait_port %BACKEND_PORT%
if not errorlevel 1 goto be_ready
ping -n 2 127.0.0.1 >nul 2>&1
set /a WAIT_N+=1
if %WAIT_N% LSS 30 goto wait_be
call :log   [警告] 后端未在预期内就绪，最近错误日志：
type "%LOGS_DIR%\backend_run.err" 2>nul
:be_ready
call :log   [OK] 后端已就绪

:: ── 5. 启动 Streamlit 前端 ──
call :log.
call :log [5/6] 启动 Streamlit 前端 ^(端口 %FRONTEND_PORT%^)...
call :launch "%PYTHON%" "-m streamlit run app.py --server.port %FRONTEND_PORT% --server.headless true --browser.gatherUsageStats false --server.fileWatcherType poll" "frontend_run"
if errorlevel 1 ( call :log   [错误] 前端启动进程拉起失败 & goto :finish_fail )
call :log   等待前端就绪 ^(最多 80 秒，Streamlit 首次较慢^)...
set WAIT_N=0
:wait_fe
call :wait_port %FRONTEND_PORT%
if not errorlevel 1 goto fe_ready
ping -n 2 127.0.0.1 >nul 2>&1
set /a WAIT_N+=1
if %WAIT_N% LSS 40 goto wait_fe
call :log   [警告] 前端启动较慢，请稍后手动访问 http://localhost:%FRONTEND_PORT%
goto after_fe
:fe_ready
call :log   [OK] 前端已就绪
:after_fe

:: ── 6. 打开浏览器 ──
call :log.
call :log   正在打开浏览器...
start "" "http://localhost:%FRONTEND_PORT%"

call :log.
call :log ===================================================
call :log     启动完成！关闭此窗口不影响项目运行
call :log ===================================================
call :log   前端地址:  http://localhost:%FRONTEND_PORT%
call :log   后端地址:  http://%BACKEND_HOST%:%BACKEND_PORT%
call :log   默认账号:  admin / Admin@123   demo / Demo@123
call :log   停止方法: 双击运行 _stop_services.bat
call :log.
call :log   ^(8 秒后自动关闭本窗口^)
>> "%DIAG%" echo [%DATE% %TIME%] === 启动完成 ===
ping -n 9 127.0.0.1 >nul
goto :eof

:: ════════════════════════════════════════════
::  失败收尾
:: ════════════════════════════════════════════
:finish_fail
>> "%DIAG%" echo [%DATE% %TIME%] === 启动失败（见上方 [错误]）===
call :log.
call :log   [!] 启动未完成。请查看 %DIAG% 获取完整诊断。
call :log   ^(8 秒后自动关闭本窗口^)
ping -n 9 127.0.0.1 >nul
exit /b 1

:: ════════════════════════════════════════════
::  子程序
:: ════════════════════════════════════════════

:: 解析 Python（逐个实测 --version，自动跳过 PATH 中的损坏解释器）
:find_python
set "PYTHON="
if exist "C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" (
    "C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" & goto :eof )
)
if exist "%PROJECT_DIR%\venv\Scripts\python.exe" (
    "%PROJECT_DIR%\venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe" & goto :eof )
)
for /f "tokens=*" %%p in ('where python 2^>nul') do (
    "%%p" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=%%p" & goto :eof )
)
goto :eof

:: 启动后台进程：%1=python路径 %2=参数 %3=日志前缀
:: 方案：先写包装脚本（重定向写在脚本内，确保日志真正落盘），再 start /min 直接运行 .cmd 文件（Windows 最稳 start 用法）
:launch
set "L_PYTHON=%~1"
set "L_ARGS=%~2"
set "L_PREFIX=%~3"
set "L_LOG=%LOGS_DIR%\%L_PREFIX%.log"
set "L_ERR=%LOGS_DIR%\%L_PREFIX%.err"
set "L_CMD=%LOGS_DIR%\run_%L_PREFIX%.cmd"
call :log [launch] PYTHON=%L_PYTHON%
call :log   ARGS=%L_ARGS%
if not exist "%L_PYTHON%" (
    call :log   [FAIL] Python 不存在: %L_PYTHON%
    echo   [错误] Python 路径不存在: %L_PYTHON%
    exit /b 1
)
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" >nul 2>&1
:: 写包装脚本（重定向在脚本内部，日志可靠落盘）
(
    echo @echo off
    echo "%L_PYTHON%" %L_ARGS% ^> "%L_LOG%" 2^> "%L_ERR%"
) > "%L_CMD%" 2>nul
if not exist "%L_CMD%" (
    call :log   [FAIL] 无法写入启动脚本: %L_CMD%
    echo   [错误] 无法写入启动脚本
    exit /b 1
)
call :log   start "" /min "%L_CMD%"
start "" /min "%L_CMD%"
set "L_RC=%errorlevel%"
call :log   start rc=%L_RC%
if %L_RC% neq 0 (
    call :log   [WARN] start 失败，降级为普通窗口
    start "" "%L_CMD%"
    set "L_RC=%errorlevel%"
    call :log   fallback rc=%L_RC%
)
exit /b %L_RC%

:: 用 Python urllib 探测端口是否就绪（不依赖 curl.exe）
:: 入参 %1=端口；8501 探测根路径 /，其它探测 /api/health
:wait_port
set "WP=%~1"
if "%WP%"=="8501" (
    "%PYTHON%" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8501/',timeout=2); sys.exit(0)" >nul 2>&1
) else (
    "%PYTHON%" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:%WP%/api/health',timeout=2); sys.exit(0)" >nul 2>&1
)
exit /b

:: 按端口号杀进程
:kill_port
set "TARGET_PORT=%~1"
if "%TARGET_PORT%"=="" goto :eof
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%TARGET_PORT% "') do (
    taskkill /f /pid %%a >nul 2>&1 && call :log   已终止 PID %%a ^(端口 %TARGET_PORT%^) || rem ignore
)
goto :eof

:: 轻量结构校验：app.db 存在且含 users/stocks 表则视为 OK
:db_ok
set "DB_PATH=%PROJECT_DIR%\backend\data\app.db"
if not exist "%DB_PATH%" exit /b 1
"%PYTHON%" -c "import sqlite3,sys; c=sqlite3.connect(r'%DB_PATH%'); t={r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=?',('table',))}; sys.exit(0 if {'users','stocks'}<=t else 1)" >nul 2>&1
if errorlevel 1 ( exit /b 1 )
exit /b 0
