"""
交易记录数据模型

统一系统中所有的交易记录相关数据结构，包括交易方向、状态和交易信息。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .order import OrderSide
from .position import Position


class TradeDirection(Enum):
    """交易方向枚举"""
    LONG = "long"
    SHORT = "short"


class TradeStatus(Enum):
    """交易状态枚举"""
    OPEN = "open"          # 开仓
    CLOSE = "close"        # 平仓
    PARTIAL_CLOSE = "partial_close"  # 部分平仓
    ADJUST = "adjust"      # 调仓
    REVERSE = "reverse"    # 反向
    FAILED = "failed"      # 失败


class TradeType(Enum):
    """交易类型枚举"""
    SPOT = "spot"              # 现货交易
    MARGIN = "margin"          # 杠杆交易
    FUTURES = "futures"        # 期货交易
    OPTIONS = "options"        # 期权交易
    SWAP = "swap"              # 掉期交易


@dataclass
class Trade:
    """
    统一的交易记录数据类

    记录每笔交易的详细信息，包括开仓、平仓、盈亏等。
    """
    trade_id: str                                    # 交易唯一标识
    symbol: str                                      # 交易对
    direction: TradeDirection                         # 交易方向
    trade_type: TradeType                              # 交易类型
    side: OrderSide                                   # 买卖方向
    quantity: float                                   # 交易数量
    entry_price: float                                # 入场价格
    exit_price: Optional[float] = None               # 出场价格
    entry_time: datetime = field(default_factory=datetime.now)    # 入场时间
    exit_time: Optional[datetime] = None             # 出场时间
    entry_order_id: Optional[str] = None             # 入场订单ID
    exit_order_id: Optional[str] = None              # 出场订单ID
    realized_pnl: float = 0.0                          # 已实现盈亏
    unrealized_pnl: float = 0.0                        # 未实现盈亏
    commission: float = 0.0                            # 手续费
    slippage: float = 0.0                              # 滑点
    status: TradeStatus = TradeStatus.OPEN           # 交易状态
    strategy_name: Optional[str] = None               # 策略名称
    timeframe: Optional[str] = None                   # 时间框架
    tags: List[str] = field(default_factory=list)    # 标签
    metadata: Optional[Dict[str, Any]] = None        # 额外元数据
    notes: Optional[str] = None                        # 交易备注
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间

    def __post_init__(self):
        """初始化后处理"""
        # 自动生成交易ID（如果没有提供）
        if not self.trade_id:
            self.trade_id = f"trade_{int(self.created_at.timestamp())}"

        # 更新时间戳
        if self.updated_at == self.created_at:
            self.updated_at = datetime.now()

        # 计算未实现盈亏（如果有持仓信息）
        if self.status == TradeStatus.OPEN and self.exit_price is None:
            # 这里需要有当前价格来计算
            pass

    @property
    def is_long(self) -> bool:
        """是否为多头交易"""
        return self.direction == TradeDirection.LONG

    @property
    def is_short(self) -> bool:
        """是否为空头交易"""
        return self.direction == TradeDirection.SHORT

    @property
    def is_open(self) -> bool:
        """是否为开仓"""
        return self.status in [TradeStatus.OPEN, TradeStatus.PARTIAL_CLOSE]

    @property
    def is_closed(self) -> bool:
        """是否已平仓"""
        return self.status == TradeStatus.CLOSE

    @property
    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.realized_pnl > 0

    @property
    def duration(self) -> Optional[float]:
        """交易持续时间（秒）"""
        if self.entry_time and self.exit_time:
            return (self.exit_time - self.entry_time).total_seconds()
        elif self.entry_time:
            return (datetime.now() - self.entry_time).total_seconds()
        return None

    @property
    def duration_days(self) -> Optional[float]:
        """交易持续时间（天）"""
        duration = self.duration
        return duration / (24 * 3600) if duration else None

    @property
    def price_change(self) -> Optional[float]:
        """价格变化"""
        if self.exit_price and self.entry_price:
            return self.exit_price - self.entry_price
        return None

    @property
    def price_change_percent(self) -> Optional[float]:
        """价格变化百分比"""
        if self.price_change and self.entry_price != 0:
            return (self.price_change / self.entry_price) * 100
        return None

    @property
    def total_cost(self) -> float:
        """总成本（包括手续费和滑点）"""
        return self.commission + self.slippage

    @property
    def net_pnl(self) -> float:
        """净盈亏（扣除成本）"""
        return self.realized_pnl - self.total_cost

    @property
    def pnl(self) -> float:
        """盈亏（别名，为了向后兼容）"""
        return self.realized_pnl

    def calculate_pnl(self) -> float:
        """计算交易盈亏"""
        if self.exit_price is None:
            return 0.0

        if self.direction == TradeDirection.LONG:
            # 多头：出场价格 - 入场价格
            return (self.exit_price - self.entry_price) * self.quantity
        else:
            # 空头：入场价格 - 出场价格
            return (self.entry_price - self.exit_price) * self.quantity

    def get_duration(self):
        """获取交易持续时间"""
        from datetime import timedelta

        if self.entry_time and self.exit_time:
            return self.exit_time - self.entry_time
        elif self.entry_time:
            return datetime.now() - self.entry_time
        else:
            return timedelta(0)

    @property
    def return_on_investment(self) -> Optional[float]:
        """投资回报率"""
        if self.entry_price and self.quantity > 0:
            investment = self.entry_price * self.quantity
            if investment > 0:
                return (self.net_pnl / investment) * 100
        return None

    def close(self, exit_price: float, exit_time: Optional[datetime] = None,
               exit_order_id: Optional[str] = None) -> float:
        """
        平仓交易

        Args:
            exit_price: 出场价格
            exit_time: 出场时间
            exit_order_id: 出场订单ID

        Returns:
            float: 已实现盈亏
        """
        if not self.is_open:
            return 0.0

        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.exit_order_id = exit_order_id
        self.status = TradeStatus.CLOSE
        self.updated_at = datetime.now()

        # 计算已实现盈亏
        if self.is_long:
            self.realized_pnl = (self.exit_price - self.entry_price) * self.quantity
        else:
            self.realized_pnl = (self.entry_price - self.exit_price) * self.quantity

        # 重置未实现盈亏
        self.unrealized_pnl = 0.0

        return self.realized_pnl

    def partial_close(self, close_quantity: float, exit_price: float,
                      exit_time: Optional[datetime] = None,
                      exit_order_id: Optional[str] = None) -> float:
        """
        部分平仓

        Args:
            close_quantity: 平仓数量
            exit_price: 出场价格
            exit_time: 出场时间
            exit_order_id: 出场订单ID

        Returns:
            float: 已实现盈亏
        """
        if not self.is_open or close_quantity <= 0 or close_quantity > self.quantity:
            return 0.0

        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.exit_order_id = exit_order_id
        self.quantity -= close_quantity
        self.updated_at = datetime.now()

        # 计算部分平仓的已实现盈亏
        if self.is_long:
            realized_pnl = (self.exit_price - self.entry_price) * close_quantity
        else:
            realized_pnl = (self.entry_price - self.exit_price) * close_quantity

        self.realized_pnl += realized_pnl

        # 如果全部平仓，更新状态
        if self.quantity <= 0:
            self.status = TradeStatus.CLOSED
            self.quantity = 0.0
        else:
            self.status = TradeStatus.PARTIAL_CLOSE

        return realized_pnl

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

    def update_price(self, current_price: float):
        """更新当前价格（用于未实现盈亏计算）"""
        if self.is_open:
            if self.is_long:
                self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
            else:
                self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'direction': self.direction.value,
            'trade_type': self.trade_type.value,
            'side': self.side.value,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'entry_order_id': self.entry_order_id,
            'exit_order_id': self.exit_order_id,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'commission': self.commission,
            'slippage': self.slippage,
            'status': self.status.value,
            'strategy_name': self.strategy_name,
            'timeframe': self.timeframe,
            'tags': self.tags,
            'metadata': self.metadata,
            'notes': self.notes,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_long': self.is_long,
            'is_short': self.is_short,
            'is_open': self.is_open,
            'is_closed': self.is_closed,
            'is_profitable': self.is_profitable,
            'duration': self.duration,
            'duration_days': self.duration_days,
            'price_change': self.price_change,
            'price_change_percent': self.price_change_percent,
            'total_cost': self.total_cost,
            'net_pnl': self.net_pnl,
            'return_on_investment': self.return_on_investment
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Trade':
        """从字典创建交易记录"""
        trade = cls(
            trade_id=data.get('trade_id'),
            symbol=data['symbol'],
            direction=TradeDirection(data['direction']),
            trade_type=TradeType(data['trade_type']),
            side=OrderSide(data['side']),
            quantity=data['quantity'],
            entry_price=data['entry_price'],
            exit_price=data.get('exit_price'),
            entry_time=datetime.fromisoformat(data.get('entry_time', datetime.now().isoformat())),
            exit_time=datetime.fromisoformat(data['exit_time']) if data.get('exit_time') else None,
            entry_order_id=data.get('entry_order_id'),
            exit_order_id=data.get('exit_order_id'),
            realized_pnl=data.get('realized_pnl', 0.0),
            unrealized_pnl=data.get('unrealized_pnl', 0.0),
            commission=data.get('commission', 0.0),
            slippage=data.get('slippage', 0.0),
            status=TradeStatus(data.get('status', 'open')),
            strategy_name=data.get('strategy_name'),
            timeframe=data.get('timeframe'),
            tags=data.get('tags', []),
            metadata=data.get('metadata'),
            notes=data.get('notes'),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat()))
        )
        return trade

    def copy(self) -> 'Trade':
        """创建交易记录的深拷贝"""
        return Trade.from_dict(self.to_dict())

    def __str__(self) -> str:
        """字符串表示"""
        return (f"Trade({self.trade_id} {self.symbol} {self.direction.value} "
                f"quantity={self.quantity} entry={self.entry_price} "
                f"exit={self.exit_price} pnl={self.realized_pnl:.2f})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


@dataclass
class TradeBatch:
    """交易批次"""
    batch_id: str                                    # 批次ID
    trades: List[Trade] = field(default_factory=list)  # 交易记录列表
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间

    @property
    def total_pnl(self) -> float:
        """总盈亏"""
        return sum(trade.net_pnl for trade in self.trades)

    @property
    def total_trades(self) -> int:
        """总交易数"""
        return len(self.trades)

    @property
    def profitable_trades(self) -> int:
        """盈利交易数"""
        return sum(1 for trade in self.trades if trade.is_profitable)

    @property
    def win_rate(self) -> float:
        """胜率"""
        if self.total_trades == 0:
            return 0.0
        return (self.profitable_trades / self.total_trades) * 100

    def add_trade(self, trade: Trade):
        """添加交易记录"""
        self.trades.append(trade)
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'batch_id': self.batch_id,
            'total_pnl': self.total_pnl,
            'total_trades': self.total_trades,
            'profitable_trades': self.profitable_trades,
            'win_rate': self.win_rate,
            'trades': [trade.to_dict() for trade in self.trades],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


# 便利函数
def create_long_trade(symbol: str, quantity: float, entry_price: float, **kwargs) -> Trade:
    """创建多头交易记录"""
    return Trade(
        symbol=symbol,
        direction=TradeDirection.LONG,
        side=OrderSide.BUY,
        quantity=quantity,
        entry_price=entry_price,
        **kwargs
    )


def create_short_trade(symbol: str, quantity: float, entry_price: float, **kwargs) -> Trade:
    """创建空头交易记录"""
    return Trade(
        symbol=symbol,
        direction=TradeDirection.SHORT,
        side=OrderSide.SELL,
        quantity=quantity,
        entry_price=entry_price,
        **kwargs
    )