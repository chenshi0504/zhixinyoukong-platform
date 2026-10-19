"""
数据采集服务示例
展示如何使用 BaseAlgorithmService 创建标准化服务
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseAlgorithmService, setup_logger
from typing import Dict, Any


class DataCollectionService(BaseAlgorithmService):
    """数据采集服务"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("data_collection", config)
        self.logger = setup_logger("data_collection", level="INFO")
        
        # 初始化检测器等组件
        self.detector = None  # 这里应该初始化 YOLOv4 检测器
        
        self.logger.info("Data Collection Service initialized")
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理数据采集请求
        
        Args:
            data: 包含视频路径或图像数据的字典
        
        Returns:
            检测结果字典
        """
        self.logger.info(f"Processing data: {data.keys()}")
        
        try:
            # 这里实现实际的数据采集逻辑
            # 1. 读取视频/图像
            # 2. 运行检测器
            # 3. 提取交通流数据
            
            result = {
                "status": "success",
                "vehicle_count": 0,
                "flow_rate": 0.0,
                "detections": []
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Processing error: {e}", exc_info=True)
            raise


def main():
    """启动服务"""
    config = {
        "model_path": "./detector/data/yolov4.weights",
        "confidence_threshold": 0.5,
        "nms_threshold": 0.4
    }
    
    service = DataCollectionService(config)
    service.start(host='0.0.0.0', port=8001, debug=False)


if __name__ == "__main__":
    main()
