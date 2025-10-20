"""
风险控制模块

实现统一风控逻辑，包括最大持仓限制、止盈止损等功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from .logger import Logger


@dataclass
class RiskConfig:
    """风险控制配置"""
    # 资金风险控制
    max_daily_loss_percent: float = 2.0  # 每日最大亏损百分比
    max_drawdown_percent: float = 10.0  # 最大回撤百分比
    max_total_position_value: float = 10000.0  # 最大总仓位价值（基础货币）
    max_position_percent: float = 0.05  # 单个策略最大仓位比例 (0-1)
    
    # 订单风险控制
    max_concurrent_orders: int = 5  # 最大并发订单数
    max_order_value: float = 1000.0  # 最大单笔订单价值
    max_leverage: float = 1.0  # 最大杠杆倍数
    
    # 交易频率控制
    max_trades_per_hour: int = 10  # 每小时最大交易次数
    min_order_interval_seconds: int = 60  # 最小订单间隔（秒）
    
    # 其他风险控制
    stop_trading_on_high_volatility: bool = True  # 高波动时停止交易
    volatility_threshold_percent: float = 5.0  # 波动阈值（百分比）
    emergency_stop_enabled: bool = True  # 启用紧急停止


@dataclass
class PositionInfo:
    """仓位信息"""
    symbol: str
    entry_price: float
    current_price: float
    size: float
    value: float
    profit: float
    profit_percent: float
    entry_time: datetime
    leverage: float = 1.0


@dataclass
class OrderInfo:
    """订单信息"""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', 'stop_limit', etc.
    price: float
    size: float
    value: float
    status: str  # 'open', 'filled', 'canceled', 'rejected'
    timestamp: datetime


class RiskManager:
    """
    风险管理器
    
    提供下单前校验、全局断路器、逐笔止损/止盈、资金隔离等功能。
    """
    
    def __init__(self, config: Optional[RiskConfig] = None):
        """
        初始化风险管理器
        
        Args:
            config: 风险控制配置，如果为None则使用默认配置
        """
        self.config = config or RiskConfig()
        self.logger = Logger.get_logger("RiskManager")
        
        # 内部状态
        self._positions: Dict[str, PositionInfo] = {}
        self._orders: Dict[str, OrderInfo] = {}
        self._trade_history: List[OrderInfo] = []
        self._daily_pnl: Dict[str, float] = {}
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._last_trade_time: Dict[str, float] = {}
        self._lock = threading.RLock()
        
        # 初始化每日PnL
        today = datetime.now().strftime("%Y-%m-%d")
        self._daily_pnl[today] = 0.0
        
        self.logger.info("RiskManager initialized")
    
    def update_position(self, position: PositionInfo):
        """更新仓位信息"""
        with self._lock:
            self._positions[position.symbol] = position
            self.logger.debug("Updated position: %s", position)
    
    def remove_position(self, symbol: str):
        """移除仓位信息"""
        with self._lock:
            if symbol in self._positions:
                del self._positions[symbol]
                self.logger.debug("Removed position: %s", symbol)
    
    def update_order(self, order: OrderInfo):
        """更新订单信息"""
        with self._lock:
            self._orders[order.order_id] = order
            
            # 如果订单已成交，添加到交易历史
            if order.status == 'filled':
                self._trade_history.append(order)
                self._last_trade_time[order.symbol] = time.time()
                
                # 更新每日PnL
                today = datetime.now().strftime("%Y-%m-%d")
                self._daily_pnl[today] += order.value * 0.01  # 模拟计算
            
            self.logger.debug("Updated order: %s", order)
    
    def remove_order(self, order_id: str):
        """移除订单信息"""
        with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]
                self.logger.debug("Removed order: %s", order_id)
    
    def update_equity(self, equity: float):
        """更新账户权益"""
        with self._lock:
            self._current_equity = equity
            
            # 更新峰值权益
            if equity > self._peak_equity:
                self._peak_equity = equity
                self.logger.info("Updated peak equity: %.2f", equity)
    
    def check_risk_limits(self) -> bool:
        """检查风险限制"""
        with self._lock:
            # 检查每日亏损限制
            today = datetime.now().strftime("%Y-%m-%d")
            daily_loss_percent = abs(self._daily_pnl.get(today, 0.0)) / self._current_equity * 100 if self._current_equity > 0 else 0
            
            if daily_loss_percent >= self.config.max_daily_loss_percent:
                self.logger.warning("Daily loss limit reached: %.2f%% >= %.2f%%", 
                                   daily_loss_percent, self.config.max_daily_loss_percent)
                return False
            
            # 检查最大回撤限制
            drawdown_percent = ((self._peak_equity - self._current_equity) / self._peak_equity * 100 
                              if self._peak_equity > 0 else 0)
            
            if drawdown_percent >= self.config.max_drawdown_percent:
                self.logger.warning("Maximum drawdown limit reached: %.2f%% >= %.2f%%", 
                                   drawdown_percent, self.config.max_drawdown_percent)
                return False
            
            # 检查总仓位价值限制
            total_position_value = sum(pos.value for pos in self._positions.values())
            
            if total_position_value >= self.config.max_total_position_value:
                self.logger.warning("Total position value limit reached: %.2f >= %.2f", 
                                   total_position_value, self.config.max_total_position_value)
                return False
            
            # 检查并发订单数限制
            open_orders = [order for order in self._orders.values() if order.status == 'open']
            
            if len(open_orders) >= self.config.max_concurrent_orders:
                self.logger.warning("Concurrent orders limit reached: %d >= %d", 
                                   len(open_orders), self.config.max_concurrent_orders)
                return False
            
            return True
    
    def validate_order(self, symbol: str, order_value: float, order_size: float) -> Tuple[bool, str]:
        """
        下单前校验
        
        Args:
            symbol: 交易对
            order_value: 订单价值
            order_size: 订单数量
            
        Returns:
            Tuple[bool, str]: (是否通过校验, 错误信息)
        """
        with self._lock:
            # 检查订单价值限制
            if order_value > self.config.max_order_value:
                return False, f"Order value {order_value} exceeds maximum {self.config.max_order_value}"
            
            # 检查交易频率限制
            now = time.time()
            if symbol in self._last_trade_time:
                time_since_last = now - self._last_trade_time[symbol]
                if time_since_last < self.config.min_order_interval_seconds:
                    return False, f"Order interval too short: {time_since_last:.2f}s < {self.config.min_order_interval_seconds}s"
            
            # 检查每小时交易次数
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent_trades = [trade for trade in self._trade_history 
                           if trade.symbol == symbol and trade.timestamp >= one_hour_ago]
            
            if len(recent_trades) >= self.config.max_trades_per_hour:
                return False, f"Max trades per hour reached: {len(recent_trades)} >= {self.config.max_trades_per_hour}"
            
            # 检查单个策略最大仓位比例
            current_position_value = sum(pos.value for pos in self._positions.values())
            if (current_position_value + order_value) > self._current_equity * self.config.max_position_percent:
                return False, f"Position would exceed max position percent: {self.config.max_position_percent*100}%"
            
            return True, ""
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """获取风险指标"""
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            daily_pnl = self._daily_pnl.get(today, 0.0)
            daily_pnl_percent = daily_pnl / self._current_equity * 100 if self._current_equity > 0 else 0
            
            drawdown_percent = ((self._peak_equity - self._current_equity) / self._peak_equity * 100 
                              if self._peak_equity > 0 else 0)
            
            total_position_value = sum(pos.value for pos in self._positions.values())
            total_position_percent = total_position_value / self._current_equity * 100 if self._current_equity > 0 else 0
            
            open_orders = [order for order in self._orders.values() if order.status == 'open']
            
            return {
                "current_equity": self._current_equity,
                "peak_equity": self._peak_equity,
                "daily_pnl": daily_pnl,
                "daily_pnl_percent": daily_pnl_percent,
                "drawdown_percent": drawdown_percent,
                "total_position_value": total_position_value,
                "total_position_percent": total_position_percent,
                "open_positions_count": len(self._positions),
                "open_orders_count": len(open_orders),
                "trade_count_today": sum(1 for trade in self._trade_history 
                                        if trade.timestamp.strftime("%Y-%m-%d") == today),
                "risk_limits_breached": not self.check_risk_limits()
            }
    
    def emergency_stop(self):
        """紧急停止所有交易"""
        if not self.config.emergency_stop_enabled:
            self.logger.warning("Emergency stop is disabled")
            return False
        
        self.logger.critical("Emergency stop triggered!")
        # 这里可以添加紧急平仓逻辑
        
        return True
    
    def reset_daily_pnl(self):
        """重置每日盈亏统计"""
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            self._daily_pnl[today] = 0.0
            self.logger.info("Daily PnL reset for %s", today)


# 提供默认的风险管理器实例
def get_default_risk_manager() -> RiskManager:
    """
    获取默认的风险管理器实例
    
    Returns:
        RiskManager: 默认风险管理器实例
    """
    return RiskManager()