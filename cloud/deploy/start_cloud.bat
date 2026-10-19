@echo off
chcp 65001 >nul
echo ========================================
echo   智信优控 · 云端管理平台 启动脚本
echo ========================================
echo.

set "CLOUD_ROOT=%~dp0.."
set "CLOUD_BACKEND=%CLOUD_ROOT%\backend"

:: ---------- Python 解释器 ----------
if defined ZXK_CLOUD_PYTHON_EXE (
    set "PYTHON_CMD=%ZXK_CLOUD_PYTHON_EXE%"
) else (
    set "PYTHON_CMD=python"
)

:: ---------- 依赖检查 ----------
echo [1/4] 检查 Python 依赖...
%PYTHON_CMD% -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, jose, bcrypt" 2>nul
if errorlevel 1 (
    echo   依赖缺失，正在安装...
    %PYTHON_CMD% -m pip install -r "%CLOUD_BACKEND%\requirements.txt" --quiet
)
echo   依赖检查完成
echo.

:: ---------- 启动模式选择 ----------
echo [2/4] 选择启动模式:
echo   1. HTTP  模式（配合 cpolar/frp 等内网穿透工具使用，推荐）
echo   2. HTTPS 模式（使用自签证书，适合局域网测试）
echo.
set /p MODE="请输入 [1/2] (默认 1): "
if "%MODE%"=="" set MODE=1

:: ---------- 启动后端 ----------
echo.
echo [3/4] 启动后端 API 服务...
if "%MODE%"=="2" (
    echo   HTTPS 模式: https://localhost:9000
    start "云端后端API" /B /D "%CLOUD_BACKEND%" %PYTHON_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --ssl-keyfile key.pem --ssl-certfile cert.pem
) else (
    echo   HTTP 模式: http://localhost:9000
    start "云端后端API" /B /D "%CLOUD_BACKEND%" %PYTHON_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 9000
)

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: ---------- 可选：启动 cpolar 穿透 ----------
echo.
echo [4/4] 是否启动 cpolar 内网穿透？
echo   （需要已安装 cpolar 并完成 authtoken 配置）
set /p TUNNEL="启动 cpolar? [y/N]: "
if /i "%TUNNEL%"=="y" (
    where cpolar >nul 2>&1
    if errorlevel 1 (
        echo   [错误] cpolar 未安装或不在 PATH 中
        echo   下载地址: https://www.cpolar.com/
    ) else (
        echo   正在启动 cpolar 穿透 9000 端口...
        start "cpolar隧道" /B cpolar http 9000
        echo   请在 cpolar 窗口中查看公网地址
        echo   ⚠️ 请将公网地址更新到:
        echo      1. cloud/frontend/.env.production 的 VITE_API_BASE_URL
        echo      2. cloud/backend/.env 的 ALLOWED_ORIGINS
        echo      3. 本地安装包 backend/.env 的 CLOUD_API_URL
    )
)

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo   后端 API:  http://localhost:9000/api/cloud/health
echo   云端前端:  https://chenshi0504.github.io/zhixinyoukong-cloud/
echo   API 文档:  http://localhost:9000/docs
echo ========================================
echo.
pause
