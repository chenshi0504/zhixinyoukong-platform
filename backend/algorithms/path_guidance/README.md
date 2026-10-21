# 路径诱导模块

## 模块简介
基于动态交通信息的路径诱导系统，为车辆提供实时最优路径规划，减少拥堵和出行时间。

## 算法原理

### 路径规划算法
- **Dijkstra算法**: 经典最短路径算法，适合静态路网
- **A*算法**: 启发式搜索，提高搜索效率
- **动态路径规划**: 基于实时交通流数据的自适应路径选择

### 交通流预测
- 基于历史数据的流量预测
- 考虑路段容量和拥堵状态
- 实时更新路径成本

## 主要功能
- 单车辆最优路径规划
- 多车辆协同路径诱导
- 实时路况更新
- 路径成本计算（时间、距离、拥堵）
- 路径可视化展示

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| origin | str | - | 起点位置 |
| destination | str | - | 终点位置 |
| algorithm | str | dijkstra | 路径算法（dijkstra/astar/dynamic） |
| cost_type | str | time | 成本类型（time/distance/mixed） |
| avoid_congestion | bool | true | 是否避开拥堵路段 |
| num_vehicles | int | 100 | 诱导车辆数量 |
| penetration_rate | float | 0.5 | CAV渗透率（0-1） |

### 运行示例

**通过Web界面运行**:
1. 在实验平台选择"路径诱导"模块
2. 设置起点和终点
3. 选择路径算法和成本类型
4. 点击"开始诱导"按钮

**通过命令行运行**:
```bash
cd backend/algorithms/path_guidance
python run_path_guidance.py --origin A --destination B --algorithm dijkstra
```

### API调用
```python
import requests

# 请求路径规划
response = requests.post('http://localhost:5003/plan', json={
    'origin': 'A',
    'destination': 'B',
    'algorithm': 'dijkstra',
    'cost_type': 'time'
})

# 获取路径结果
path = response.json()['path']
```

## 输出结果
- **路径规划结果JSON**: `output/path_result_{timestamp}.json`
  - 路径节点序列、总成本、预计时间
- **路径可视化图**: `output/path_visualization_{timestamp}.png`
  - 路网图和规划路径
- **诱导效果统计**: `output/guidance_statistics_{timestamp}.json`
  - 平均出行时间、拥堵缓解率、系统总延误

## 性能指标
- **平均出行时间**: 所有车辆的平均行程时间
- **路径长度**: 平均路径长度（公里）
- **拥堵缓解率**: 相比无诱导的拥堵改善百分比
- **系统总延误**: 所有车辆的总延误时间

## 依赖环境
- Python 3.10
- SUMO 1.15+
- networkx (图算法库)
- numpy, pandas
- matplotlib

## 常见问题

### 1. 找不到路径
**问题**: 提示"无法找到从A到B的路径"
**解决方案**:
- 检查起点和终点是否在路网中
- 确认路网连通性
- 查看路网配置文件是否正确

### 2. 路径不合理
**问题**: 规划的路径绕远或不符合实际
**解决方案**:
- 检查路段成本设置是否合理
- 调整cost_type参数（时间/距离/混合）
- 更新实时交通流数据

### 3. 诱导效果不明显
**问题**: 诱导后出行时间改善小于5%
**解决方案**:
- 增加CAV渗透率（如0.8）
- 使用动态路径规划算法
- 增加诱导车辆数量
- 检查路网是否有足够的替代路径

## 技术细节

### Dijkstra算法实现
```python
def dijkstra(graph, start, end):
    distances = {node: float('inf') for node in graph}
    distances[start] = 0
    visited = set()
    
    while len(visited) < len(graph):
        # 选择未访问节点中距离最小的
        current = min((node for node in graph if node not in visited),
                     key=lambda x: distances[x])
        visited.add(current)
        
        # 更新相邻节点距离
        for neighbor, cost in graph[current].items():
            new_distance = distances[current] + cost
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
    
    return distances[end]
```

### 路段成本计算
```python
# 时间成本 = 自由流时间 * (1 + α * (流量/容量)^β)
travel_time = free_flow_time * (1 + 0.15 * (flow / capacity) ** 4)

# 混合成本 = w1 * 时间 + w2 * 距离
mixed_cost = 0.7 * travel_time + 0.3 * distance
```

### SUMO路网配置
- 路网文件: `data/network.net.xml`
- 路由文件: `data/routes.rou.xml`
- 配置文件: `data/config.sumocfg`

## 实验建议

### 基础实验
1. 使用Dijkstra算法规划单条路径
2. 对比不同成本类型的路径差异
3. 观察路径可视化结果

### 进阶实验
1. 对比不同算法的性能（Dijkstra vs A*）
2. 测试不同CAV渗透率的诱导效果
3. 分析多车辆协同诱导的系统优化
4. 研究拥堵情况下的动态路径调整

## 参考文献
1. Dijkstra, E. W., "A note on two problems in connexion with graphs", 1959
2. Hart, P. E., et al., "A Formal Basis for the Heuristic Determination of Minimum Cost Paths", 1968
3. 交通流理论: Lighthill-Whitham-Richards (LWR) 模型
