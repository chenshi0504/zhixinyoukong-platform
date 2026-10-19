"""
SUMO输出文件分析模块
处理SUMO仿真输出的XML文件，提取额外的评价指标
只分析tripinfo和summary文件，避免影响仿真性能
"""
import os
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np


class SumoOutputAnalyzer:
    """SUMO输出文件分析器（轻量级版本）"""
    
    def __init__(self, output_dir):
        """
        初始化分析器
        
        Args:
            output_dir: SUMO输出文件目录
        """
        self.output_dir = output_dir
        self.results = {}
    
    def analyze_tripinfo(self, tripinfo_file):
        """
        分析tripinfo文件，提取车辆行程信息
        
        Args:
            tripinfo_file: tripinfo.xml文件路径
            
        Returns:
            dict: 包含平均速度、停车次数等指标
        """
        if not os.path.exists(tripinfo_file):
            print(f"Warning: tripinfo file not found: {tripinfo_file}")
            return {}
        
        try:
            tree = ET.parse(tripinfo_file)
            root = tree.getroot()
            
            speeds = []
            durations = []
            waiting_times = []
            time_losses = []
            depart_delays = []
            
            for tripinfo in root.findall('tripinfo'):
                duration = float(tripinfo.get('duration', 0))
                route_length = float(tripinfo.get('routeLength', 0))
                waiting_time = float(tripinfo.get('waitingTime', 0))
                time_loss = float(tripinfo.get('timeLoss', 0))
                depart_delay = float(tripinfo.get('departDelay', 0))
                
                if duration > 0 and route_length > 0:
                    avg_speed = route_length / duration
                    speeds.append(avg_speed)
                
                durations.append(duration)
                waiting_times.append(waiting_time)
                time_losses.append(time_loss)
                depart_delays.append(depart_delay)
            
            results = {
                'avg_speed': np.mean(speeds) if speeds else 0,
                'avg_duration': np.mean(durations) if durations else 0,
                'avg_waiting_time': np.mean(waiting_times) if waiting_times else 0,
                'avg_time_loss': np.mean(time_losses) if time_losses else 0,
                'avg_depart_delay': np.mean(depart_delays) if depart_delays else 0,
                'total_vehicles': len(durations)
            }
            
            return results
            
        except Exception as e:
            print(f"Error analyzing tripinfo file: {e}")
            return {}
    

    
    def analyze_summary(self, summary_file):
        """
        分析summary文件，提取总体统计信息
        
        Args:
            summary_file: summary.xml文件路径
            
        Returns:
            dict: 包含总体统计指标
        """
        if not os.path.exists(summary_file):
            print(f"Warning: summary file not found: {summary_file}")
            return {}
        
        try:
            tree = ET.parse(summary_file)
            root = tree.getroot()
            
            # 获取最后一个时间步的统计
            last_step = None
            for step in root.findall('step'):
                last_step = step
            
            if last_step is not None:
                results = {
                    'simulation_time': float(last_step.get('time', 0)),
                    'vehicles_loaded': int(last_step.get('loaded', 0)),
                    'vehicles_inserted': int(last_step.get('inserted', 0)),
                    'vehicles_running': int(last_step.get('running', 0)),
                    'vehicles_waiting': int(last_step.get('waiting', 0)),
                    'vehicles_ended': int(last_step.get('ended', 0)),
                    'mean_waiting_time': float(last_step.get('meanWaitingTime', 0)),
                    'mean_travel_time': float(last_step.get('meanTravelTime', 0)),
                    'mean_speed': float(last_step.get('meanSpeed', 0))
                }
                return results
            
            return {}
            
        except Exception as e:
            print(f"Error analyzing summary file: {e}")
            return {}
    
    def analyze_all(self, mode, flow, pr):
        """
        分析所有输出文件（仅tripinfo和summary）- 旧目录结构
        
        Args:
            mode: 实验模式
            flow: 流量比例
            pr: 渗透率
            
        Returns:
            dict: 所有分析结果
        """
        print(f"\nAnalyzing SUMO output files...")
        
        # 构建文件名（旧目录结构）
        tripinfo_file = os.path.join(self.output_dir, f'tripinfo_{mode}_{flow}_{pr}.xml')
        summary_file = os.path.join(self.output_dir, f'summary_{mode}_{flow}_{pr}.xml')
        
        # 分析各个文件
        tripinfo_results = self.analyze_tripinfo(tripinfo_file)
        summary_results = self.analyze_summary(summary_file)
        
        # 合并结果
        all_results = {
            **tripinfo_results,
            **summary_results
        }
        
        print(f"Analysis completed, extracted {len(all_results)} metrics")
        
        return all_results
    
    def analyze_all_new(self):
        """
        分析所有输出文件（仅tripinfo和summary）- 新目录结构
        
        新目录结构：output/{config_name}/
        - tripinfo.xml
        - summary.xml
        
        Returns:
            dict: 所有分析结果
        """
        print(f"\nAnalyzing SUMO output files (new structure)...")
        
        # 新目录结构：直接在实验配置目录下
        tripinfo_file = os.path.join(self.output_dir, 'tripinfo.xml')
        summary_file = os.path.join(self.output_dir, 'summary.xml')
        
        # 分析各个文件
        tripinfo_results = self.analyze_tripinfo(tripinfo_file)
        summary_results = self.analyze_summary(summary_file)
        
        # 合并结果
        all_results = {
            **tripinfo_results,
            **summary_results
        }
        
        print(f"Analysis completed, extracted {len(all_results)} metrics")
        
        return all_results
    
    def save_to_excel(self, results, output_file, mode_name):
        """
        将分析结果保存到Excel
        
        Args:
            results: 分析结果字典
            output_file: 输出文件路径
            mode_name: 实验模式名称
        """
        # 准备数据
        data = {
            '指标类别': [],
            '指标名称': [],
            '数值': [],
            '单位': []
        }
        
        # 定义指标分类和单位
        metrics_info = {
            # 行程指标（来自tripinfo）
            'avg_speed': ('行程指标', '平均速度', 'm/s'),
            'avg_duration': ('行程指标', '平均行程时间', 's'),
            'avg_waiting_time': ('行程指标', '平均等待时间', 's'),
            'avg_time_loss': ('行程指标', '平均时间损失', 's'),
            'avg_depart_delay': ('行程指标', '平均出发延误', 's'),
            'total_vehicles': ('行程指标', '完成车辆数', '辆'),
            
            # 总体指标（来自summary）
            'simulation_time': ('总体指标', '仿真时间', 's'),
            'vehicles_loaded': ('总体指标', '加载车辆数', '辆'),
            'vehicles_inserted': ('总体指标', '插入车辆数', '辆'),
            'vehicles_running': ('总体指标', '运行中车辆数', '辆'),
            'vehicles_waiting': ('总体指标', '等待中车辆数', '辆'),
            'vehicles_ended': ('总体指标', '结束车辆数', '辆'),
            'mean_waiting_time': ('总体指标', '平均等待时间(summary)', 's'),
            'mean_travel_time': ('总体指标', '平均行程时间(summary)', 's'),
            'mean_speed': ('总体指标', '平均速度(summary)', 'm/s')
        }
        
        # 填充数据
        for key, value in results.items():
            if key in metrics_info:
                category, name, unit = metrics_info[key]
                data['指标类别'].append(category)
                data['指标名称'].append(name)
                data['数值'].append(value)
                data['单位'].append(unit)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 保存到Excel
        with pd.ExcelWriter(output_file, engine='openpyxl', mode='a' if os.path.exists(output_file) else 'w') as writer:
            sheet_name = f'{mode_name}_详细指标'
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        print(f"Detailed metrics saved to: {output_file}, sheet: {sheet_name}")


def test_analyzer():
    """测试分析器"""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    analyzer = SumoOutputAnalyzer(output_dir)
    
    # 测试分析
    results = analyzer.analyze_all(mode='test', flow='3', pr='80')
    
    # 打印结果
    print("\n分析结果:")
    for key, value in results.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python 5_analysis.py <mode> <flow> <pr>")
        print("Example: python 5_analysis.py 2 1 5")
        test_analyzer()
    else:
        mode = sys.argv[1]
        flow = sys.argv[2]
        pr = sys.argv[3]
        
        # 设置路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, 'output')
        
        # 执行分析
        analyzer = SumoOutputAnalyzer(output_dir)
        results = analyzer.analyze_all(mode, flow, pr)
        
        # 打印结果
        print("\n分析结果:")
        for key, value in results.items():
            print(f"  {key}: {value}")
