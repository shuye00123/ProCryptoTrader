"""
分析模块初始化文件

本模块提供交易结果分析、可视化绘图和因子效果评估等功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。

主要功能：
1. 交易结果分析 - 交易统计、绩效评估、风险分析
2. 可视化绘图 - 收益曲线、回撤分析、交易分布图
3. 因子效果评估 - 因子收益分析、因子IC分析、因子换手率分析

使用示例：
```python
from core.analysis import TradeAnalyzer, PerformancePlotter, FactorAnalyzer

# 交易分析
analyzer = TradeAnalyzer()
statistics = analyzer.calculate_statistics()

# 可视化绘图
plotter = PerformancePlotter()
fig = plotter.plot_equity_curve(data)

# 因子分析
factor_analyzer = FactorAnalyzer()
performance = factor_analyzer.analyze_factor(factor_name, price_data)
```
"""

from .trade_analyzer import (
    Trade,
    TradeDirection,
    TradeStatus,
    TradeStatistics,
    TradeAnalyzer
)

from .performance_plot import (
    PlotConfig,
    PerformancePlotter
)

from .factor_analysis import (
    FactorData,
    FactorType,
    FactorPerformance,
    FactorAnalyzer
)

__all__ = [
    # 交易分析相关
    'Trade',
    'TradeDirection',
    'TradeStatus',
    'TradeStatistics',
    'TradeAnalyzer',
    
    # 可视化绘图相关
    'PlotConfig',
    'PerformancePlotter',
    
    # 因子分析相关
    'FactorData',
    'FactorType',
    'FactorPerformance',
    'FactorAnalyzer'
]