@echo off
chcp 65001 >nul

:restart
cls
title 智信优控-综合交通实验平台
echo ========================================
echo   综合交通实验教学平台 - 一键启动
echo ========================================
echo.
echo   所有服务将在同一窗口中启动
echo   按 ^Ctrl+C 停止服务
echo ========================================
echo.

set "CONFIG_FILE=%~dp0config.local.env"
if not exist "%CONFIG_FILE%" set "CONFIG_FILE=%~dp0installer\env\config.local.env"
if exist "%CONFIG_FILE%" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
        if not "%%~A"=="" set "%%~A=%%~B"
    )
)

cd /d "%~dp0backend"
if defined ZXK_PYTHON_EXE (
    set "PYTHON_CMD=%ZXK_PYTHON_EXE%"
) else (
    if defined ZXK_ALGO_PYTHON_EXE (
        set "PYTHON_CMD=%ZXK_ALGO_PYTHON_EXE%"
    ) else (
        set "PYTHON_CMD=python"
    )
)
cmd /c ""%PYTHON_CMD%" run.py"

echo.
echo ========================================
echo   服务已停止
echo ========================================
echo.
set /p choice=是否重启服务？(yes/no): 
if /i "%choice%"=="yes" goto restart
if /i "%choice%"=="y" goto restart
echo 正在退出...
exit
