@echo off
chcp 65001 >nul
echo ========================================
echo   智信优控 · 云端管理平台 启动脚本
echo ========================================
echo.

set "CLOUD_ROOT=%~dp0"
set "CLOUD_BACKEND=%CLOUD_ROOT%backend"
if "%CLOUD_PORT%"=="" set "CLOUD_PORT=9100"

:: ---------- Python 解释器 ----------
if defined ZXK_CLOUD_PYTHON_EXE (
    set "PYTHON_CMD=%ZXK_CLOUD_PYTHON_EXE%"
) else (
    set "PYTHON_CMD=python"
)

:: ---------- 依赖检查 ----------
echo [1/5] 检查 Python 依赖...
%PYTHON_CMD% -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, jose, bcrypt" 2>nul
if errorlevel 1 (
    echo   依赖缺失，正在安装...
    %PYTHON_CMD% -m pip install -r "%CLOUD_BACKEND%\requirements.txt" --quiet
)
echo   依赖检查完成
echo.

:: ---------- 构建前端 ----------
echo [2/5] 构建云端前端页面...
where node >nul 2>&1
if errorlevel 1 (
    echo   [警告] 未检测到 Node.js，将使用已有 dist 目录
) else (
    pushd "%CLOUD_ROOT%frontend"
    if not exist node_modules (
        echo   正在安装前端依赖...
        call npm install
    )
    call npm run build
    popd
)

:: ---------- 后端协议选择 ----------
echo.
echo [3/5] 选择后端协议:
echo   1. HTTP  模式（推荐）
echo   2. HTTPS 模式（使用自签证书）
echo.
set /p PROTOCOL_MODE="请输入 [1/2] (默认 1): "
if "%PROTOCOL_MODE%"=="" set PROTOCOL_MODE=1

:: ---------- 启动后端 ----------
echo.
echo [4/5] 启动后端 API 服务...
if "%PROTOCOL_MODE%"=="2" (
    echo   HTTPS 模式: https://localhost:%CLOUD_PORT%
    start "云端平台Web服务" /B /D "%CLOUD_BACKEND%" %PYTHON_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port %CLOUD_PORT% --ssl-keyfile key.pem --ssl-certfile cert.pem
) else (
    echo   HTTP 模式: http://localhost:%CLOUD_PORT%
    start "云端平台Web服务" /B /D "%CLOUD_BACKEND%" %PYTHON_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port %CLOUD_PORT%
)

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: ---------- 访问说明 ----------
echo.
echo [5/5] 云端平台由 %CLOUD_PORT% 端口统一提供前端页面和后端 API
start http://localhost:%CLOUD_PORT%/#/login

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo   云端页面:  http://localhost:%CLOUD_PORT%/#/login
echo   后端 API:  http://localhost:%CLOUD_PORT%/api/cloud/health
echo   API 文档:  http://localhost:%CLOUD_PORT%/docs
echo ========================================
echo.
pause
