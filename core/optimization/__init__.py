"""
性能优化模块

提供缓存机制、向量化计算和性能监控功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from .vectorized_calculator import (
    VectorizedIndicatorCalculator,
    MovingAverageCalculator,
    RSICalculator,
    BollingerBandsCalculator,
    MACDCalculator,
    StochasticCalculator,
    get_vectorized_calculator,
    calculate_indicators_fast
)

__all__ = [
    'VectorizedIndicatorCalculator',
    'MovingAverageCalculator',
    'RSICalculator',
    'BollingerBandsCalculator',
    'MACDCalculator',
    'StochasticCalculator',
    'get_vectorized_calculator',
    'calculate_indicators_fast'
]