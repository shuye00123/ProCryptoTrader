"""
回测模块

提供量化交易策略的回测功能，包括回测引擎、绩效评估和报告生成。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from .backtester import Backtester, BacktestConfig, TradeRecord
from .metrics import PerformanceMetrics, MetricsCalculator
from .report_generator import ReportGenerator

__all__ = [
    'Backtester',
    'BacktestConfig',
    'TradeRecord',
    'PerformanceMetrics',
    'MetricsCalculator',
    'ReportGenerator'
]