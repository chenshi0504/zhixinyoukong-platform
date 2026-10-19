@echo off
chcp 65001 >nul
echo ========================================
echo 综合交通实验平台 - 批量启动后端服务
echo ========================================
echo.

cd /d "%~dp0"

echo [1/6] 正在启动多源数据融合后端服务...
echo 端口: 5000
start "数据融合服务-5000" cmd /k "cd /d "%~dp03_Back-end\algorithm\2_多源数据融合" && python simple_server.py"
timeout /t 2 /nobreak >nul

echo.
echo [2/6] 正在启动多源数据采集后端服务...
echo 端口: 5002
start "数据采集服务-5002" cmd /k "cd /d "%~dp03_Back-end\algorithm\1_多源数据采集\yolov4_车辆检测跟踪" && python detection_server.py"
timeout /t 1 /nobreak >nul

echo.
echo [3/6] 正在启动交通流预测后端服务...
echo 端口: 5003
start "交通流预测服务-5003" cmd /k "cd /d "%~dp03_Back-end\algorithm\3_交通流预测" && python prediction_server.py"
timeout /t 1 /nobreak >nul

echo.
echo [4/6] 正在启动交通流重构后端服务...
echo 端口: 5001
start "交通流重构服务-5001" cmd /k "cd /d "%~dp03_Back-end\algorithm\4_交通流重构" && python reconstruction_server.py"
timeout /t 1 /nobreak >nul

echo.
echo [5/6] 正在启动三层级优化后端服务...
echo 端口: 8002
start "三层级优化服务-8002" cmd /k "cd /d "%~dp03_Back-end\algorithm\5_三层级优化" && python backend_server.py"
timeout /t 1 /nobreak >nul

echo.
echo [6/6] 正在启动SUMO仿真测试后端服务...
echo 端口: 8001
start "SUMO仿真服务-8001" cmd /k "cd /d "%~dp01_Front-end\4_面向车路协同的虚实结合仿真模块\4.3_虚实结合仿真场景算法测试功能\backend" && python simulation_server.py"
timeout /t 1 /nobreak >nul

echo.
echo ========================================
echo 所有后端服务启动完成！
echo ========================================
echo.
echo 已启动的服务：
echo.
echo   模块1 - 多源数据采集与融合：
echo     - 数据融合服务    http://localhost:5000
echo     - 数据采集服务    http://localhost:5002
echo.
echo   模块2 - 交通流重构与预测：
echo     - 交通流预测服务  http://localhost:5003
echo     - 交通流重构服务  http://localhost:5001
echo.
echo   模块3 - 三层级协同优化控制：
echo     - 三层级优化服务  http://localhost:8002
echo.
echo   模块4 - 虚实结合仿真：
echo     - SUMO仿真服务    http://localhost:8001
echo.
echo ========================================
echo.
echo 单独启动脚本位置：
echo   3_Back-end\algorithm\1_多源数据采集\启动多源数据采集后端.bat
echo   3_Back-end\algorithm\2_多源数据融合\启动多源数据融合后端.bat
echo   3_Back-end\algorithm\3_交通流预测\启动交通流预测后端.bat
echo   3_Back-end\algorithm\4_交通流重构\启动交通流重构后端.bat
echo   3_Back-end\algorithm\5_三层级优化\启动三层级优化后端.bat
echo.
echo 提示：关闭对应窗口即可停止该服务
echo ========================================
echo.
pause
