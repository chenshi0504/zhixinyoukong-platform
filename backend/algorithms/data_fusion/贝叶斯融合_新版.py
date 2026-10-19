# -*- coding: utf-8 -*-
"""
贝叶斯融合_新版 - 调用 bayesian_fusion.py 的入口脚本
"""
import os
import sys

# 确保能导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bayesian_fusion import main

if __name__ == '__main__':
    main()
