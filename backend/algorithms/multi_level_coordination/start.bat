@echo off
REM 多层级协调控制系统 - 快速启动脚本
REM 用于 Windows 系统

echo ============================================================
echo 多层级协调控制系统 - 快速启动
echo ============================================================
echo.

REM 检查 SUMO_HOME
if not defined SUMO_HOME (
    echo [ERROR] SUMO_HOME 环境变量未设置！
    echo 请先安装 SUMO 并设置 SUMO_HOME 环境变量。
    echo.
    echo 示例：
    echo   set SUMO_HOME=D:\Download\SUMO
    echo   set PATH=%%PATH%%;%%SUMO_HOME%%\bin
    echo.
    pause
    exit /b 1
)

echo [OK] SUMO_HOME: %SUMO_HOME%
echo.

REM 菜单选择
echo 请选择操作：
echo   1. 测试 SUMO 场景（100 步）
echo   2. 运行单个实验（无协调模式）
echo   3. 运行单个实验（局部协调模式）
echo   4. 运行单个实验（全局协调模式）
echo   5. 运行对比实验（三种模式）
echo   6. 生成新场景
echo   7. 评估实验结果
echo   0. 退出
echo.

set /p choice="请输入选项 (0-7): "

if "%choice%"=="1" goto test_scenario
if "%choice%"=="2" goto run_none
if "%choice%"=="3" goto run_local
if "%choice%"=="4" goto run_full
if "%choice%"=="5" goto run_comparison
if "%choice%"=="6" goto generate_scenario
if "%choice%"=="7" goto evaluate
if "%choice%"=="0" goto end

echo [ERROR] 无效选项！
pause
exit /b 1

:test_scenario
echo.
echo [1] 测试 SUMO 场景
echo ============================================================
python test_sumo_scenario.py --scenario grid_4x4 --max-steps 100
goto end

:run_none
echo.
echo [2] 运行实验 - 无协调模式
echo ============================================================
python run_multi_level_coordination.py --scenario grid_4x4 --coordination-mode none --max-steps 500
goto end

:run_local
echo.
echo [3] 运行实验 - 局部协调模式
echo ============================================================
python run_multi_level_coordination.py --scenario grid_4x4 --coordination-mode local --max-steps 500
goto end

:run_full
echo.
echo [4] 运行实验 - 全局协调模式
echo ============================================================
python run_multi_level_coordination.py --scenario grid_4x4 --coordination-mode full --max-steps 500
goto end

:run_comparison
echo.
echo [5] 运行对比实验（三种模式）
echo ============================================================
echo 这将依次运行 none、local、full 三种模式，需要较长时间...
echo.
set /p confirm="确认继续？(Y/N): "
if /i not "%confirm%"=="Y" goto end

python run_comparison.py --traffic-level medium --cav-penetration 0.6 --max-steps 500
goto end

:generate_scenario
echo.
echo [6] 生成新场景
echo ============================================================
set /p scenario_name="场景名称 (默认: grid_new): "
if "%scenario_name%"=="" set scenario_name=grid_new

set /p traffic_level="流量等级 (low/medium/high, 默认: medium): "
if "%traffic_level%"=="" set traffic_level=medium

set /p cav_penetration="CAV 渗透率 (0-1, 默认: 0.6): "
if "%cav_penetration%"=="" set cav_penetration=0.6

python generate_complete_scenario.py --scenario %scenario_name% --traffic-level %traffic_level% --cav-penetration %cav_penetration%
goto end

:evaluate
echo.
echo [7] 评估实验结果
echo ============================================================
cd evaluation
python metrics.py --metrics-dir ../output
cd ..
goto end

:end
echo.
echo ============================================================
echo 操作完成
echo ============================================================
pause
