# 虚实结合仿真场景算法测试功能

## 功能说明

本模块提供基于SUMO的交通仿真算法测试功能，支持：
- 启动SUMO仿真
- 实时监控仿真状态
- 分析仿真结果
- 导出实验报告

## 使用步骤

### 1. 检查服务器后端服务

Web访问模式下由主平台统一监听 `http://服务器IP:8000`，本模块接口通过 `/api/simulation/*` 代理到服务器本机子服务。
页面会自动请求 `/api/simulation/health` 判断服务状态；如果显示“服务不可用”，请联系平台维护人员检查主平台服务和 SUMO 仿真子服务。

### 2. 打开前端页面

在浏览器中打开：
```
algorithm_testing.html
```

### 3. 进行算法测试

1. **选择算法类型**：基线算法、优化算法、高级算法或自定义算法
2. **选择测试场景**：城市路网、高速公路、交叉口或混合场景
3. **配置参数**：搜索半径、优化等级、收敛阈值等
4. **点击"开始测试"**：启动SUMO仿真GUI
5. **在SUMO中运行仿真**：点击SUMO界面的播放按钮
6. **点击"仿真结果"**：查看分析结果和图表
7. **点击"导出报告"**：下载实验报告文档

## 后端API接口

### 健康检查
```
GET /health
```

### 启动仿真
```
POST /start_simulation
Content-Type: application/json

{
  "algorithm": "baseline",
  "scenario": "urban"
}
```

### 分析结果
```
POST /analyze_results
```

### 下载报告
```
POST /download_report
```

## 目录结构

```
4.3_虚实结合仿真场景算法测试功能/
├── algorithm_testing.html      # 前端页面
├── algorithm_testing.js        # 前端逻辑
├── algorithm_testing.css       # 样式文件
├── backend/                    # 后端服务
│   └── simulation_server.py   # 服务器侧仿真服务
└── README.md                   # 本文档
```

## 依赖要求

- Python 3.6+
- SUMO (已安装并配置在系统PATH中)
- 现代浏览器（Chrome、Firefox、Edge等）

## 故障排除

### 问题：后端服务启动失败
- 检查Python是否已安装
- 检查端口8000是否被占用

### 问题：SUMO启动失败
- 确认SUMO已正确安装
- 确认SUMO在系统PATH中
- 检查配置文件路径是否正确

### 问题：无法查看分析结果
- 确保SUMO仿真已完成
- 检查results目录是否有输出文件
- 查看服务器后端日志获取详细错误信息

## 技术支持

如有问题，请查看服务器后端服务日志获取详细错误信息。
