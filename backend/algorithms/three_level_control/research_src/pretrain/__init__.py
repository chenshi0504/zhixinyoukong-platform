"""
预训练模块

包含 DQN 和 PPO 的预训练脚本

使用方法：
    # DQN 预训练
    python -m pretrain.pretrain_dqn --flow 4 --episodes 30
    
    # PPO 预训练
    python -m pretrain.pretrain_ppo --flow 4 --episodes 30
    
    # 或者直接运行
    cd Step2_Algorithm/src/pretrain
    python pretrain_dqn.py --flow 4 --episodes 30
    python pretrain_ppo.py --flow 4 --episodes 30

模型保存位置：
    Step2_Algorithm/models/
    - dqn_flow{X}_final.pth
    - ppo_flow{X}_final.pth
"""

from pathlib import Path

# 模型目录
MODELS_DIR = Path(__file__).parent.parent.parent / 'models'

def get_model_path(algorithm: str, flow_level: int) -> Path:
    """
    获取预训练模型路径
    
    Args:
        algorithm: 'dqn' 或 'ppo'
        flow_level: 流量等级 (2, 4, 6)
    
    Returns:
        模型文件路径
    """
    return MODELS_DIR / f"{algorithm}_flow{flow_level}_final.pth"


def model_exists(algorithm: str, flow_level: int) -> bool:
    """检查预训练模型是否存在"""
    return get_model_path(algorithm, flow_level).exists()
