"""
TuRBO (Trust Region Bayesian Optimization) 算法
基于Uber的开源实现

参考文献:
Eriksson, D., Pearce, M., Gardner, J., Turner, R. D., & Poloczek, M. (2019).
Scalable global optimization via local Bayesian optimization.
Advances in Neural Information Processing Systems, 32.
"""
from .turbo_1 import Turbo1

__all__ = ['Turbo1']
