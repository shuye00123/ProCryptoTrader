"""
持仓数据模型

统一系统中所有的持仓相关数据结构，包括持仓方向、状态和持仓信息。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PositionSide(Enum):
    """持仓方向枚举"""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"  # 双向持仓（适用于期货）


class PositionStatus(Enum):
    """持仓状态枚举"""
    OPEN = "open"          # 开仓
    CLOSED = "closed"      # 已平仓
    PARTIALLY_CLOSED = "partially_closed"  # 部分平仓


@dataclass
class Position:
    """
    统一的持仓数据类

    整合了各个模块中Position类的功能，提供完整的持仓信息管理。
    """
    symbol: str                                    # 交易对
    side: PositionSide                             # 持仓方向
    size: float                                    # 持仓数量
    entry_price: float                              # 入场价格
    current_price: float = 0.0                      # 当前价格
    unrealized_pnl: float = 0.0                     # 未实现盈亏
    realized_pnl: float = 0.0                       # 已实现盈亏
    percentage: float = 0.0                         # 收益率百分比
    status: PositionStatus = PositionStatus.OPEN    # 持仓状态
    timestamp: datetime = field(default_factory=datetime.now)  # 创建时间
    leverage: float = 1.0                           # 杠杆倍数
    margin: float = 0.0                            # 保证金
    margin_type: str = "isolated"                  # 保证金类型 (isolated, cross)
    info: Optional[Dict[str, Any]] = None           # 额外信息

    def __post_init__(self):
        """初始化后处理"""
        if self.current_price == 0.0:
            self.current_price = self.entry_price
        self.update_unrealized_pnl()

    @property
    def is_long(self) -> bool:
        """是否为多头持仓"""
        return self.side == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        """是否为空头持仓"""
        return self.side == PositionSide.SHORT

    @property
    def position_value(self) -> float:
        """计算持仓价值"""
        return abs(self.size) * self.entry_price

    @property
    def current_value(self) -> float:
        """计算当前价值"""
        return abs(self.size) * self.current_price

    @property
    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.unrealized_pnl > 0

    @property
    def side_str(self) -> str:
        """获取持仓方向字符串（向后兼容性）"""
        return self.side.value

    def update_unrealized_pnl(self):
        """更新未实现盈亏"""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.size
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.size
        else:
            self.unrealized_pnl = 0.0

        # 计算收益率百分比
        if self.entry_price > 0 and self.size != 0:
            entry_value = self.entry_price * abs(self.size)
            if entry_value > 0:
                self.percentage = (self.unrealized_pnl / entry_value) * 100

    def update_price(self, new_price: float):
        """更新当前价格并重新计算盈亏"""
        self.current_price = new_price
        self.update_unrealized_pnl()

    def add_realized_pnl(self, pnl: float):
        """添加已实现盈亏"""
        self.realized_pnl += pnl

    def close(self, close_price: Optional[float] = None, close_size: Optional[float] = None) -> float:
        """
        平仓并计算已实现盈亏

        Args:
            close_price: 平仓价格，如果为None则使用当前价格
            close_size: 平仓数量，如果为None则全部平仓

        Returns:
            float: 已实现盈亏
        """
        price = close_price or self.current_price
        size = close_size or self.size

        # 计算已实现盈亏
        if self.side == PositionSide.LONG:
            realized_pnl = (price - self.entry_price) * size
        elif self.side == PositionSide.SHORT:
            realized_pnl = (self.entry_price - price) * size
        else:
            realized_pnl = 0.0

        # 更新持仓
        self.size -= size
        self.add_realized_pnl(realized_pnl)

        # 如果全部平仓，更新状态
        if self.size <= 0.0001:  # 使用小值避免浮点数精度问题
            self.size = 0.0
            self.status = PositionStatus.CLOSED

        return realized_pnl

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'side': self.side.value,
            'size': self.size,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'percentage': self.percentage,
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat(),
            'leverage': self.leverage,
            'margin': self.margin,
            'margin_type': self.margin_type,
            'info': self.info,
            'is_long': self.is_long,
            'is_short': self.is_short,
            'is_profitable': self.is_profitable,
            'position_value': self.position_value,
            'current_value': self.current_value
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """从字典创建持仓"""
        position = cls(
            symbol=data['symbol'],
            side=PositionSide(data['side']),
            size=data['size'],
            entry_price=data['entry_price'],
            current_price=data.get('current_price', data.get('entry_price', 0.0)),
            unrealized_pnl=data.get('unrealized_pnl', 0.0),
            realized_pnl=data.get('realized_pnl', 0.0),
            percentage=data.get('percentage', 0.0),
            status=PositionStatus(data.get('status', 'open')),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            leverage=data.get('leverage', 1.0),
            margin=data.get('margin', 0.0),
            margin_type=data.get('margin_type', 'isolated'),
            info=data.get('info')
        )
        return position

    def calculate_unrealized_pnl(self) -> float:
        """计算未实现盈亏"""
        if self.current_price <= 0:
            return 0.0

        if self.side == PositionSide.LONG:
            # 多头：当前价格 > 入场价格为盈利
            return (self.current_price - self.entry_price) * self.size
        else:
            # 空头：当前价格 < 入场价格为盈利
            return (self.entry_price - self.current_price) * self.size

    def calculate_pnl_percentage(self) -> float:
        """计算盈亏百分比"""
        if self.entry_price <= 0:
            return 0.0

        if self.side == PositionSide.LONG:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

    def is_valid(self) -> bool:
        """验证持仓是否有效"""
        # 基本参数验证
        if not self.symbol or self.size <= 0 or self.entry_price <= 0:
            return False

        # 价格验证
        if self.current_price < 0:
            return False

        # 持仓大小验证
        if abs(self.size) > 1.0:  # 假设最大100%持仓
            return False

        return True

    def copy(self) -> 'Position':
        """创建持仓的深拷贝"""
        return Position.from_dict(self.to_dict())

    def __str__(self) -> str:
        """字符串表示"""
        return (f"Position({self.symbol} {self.side.value} "
                f"size={self.size} entry={self.entry_price} "
                f"current={self.current_price} pnl={self.unrealized_pnl:.2f})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


@dataclass
class PositionConfig:
    """持仓管理配置"""
    max_positions: int = 10  # 最大持仓数量
    position_size_method: str = "fixed"  # fixed, percent, risk
    default_size: float = 0.01  # 默认持仓大小
    max_position_percent: float = 0.1  # 单个持仓最大比例
    max_leverage: float = 1.0  # 最大杠杆
    enable_auto_update: bool = True  # 启用自动更新
    update_interval: int = 60  # 更新间隔（秒）
    enable_position_validation: bool = True  # 启用持仓验证
    enable_risk_calculation: bool = True  # 启用风险计算


# 便利函数
def create_long_position(symbol: str, size: float, entry_price: float,
                          current_price: Optional[float] = None, **kwargs) -> Position:
    """创建多头持仓的便利函数"""
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        size=size,
        entry_price=entry_price,
        current_price=current_price or entry_price,
        **kwargs
    )


def create_short_position(symbol: str, size: float, entry_price: float,
                           current_price: Optional[float] = None, **kwargs) -> Position:
    """创建空头持仓的便利函数"""
    return Position(
        symbol=symbol,
        side=PositionSide.SHORT,
        size=size,
        entry_price=entry_price,
        current_price=current_price or entry_price,
        **kwargs
    )