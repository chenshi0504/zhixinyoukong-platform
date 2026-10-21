#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由文件生成器（模式0专用）
基于最短路径方法，从缩放后的OD生成路由文件
"""

import xml.etree.ElementTree as ET
import pandas as pd
import random
import os


class RouteGenerator:
    def __init__(self, shortest_paths_file, scaled_od_file):
        """
        初始化路由生成器
        
        Args:
            shortest_paths_file: 最短路径XML文件路径
            scaled_od_file: 缩放后的OD矩阵CSV文件路径
        """
        self.shortest_paths_file = shortest_paths_file
        self.scaled_od_file = scaled_od_file
        self.routes_dict = {}
        
    def load_shortest_paths(self):
        """加载最短路径文件"""
        print(f"  加载最短路径: {os.path.basename(self.shortest_paths_file)}")
        
        try:
            tree = ET.parse(self.shortest_paths_file)
            root = tree.getroot()
            
            for route in root.findall('route'):
                edges = route.get('edges')
                from_node = route.get('from')
                to_node = route.get('to')
                
                if from_node and to_node and edges:
                    self.routes_dict[(from_node, to_node)] = edges
            
            print(f"  成功加载 {len(self.routes_dict)} 条路径")
            return True
            
        except Exception as e:
            print(f"  加载最短路径文件失败: {e}")
            return False
    
    def generate_route_file(self, output_file, simulation_time=4800, time_interval=360):
        """
        从缩放后的OD生成路由文件
        
        Args:
            output_file: 输出文件路径
            simulation_time: 仿真时间长度（秒）
            time_interval: 时间间隔（秒）
            
        Returns:
            (success, vehicle_count)
        """
        # 读取缩放后的OD
        print(f"  加载缩放OD: {os.path.basename(self.scaled_od_file)}")
        try:
            df_od = pd.read_csv(self.scaled_od_file)
        except Exception as e:
            print(f"  加载OD文件失败: {e}")
            return False, 0
        
        # 创建XML
        root = ET.Element("routes")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xsi:noNamespaceSchemaLocation", "http://sumo.dlr.de/xsd/routes_file.xsd")
        
        # 车辆类型
        vtype_elem = ET.SubElement(root, "vType")
        vtype_elem.set("id", "passenger")
        vtype_elem.set("accel", "2.6")
        vtype_elem.set("decel", "4.5")
        vtype_elem.set("sigma", "0.5")
        vtype_elem.set("length", "5.0")
        vtype_elem.set("maxSpeed", "70.0")
        
        # 收集所有车辆
        all_trips = []
        trip_id = 0
        
        for _, row in df_od.iterrows():
            origin = str(int(row['O']))
            destination = str(int(row['D']))
            trips = int(row['Trips'])  # 使用缩放后的行程数
            
            if (origin, destination) in self.routes_dict:
                edges = self.routes_dict[(origin, destination)].split()
                
                for _ in range(trips):
                    trip_info = {
                        'id': f"trip_{trip_id}",
                        'from_edge': edges[0],
                        'to_edge': edges[-1],
                        'via_edges': " ".join(edges[1:-1]) if len(edges) > 2 else "",
                    }
                    all_trips.append(trip_info)
                    trip_id += 1
        
        total_vehicles = len(all_trips)
        print(f"  总车辆数: {total_vehicles:,} 辆")
        
        # 时间分布（在仿真时间的75%内均匀分布）
        loading_time = simulation_time * 0.75  # 3600秒
        num_intervals = int(loading_time / time_interval)
        vehicles_per_interval = total_vehicles // num_intervals
        remaining_vehicles = total_vehicles % num_intervals
        
        # 随机打乱（固定种子保证可重复性）
        random.seed(42)
        random.shuffle(all_trips)
        
        # 分配出发时间
        vehicle_index = 0
        for interval_idx in range(num_intervals):
            interval_vehicles = vehicles_per_interval + (1 if interval_idx < remaining_vehicles else 0)
            interval_start = interval_idx * time_interval
            
            for i in range(interval_vehicles):
                if vehicle_index < total_vehicles:
                    if interval_vehicles > 1:
                        depart_time = interval_start + (i / (interval_vehicles - 1)) * (time_interval - 1)
                    else:
                        depart_time = interval_start + time_interval / 2
                    
                    all_trips[vehicle_index]['depart_time'] = depart_time
                    vehicle_index += 1
        
        # 按出发时间排序
        all_trips.sort(key=lambda x: x['depart_time'])
        
        # 写入XML
        for trip_info in all_trips:
            trip_elem = ET.SubElement(root, "trip")
            trip_elem.set("id", trip_info['id'])
            trip_elem.set("depart", f"{trip_info['depart_time']:.2f}")
            trip_elem.set("from", trip_info['from_edge'])
            trip_elem.set("to", trip_info['to_edge'])
            if trip_info['via_edges']:
                trip_elem.set("via", trip_info['via_edges'])
            trip_elem.set("type", "passenger")
        
        try:
            tree = ET.ElementTree(root)
            self._indent(root)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
            print(f"  [OK] 路由文件生成成功: {os.path.basename(output_file)}")
            return True, total_vehicles
        except Exception as e:
            print(f"  [ERROR] 写入文件失败: {e}")
            return False, 0
    
    def _indent(self, elem, level=0):
        """格式化XML输出"""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self._indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i


def generate_baseline_route_file(config_dir, data_dir, experiment_id=None, flow_level=None, output_dir=None):
    """
    为模式0生成路由文件（供main.py调用）
    使用已经生成的缩放OD文件
    
    Args:
        config_dir: 配置文件目录
        data_dir: 数据文件目录
        experiment_id: 实验唯一标识（用于并行实验避免冲突，如 "0_1_X"）
        flow_level: 流量等级（用于查找按流量命名的缩放OD文件）
        output_dir: 输出目录（如果指定，路由文件保存到该目录）
        
    Returns:
        route_file: 生成的路由文件路径
        vehicle_count: 车辆数量
    """
    # 文件路径
    shortest_paths_file = os.path.join(data_dir, "shortest_paths_v2_routes.xml")
    
    # 根据参数选择缩放OD文件
    if experiment_id:
        # 并行实验模式
        scaled_od_file = os.path.join(data_dir, f"SiouxFalls_od_scaled_{experiment_id}.csv")
    elif flow_level is not None:
        # 按流量等级命名
        scaled_od_file = os.path.join(data_dir, f"SiouxFalls_od_scaled_flow{flow_level}.csv")
    else:
        # 兼容旧代码
        scaled_od_file = os.path.join(data_dir, "SiouxFalls_od_scaled.csv")
    
    # 确定输出文件路径
    if output_dir:
        # 保存到指定目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, "siouxfalls.rou.xml")
    elif experiment_id:
        output_file = os.path.join(config_dir, f"siouxfalls_{experiment_id}.rou.xml")
    else:
        output_file = os.path.join(config_dir, "siouxfalls.rou.xml")
    
    # 检查文件
    if not os.path.exists(shortest_paths_file):
        print(f"Error: Shortest paths file not found: {shortest_paths_file}")
        return None, 0
    
    if not os.path.exists(scaled_od_file):
        print(f"Error: Scaled OD file not found: {scaled_od_file}")
        print("Please select flow level first to generate scaled OD")
        return None, 0
    
    # 生成路由文件
    generator = RouteGenerator(shortest_paths_file, scaled_od_file)
    
    if not generator.load_shortest_paths():
        return None, 0
    
    success, vehicle_count = generator.generate_route_file(output_file)
    
    if success:
        return output_file, vehicle_count
    
    return None, 0


if __name__ == "__main__":
    print("此模块供main.py调用，请运行main.py")
