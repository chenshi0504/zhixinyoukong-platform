"""生成完整可运行的 SUMO 场景

使用 netgenerate 和 randomTrips.py 生成标准的 SUMO 场景。
"""

import os
import subprocess
import sys
from pathlib import Path


def generate_complete_scenario(
    scenario_name: str = "grid_4x4",
    traffic_level: str = "medium",
    cav_penetration: float = 0.6,
) -> Path:
    """生成完整的 SUMO 场景

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

    print(f"Generating complete SUMO scenario: {scenario_name}")
    print(f"  Output directory: {output_dir}")
    print(f"  Traffic level: {traffic_level}")
    print(f"  CAV penetration: {cav_penetration * 100:.0f}%")

    # 检查 SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        print("Error: SUMO_HOME environment variable not set!")
        print("Please install SUMO and set SUMO_HOME.")
        sys.exit(1)

    print(f"  SUMO_HOME: {sumo_home}")

    # 1. 使用 netgenerate 生成网格路网
    print("\n[1/4] Generating network with netgenerate...")
    net_file = output_dir / "grid.net.xml"

    netgenerate_cmd = [
        os.path.join(sumo_home, "bin", "netgenerate"),
        "--grid",
        "--grid.number=3",  # 3x3 节点 = 4个路口
        "--grid.length=200",
        "--default.lanenumber=2",
        "--default.speed=13.89",
        "--output-file", str(net_file),
        "--tls.guess", "true",
        "--no-turnarounds", "false",
    ]

    try:
        result = subprocess.run(netgenerate_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  [OK] Network generated: {net_file}")
        else:
            print(f"  [ERROR] netgenerate failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"  [ERROR] Error running netgenerate: {e}")
        return None

    # 2. 使用 randomTrips.py 生成交通流
    print("\n[2/4] Generating traffic with randomTrips.py...")
    trips_file = output_dir / "trips.trips.xml"
    rou_file = output_dir / "grid.rou.xml"

    # 流量等级映射到车辆数
    vehicle_counts = {
        "low": 200,
        "medium": 400,
        "high": 600,
    }
    vehicle_count = vehicle_counts.get(traffic_level, 400)

    randomtrips_script = os.path.join(sumo_home, "tools", "randomTrips.py")

    randomtrips_cmd = [
        sys.executable,  # Python 解释器
        randomtrips_script,
        "-n", str(net_file),
        "-o", str(trips_file),
        "-e", "3600",  # 仿真时长
        "--vehicle-class", "passenger",
        "--vclass", "passenger",
        "--prefix", "veh",
        "--min-distance", "200",
        "--trip-attributes", f'departLane="best" departSpeed="max"',
        "--fringe-factor", "5",
        "--period", str(3600 / vehicle_count),  # 生成间隔
    ]

    try:
        result = subprocess.run(randomtrips_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"  [OK] Trips generated: {trips_file}")
        else:
            print(f"  [ERROR] randomTrips.py failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"  [ERROR] Error running randomTrips.py: {e}")
        return None

    # 3. 使用 duarouter 将 trips 转换为 routes
    print("\n[3/4] Converting trips to routes with duarouter...")

    duarouter_cmd = [
        os.path.join(sumo_home, "bin", "duarouter"),
        "-n", str(net_file),
        "-t", str(trips_file),
        "-o", str(rou_file),
        "--ignore-errors",
        "--no-warnings",
    ]

    try:
        result = subprocess.run(duarouter_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"  [OK] Routes generated: {rou_file}")
        else:
            print(f"  [ERROR] duarouter failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"  [ERROR] Error running duarouter: {e}")
        return None

    # 4. 修改路径文件，添加 CAV 车辆类型
    print(f"\n[4/4] Adding CAV vehicle types (penetration={cav_penetration*100:.0f}%)...")
    _add_cav_types(rou_file, cav_penetration)

    # 5. 生成 SUMO 配置文件
    print("\n[5/5] Generating SUMO configuration...")
    _generate_sumocfg(output_dir)

    print(f"\n{'='*60}")
    print(f"[SUCCESS] Complete SUMO scenario generated successfully!")
    print(f"{'='*60}")
    print(f"\nTo run the simulation:")
    print(f"  cd {output_dir}")
    print(f"  sumo-gui -c grid.sumocfg")
    print(f"\nOr use the Python script:")
    print(f"  python run_multi_level_coordination.py --scenario {scenario_name}")

    return output_dir


def _add_cav_types(rou_file: Path, cav_penetration: float) -> None:
    """在路径文件中添加 CAV 车辆类型"""
    import xml.etree.ElementTree as ET

    # 解析 XML
    tree = ET.parse(rou_file)
    root = tree.getroot()

    # 添加 CAV 车辆类型（如果不存在）
    has_cav_type = False
    for vtype in root.findall("vType"):
        if vtype.get("id") == "cav":
            has_cav_type = True
            break

    if not has_cav_type:
        # 在第一个元素前插入 vType
        cav_vtype = ET.Element("vType", {
            "id": "cav",
            "accel": "3.0",
            "decel": "5.0",
            "sigma": "0.1",
            "length": "5",
            "maxSpeed": "50",
            "color": "0,1,0",
        })
        root.insert(0, cav_vtype)

    # 修改部分车辆为 CAV
    import random
    random.seed(42)

    vehicles = root.findall("vehicle")
    cav_count = 0

    for vehicle in vehicles:
        if random.random() < cav_penetration:
            vehicle.set("type", "cav")
            cav_count += 1

    # 保存修改后的文件
    tree.write(rou_file, encoding="utf-8", xml_declaration=True)

    print(f"  [OK] Modified {cav_count}/{len(vehicles)} vehicles to CAV type")


def _generate_sumocfg(output_dir: Path) -> None:
    """生成 SUMO 配置文件"""
    cfg_file = output_dir / "grid.sumocfg"

    config_content = """<?xml version="1.0" encoding="UTF-8"?>
<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">

    <input>
        <net-file value="grid.net.xml"/>
        <route-files value="grid.rou.xml"/>
    </input>

    <time>
        <begin value="0"/>
        <end value="3600"/>
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

    print(f"  [OK] Configuration file generated: {cfg_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成完整的 SUMO 场景")
    parser.add_argument("--scenario", type=str, default="grid_4x4", help="场景名称")
    parser.add_argument("--traffic-level", type=str, default="medium", choices=["low", "medium", "high"], help="流量等级")
    parser.add_argument("--cav-penetration", type=float, default=0.6, help="CAV 渗透率 (0-1)")

    args = parser.parse_args()

    generate_complete_scenario(
        scenario_name=args.scenario,
        traffic_level=args.traffic_level,
        cav_penetration=args.cav_penetration,
    )
