@echo off
chcp 65001 >nul
echo ========================================
echo   综合交通实验教学平台 - 启动后端服务
echo ========================================
echo.

cd /d "%~dp0..\backend"

echo 正在初始化数据库并启动服务...
python run.py

pause
