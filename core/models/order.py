"""
订单数据模型

统一系统中所有的订单相关数据结构，包括订单类型、方向、状态和订单信息。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """订单类型枚举"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"
    ICEBERG = "iceberg"
    TWAP = "twap"
    TRAILING_STOP = "trailing_stop"


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态枚举"""
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    PENDING_CANCEL = "pending_cancel"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderTimeInForce(Enum):
    """订单有效期类型"""
    GTC = "gtc"  # Good Till Canceled
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill
    DAY = "day"  # Day Order


@dataclass
class Order:
    """
    统一的订单数据类

    整合了各个模块中Order类的功能，提供完整的订单信息管理。
    """
    order_id: str                                    # 订单唯一标识
    symbol: str                                      # 交易对
    side: OrderSide                                   # 买卖方向
    order_type: OrderType                             # 订单类型
    amount: float                                     # 订单数量
    price: Optional[float] = None                      # 限价单价格
    stop_price: Optional[float] = None                # 止损价格
    take_profit_price: Optional[float] = None         # 止盈价格
    trailing_amount: Optional[float] = None           # 追踪止损金额
    trailing_percent: Optional[float] = None          # 追踪止损百分比
    filled: float = 0.0                               # 已成交数量
    remaining: float = 0.0                            # 剩余数量
    average_price: Optional[float] = None             # 平均成交价格
    status: OrderStatus = OrderStatus.OPEN             # 订单状态
    time_in_force: OrderTimeInForce = OrderTimeInForce.GTC  # 有效期类型
    timestamp: datetime = field(default_factory=datetime.now)  # 创建时间
    exchange_order_id: Optional[str] = None           # 交易所订单ID
    client_order_id: Optional[str] = None             # 客户端订单ID
    fee: Optional[float] = None                        # 手续费
    fees: Optional[Dict[str, float]] = None            # 各币种手续费
    info: Optional[Dict[str, Any]] = None              # 交易所返回的原始信息
    trades: List[Dict[str, Any]] = field(default_factory=list)  # 成交记录
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间

    def __post_init__(self):
        """初始化后处理"""
        # 自动生成订单ID（如果没有提供）
        if not self.order_id:
            self.order_id = str(uuid.uuid4())

        # 自动生成客户端订单ID（如果没有提供）
        if not self.client_order_id:
            self.client_order_id = f"client_{self.order_id}"

        # 计算剩余数量
        self.remaining = self.amount - self.filled

        # 更新时间戳
        if self.updated_at == self.created_at:
            self.updated_at = datetime.now()

    @property
    def is_buy(self) -> bool:
        """是否为买单"""
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        """是否为卖单"""
        return self.side == OrderSide.SELL

    @property
    def is_market_order(self) -> bool:
        """是否为市价单"""
        return self.order_type == OrderType.MARKET

    @property
    def is_limit_order(self) -> bool:
        """是否为限价单"""
        return self.order_type == OrderType.LIMIT

    @property
    def is_stop_order(self) -> bool:
        """是否为止损单"""
        return self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP]

    @property
    def is_active(self) -> bool:
        """是否为活跃订单"""
        return self.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]

    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]

    @property
    def fill_percentage(self) -> float:
        """成交百分比"""
        if self.amount == 0:
            return 0.0
        return (self.filled / self.amount) * 100

    @property
    def total_fee(self) -> float:
        """总手续费"""
        if self.fee is not None:
            return self.fee
        elif self.fees:
            return sum(self.fees.values())
        return 0.0

    def add_trade(self, trade: Dict[str, Any]):
        """添加成交记录"""
        self.trades.append(trade)

        # 更新成交信息
        trade_amount = trade.get('amount', 0)
        trade_price = trade.get('price', 0)
        trade_fee = trade.get('fee', 0)

        self.filled += trade_amount
        self.remaining = max(0, self.amount - self.filled)

        # 更新平均成交价格
        if self.filled > 0:
            total_value = sum(t.get('amount', 0) * t.get('price', 0) for t in self.trades)
            self.average_price = total_value / self.filled

        # 更新手续费
        if trade_fee:
            if self.fees is None:
                self.fees = {}
            fee_currency = trade.get('feeCurrency', 'USDT')
            self.fees[fee_currency] = self.fees.get(fee_currency, 0) + trade_fee
            self.fee = self.total_fee

    def update_status(self, status: OrderStatus):
        """更新订单状态"""
        old_status = self.status
        self.status = status
        self.updated_at = datetime.now()

        # 如果订单完成，更新剩余数量
        if status == OrderStatus.FILLED:
            self.remaining = 0.0

    def update_fill(self, amount: float, price: float):
        """更新订单成交信息"""
        # 创建成交记录
        trade = {
            'amount': amount,
            'price': price,
            'timestamp': datetime.now(),
            'side': self.side.value
        }

        # 添加成交记录
        self.add_trade(trade)

        # 更新订单状态
        if self.filled >= self.amount:
            self.update_status(OrderStatus.FILLED)
        elif self.filled > 0:
            self.update_status(OrderStatus.PARTIALLY_FILLED)

    def cancel(self, reason: Optional[str] = None) -> bool:
        """取消订单"""
        if not self.is_active:
            return False

        self.update_status(OrderStatus.CANCELED)
        if reason:
            if self.info is None:
                self.info = {}
            self.info['cancel_reason'] = reason

        return True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'amount': self.amount,
            'price': self.price,
            'stop_price': self.stop_price,
            'take_profit_price': self.take_profit_price,
            'trailing_amount': self.trailing_amount,
            'trailing_percent': self.trailing_percent,
            'filled': self.filled,
            'remaining': self.remaining,
            'average_price': self.average_price,
            'status': self.status.value,
            'time_in_force': self.time_in_force.value,
            'timestamp': self.timestamp.isoformat(),
            'exchange_order_id': self.exchange_order_id,
            'client_order_id': self.client_order_id,
            'fee': self.fee,
            'fees': self.fees,
            'info': self.info,
            'trades': self.trades,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_buy': self.is_buy,
            'is_sell': self.is_sell,
            'is_market_order': self.is_market_order,
            'is_limit_order': self.is_limit_order,
            'is_stop_order': self.is_stop_order,
            'is_active': self.is_active,
            'is_completed': self.is_completed,
            'fill_percentage': self.fill_percentage,
            'total_fee': self.total_fee
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """从字典创建订单"""
        order = cls(
            order_id=data.get('order_id', data.get('id')),
            symbol=data['symbol'],
            side=OrderSide(data['side']),
            order_type=OrderType(data['type']),
            amount=data['amount'],
            price=data.get('price'),
            stop_price=data.get('stopPrice'),
            take_profit_price=data.get('takeProfitPrice'),
            trailing_amount=data.get('trailingAmount'),
            trailing_percent=data.get('trailingPercent'),
            filled=data.get('filled', 0.0),
            remaining=data.get('remaining', 0.0),
            average_price=data.get('average'),
            status=OrderStatus(data.get('status', 'open')),
            time_in_force=OrderTimeInForce(data.get('timeInForce', 'gtc')),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            exchange_order_id=data.get('id'),
            client_order_id=data.get('clientOrderId'),
            fee=data.get('fee'),
            fees=data.get('fees'),
            info=data,
            trades=data.get('trades', []),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat()))
        )
        return order

    def is_valid(self) -> bool:
        """验证订单是否有效"""
        # 基本参数验证
        if not self.order_id or not self.symbol or self.amount <= 0:
            return False

        # 价格验证
        if self.order_type == OrderType.LIMIT and (self.price is None or self.price <= 0):
            return False

        # 数量验证
        if self.filled < 0 or self.remaining < 0:
            return False

        # 状态一致性验证
        if self.amount != self.filled + self.remaining:
            return False

        return True

    def copy(self) -> 'Order':
        """创建订单的深拷贝"""
        return Order.from_dict(self.to_dict())

    def __str__(self) -> str:
        """字符串表示"""
        return (f"Order({self.order_id} {self.symbol} {self.side.value} "
                f"{self.order_type.value} amount={self.amount} "
                f"price={self.price} status={self.status.value})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


@dataclass
class OrderConfig:
    """订单管理配置"""
    default_type: OrderType = OrderType.LIMIT
    default_time_in_force: OrderTimeInForce = OrderTimeInForce.GTC
    retry_attempts: int = 3
    order_timeout: int = 60  # 秒
    partial_fill_threshold: float = 0.9  # 部分成交阈值
    max_slippage_percent: float = 0.1  # 最大滑点百分比
    enable_order_validation: bool = True
    enable_rate_limit: bool = True
    rate_limit_per_second: float = 10.0  # 每秒最大请求数
    iceberg_visible_size: float = 0.01  # 冰山单可见部分大小
    twap_num_slices: int = 10  # TWAP订单切片数量
    twap_slice_interval: int = 60  # TWAP切片间隔（秒）


# 便利函数
def create_market_order(symbol: str, side: OrderSide, amount: float, **kwargs) -> Order:
    """创建市价单的便利函数"""
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        amount=amount,
        **kwargs
    )


def create_limit_order(symbol: str, side: OrderSide, amount: float, price: float, **kwargs) -> Order:
    """创建限价单的便利函数"""
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.LIMIT,
        amount=amount,
        price=price,
        **kwargs
    )


def create_stop_order(symbol: str, side: OrderSide, amount: float, stop_price: float, **kwargs) -> Order:
    """创建止损单的便利函数"""
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.STOP,
        amount=amount,
        stop_price=stop_price,
        **kwargs
    )