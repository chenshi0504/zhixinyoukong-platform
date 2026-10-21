@echo off
chcp 65001 >nul
echo ========================================
echo   智信优控综合交通实验平台 - 前端服务
echo ========================================
echo.
echo 正在启动HTTP服务器...
echo.
echo 请手动在浏览器中访问:
echo http://localhost:8000/1_Front-end/0_登录界面/login.html
echo.
echo 按 Ctrl+C 可停止服务
echo.
python -m http.server 8000
pause
