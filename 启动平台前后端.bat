@echo off
chcp 65001 >nul
setlocal EnableExtensions
title 智信优控-综合交通实验平台

set "ROOT_DIR=%~dp0"
set "CONFIG_FILE=%ROOT_DIR%config.local.env"
if not exist "%CONFIG_FILE%" set "CONFIG_FILE=%ROOT_DIR%installer\env\config.local.env"
if exist "%CONFIG_FILE%" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
        if not "%%~A"=="" set "%%~A=%%~B"
    )
)

cd /d "%ROOT_DIR%backend"
if defined ZXK_PYTHON_EXE (
    set "PYTHON_CMD=%ZXK_PYTHON_EXE%"
) else (
    if defined ZXK_ALGO_PYTHON_EXE (
        set "PYTHON_CMD=%ZXK_ALGO_PYTHON_EXE%"
    ) else (
        set "PYTHON_CMD=python"
    )
)

rem 允许命令行直接指定模式，便于教学现场与自动化测试：
rem   启动平台前后端.bat demo
rem   启动平台前后端.bat student
if defined ZXK_RUN_MODE goto :mode_ready
if /i "%~1"=="demo" (
    set "ZXK_RUN_MODE=demo"
    goto :mode_ready
)
if /i "%~1"=="student" (
    set "ZXK_RUN_MODE=student"
    goto :mode_ready
)

:ask_mode
cls
echo ========================================
echo   智信优控 - 综合交通实验平台
echo ========================================
echo.
echo   请选择平台运行模式：
echo.
echo   [1] 演示模式 demo
echo       后端会弹出 CMD、SUMO-GUI、CARLA 等窗口，
echo       适合课堂演示、讲解和现场排障。
echo.
echo   [2] 学生模式 student
echo       后端完全静默运行，不弹任何 CMD/SUMO/CARLA 窗口，
echo       学生通过浏览器照常查看状态、提交任务、下载结果。
echo.
echo   15 秒内不选择，默认按学生模式启动。
echo.
choice /c 12 /n /t 15 /d 2 /m "请选择运行模式 [1=演示模式 2=学生模式]: "
if errorlevel 2 (
    set "ZXK_RUN_MODE=student"
) else (
    set "ZXK_RUN_MODE=demo"
)

:mode_ready
rem 兼容 demo/演示/1、student/学生/0 等写法，统一成 demo / student。
rem 未填写或无法识别时按学生模式处理，避免误弹窗口。
if /i "%ZXK_RUN_MODE%"=="demo" goto :mode_demo
if /i "%ZXK_RUN_MODE%"=="演示" goto :mode_demo
if /i "%ZXK_RUN_MODE%"=="演示模式" goto :mode_demo
if /i "%ZXK_RUN_MODE%"=="1" goto :mode_demo
goto :mode_student

:mode_demo
set "ZXK_RUN_MODE=demo"
set "MODE_LABEL=演示模式"
set "MODE_DESC=后端将弹出 SUMO/CMD/CARLA 窗口"
set "PLATFORM_SILENT="
goto :mode_summary

:mode_student
set "ZXK_RUN_MODE=student"
set "MODE_LABEL=学生模式"
set "MODE_DESC=后端静默运行，不弹任何窗口"
rem 学生模式不打开服务器浏览器，界面只在访问端打开
set "PLATFORM_SILENT=1"

:mode_summary
title 智信优控-综合交通实验平台 [%MODE_LABEL%]
cls
echo ========================================
echo   智信优控 - 综合交通实验平台
echo ========================================
echo.
echo   运行模式: %MODE_LABEL%
echo   %MODE_DESC%
echo.
echo   本机访问:   http://localhost:8000
if defined LOCAL_APP_PORT if not "%LOCAL_APP_PORT%"=="8000" echo   本机访问:   http://localhost:%LOCAL_APP_PORT%
echo   局域网访问: http://本机IPv4地址:8000   ^(学生浏览器使用^)
echo               可用 ipconfig 查看本机 IPv4 地址
echo.
echo   所有平台服务（主服务、交通流重构、SUMO 仿真）将在本窗口启动
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

rem 放行局域网访问 8000 端口（已存在规则时会失败，忽略即可）
netsh advfirewall firewall add rule name="ZXYK Local Platform Web 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>nul

:run_services
"%PYTHON_CMD%" run.py

echo.
echo ========================================
echo   服务已停止
echo ========================================
echo.
set "choice="
set /p choice=是否重启服务？(yes/no): 
if /i "%choice%"=="yes" goto :run_services
if /i "%choice%"=="y" goto :run_services
echo 正在退出...
endlocal
exit /b 0
