@echo off
chcp 936 >nul 2>&1
title StockSignal 启动器

:: ════════════════════════════════════════════
::  StockSignal 一键启动脚本 (Windows CMD)
::  自动启动 Flask 后端 (5050) + Streamlit 前端 (8501)
::  进程通过 start /min 最小化窗口后台启动，脱离终端、关闭主窗口不影响
::  关闭此窗口不会中断项目
:: ════════════════════════════════════════════

set "PROJECT_DIR=%~dp0"
set "LOGS_DIR=%PROJECT_DIR%\logs"
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" >nul 2>&1

:: ── 可覆盖的环境变量（容器/部署时由外部注入；缺省取本地安全值）──
if not defined BACKEND_HOST        set "BACKEND_HOST=127.0.0.1"
if not defined BACKEND_PORT        set "BACKEND_PORT=5050"
if not defined FRONTEND_PORT       set "FRONTEND_PORT=8501"
if not defined STOCKSIGNAL_SECRET  set "STOCKSIGNAL_SECRET=dev-only-change-me-in-production"
if not defined CORS_ORIGINS        set "CORS_ORIGINS=*"
if not defined JWT_EXPIRES_SECONDS set "JWT_EXPIRES_SECONDS=3600"
if not defined EXPOSE_INTERNAL_ERROR set "EXPOSE_INTERNAL_ERROR=0"
if not defined DATABASE_URL        set "DATABASE_URL=sqlite:///backend/data/app.db"

:: 清除可能干扰虚拟环境 Python 的环境变量
set PYTHONHOME=
set PYTHONPATH=
set PYTHONIOENCODING=utf-8

:: 日志时间戳（用于按次命名，避免覆盖）
for /f "tokens=*" %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%t"

echo.
echo ===================================================
echo   StockSignal 一键启动
echo   A股事件驱动投资分析平台
echo ===================================================
echo.

:: ── 0. 解析 Python 解释器（去硬编码，支持 venv / PATH / 原路径兜底）──
echo [0/6] 解析 Python 解释器...
call :find_python
if not defined PYTHON (
    echo   [错误] 找不到可用的 Python。请先创建 venv（StockSignal\venv）或将其加入 PATH。
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do echo   [OK] %%v  ^(%PYTHON%^)

:: ── 1. 清理占用端口的旧进程 ──
echo.
echo [1/6] 清理占用 %BACKEND_PORT% / %FRONTEND_PORT% 端口的旧进程...
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
ping -n 2 127.0.0.1 >nul 2>&1
echo   [OK] 端口清理完成
echo.

:: ── 2. 检查项目目录 ──
echo [2/6] 检查项目目录...
if not exist "%PROJECT_DIR%\app.py" ( echo   [错误] 找不到 %PROJECT_DIR%\app.py & pause & exit /b 1 )
if not exist "%PROJECT_DIR%\backend\app.py" ( echo   [错误] 找不到 %PROJECT_DIR%\backend\app.py & pause & exit /b 1 )
echo   [OK] 项目目录: %PROJECT_DIR%
echo.

:: ── 3. 检查 / 初始化数据库（含轻量健壮性校验）──
echo [3/6] 检查数据库...
call :db_ok
if errorlevel 1 (
    echo   数据库缺失或结构不完整，正在初始化...
    cd /d "%PROJECT_DIR%"
    "%PYTHON%" -m backend.scripts.init_db
    if errorlevel 1 ( echo   [错误] 数据库初始化失败 & pause & exit /b 1 )
    echo   导入A股股票数据（约5177只，请稍候）...
    "%PYTHON%" -m backend.scripts.import_stocks
    if errorlevel 1 (
        echo   [警告] 股票数据导入失败（可能无外网）。
        echo           可稍后手动重试：python -m backend.scripts.import_stocks
    )
    echo   [OK] 数据库初始化完成
) else (
    echo   [OK] 数据库已存在且结构完整（如需重建请删除 backend\data\app.db）
)
echo.

:: ── 4. 启动 Flask 后端（隐藏窗口 + 脱离终端，日志按时间戳落盘）──
echo [4/6] 启动 Flask 后端 (端口 %BACKEND_PORT%)...
call :launch "%PYTHON%" "-m flask --app backend.app:app run --host %BACKEND_HOST% --port %BACKEND_PORT%" "backend_%TS%"
if errorlevel 1 ( echo   [错误] 后端启动失败 & pause & exit /b 1 )
ping -n 2 127.0.0.1 >nul 2>&1

:: 等待后端就绪（健康检查 GET /api/health，最多 30 秒）
echo   等待后端就绪（健康检查 /api/health）...
set WAIT_BE=0
:wait_be_loop
curl -fsS "http://127.0.0.1:%BACKEND_PORT%/api/health" >nul 2>&1
if not errorlevel 1 goto be_ready
ping -n 2 127.0.0.1 >nul 2>&1
set /a WAIT_BE+=1
if %WAIT_BE% LSS 15 goto wait_be_loop
echo   [警告] 后端未在预期内就绪，最近错误日志：
powershell -NoProfile -Command "Get-Content '%LOGS_DIR%\backend_%TS%.err' -Tail 10 -ErrorAction SilentlyContinue"
goto after_be
:be_ready
echo   [OK] 后端已就绪 (~%WAIT_BE%s)
:after_be
echo.

:: ── 5. 启动 Streamlit 前端 ──
echo [5/6] 启动 Streamlit 前端 (端口 %FRONTEND_PORT%)...
call :launch "%PYTHON%" "-m streamlit run app.py --server.port %FRONTEND_PORT% --server.headless true --browser.gatherUsageStats false --server.fileWatcherType poll" "frontend_%TS%"
if errorlevel 1 ( echo   [错误] 前端启动失败 & pause & exit /b 1 )

echo   等待前端就绪（最多 40 秒，Streamlit 首次较慢）...
set WAIT_FE=0
:wait_fe_loop
curl -fsS "http://127.0.0.1:%FRONTEND_PORT%/" >nul 2>&1
if not errorlevel 1 goto fe_ready
ping -n 2 127.0.0.1 >nul 2>&1
set /a WAIT_FE+=1
if %WAIT_FE% LSS 20 goto wait_fe_loop
echo   [警告] 前端启动较慢，请稍后手动访问 http://localhost:%FRONTEND_PORT%
goto after_fe
:fe_ready
echo   [OK] 前端已就绪 (~%WAIT_FE%s)
:after_fe

:: 打开浏览器
echo.
echo   正在打开浏览器...
start "" "http://localhost:%FRONTEND_PORT%"

echo.
echo ===================================================
echo     启动完成！关闭此窗口不影响项目运行
echo ===================================================
echo.
echo   前端地址:  http://localhost:%FRONTEND_PORT%
echo   后端地址:  http://%BACKEND_HOST%:%BACKEND_PORT%
echo   默认账号:  admin / Admin@123
echo             demo  / Demo@123
echo.
echo   停止方法: 双击运行 _stop_services.bat
echo.
pause
goto :eof


:: ════════════════════════════════════════════
::  子程序
:: ════════════════════════════════════════════

:: 解析 Python（逐个实测 --version，自动跳过 PATH 中的损坏解释器）
:: 优先级：已知可用的工作 venv → 项目 venv → PATH 中实测可用的 python
:find_python
set "PYTHON="
:: 1) 已知可用的工作 venv（已验证可正常 import 与建库，优先避免损坏解释器）
if exist "C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" (
    "C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe" & goto :eof )
)
:: 2) 项目内 venv
if exist "%PROJECT_DIR%\venv\Scripts\python.exe" (
    "%PROJECT_DIR%\venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe" & goto :eof )
)
:: 3) PATH 中的 python（必须实测 --version 通过，自动跳过损坏解释器）
for /f "tokens=*" %%p in ('where python 2^>nul') do (
    "%%p" --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=%%p" & goto :eof )
)
goto :eof

:: 启动后台进程：%1=python路径 %2=参数 %3=日志前缀
:: 方案：start /min 最小化窗口启动（Windows 原生最稳，关闭主窗口不影响子进程）
:: 全程诊断追加写入 logs/launch_diag.log，便于无头环境排错
:launch
set "L_PYTHON=%~1"
set "L_ARGS=%~2"
set "L_PREFIX=%~3"
set "L_LOG=%LOGS_DIR%\%L_PREFIX%.log"
set "L_ERR=%LOGS_DIR%\%L_PREFIX%.err"
set "L_DIAG=%LOGS_DIR%\launch_diag.log"
>> "%L_DIAG%" echo [%DATE% %TIME%] launch PYTHON=%L_PYTHON% ARGS=%L_ARGS% PREFIX=%L_PREFIX%
if not exist "%L_PYTHON%" (
  >> "%L_DIAG%" echo   [FAIL] python 不存在: %L_PYTHON%
  echo   [错误] Python 路径不存在: %L_PYTHON%
  exit /b 1
)
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" >nul 2>&1
:: 主方案：最小化窗口后台启动（原生、最稳，直接拉起 python，不依赖包装脚本）
start "" /min "%L_PYTHON%" %L_ARGS% > "%L_LOG%" 2>&1
set "L_RC=%errorlevel%"
>> "%L_DIAG%" echo   rc=%L_RC%  start "" /min "%L_PYTHON%" %L_ARGS% ^> "%L_LOG%" 2^>^&1
if %L_RC% neq 0 (
  >> "%L_DIAG%" echo   [WARN] start 返回非0，改用普通窗口兜底
  start "" "%L_PYTHON%" %L_ARGS% > "%L_LOG%" 2>&1
  set "L_RC=%errorlevel%"
  >> "%L_DIAG%" echo   fallback rc=%L_RC%
)
:: 校验：等待日志文件出现（最多 ~10s）
set /a L_WAIT=0
:launch_wait
if exist "%L_LOG%" goto launch_ok
ping -n 2 127.0.0.1 >nul 2>&1
set /a L_WAIT+=1
if %L_WAIT% LSS 5 goto launch_wait
:launch_ok
if %L_RC% neq 0 (
  >> "%L_DIAG%" echo   [FAIL] 启动进程失败
  echo   [错误] 后端/前端启动进程失败 (rc=%L_RC%)，详见 %L_DIAG%
  exit /b 1
)
>> "%L_DIAG%" echo   [OK] 进程已拉起，日志: %L_LOG%
exit /b 0

:: 按端口号杀进程
:kill_port
set "TARGET_PORT=%~1"
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%TARGET_PORT% "') do (
    taskkill /f /pid %%a >nul 2>&1 && echo   已终止 PID %%a ^(端口 %TARGET_PORT%^) || rem 忽略已退出
)
goto :eof

:: 轻量结构校验：app.db 存在且含 users/stocks 表则视为 OK（errorlevel 0）
:db_ok
set "DB_PATH=%PROJECT_DIR%\backend\data\app.db"
if not exist "%DB_PATH%" exit /b 1
"%PYTHON%" -c "import sqlite3,sys; c=sqlite3.connect(r'%DB_PATH%'); t={r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=?',('table',))}; sys.exit(0 if {'users','stocks'}<=t else 1)" >nul 2>&1
if errorlevel 1 ( exit /b 1 )
exit /b 0
