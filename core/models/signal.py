"""
交易信号数据模型

统一系统中所有的交易信号相关数据结构，包括信号类型和信号信息。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .order import OrderSide


class SignalType(Enum):
    """信号类型枚举"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"  # 平仓信号
    ADJUST = "adjust"  # 调仓信号


class SignalPriority(Enum):
    """信号优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Signal:
    """
    统一的交易信号数据类

    定义了标准化的交易信号格式，用于策略和交易系统之间的通信。
    """
    signal_type: SignalType                          # 信号类型
    symbol: str                                      # 交易对
    amount: float                                    # 建议交易数量
    price: Optional[float] = None                   # 建议价格
    current_price: Optional[float] = None           # 当前市场价格
    stop_loss: Optional[float] = None               # 止损价格
    take_profit: Optional[float] = None            # 止盈价格
    trailing_stop: Optional[float] = None           # 追踪止损价格
    priority: SignalPriority = SignalPriority.NORMAL  # 信号优先级
    timestamp: datetime = field(default_factory=datetime.now)  # 信号时间
    strategy_name: Optional[str] = None              # 策略名称
    reason: Optional[str] = None                     # 信号原因
    confidence: Optional[float] = None               # 信号置信度 (0-1)
    metadata: Optional[Dict[str, Any]] = None        # 额外元数据
    expires_at: Optional[datetime] = None            # 过期时间
    tags: List[str] = field(default_factory=list)    # 标签

    def __post_init__(self):
        """初始化后处理"""
        # 验证信号参数
        self.validate()

        if self.confidence is not None:
            self.confidence = max(0.0, min(1.0, self.confidence))

    def validate(self):
        """验证信号参数，如果无效则抛出异常"""
        if not self.symbol:
            raise ValueError("Signal symbol cannot be empty")

        if self.amount < 0:
            raise ValueError("Signal amount cannot be negative")

        if self.signal_type in [SignalType.BUY, SignalType.SELL] and self.amount <= 0:
            raise ValueError("Buy/Sell signals must have positive amount")

        if self.price is not None and self.price <= 0:
            raise ValueError("Signal price must be positive")

        if self.stop_loss is not None and self.stop_loss <= 0:
            raise ValueError("Stop loss must be positive")

        if self.take_profit is not None and self.take_profit <= 0:
            raise ValueError("Take profit must be positive")

        if self.confidence is not None and (self.confidence < 0 or self.confidence > 1):
            raise ValueError("Signal confidence must be between 0 and 1")

    @property
    def is_buy_signal(self) -> bool:
        """是否为买入信号"""
        return self.signal_type == SignalType.BUY

    @property
    def is_sell_signal(self) -> bool:
        """是否为卖出信号"""
        return self.signal_type == SignalType.SELL

    @property
    def is_hold_signal(self) -> bool:
        """是否为持有信号"""
        return self.signal_type == SignalType.HOLD

    @property
    def is_close_signal(self) -> bool:
        """是否为平仓信号"""
        return self.signal_type == SignalType.CLOSE

    @property
    def is_adjust_signal(self) -> bool:
        """是否为调仓信号"""
        return self.signal_type == SignalType.ADJUST

    @property
    def is_valid(self) -> bool:
        """检查信号是否有效"""
        # 检查是否过期
        if self.expires_at and datetime.now() > self.expires_at:
            return False

        # 检查基本参数
        if not self.symbol or self.amount <= 0:
            return False

        # 检查买卖信号必须有价格或止损/止盈
        if self.signal_type in [SignalType.BUY, SignalType.SELL]:
            if (self.price is None and
                self.stop_loss is None and
                self.take_profit is None):
                return False

        return True

    @property
    def requires_price(self) -> bool:
        """是否需要指定价格"""
        return self.signal_type in [SignalType.BUY, SignalType.SELL]

    def add_tag(self, tag: str):
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str):
        """移除标签"""
        if tag in self.tags:
            self.tags.remove(tag)

    def has_tag(self, tag: str) -> bool:
        """检查是否有指定标签"""
        return tag in self.tags

    def is_expired(self) -> bool:
        """检查信号是否过期"""
        return self.expires_at is not None and datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'signal_type': self.signal_type.value,
            'symbol': self.symbol,
            'amount': self.amount,
            'price': self.price,
            'current_price': self.current_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'trailing_stop': self.trailing_stop,
            'priority': self.priority.value,
            'timestamp': self.timestamp.isoformat(),
            'strategy_name': self.strategy_name,
            'reason': self.reason,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'tags': self.tags,
            'is_buy_signal': self.is_buy_signal,
            'is_sell_signal': self.is_sell_signal,
            'is_hold_signal': self.is_hold_signal,
            'is_close_signal': self.is_close_signal,
            'is_adjust_signal': self.is_adjust_signal,
            'is_valid': self.is_valid,
            'requires_price': self.requires_price,
            'is_expired': self.is_expired
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Signal':
        """从字典创建信号"""
        signal = cls(
            signal_type=SignalType(data['signal_type']),
            symbol=data['symbol'],
            amount=data['amount'],
            price=data.get('price'),
            current_price=data.get('current_price'),
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit'),
            trailing_stop=data.get('trailing_stop'),
            priority=SignalPriority(data.get('priority', SignalPriority.NORMAL.value)),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            strategy_name=data.get('strategy_name'),
            reason=data.get('reason'),
            confidence=data.get('confidence'),
            metadata=data.get('metadata'),
            expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None,
            tags=data.get('tags', [])
        )
        return signal

    def copy(self) -> 'Signal':
        """创建信号的深拷贝"""
        return Signal.from_dict(self.to_dict())

    def __str__(self) -> str:
        """字符串表示"""
        return (f"Signal({self.signal_type.value} {self.symbol} "
                f"amount={self.amount} price={self.price} "
                f"priority={self.priority.name})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


# 便利函数
def create_buy_signal(symbol: str, amount: float, price: Optional[float] = None, **kwargs) -> Signal:
    """创建买入信号的便利函数"""
    return Signal(
        signal_type=SignalType.BUY,
        symbol=symbol,
        amount=amount,
        price=price,
        **kwargs
    )


def create_sell_signal(symbol: str, amount: float, price: Optional[float] = None, **kwargs) -> Signal:
    """创建卖出信号的便利函数"""
    return Signal(
        signal_type=SignalType.SELL,
        symbol=symbol,
        amount=amount,
        price=price,
        **kwargs
    )


def create_hold_signal(symbol: str, reason: Optional[str] = None, **kwargs) -> Signal:
    """创建持有信号的便利函数"""
    return Signal(
        signal_type=SignalType.HOLD,
        symbol=symbol,
        amount=0.0,
        reason=reason,
        **kwargs
    )


def create_close_signal(symbol: str, amount: Optional[float] = None, **kwargs) -> Signal:
    """创建平仓信号的便利函数"""
    return Signal(
        signal_type=SignalType.CLOSE,
        symbol=symbol,
        amount=amount or 0.0,
        **kwargs
    )