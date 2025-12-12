"""
数据模型模块

统一系统中所有的数据模型定义，包括：
- Position: 持仓信息
- Order: 订单信息
- Signal: 交易信号
- Risk: 风险相关数据
- Trade: 交易记录

遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from .position import Position, PositionSide, PositionStatus
from .order import Order, OrderType, OrderSide, OrderStatus
from .signal import Signal, SignalType, SignalPriority
from .risk import Risk, RiskMetrics, RiskLevel, RiskConfig
from .trade import Trade, TradeDirection, TradeStatus

__all__ = [
    # Position相关
    'Position',
    'PositionSide',
    'PositionStatus',

    # Order相关
    'Order',
    'OrderType',
    'OrderSide',
    'OrderStatus',

    # Signal相关
    'Signal',
    'SignalType',
    'SignalPriority',

    # Risk相关
    'Risk',
    'RiskMetrics',
    'RiskLevel',
    'RiskConfig',

    # Trade相关
    'Trade',
    'TradeDirection',
    'TradeStatus'
]