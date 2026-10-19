"""SUMO 场景生成工具

生成多路口区域路网和交通流配置。
"""

import os
from pathlib import Path
from typing import List, Tuple


def generate_grid_network(
    output_dir: Path,
    grid_size: Tuple[int, int] = (2, 2),
    block_length: float = 200.0,
    lane_count: int = 2,
) -> None:
    """生成网格路网

    Args:
        output_dir: 输出目录
        grid_size: 网格大小 (rows, cols)
        block_length: 街区长度 (米)
        lane_count: 每个方向的车道数
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    rows, cols = grid_size
    net_file = output_dir / "grid.net.xml"

    # 生成节点和边
    nodes = []
    edges = []
    connections = []

    # 创建节点
    for i in range(rows + 1):
        for j in range(cols + 1):
            node_id = f"n_{i}_{j}"
            x = j * block_length
            y = i * block_length
            nodes.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="traffic_light"/>')

    # 创建边（水平和垂直）
    edge_id = 0

    # 水平边
    for i in range(rows + 1):
        for j in range(cols):
            # 向右
            from_node = f"n_{i}_{j}"
            to_node = f"n_{i}_{j+1}"
            edge_id_str = f"e_{edge_id}"
            edges.append(
                f'    <edge id="{edge_id_str}" from="{from_node}" to="{to_node}" '
                f'numLanes="{lane_count}" speed="13.89"/>'
            )
            edge_id += 1

            # 向左
            edge_id_str = f"e_{edge_id}"
            edges.append(
                f'    <edge id="{edge_id_str}" from="{to_node}" to="{from_node}" '
                f'numLanes="{lane_count}" speed="13.89"/>'
            )
            edge_id += 1

    # 垂直边
    for i in range(rows):
        for j in range(cols + 1):
            # 向上
            from_node = f"n_{i}_{j}"
            to_node = f"n_{i+1}_{j}"
            edge_id_str = f"e_{edge_id}"
            edges.append(
                f'    <edge id="{edge_id_str}" from="{from_node}" to="{to_node}" '
                f'numLanes="{lane_count}" speed="13.89"/>'
            )
            edge_id += 1

            # 向下
            edge_id_str = f"e_{edge_id}"
            edges.append(
                f'    <edge id="{edge_id_str}" from="{to_node}" to="{from_node}" '
                f'numLanes="{lane_count}" speed="13.89"/>'
            )
            edge_id += 1

    # 写入网络文件
    with open(net_file, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<net version="1.9" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        f.write('xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/net_file.xsd">\n\n')

        # 写入节点
        f.write("  <nodes>\n")
        f.write("\n".join(nodes))
        f.write("\n  </nodes>\n\n")

        # 写入边
        f.write("  <edges>\n")
        f.write("\n".join(edges))
        f.write("\n  </edges>\n\n")

        f.write("</net>\n")

    print(f"Network file generated: {net_file}")


def generate_traffic_flow(
    output_dir: Path,
    duration: int = 3600,
    flow_rate: float = 0.1,
    cav_penetration: float = 0.6,
) -> None:
    """生成交通流配置

    Args:
        output_dir: 输出目录
        duration: 仿真时长 (秒)
        flow_rate: 车流生成率 (车辆/秒)
        cav_penetration: CAV 渗透率 (0-1)
    """
    rou_file = output_dir / "grid.rou.xml"

    # 定义车辆类型
    vehicle_types = [
        '    <vType id="normal" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="50" color="1,1,0"/>',
        '    <vType id="cav" accel="3.0" decel="5.0" sigma="0.1" length="5" maxSpeed="50" color="0,1,0"/>',
    ]

    # 定义路径（简化：4个主要OD对）
    routes = [
        '    <route id="route_0" edges="e_0 e_2 e_4 e_6"/>',
        '    <route id="route_1" edges="e_8 e_10 e_12 e_14"/>',
        '    <route id="route_2" edges="e_1 e_3 e_5 e_7"/>',
        '    <route id="route_3" edges="e_9 e_11 e_13 e_15"/>',
    ]

    # 生成车流
    flows = []
    for route_id in range(4):
        # 普通车辆流
        normal_rate = flow_rate * (1 - cav_penetration)
        if normal_rate > 0:
            flows.append(
                f'    <flow id="flow_normal_{route_id}" type="normal" route="route_{route_id}" '
                f'begin="0" end="{duration}" probability="{normal_rate}"/>'
            )

        # CAV 车辆流
        cav_rate = flow_rate * cav_penetration
        if cav_rate > 0:
            flows.append(
                f'    <flow id="flow_cav_{route_id}" type="cav" route="route_{route_id}" '
                f'begin="0" end="{duration}" probability="{cav_rate}"/>'
            )

    # 写入路径文件
    with open(rou_file, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        f.write('xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n\n')

        # 写入车辆类型
        f.write("  <!-- Vehicle Types -->\n")
        f.write("\n".join(vehicle_types))
        f.write("\n\n")

        # 写入路径
        f.write("  <!-- Routes -->\n")
        f.write("\n".join(routes))
        f.write("\n\n")

        # 写入车流
        f.write("  <!-- Flows -->\n")
        f.write("\n".join(flows))
        f.write("\n\n")

        f.write("</routes>\n")

    print(f"Route file generated: {rou_file}")


def generate_sumo_config(
    output_dir: Path,
    duration: int = 3600,
) -> None:
    """生成 SUMO 配置文件

    Args:
        output_dir: 输出目录
        duration: 仿真时长 (秒)
    """
    cfg_file = output_dir / "grid.sumocfg"

    config_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">

    <input>
        <net-file value="grid.net.xml"/>
        <route-files value="grid.rou.xml"/>
    </input>

    <time>
        <begin value="0"/>
        <end value="{duration}"/>
        <step-length value="1"/>
    </time>

    <processing>
        <time-to-teleport value="-1"/>
    </processing>

    <report>
        <verbose value="false"/>
        <no-step-log value="true"/>
        <no-warnings value="true"/>
    </report>

    <gui_only>
        <start value="true"/>
        <quit-on-end value="false"/>
    </gui_only>

</configuration>
"""

    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"Config file generated: {cfg_file}")


def generate_scenario(
    scenario_name: str = "grid_4x4",
    traffic_level: str = "medium",
    cav_penetration: float = 0.6,
) -> Path:
    """生成完整场景

    Args:
        scenario_name: 场景名称
        traffic_level: 流量等级 (low/medium/high)
        cav_penetration: CAV 渗透率

    Returns:
        Path: 场景目录路径
    """
    # 确定输出目录
    base_dir = Path(__file__).parent
    output_dir = base_dir / "scenarios" / scenario_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 流量等级映射
    flow_rates = {
        "low": 0.05,    # 180 辆/小时/方向
        "medium": 0.1,  # 360 辆/小时/方向
        "high": 0.15,   # 540 辆/小时/方向
    }
    flow_rate = flow_rates.get(traffic_level, 0.1)

    print(f"Generating scenario: {scenario_name}")
    print(f"  Traffic level: {traffic_level} (flow_rate={flow_rate})")
    print(f"  CAV penetration: {cav_penetration * 100:.0f}%")

    # 生成网络
    generate_grid_network(output_dir, grid_size=(2, 2), block_length=200.0)

    # 生成交通流
    generate_traffic_flow(
        output_dir,
        duration=3600,
        flow_rate=flow_rate,
        cav_penetration=cav_penetration,
    )

    # 生成配置文件
    generate_sumo_config(output_dir, duration=3600)

    print(f"\nScenario generated successfully at: {output_dir}")
    return output_dir


if __name__ == "__main__":
    # 生成默认场景
    generate_scenario(
        scenario_name="grid_4x4",
        traffic_level="medium",
        cav_penetration=0.6,
    )
