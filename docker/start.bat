@echo off
chcp 65001 >nul
echo ========================================
echo   启动算法Docker容器
echo ========================================
echo.

cd /d "%~dp0"

docker-compose up -d

echo.
echo 算法服务已在后台启动：
echo   多源数据融合:  容器内部 5000
echo   交通流重构:    容器内部 5001
echo   交通流预测:    容器内部 5002
echo   三层级优化:    容器内部 5003
echo.
echo 这些端口不对外暴露，只能通过教学后端代理访问。
echo 查看状态: docker-compose ps
echo 查看日志: docker-compose logs -f
echo 停止服务: docker-compose down
echo.
pause
