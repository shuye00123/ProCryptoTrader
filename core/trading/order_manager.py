"""
订单管理模块

提供订单创建、查询、取消等功能，支持多种订单类型。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import time
import uuid
from typing import Dict, List, Optional, Union, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..exchange.base_exchange import BaseExchange
from ..utils.logger import Logger


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


@dataclass
class Order:
    """订单数据类"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    filled: float = 0.0
    remaining: float = 0.0
    average_price: Optional[float] = None
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime = field(default_factory=datetime.now)
    exchange_order_id: Optional[str] = None
    fee: Optional[float] = None
    fees: Optional[Dict[str, float]] = None
    info: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """初始化后处理"""
        self.remaining = self.amount - self.filled
        if self.status == OrderStatus.FILLED:
            self.remaining = 0.0
    
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
            'filled': self.filled,
            'remaining': self.remaining,
            'average_price': self.average_price,
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat(),
            'exchange_order_id': self.exchange_order_id,
            'fee': self.fee,
            'fees': self.fees,
            'info': self.info
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """从字典创建订单"""
        order = cls(
            order_id=data['order_id'],
            symbol=data['symbol'],
            side=OrderSide(data['side']),
            order_type=OrderType(data['order_type']),
            amount=data['amount'],
            price=data.get('price'),
            stop_price=data.get('stop_price'),
            take_profit_price=data.get('take_profit_price'),
            filled=data.get('filled', 0.0),
            status=OrderStatus(data.get('status', OrderStatus.OPEN.value)),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            exchange_order_id=data.get('exchange_order_id'),
            fee=data.get('fee'),
            fees=data.get('fees'),
            info=data.get('info')
        )
        return order


@dataclass
class OrderConfig:
    """订单管理配置"""
    default_type: OrderType = OrderType.LIMIT
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


class OrderManager:
    """
    订单管理器
    
    提供订单创建、查询、取消等功能，支持多种订单类型。
    """
    
    def __init__(self, exchange: Optional[BaseExchange] = None, config: Optional[OrderConfig] = None):
        """
        初始化订单管理器
        
        Args:
            exchange: 交易所接口实例
            config: 订单管理配置
        """
        self.exchange = exchange
        self.config = config or OrderConfig()
        self.logger = Logger.get_logger("OrderManager")
        
        # 内部状态
        self._orders: Dict[str, Order] = {}
        self._last_request_time = 0.0
        self._request_count = 0
        self._request_start_time = time.time()
        
        self.logger.info("OrderManager initialized")
    
    def set_exchange(self, exchange: BaseExchange):
        """设置交易所接口"""
        self.exchange = exchange
        self.logger.info("Exchange set: %s", exchange.__class__.__name__)
    
    def _generate_order_id(self) -> str:
        """生成订单ID"""
        return str(uuid.uuid4())
    
    def _check_rate_limit(self):
        """检查请求频率限制"""
        if not self.config.enable_rate_limit:
            return
        
        current_time = time.time()
        self._request_count += 1
        
        # 重置计数器（每秒）
        if current_time - self._request_start_time >= 1.0:
            self._request_count = 0
            self._request_start_time = current_time
            return
        
        # 检查是否超过限制
        if self._request_count >= self.config.rate_limit_per_second:
            sleep_time = 1.0 - (current_time - self._request_start_time)
            if sleep_time > 0:
                self.logger.debug("Rate limit reached, sleeping for %.2f seconds", sleep_time)
                time.sleep(sleep_time)
    
    def _validate_order(self, symbol: str, side: OrderSide, amount: float, price: Optional[float] = None) -> Tuple[bool, str]:
        """
        验证订单参数
        
        Args:
            symbol: 交易对
            side: 订单方向
            amount: 数量
            price: 价格
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not self.exchange:
            return False, "Exchange not set"
        
        if not symbol:
            return False, "Symbol is required"
        
        if amount <= 0:
            return False, "Amount must be positive"
        
        if side not in [OrderSide.BUY, OrderSide.SELL]:
            return False, "Invalid side"
        
        # 对于限价单，检查价格
        if price is not None and price <= 0:
            return False, "Price must be positive"
        
        return True, ""
    
    def create_market_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                           params: Optional[Dict[str, Any]] = None) -> Order:
        """
        创建市价单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            params: 额外参数
            
        Returns:
            Order: 创建的订单
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount)
        if not is_valid:
            raise ValueError(error_msg)
        
        # 创建订单
        order_id = self._generate_order_id()
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            amount=amount
        )
        
        # 保存订单
        self._orders[order_id] = order
        
        # 提交到交易所
        if self.exchange:
            try:
                self._check_rate_limit()
                
                exchange_result = self.exchange.create_market_order(
                    symbol=symbol,
                    side=side.value,
                    amount=amount,
                    params=params
                )
                
                # 更新订单信息
                order.exchange_order_id = exchange_result.get('id')
                order.status = OrderStatus.OPEN
                order.info = exchange_result
                
                self.logger.info("Market order created: %s", order.order_id)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                self.logger.error("Failed to create market order: %s", str(e))
                raise
        
        return order
    
    def create_limit_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                          price: float, params: Optional[Dict[str, Any]] = None) -> Order:
        """
        创建限价单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            price: 价格
            params: 额外参数
            
        Returns:
            Order: 创建的订单
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount, price)
        if not is_valid:
            raise ValueError(error_msg)
        
        # 创建订单
        order_id = self._generate_order_id()
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=price
        )
        
        # 保存订单
        self._orders[order_id] = order
        
        # 提交到交易所
        if self.exchange:
            try:
                self._check_rate_limit()
                
                exchange_result = self.exchange.create_limit_order(
                    symbol=symbol,
                    side=side.value,
                    amount=amount,
                    price=price,
                    params=params
                )
                
                # 更新订单信息
                order.exchange_order_id = exchange_result.get('id')
                order.status = OrderStatus.OPEN
                order.info = exchange_result
                
                self.logger.info("Limit order created: %s", order.order_id)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                self.logger.error("Failed to create limit order: %s", str(e))
                raise
        
        return order
    
    def create_stop_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                         stop_price: float, params: Optional[Dict[str, Any]] = None) -> Order:
        """
        创建止损单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            stop_price: 止损价格
            params: 额外参数
            
        Returns:
            Order: 创建的订单
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount)
        if not is_valid:
            raise ValueError(error_msg)
        
        if stop_price <= 0:
            raise ValueError("Stop price must be positive")
        
        # 创建订单
        order_id = self._generate_order_id()
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP,
            amount=amount,
            stop_price=stop_price
        )
        
        # 保存订单
        self._orders[order_id] = order
        
        # 提交到交易所
        if self.exchange:
            try:
                self._check_rate_limit()
                
                # 使用交易所的止损单接口
                exchange_result = self.exchange.create_order(
                    symbol=symbol,
                    type='stop',
                    side=side.value,
                    amount=amount,
                    price=None,
                    params={
                        'stopPrice': stop_price,
                        **(params or {})
                    }
                )
                
                # 更新订单信息
                order.exchange_order_id = exchange_result.get('id')
                order.status = OrderStatus.OPEN
                order.info = exchange_result
                
                self.logger.info("Stop order created: %s", order.order_id)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                self.logger.error("Failed to create stop order: %s", str(e))
                raise
        
        return order
    
    def create_take_profit_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                                take_profit_price: float, params: Optional[Dict[str, Any]] = None) -> Order:
        """
        创建止盈单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            take_profit_price: 止盈价格
            params: 额外参数
            
        Returns:
            Order: 创建的订单
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount)
        if not is_valid:
            raise ValueError(error_msg)
        
        if take_profit_price <= 0:
            raise ValueError("Take profit price must be positive")
        
        # 创建订单
        order_id = self._generate_order_id()
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT,
            amount=amount,
            take_profit_price=take_profit_price
        )
        
        # 保存订单
        self._orders[order_id] = order
        
        # 提交到交易所
        if self.exchange:
            try:
                self._check_rate_limit()
                
                # 使用交易所的止盈单接口
                exchange_result = self.exchange.create_order(
                    symbol=symbol,
                    type='take_profit',
                    side=side.value,
                    amount=amount,
                    price=None,
                    params={
                        'takeProfitPrice': take_profit_price,
                        **(params or {})
                    }
                )
                
                # 更新订单信息
                order.exchange_order_id = exchange_result.get('id')
                order.status = OrderStatus.OPEN
                order.info = exchange_result
                
                self.logger.info("Take profit order created: %s", order.order_id)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                self.logger.error("Failed to create take profit order: %s", str(e))
                raise
        
        return order
    
    def create_iceberg_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                            price: float, visible_size: Optional[float] = None, 
                            params: Optional[Dict[str, Any]] = None) -> List[Order]:
        """
        创建冰山单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 总数量
            price: 价格
            visible_size: 可见部分大小，如果为None则使用配置中的默认值
            params: 额外参数
            
        Returns:
            List[Order]: 创建的订单列表
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount, price)
        if not is_valid:
            raise ValueError(error_msg)
        
        # 设置可见部分大小
        visible_size = visible_size or self.config.iceberg_visible_size
        if visible_size <= 0:
            raise ValueError("Visible size must be positive")
        
        # 计算订单数量
        num_orders = int(amount / visible_size)
        remaining_amount = amount - (num_orders * visible_size)
        
        orders = []
        
        # 创建多个限价单
        for i in range(num_orders):
            order = self.create_limit_order(
                symbol=symbol,
                side=side,
                amount=visible_size,
                price=price,
                params=params
            )
            order.order_type = OrderType.ICEBERG
            orders.append(order)
        
        # 创建剩余部分的订单
        if remaining_amount > 0:
            order = self.create_limit_order(
                symbol=symbol,
                side=side,
                amount=remaining_amount,
                price=price,
                params=params
            )
            order.order_type = OrderType.ICEBERG
            orders.append(order)
        
        self.logger.info("Iceberg order created: %d orders for total amount %f", 
                        len(orders), amount)
        
        return orders
    
    def create_twap_order(self, symbol: str, side: Union[str, OrderSide], amount: float, 
                         duration: int, num_slices: Optional[int] = None, 
                         params: Optional[Dict[str, Any]] = None) -> List[Order]:
        """
        创建TWAP订单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 总数量
            duration: 持续时间（秒）
            num_slices: 切片数量，如果为None则使用配置中的默认值
            params: 额外参数
            
        Returns:
            List[Order]: 创建的订单列表
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = OrderSide(side.lower())
        
        # 验证订单
        is_valid, error_msg = self._validate_order(symbol, side, amount)
        if not is_valid:
            raise ValueError(error_msg)
        
        if duration <= 0:
            raise ValueError("Duration must be positive")
        
        # 设置切片数量
        num_slices = num_slices or self.config.twap_num_slices
        if num_slices <= 0:
            raise ValueError("Number of slices must be positive")
        
        # 计算每个切片的数量和间隔
        slice_amount = amount / num_slices
        slice_interval = duration / num_slices
        
        orders = []
        
        # 创建多个市价单
        for i in range(num_slices):
            order = self.create_market_order(
                symbol=symbol,
                side=side,
                amount=slice_amount,
                params=params
            )
            order.order_type = OrderType.TWAP
            
            # 对于非第一个订单，延迟执行
            if i > 0:
                # 这里只是标记，实际执行需要外部调度器
                order.info = {'execute_at': time.time() + (i * slice_interval)}
            
            orders.append(order)
        
        self.logger.info("TWAP order created: %d orders for total amount %f over %d seconds", 
                        len(orders), amount, duration)
        
        return orders
    
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 是否成功取消
        """
        if order_id not in self._orders:
            self.logger.warning("Order not found: %s", order_id)
            return False
        
        order = self._orders[order_id]
        
        # 检查订单状态
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED]:
            self.logger.warning("Cannot cancel order with status: %s", order.status.value)
            return False
        
        # 更新订单状态
        order.status = OrderStatus.PENDING_CANCEL
        
        # 提交到交易所
        if self.exchange and order.exchange_order_id:
            try:
                self._check_rate_limit()
                
                self.exchange.cancel_order(
                    order_id=order.exchange_order_id,
                    symbol=order.symbol
                )
                
                # 更新订单状态
                order.status = OrderStatus.CANCELED
                
                self.logger.info("Order canceled: %s", order_id)
                return True
            except Exception as e:
                # 恢复订单状态
                order.status = OrderStatus.OPEN
                self.logger.error("Failed to cancel order: %s", str(e))
                return False
        
        # 如果没有交易所接口，直接更新状态
        order.status = OrderStatus.CANCELED
        self.logger.info("Order canceled locally: %s", order_id)
        return True
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            Optional[Order]: 订单信息，如果不存在则返回None
        """
        return self._orders.get(order_id)
    
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        获取订单状态
        
        Args:
            order_id: 订单ID
            
        Returns:
            Optional[OrderStatus]: 订单状态，如果不存在则返回None
        """
        order = self._orders.get(order_id)
        if order:
            return order.status
        return None
    
    def update_order_status(self, order_id: str) -> bool:
        """
        更新订单状态（从交易所获取最新状态）
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 是否成功更新
        """
        if order_id not in self._orders:
            self.logger.warning("Order not found: %s", order_id)
            return False
        
        order = self._orders[order_id]
        
        # 检查订单状态
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED]:
            return True
        
        # 从交易所获取最新状态
        if self.exchange and order.exchange_order_id:
            try:
                self._check_rate_limit()
                
                exchange_result = self.exchange.get_order(
                    order_id=order.exchange_order_id,
                    symbol=order.symbol
                )
                
                # 更新订单信息
                order.status = OrderStatus(exchange_result.get('status', 'unknown'))
                order.filled = exchange_result.get('filled', 0.0)
                order.remaining = exchange_result.get('remaining', order.amount - order.filled)
                order.average_price = exchange_result.get('average', None)
                order.fee = exchange_result.get('fee', None)
                order.fees = exchange_result.get('fees', None)
                order.info = exchange_result
                
                self.logger.debug("Order status updated: %s -> %s", 
                                 order_id, order.status.value)
                return True
            except Exception as e:
                self.logger.error("Failed to update order status: %s", str(e))
                return False
        
        return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        获取未成交订单
        
        Args:
            symbol: 交易对，如果为None则获取所有交易对的未成交订单
            
        Returns:
            List[Order]: 未成交订单列表
        """
        open_orders = []
        
        for order in self._orders.values():
            if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                if symbol is None or order.symbol == symbol:
                    open_orders.append(order)
        
        return open_orders
    
    def get_order_history(self, symbol: Optional[str] = None, limit: Optional[int] = None) -> List[Order]:
        """
        获取历史订单
        
        Args:
            symbol: 交易对，如果为None则获取所有交易对的历史订单
            limit: 限制数量
            
        Returns:
            List[Order]: 历史订单列表
        """
        history_orders = []
        
        for order in self._orders.values():
            if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                if symbol is None or order.symbol == symbol:
                    history_orders.append(order)
        
        # 按时间排序（最新的在前）
        history_orders.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 限制数量
        if limit is not None and limit > 0:
            history_orders = history_orders[:limit]
        
        return history_orders
    
    def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        取消所有未成交订单
        
        Args:
            symbol: 交易对，如果为None则取消所有交易对的未成交订单
            
        Returns:
            int: 成功取消的订单数量
        """
        open_orders = self.get_open_orders(symbol)
        canceled_count = 0
        
        for order in open_orders:
            if self.cancel_order(order.order_id):
                canceled_count += 1
        
        self.logger.info("Canceled %d orders", canceled_count)
        return canceled_count
    
    def get_order_stats(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取订单统计信息
        
        Args:
            symbol: 交易对，如果为None则统计所有交易对的订单
            
        Returns:
            Dict[str, Any]: 订单统计信息
        """
        orders = list(self._orders.values())
        
        if symbol is not None:
            orders = [order for order in orders if order.symbol == symbol]
        
        # 统计各状态订单数量
        status_counts = {}
        for status in OrderStatus:
            status_counts[status.value] = 0
        
        for order in orders:
            status_counts[order.status.value] += 1
        
        # 统计各类型订单数量
        type_counts = {}
        for order_type in OrderType:
            type_counts[order_type.value] = 0
        
        for order in orders:
            type_counts[order.order_type.value] += 1
        
        # 计算总成交量
        total_filled = sum(order.filled for order in orders if order.status == OrderStatus.FILLED)
        
        # 计算总手续费
        total_fees = 0.0
        for order in orders:
            if order.fee is not None:
                total_fees += order.fee
            elif order.fees:
                total_fees += sum(order.fees.values())
        
        return {
            'total_orders': len(orders),
            'status_counts': status_counts,
            'type_counts': type_counts,
            'total_filled': total_filled,
            'total_fees': total_fees
        }