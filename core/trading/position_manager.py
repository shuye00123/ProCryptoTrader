"""
持仓管理模块

提供持仓查询、调整、风险计算等功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import time
from typing import Dict, List, Optional, Union, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..exchange.base_exchange import BaseExchange
from ..utils.logger import Logger


class PositionSide(Enum):
    """持仓方向枚举"""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"  # 双向持仓（适用于期货）


@dataclass
class Position:
    """持仓数据类"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    percentage: float = 0.0  # 收益率百分比
    timestamp: datetime = field(default_factory=datetime.now)
    leverage: float = 1.0
    margin: float = 0.0
    margin_type: str = "isolated"  # isolated, cross
    info: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """初始化后处理"""
        self.update_unrealized_pnl()
    
    def update_unrealized_pnl(self):
        """更新未实现盈亏"""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.size
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.size
        else:
            self.unrealized_pnl = 0.0
        
        # 计算收益率
        if self.entry_price > 0 and self.size > 0:
            entry_value = self.entry_price * self.size
            if entry_value > 0:
                self.percentage = (self.unrealized_pnl / entry_value) * 100
    
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
            'timestamp': self.timestamp.isoformat(),
            'leverage': self.leverage,
            'margin': self.margin,
            'margin_type': self.margin_type,
            'info': self.info
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """从字典创建持仓"""
        position = cls(
            symbol=data['symbol'],
            side=PositionSide(data['side']),
            size=data['size'],
            entry_price=data['entry_price'],
            current_price=data['current_price'],
            unrealized_pnl=data.get('unrealized_pnl', 0.0),
            realized_pnl=data.get('realized_pnl', 0.0),
            percentage=data.get('percentage', 0.0),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            leverage=data.get('leverage', 1.0),
            margin=data.get('margin', 0.0),
            margin_type=data.get('margin_type', 'isolated'),
            info=data.get('info')
        )
        return position


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


class PositionManager:
    """
    持仓管理器
    
    提供持仓查询、调整、风险计算等功能。
    """
    
    def __init__(self, exchange: Optional[BaseExchange] = None, config: Optional[PositionConfig] = None):
        """
        初始化持仓管理器
        
        Args:
            exchange: 交易所接口实例
            config: 持仓管理配置
        """
        self.exchange = exchange
        self.config = config or PositionConfig()
        self.logger = Logger.get_logger("PositionManager")
        
        # 内部状态
        self._positions: Dict[str, Position] = {}
        self._last_update_time = 0.0
        
        self.logger.info("PositionManager initialized")
    
    def set_exchange(self, exchange: BaseExchange):
        """设置交易所接口"""
        self.exchange = exchange
        self.logger.info("Exchange set: %s", exchange.__class__.__name__)
    
    def _validate_position(self, symbol: str, side: PositionSide, size: float, 
                          price: float) -> Tuple[bool, str]:
        """
        验证持仓参数
        
        Args:
            symbol: 交易对
            side: 持仓方向
            size: 持仓大小
            price: 价格
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not self.exchange:
            return False, "Exchange not set"
        
        if not symbol:
            return False, "Symbol is required"
        
        if size <= 0:
            return False, "Size must be positive"
        
        if price <= 0:
            return False, "Price must be positive"
        
        # 检查最大持仓数量
        if self.config.enable_position_validation:
            if symbol not in self._positions and len(self._positions) >= self.config.max_positions:
                return False, f"Maximum positions limit reached: {self.config.max_positions}"
        
        return True, ""
    
    def _calculate_position_size(self, symbol: str, method: Optional[str] = None, 
                                params: Optional[Dict[str, Any]] = None) -> float:
        """
        计算持仓大小
        
        Args:
            symbol: 交易对
            method: 计算方法，如果为None则使用配置中的默认方法
            params: 额外参数
            
        Returns:
            float: 持仓大小
        """
        method = method or self.config.position_size_method
        params = params or {}
        
        if method == "fixed":
            return self.config.default_size
        elif method == "percent":
            # 计算账户总价值的百分比
            if self.exchange:
                try:
                    balance = self.exchange.get_balance()
                    total_value = balance.get('USDT', {}).get('total', 0.0)
                    percent = params.get('percent', self.config.max_position_percent)
                    return total_value * percent
                except Exception as e:
                    self.logger.error("Failed to calculate position size by percent: %s", str(e))
                    return self.config.default_size
            else:
                return self.config.default_size
        elif method == "risk":
            # 基于风险计算持仓大小
            risk_percent = params.get('risk_percent', 0.02)  # 默认2%风险
            stop_loss_percent = params.get('stop_loss_percent', 0.05)  # 默认5%止损
            
            if self.exchange:
                try:
                    balance = self.exchange.get_balance()
                    total_value = balance.get('USDT', {}).get('total', 0.0)
                    risk_amount = total_value * risk_percent
                    return risk_amount / stop_loss_percent
                except Exception as e:
                    self.logger.error("Failed to calculate position size by risk: %s", str(e))
                    return self.config.default_size
            else:
                return self.config.default_size
        else:
            return self.config.default_size
    
    def create_position(self, symbol: str, side: Union[str, PositionSide], size: float, 
                       price: float, leverage: float = 1.0, 
                       margin_type: str = "isolated") -> Position:
        """
        创建持仓
        
        Args:
            symbol: 交易对
            side: 持仓方向
            size: 持仓大小
            price: 价格
            leverage: 杠杆倍数
            margin_type: 保证金类型
            
        Returns:
            Position: 创建的持仓
        """
        # 转换side为枚举
        if isinstance(side, str):
            side = PositionSide(side.lower())
        
        # 验证持仓
        is_valid, error_msg = self._validate_position(symbol, side, size, price)
        if not is_valid:
            raise ValueError(error_msg)
        
        # 检查杠杆
        if leverage > self.config.max_leverage:
            leverage = self.config.max_leverage
            self.logger.warning("Leverage adjusted to maximum: %f", leverage)
        
        # 创建持仓
        position = Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=price,
            current_price=price,
            leverage=leverage,
            margin_type=margin_type
        )
        
        # 计算保证金
        position.margin = (size * price) / leverage
        
        # 保存持仓
        self._positions[symbol] = position
        
        self.logger.info("Position created: %s %s %f @ %f", 
                        symbol, side.value, size, price)
        
        return position
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            Optional[Position]: 持仓信息，如果不存在则返回None
        """
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """
        获取所有持仓
        
        Returns:
            Dict[str, Position]: 所有持仓信息
        """
        return self._positions.copy()
    
    def update_position_price(self, symbol: str, current_price: float) -> bool:
        """
        更新持仓价格
        
        Args:
            symbol: 交易对
            current_price: 当前价格
            
        Returns:
            bool: 是否成功更新
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        position.current_price = current_price
        position.update_unrealized_pnl()
        
        self.logger.debug("Position price updated: %s -> %f", symbol, current_price)
        return True
    
    def increase_position(self, symbol: str, amount: float, price: float) -> bool:
        """
        增加持仓
        
        Args:
            symbol: 交易对
            amount: 增加数量
            price: 价格
            
        Returns:
            bool: 是否成功增加
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        
        # 计算新的平均持仓价格
        total_value = (position.size * position.entry_price) + (amount * price)
        position.size += amount
        position.entry_price = total_value / position.size
        position.current_price = price
        
        # 重新计算保证金
        position.margin = (position.size * position.entry_price) / position.leverage
        
        # 更新未实现盈亏
        position.update_unrealized_pnl()
        
        self.logger.info("Position increased: %s +%f @ %f, new size: %f", 
                        symbol, amount, price, position.size)
        
        return True
    
    def decrease_position(self, symbol: str, amount: float, price: float) -> bool:
        """
        减少持仓
        
        Args:
            symbol: 交易对
            amount: 减少数量
            price: 价格
            
        Returns:
            bool: 是否成功减少
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        
        # 检查是否可以减少
        if amount > position.size:
            amount = position.size
        
        # 计算已实现盈亏
        if position.side == PositionSide.LONG:
            realized_pnl = (price - position.entry_price) * amount
        elif position.side == PositionSide.SHORT:
            realized_pnl = (position.entry_price - price) * amount
        else:
            realized_pnl = 0.0
        
        # 更新持仓
        position.size -= amount
        position.realized_pnl += realized_pnl
        position.current_price = price
        
        # 如果持仓为0，则移除
        if position.size <= 0.0001:  # 使用小值避免浮点数精度问题
            del self._positions[symbol]
            self.logger.info("Position closed: %s, realized PnL: %f", symbol, realized_pnl)
        else:
            # 重新计算保证金
            position.margin = (position.size * position.entry_price) / position.leverage
            
            # 更新未实现盈亏
            position.update_unrealized_pnl()
            
            self.logger.info("Position decreased: %s -%f @ %f, new size: %f, realized PnL: %f", 
                            symbol, amount, price, position.size, realized_pnl)
        
        return True
    
    def close_position(self, symbol: str, price: Optional[float] = None) -> bool:
        """
        平仓
        
        Args:
            symbol: 交易对
            price: 平仓价格，如果为None则使用当前价格
            
        Returns:
            bool: 是否成功平仓
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        
        # 使用当前价格或指定价格
        close_price = price or position.current_price
        
        # 计算已实现盈亏
        if position.side == PositionSide.LONG:
            realized_pnl = (close_price - position.entry_price) * position.size
        elif position.side == PositionSide.SHORT:
            realized_pnl = (position.entry_price - close_price) * position.size
        else:
            realized_pnl = 0.0
        
        # 更新已实现盈亏
        position.realized_pnl += realized_pnl
        
        # 移除持仓
        del self._positions[symbol]
        
        self.logger.info("Position closed: %s, size: %f, price: %f, realized PnL: %f", 
                        symbol, position.size, close_price, realized_pnl)
        
        return True
    
    def close_all_positions(self) -> int:
        """
        平仓所有持仓
        
        Returns:
            int: 成功平仓的持仓数量
        """
        closed_count = 0
        
        # 使用列表避免在迭代过程中修改字典
        symbols = list(self._positions.keys())
        
        for symbol in symbols:
            if self.close_position(symbol):
                closed_count += 1
        
        self.logger.info("Closed %d positions", closed_count)
        return closed_count
    
    def adjust_stop_loss(self, symbol: str, stop_loss: float) -> bool:
        """
        调整止损
        
        Args:
            symbol: 交易对
            stop_loss: 止损价格
            
        Returns:
            bool: 是否成功调整
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        
        # 这里只是记录止损价格，实际止损需要通过订单管理器实现
        if not position.info:
            position.info = {}
        
        position.info['stop_loss'] = stop_loss
        
        self.logger.info("Stop loss adjusted: %s -> %f", symbol, stop_loss)
        return True
    
    def adjust_take_profit(self, symbol: str, take_profit: float) -> bool:
        """
        调整止盈
        
        Args:
            symbol: 交易对
            take_profit: 止盈价格
            
        Returns:
            bool: 是否成功调整
        """
        if symbol not in self._positions:
            return False
        
        position = self._positions[symbol]
        
        # 这里只是记录止盈价格，实际止盈需要通过订单管理器实现
        if not position.info:
            position.info = {}
        
        position.info['take_profit'] = take_profit
        
        self.logger.info("Take profit adjusted: %s -> %f", symbol, take_profit)
        return True
    
    def get_position_value(self, symbol: str) -> float:
        """
        获取持仓价值
        
        Args:
            symbol: 交易对
            
        Returns:
            float: 持仓价值
        """
        position = self._positions.get(symbol)
        if position:
            return position.size * position.current_price
        return 0.0
    
    def get_unrealized_pnl(self, symbol: str) -> float:
        """
        获取未实现盈亏
        
        Args:
            symbol: 交易对
            
        Returns:
            float: 未实现盈亏
        """
        position = self._positions.get(symbol)
        if position:
            return position.unrealized_pnl
        return 0.0
    
    def get_realized_pnl(self, symbol: str) -> float:
        """
        获取已实现盈亏
        
        Args:
            symbol: 交易对
            
        Returns:
            float: 已实现盈亏
        """
        position = self._positions.get(symbol)
        if position:
            return position.realized_pnl
        return 0.0
    
    def get_total_unrealized_pnl(self) -> float:
        """
        获取总未实现盈亏
        
        Returns:
            float: 总未实现盈亏
        """
        return sum(position.unrealized_pnl for position in self._positions.values())
    
    def get_total_realized_pnl(self) -> float:
        """
        获取总已实现盈亏
        
        Returns:
            float: 总已实现盈亏
        """
        return sum(position.realized_pnl for position in self._positions.values())
    
    def get_total_position_value(self) -> float:
        """
        获取总持仓价值
        
        Returns:
            float: 总持仓价值
        """
        return sum(position.size * position.current_price for position in self._positions.values())
    
    def get_position_stats(self) -> Dict[str, Any]:
        """
        获取持仓统计信息
        
        Returns:
            Dict[str, Any]: 持仓统计信息
        """
        # 统计各方向持仓数量
        side_counts = {}
        for side in PositionSide:
            side_counts[side.value] = 0
        
        for position in self._positions.values():
            side_counts[position.side.value] += 1
        
        # 计算总持仓价值
        total_value = self.get_total_position_value()
        
        # 计算总未实现盈亏
        total_unrealized_pnl = self.get_total_unrealized_pnl()
        
        # 计算总已实现盈亏
        total_realized_pnl = self.get_total_realized_pnl()
        
        # 计算总保证金
        total_margin = sum(position.margin for position in self._positions.values())
        
        # 计算平均杠杆
        avg_leverage = 0.0
        if self._positions:
            avg_leverage = sum(position.leverage for position in self._positions.values()) / len(self._positions)
        
        # 计算盈亏持仓数量
        profit_positions = sum(1 for position in self._positions.values() if position.unrealized_pnl > 0)
        loss_positions = sum(1 for position in self._positions.values() if position.unrealized_pnl < 0)
        
        return {
            'total_positions': len(self._positions),
            'side_counts': side_counts,
            'total_value': total_value,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_realized_pnl': total_realized_pnl,
            'total_margin': total_margin,
            'avg_leverage': avg_leverage,
            'profit_positions': profit_positions,
            'loss_positions': loss_positions
        }
    
    def sync_positions_from_exchange(self) -> bool:
        """
        从交易所同步持仓信息
        
        Returns:
            bool: 是否成功同步
        """
        if not self.exchange:
            self.logger.warning("Exchange not set, cannot sync positions")
            return False
        
        try:
            # 获取交易所持仓信息
            exchange_positions = self.exchange.fetch_positions()
            
            # 清空本地持仓
            self._positions.clear()
            
            # 转换为本地持仓格式
            for pos_data in exchange_positions:
                if pos_data.get('size', 0) == 0:
                    continue
                
                # 创建本地持仓对象
                position = Position(
                    symbol=pos_data['symbol'],
                    side=PositionSide(pos_data['side']),
                    size=pos_data['size'],
                    entry_price=pos_data['entryPrice'] or 0.0,
                    current_price=pos_data['markPrice'] or 0.0,
                    unrealized_pnl=pos_data.get('unrealizedPnl', 0.0),
                    realized_pnl=pos_data.get('realizedPnl', 0.0),
                    leverage=pos_data.get('leverage', 1.0),
                    margin=pos_data.get('margin', 0.0),
                    margin_type=pos_data.get('marginType', 'isolated'),
                    info=pos_data
                )
                
                self._positions[pos_data['symbol']] = position
            
            self._last_update_time = time.time()
            self.logger.info("Synced %d positions from exchange", len(self._positions))
            return True
        except Exception as e:
            self.logger.error("Failed to sync positions from exchange: %s", str(e))
            return False
    
    def auto_update_positions(self) -> bool:
        """
        自动更新持仓信息
        
        Returns:
            bool: 是否成功更新
        """
        if not self.config.enable_auto_update:
            return False
        
        current_time = time.time()
        
        # 检查是否需要更新
        if current_time - self._last_update_time < self.config.update_interval:
            return False
        
        # 从交易所同步持仓信息
        return self.sync_positions_from_exchange()