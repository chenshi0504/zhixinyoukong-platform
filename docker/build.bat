@echo off
chcp 65001 >nul
echo ========================================
echo   构建算法Docker镜像
echo ========================================
echo.

cd /d "%~dp0"

echo 正在构建算法镜像（源码将被封装在镜像内部）...
echo.

docker-compose build

echo.
echo ========================================
echo   构建完成！
echo   启动: docker-compose up -d
echo   停止: docker-compose down
echo ========================================
pause
