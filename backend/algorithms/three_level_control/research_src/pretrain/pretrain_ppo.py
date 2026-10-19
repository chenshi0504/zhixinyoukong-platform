"""
PPO 信号优化模型预训练脚本

用于在正式仿真前训练 PPO 模型，训练完成后保存模型供后续仿真使用

使用方法：
    python pretrain_ppo.py --flow 4 --episodes 30
    python pretrain_ppo.py --flow 6 --episodes 50
"""
import os
import sys
import argparse
import random
import numpy as np

# 设置全局随机种子（在所有导入之前）
GLOBAL_SEED = 42
random.seed(GLOBAL_SEED)
np.random.seed(GLOBAL_SEED)

# 尝试设置PyTorch种子
try:
    import torch
    torch.manual_seed(GLOBAL_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(GLOBAL_SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
except ImportError:
    pass

# 添加父目录到路径
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, src_dir)

# 添加tools目录到路径
tools_dir = os.path.join(src_dir, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# 添加data目录到路径
data_dir = os.path.join(os.path.dirname(src_dir), 'data')
if data_dir not in sys.path:
    sys.path.insert(0, data_dir)

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
MODELS_DIR = os.path.join(PROJECT_ROOT, 'models')

# 确保模型目录存在
if not os.path.exists(MODELS_DIR):
    os.makedirs(MODELS_DIR)


def generate_signal_config(net_file: str, output_dir: str):
    """使用与main_batch相同的方法生成signal_config.xml"""
    from regenerate_signal_config import extract_phase_edge_mapping, generate_signal_config_file
    mapping = extract_phase_edge_mapping(net_file)
    return generate_signal_config_file(mapping, output_dir)


def pretrain_ppo(flow_level: int, episodes: int = 30, save_interval: int = 10):
    """
    预训练 PPO 模型
    
    使用多轮仿真进行训练，每轮仿真后保存模型
    
    Args:
        flow_level: 流量等级 (2, 4, 6)
        episodes: 训练轮数
        save_interval: 每隔多少轮保存一次模型
    """
    import traci
    from sumolib import checkBinary
    import xml.etree.ElementTree as ET
    from importlib import import_module
    
    # 导入模块
    ppo_module = import_module('2_3_PPO')
    PPOOptimizer = ppo_module.PPOOptimizer
    
    # 导入OD生成和路由生成函数
    from od_scaler import generate_scaled_od
    from batch_generate_routes import generate_baseline_route_file
    
    # 准备配置
    net_file = os.path.join(CONFIG_DIR, "siouxfalls.net.xml")
    config_name = f"pretrain_ppo_{flow_level}"
    exp_input_dir = os.path.join(CONFIG_DIR, 'input', config_name)
    exp_output_dir = os.path.join(OUTPUT_DIR, config_name)
    
    if not os.path.exists(exp_input_dir):
        os.makedirs(exp_input_dir)
    if not os.path.exists(exp_output_dir):
        os.makedirs(exp_output_dir)
    
    # 生成信号配置（使用与main_batch相同的方法）
    generate_signal_config(net_file, exp_input_dir)
    
    # 初始化优化器（只初始化一次，跨episode保持）
    optimizer = PPOOptimizer(net_file, exp_input_dir)
    optimizer.auto_initialize(exp_input_dir)
    optimizer.enabled = True
    optimizer.set_output_dir(exp_output_dir)
    
    print(f"\n{'='*60}")
    print(f"PPO Pre-training")
    print(f"{'='*60}")
    print(f"  Flow Level: {flow_level}")
    print(f"  Episodes: {episodes}")
    print(f"  Save Interval: {save_interval}")
    print(f"  Model Dir: {MODELS_DIR}")
    print(f"{'='*60}")
    
    total_rewards = []
    
    # 多轮训练
    for episode in range(1, episodes + 1):
        print(f"\n[Episode {episode}/{episodes}]")
        
        # 生成路由文件
        generate_scaled_od(flow_level, DATA_DIR)
        route_file, _ = generate_baseline_route_file(
            CONFIG_DIR, DATA_DIR, flow_level=flow_level, output_dir=exp_input_dir
        )
        
        # 准备SUMO配置
        sumo_config = os.path.join(CONFIG_DIR, "siouxfalls.sumocfg")
        tree = ET.parse(sumo_config)
        root = tree.getroot()
        
        for input_elem in root.findall('.//route-files'):
            input_elem.set('value', os.path.abspath(route_file))
        for input_elem in root.findall('.//net-file'):
            input_elem.set('value', os.path.abspath(net_file))
        
        # 修复gui-settings-file路径（解决osm.view.xml找不到的问题）
        view_file = os.path.join(CONFIG_DIR, "osm.view.xml")
        for gui_elem in root.findall('.//gui-settings-file'):
            gui_elem.set('value', os.path.abspath(view_file))
        
        # 设置输出文件
        for output_elem in root.findall('.//output/*'):
            tag = output_elem.tag
            if tag == 'tripinfo-output':
                output_elem.set('value', os.path.join(exp_output_dir, 'tripinfo.xml'))
        
        temp_config = os.path.join(exp_input_dir, "temp.sumocfg")
        tree.write(temp_config)
        
        # 启动SUMO（先关闭可能存在的连接）
        sumo_binary = checkBinary('sumo')
        try:
            traci.close()
        except:
            pass
        
        try:
            traci.start([sumo_binary, "-c", temp_config, "--no-warnings", "--no-step-log", "-v", "false", "--seed", "42"])
        except Exception as e:
            print(f"  Failed to start SUMO: {e}")
            continue
        
        # 记录初始配时（仅第一轮）
        if episode == 1:
            optimizer.record_initial_green_times()
        
        # 运行仿真
        sim_step = 0
        max_sim_time = 8000  # 增加训练时间，接近正式仿真
        episode_reward = 0
        
        while traci.simulation.getMinExpectedNumber() > 0 and sim_step < max_sim_time:
            traci.simulationStep()
            sim_step += 1
            
            # 执行优化步骤
            optimizer.step(sim_step)
            
            # 累计奖励
            if hasattr(optimizer, 'last_reward') and optimizer.last_reward:
                episode_reward += optimizer.last_reward
            
            # 进度显示
            if sim_step % 1000 == 0:
                buf_size = len(optimizer.buffer) if hasattr(optimizer, 'buffer') else 0
                print(f"  Step {sim_step}, Training: {optimizer.training_steps}, Buffer: {buf_size}")
        
        traci.close()
        
        total_rewards.append(episode_reward)
        avg_reward = sum(total_rewards[-10:]) / min(len(total_rewards), 10)
        
        print(f"  Episode {episode} done: reward={episode_reward:.1f}, "
              f"avg(10)={avg_reward:.1f}, training={optimizer.training_steps}")
        
        # 定期保存模型
        if episode % save_interval == 0:
            model_path = os.path.join(MODELS_DIR, f"ppo_flow{flow_level}_ep{episode}.pth")
            optimizer.save_model(model_path)
    
    # 保存最终模型
    final_model_path = os.path.join(MODELS_DIR, f"ppo_flow{flow_level}_final.pth")
    optimizer.save_model(final_model_path)
    
    # 保存训练曲线
    import pandas as pd
    df = pd.DataFrame({
        'episode': range(1, len(total_rewards) + 1),
        'reward': total_rewards
    })
    df.to_csv(os.path.join(MODELS_DIR, f"ppo_flow{flow_level}_training.csv"), index=False)
    
    print(f"\n{'='*60}")
    print(f"PPO Pre-training completed!")
    print(f"  Total episodes: {episodes}")
    print(f"  Total training steps: {optimizer.training_steps}")
    print(f"  Final model: {final_model_path}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='Pre-train PPO model for signal optimization')
    parser.add_argument('--flow', type=int, default=4, choices=[2, 4, 6],
                        help='Flow level for training (default: 4)')
    parser.add_argument('--episodes', type=int, default=30,
                        help='Number of training episodes (default: 30)')
    parser.add_argument('--save-interval', type=int, default=10,
                        help='Save model every N episodes (default: 10)')
    
    args = parser.parse_args()
    pretrain_ppo(args.flow, args.episodes, args.save_interval)


if __name__ == '__main__':
    main()
