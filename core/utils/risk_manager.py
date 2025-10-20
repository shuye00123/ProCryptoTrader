"""
风险控制模块

提供统一的风险控制、仓位管理、止损止盈和风险评估功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。

注：此模块整合了risk_control.py和risk_tools.py的核心功能，
    提供统一的风险管理层，避免重复实现。
"""

import os
from enum import Enum
from typing import Dict, List, Optional, Union, Any, Tuple, Set
from dataclasses import dataclass, field
import logging
import numpy as np
from datetime import datetime, timedelta
from statistics import mean, stdev

from .logger import Logger

# 导入core.trading.position_manager中的PositionManager
from ..trading.position_manager import PositionManager as TradingPositionManager

logger = Logger.get_logger("RiskManager")


class RiskLevel(Enum):
    """
    风险等级枚举
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class OrderSide(Enum):
    """
    订单方向枚举
    """
    BUY = "buy"
    SELL = "sell"


@dataclass
class RiskConfig:
    """
    风险控制配置
    """
    # 资金风险控制
    max_position_value: float = 10000.0  # 最大持仓价值
    max_loss_percent: float = 2.0  # 最大亏损百分比(%)
    max_drawdown_percent: float = 10.0  # 最大回撤百分比(%)
    risk_reward_ratio: float = 1.5  # 风险回报比
    
    # 交易频率控制
    max_trades_per_day: int = 10  # 每日最大交易次数
    max_concurrent_trades: int = 5  # 最大并发交易数
    
    # 止损止盈配置
    stop_loss_percent: float = 1.0  # 止损百分比(%)
    take_profit_percent: float = 2.0  # 止盈百分比(%)
    trailing_stop_percent: Optional[float] = None  # 追踪止损百分比(%)
    
    # 单个交易风险控制
    max_position_size_per_trade: float = 1000.0  # 单笔交易最大持仓价值
    max_leverage: float = 1.0  # 最大杠杆倍数
    
    # 策略风险控制
    enable_position_limits: bool = True  # 是否启用仓位限制
    enable_drawdown_control: bool = True  # 是否启用回撤控制
    enable_frequency_control: bool = True  # 是否启用频率控制


@dataclass
class Position:
    """
    仓位信息类
    整合了risk_control中的PositionInfo和risk_tools中的Position
    """
    symbol: str  # 交易对
    size: float  # 持仓数量（正数为多头，负数为空头）
    entry_price: float  # 入场价格
    entry_time: datetime  # 入场时间
    current_price: float = 0.0  # 当前价格
    stop_loss: Optional[float] = None  # 止损价格
    take_profit: Optional[float] = None  # 止盈价格
    trailing_stop: Optional[float] = None  # 追踪止损
    leverage: float = 1.0  # 杠杆倍数
    risk_percent: float = 0.01  # 风险百分比
    order_id: Optional[str] = None  # 关联的订单ID
    
    @property
    def is_long(self) -> bool:
        """是否为多头持仓"""
        return self.size > 0
    
    @property
    def is_short(self) -> bool:
        """是否为空头持仓"""
        return self.size < 0
    
    @property
    def position_value(self) -> float:
        """计算持仓价值"""
        return abs(self.size) * self.entry_price
    
    @property
    def current_value(self) -> float:
        """计算当前价值"""
        return abs(self.size) * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        """计算未实现盈亏"""
        return self.size * (self.current_price - self.entry_price)
    
    @property
    def unrealized_pnl_percent(self) -> float:
        """计算未实现盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        return (self.unrealized_pnl / self.position_value) * 100
    
    @property
    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.unrealized_pnl > 0


@dataclass
class OrderInfo:
    """
    订单信息
    """
    order_id: str  # 订单ID
    symbol: str  # 交易对
    order_type: str  # 订单类型
    side: str  # 买入/卖出
    size: float  # 订单数量
    price: float  # 订单价格
    status: str  # 订单状态
    timestamp: datetime  # 订单时间
    filled_size: float = 0.0  # 已成交数量
    remaining_size: float = 0.0  # 剩余数量
    fee: float = 0.0  # 手续费
    realized_pnl: float = 0.0  # 已实现盈亏


@dataclass
class RiskMetrics:
    """
    风险指标数据类
    提供风险评估的核心指标
    """
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    max_drawdown: float = 0.0  # 最大回撤
    win_rate: float = 0.0  # 胜率
    average_profit: float = 0.0  # 平均盈利
    average_loss: float = 0.0  # 平均亏损
    profit_factor: float = 0.0  # 盈亏比
    trading_frequency: float = 0.0  # 交易频率（每天）
    volatility: float = 0.0  # 波动率


class StopLossManager:
    """
    止损止盈管理器
    负责计算和更新止损止盈价格
    """
    
    def __init__(self):
        self.logger = Logger.get_logger("StopLossManager")
    
    def calculate_stop_loss_take_profit(
        self, 
        entry_price: float, 
        is_long: bool, 
        stop_loss_percent: float, 
        take_profit_percent: float,
        risk_reward_ratio: float = 1.5
    ) -> Tuple[float, float]:
        """
        计算止损止盈价格
        
        Args:
            entry_price: 入场价格
            is_long: 是否为多头
            stop_loss_percent: 止损百分比
            take_profit_percent: 止盈百分比
            risk_reward_ratio: 风险回报比
            
        Returns:
            Tuple[float, float]: (止损价格, 止盈价格)
        """
        # 如果未指定止盈百分比，使用风险回报比自动计算
        if take_profit_percent <= 0:
            take_profit_percent = stop_loss_percent * risk_reward_ratio
        
        if is_long:
            stop_loss = entry_price * (1 - stop_loss_percent / 100)
            take_profit = entry_price * (1 + take_profit_percent / 100)
        else:
            stop_loss = entry_price * (1 + stop_loss_percent / 100)
            take_profit = entry_price * (1 - take_profit_percent / 100)
        
        return stop_loss, take_profit
    
    def update_trailing_stop(
        self, 
        current_price: float, 
        entry_price: float, 
        is_long: bool, 
        trailing_stop_percent: float,
        current_trailing_stop: Optional[float]
    ) -> float:
        """
        更新追踪止损价格
        
        Args:
            current_price: 当前价格
            entry_price: 入场价格
            is_long: 是否为多头
            trailing_stop_percent: 追踪止损百分比
            current_trailing_stop: 当前追踪止损价格
            
        Returns:
            float: 更新后的追踪止损价格
        """
        # 验证输入参数
        if current_price <= 0 or trailing_stop_percent < 0:
            self.logger.warning(f"Invalid parameters: current_price={current_price}, trailing_stop_percent={trailing_stop_percent}")
            return current_trailing_stop or entry_price
        
        # 计算新的追踪止损价格
        if is_long:
            new_trailing_stop = current_price * (1 - trailing_stop_percent / 100)
            # 如果是多头，追踪止损只能上移
            if current_trailing_stop is None or new_trailing_stop > current_trailing_stop:
                return new_trailing_stop
        else:
            new_trailing_stop = current_price * (1 + trailing_stop_percent / 100)
            # 如果是空头，追踪止损只能下移
            if current_trailing_stop is None or new_trailing_stop < current_trailing_stop:
                return new_trailing_stop
        
        return current_trailing_stop or entry_price
    
    def should_exit(
        self, 
        position: Position,
        max_loss_percent: float
    ) -> Tuple[bool, str, float]:
        """
        检查是否应该平仓
        
        Args:
            position: 仓位对象
            max_loss_percent: 最大亏损百分比
            
        Returns:
            Tuple[bool, str, float]: (是否应该平仓, 原因, 建议价格)
        """
        current_price = position.current_price
        
        # 检查止损
        if position.stop_loss:
            if (position.is_long and current_price <= position.stop_loss) or \
               (position.is_short and current_price >= position.stop_loss):
                return True, "Stop loss triggered", current_price
        
        # 检查止盈
        if position.take_profit:
            if (position.is_long and current_price >= position.take_profit) or \
               (position.is_short and current_price <= position.take_profit):
                return True, "Take profit triggered", current_price
        
        # 检查追踪止损
        if position.trailing_stop:
            if (position.is_long and current_price <= position.trailing_stop) or \
               (position.is_short and current_price >= position.trailing_stop):
                return True, "Trailing stop triggered", current_price
        
        # 检查最大亏损百分比
        if abs(position.unrealized_pnl_percent) >= max_loss_percent:
            return True, "Max loss percent reached", current_price
        
        return False, "", 0.0


class RiskCalculator:
    """
    风险计算器
    负责计算各种风险指标
    """
    
    def __init__(self):
        self.logger = Logger.get_logger("RiskCalculator")
        self.trade_history: List[OrderInfo] = []
    
    def add_trade(self, order: OrderInfo) -> None:
        """
        添加交易记录
        
        Args:
            order: 订单信息
        """
        self.trade_history.append(order)
    
    def calculate_risk_metrics(self) -> RiskMetrics:
        """
        计算风险指标
        
        Returns:
            RiskMetrics: 风险指标对象
        """
        if not self.trade_history:
            return RiskMetrics(max_drawdown=0.0)
        
        # 计算基础指标
        profits = []
        losses = []
        returns = []
        
        for trade in self.trade_history:
            pnl = trade.realized_pnl
            returns.append(pnl)
            
            if pnl > 0:
                profits.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))
        
        # 计算胜率
        win_rate = len(profits) / len(self.trade_history) if self.trade_history else 0
        
        # 计算平均盈利和亏损
        average_profit = sum(profits) / len(profits) if profits else 0
        average_loss = sum(losses) / len(losses) if losses else 0
        
        # 计算盈亏比
        profit_factor = average_profit / average_loss if average_loss > 0 else 0
        
        # 计算波动率
        volatility = stdev(returns) if len(returns) > 1 else 0
        
        # 计算夏普比率（简化版，假设无风险利率为0）
        sharpe_ratio = mean(returns) / volatility if volatility > 0 else 0
        
        # 计算索提诺比率（简化版，只考虑负收益的波动率）
        negative_returns = [r for r in returns if r < 0]
        downside_volatility = stdev(negative_returns) if len(negative_returns) > 1 else 0
        sortino_ratio = mean(returns) / downside_volatility if downside_volatility > 0 else 0
        
        # 计算交易频率（假设交易历史不超过365天）
        if len(self.trade_history) > 1:
            first_trade = min(trade.timestamp for trade in self.trade_history)
            last_trade = max(trade.timestamp for trade in self.trade_history)
            days = (last_trade - first_trade).days + 1
            trading_frequency = len(self.trade_history) / days if days > 0 else 0
        else:
            trading_frequency = 0
        
        return RiskMetrics(
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            win_rate=win_rate,
            average_profit=average_profit,
            average_loss=average_loss,
            profit_factor=profit_factor,
            trading_frequency=trading_frequency,
            volatility=volatility
        )
    
    def calculate_position_size(
        self, 
        account_balance: float, 
        risk_percent: float, 
        stop_loss_percent: float,
        entry_price: float
    ) -> float:
        """
        计算合适的仓位大小
        
        Args:
            account_balance: 账户余额
            risk_percent: 风险百分比
            stop_loss_percent: 止损百分比
            entry_price: 入场价格
            
        Returns:
            float: 建议的仓位大小
        """
        # 计算可承担的风险金额
        risk_amount = account_balance * (risk_percent / 100)
        
        # 计算价格变动幅度
        price_movement = entry_price * (stop_loss_percent / 100)
        
        # 计算仓位大小
        position_size = risk_amount / price_movement
        
        return position_size
    
    def assess_risk_level(self, metrics: RiskMetrics) -> RiskLevel:
        """
        评估整体风险等级
        
        Args:
            metrics: 风险指标
            
        Returns:
            RiskLevel: 风险等级
        """
        # 基于多个指标的综合评估
        risk_score = 0
        
        # 夏普比率评估（越高越好）
        if metrics.sharpe_ratio >= 2:
            risk_score -= 2
        elif metrics.sharpe_ratio >= 1:
            risk_score -= 1
        elif metrics.sharpe_ratio < 0:
            risk_score += 2
        
        # 最大回撤评估
        if metrics.max_drawdown >= 30:
            risk_score += 3
        elif metrics.max_drawdown >= 20:
            risk_score += 2
        elif metrics.max_drawdown >= 10:
            risk_score += 1
        
        # 胜率评估
        if metrics.win_rate >= 0.6:
            risk_score -= 1
        elif metrics.win_rate < 0.4:
            risk_score += 1
        
        # 交易频率评估
        if metrics.trading_frequency > 5:
            risk_score += 2
        elif metrics.trading_frequency > 2:
            risk_score += 1
        
        # 根据风险得分确定等级
        if risk_score >= 4:
            return RiskLevel.EXTREME
        elif risk_score >= 2:
            return RiskLevel.HIGH
        elif risk_score >= -1:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW


class RiskManager:
    """
    风险管理器（主类）
    整合了仓位管理、止损止盈管理和风险计算功能
    """
    
    def __init__(self, risk_config: Optional[RiskConfig] = None):
        """
        初始化风险管理器
        
        Args:
            risk_config: 风险控制配置
        """
        self.risk_config = risk_config or RiskConfig()
        self.logger = Logger.get_logger("RiskManager")
        
        # 初始化组件
        self.position_manager = TradingPositionManager()
        self.stop_loss_manager = StopLossManager()
        self.risk_calculator = RiskCalculator()
        
        # 追踪变量
        self.trade_history: List[OrderInfo] = []
        self.daily_trades: Dict[str, int] = {}  # 每日交易次数
        self.total_pnl: float = 0.0  # 总盈亏
        self.highest_equity: float = 0.0  # 最高权益
        self.current_equity: float = 0.0  # 当前权益
        
        # 初始化权益
        self.current_equity = self.risk_config.max_position_value
        self.highest_equity = self.current_equity
    
    def check_trade_risk(
        self, 
        symbol: str, 
        size: float, 
        price: float,
        leverage: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        检查交易风险
        
        Args:
            symbol: 交易对
            size: 交易数量
            price: 交易价格
            leverage: 杠杆倍数
            
        Returns:
            Tuple[bool, str]: (是否允许交易, 原因)
        """
        # 检查仓位限制
        position_value = abs(size) * price
        
        if (self.risk_config.enable_position_limits and 
            position_value > self.risk_config.max_position_size_per_trade):
            reason = f"Position size exceeds max limit {self.risk_config.max_position_size_per_trade}"
            self.logger.warning(reason)
            return False, reason
        
        # 检查杠杆限制
        if leverage is not None and leverage > self.risk_config.max_leverage:
            reason = f"Leverage exceeds max limit {self.risk_config.max_leverage}"
            self.logger.warning(reason)
            return False, reason
        
        # 检查总体持仓限制
        total_position_value = self.position_manager.get_total_position_value() + position_value
        if (self.risk_config.enable_position_limits and 
            total_position_value > self.risk_config.max_position_value):
            reason = f"Total position value exceeds max limit {self.risk_config.max_position_value}"
            self.logger.warning(reason)
            return False, reason
        
        # 检查交易频率
        if self.risk_config.enable_frequency_control:
            today = datetime.now().strftime("%Y-%m-%d")
            if self.daily_trades.get(today, 0) >= self.risk_config.max_trades_per_day:
                reason = f"Daily trade limit {self.risk_config.max_trades_per_day} reached"
                self.logger.warning(reason)
                return False, reason
            
            if len(self.position_manager.get_all_positions()) >= self.risk_config.max_concurrent_trades:
                reason = f"Concurrent trade limit {self.risk_config.max_concurrent_trades} reached"
                self.logger.warning(reason)
                return False, reason
        
        # 检查回撤控制
        if self.risk_config.enable_drawdown_control:
            drawdown = self.get_current_drawdown()
            if drawdown >= self.risk_config.max_drawdown_percent:
                reason = f"Max drawdown {self.risk_config.max_drawdown_percent}% reached"
                self.logger.warning(reason)
                return False, reason
        
        return True, ""
    
    def open_position(
        self, 
        symbol: str, 
        size: float, 
        price: float, 
        timestamp: datetime,
        risk_percent: Optional[float] = None,
        leverage: Optional[float] = None
    ) -> Optional[Position]:
        """
        开仓
        
        Args:
            symbol: 交易对
            size: 交易数量
            price: 入场价格
            timestamp: 入场时间
            risk_percent: 风险百分比
            leverage: 杠杆倍数
            
        Returns:
            Optional[Position]: 创建的仓位，失败则返回None
        """
        # 检查风险
        allowed, reason = self.check_trade_risk(symbol, size, price, leverage)
        if not allowed:
            self.logger.warning(f"Failed to open position for {symbol}: {reason}")
            return None
        
        # 计算止损止盈
        risk_pct = risk_percent or self.risk_config.stop_loss_percent
        stop_loss, take_profit = self.stop_loss_manager.calculate_stop_loss_take_profit(
            price, 
            size > 0,  # 是否为多头
            risk_pct,
            self.risk_config.take_profit_percent,
            self.risk_config.risk_reward_ratio
        )
        
        # 创建仓位
        position = Position(
            symbol=symbol,
            size=size,
            entry_price=price,
            entry_time=timestamp,
            current_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage or self.risk_config.max_leverage,
            risk_percent=risk_pct
        )
        
        # 如果启用追踪止损
        if self.risk_config.trailing_stop_percent:
            position.trailing_stop = stop_loss
        
        # 添加仓位
        self.position_manager.add_position(position)
        
        return position
    
    def update_market_data(self, symbol: str, price: float) -> None:
        """
        更新市场数据
        
        Args:
            symbol: 交易对
            price: 当前价格
        """
        position = self.position_manager.get_position(symbol)
        if not position:
            return
        
        # 更新价格
        self.position_manager.update_position(symbol, current_price=price)
        
        # 更新追踪止损
        if self.risk_config.trailing_stop_percent and position.trailing_stop:
            new_trailing_stop = self.stop_loss_manager.update_trailing_stop(
                price,
                position.entry_price,
                position.is_long,
                self.risk_config.trailing_stop_percent,
                position.trailing_stop
            )
            self.position_manager.update_position(symbol, trailing_stop=new_trailing_stop)
    
    def should_exit_position(self, symbol: str) -> Tuple[bool, str, float]:
        """
        检查是否应该平仓
        
        Args:
            symbol: 交易对
            
        Returns:
            Tuple[bool, str, float]: (是否应该平仓, 原因, 建议价格)
        """
        position = self.position_manager.get_position(symbol)
        if not position:
            return False, "Position not found", 0.0
        
        return self.stop_loss_manager.should_exit(
            position,
            self.risk_config.max_loss_percent
        )
    
    def close_position(
        self, 
        symbol: str, 
        exit_price: float, 
        timestamp: datetime
    ) -> Optional[Position]:
        """
        平仓
        
        Args:
            symbol: 交易对
            exit_price: 出场价格
            timestamp: 出场时间
            
        Returns:
            Optional[Position]: 已平仓的仓位，未找到则返回None
        """
        # 确保价格已更新
        self.update_market_data(symbol, exit_price)
        
        # 平仓
        position = self.position_manager.close_position(symbol)
        if not position:
            return None
        
        # 计算实现盈亏
        realized_pnl = position.unrealized_pnl
        
        # 创建并记录交易
        order_info = OrderInfo(
            symbol=symbol,
            size=position.size,
            price=exit_price,
            timestamp=timestamp,
            status="closed",
            realized_pnl=realized_pnl,
            entry_price=position.entry_price
        )
        self.record_trade(order_info)
        
        return position
    
    def record_trade(self, order: OrderInfo) -> None:
        """
        记录交易
        
        Args:
            order: 订单信息
        """
        self.trade_history.append(order)
        self.risk_calculator.add_trade(order)
        
        # 更新每日交易次数
        today = order.timestamp.strftime("%Y-%m-%d")
        if today not in self.daily_trades:
            self.daily_trades[today] = 0
        self.daily_trades[today] += 1
        
        # 更新权益和盈亏
        self.total_pnl += order.realized_pnl
        self.current_equity = self.risk_config.max_position_value + self.total_pnl
        
        # 更新最高权益
        if self.current_equity > self.highest_equity:
            self.highest_equity = self.current_equity
        
        self.logger.info(
            f"Recorded trade: {order.symbol}, size: {order.size}, price: {order.price}, "
            f"status: {order.status}, PnL: {order.realized_pnl}")
    
    def get_current_drawdown(self) -> float:
        """
        获取当前回撤百分比
        
        Returns:
            float: 回撤百分比
        """
        if self.highest_equity <= 0:
            return 0.0
        
        drawdown = ((self.highest_equity - self.current_equity) / self.highest_equity) * 100
        return max(0.0, drawdown)
    
    def get_risk_metrics(self) -> RiskMetrics:
        """
        获取风险指标
        
        Returns:
            RiskMetrics: 风险指标对象
        """
        metrics = self.risk_calculator.calculate_risk_metrics()
        # 添加最大回撤信息
        metrics.max_drawdown = self.get_current_drawdown()
        return metrics
    
    def get_risk_level(self) -> RiskLevel:
        """
        获取当前风险等级
        
        Returns:
            RiskLevel: 风险等级
        """
        metrics = self.get_risk_metrics()
        return self.risk_calculator.assess_risk_level(metrics)
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """
        获取风险摘要
        
        Returns:
            Dict[str, Any]: 风险摘要信息
        """
        metrics = self.get_risk_metrics()
        risk_level = self.get_risk_level()
        
        # 获取当前交易信息
        today = datetime.now().strftime("%Y-%m-%d")
        today_trades = self.daily_trades.get(today, 0)
        
        return {
            "current_equity": self.current_equity,
            "total_pnl": self.total_pnl,
            "highest_equity": self.highest_equity,
            "drawdown": metrics.max_drawdown,
            "risk_level": risk_level.value,
            "open_positions": len(self.position_manager.get_all_positions()),
            "today_trades": today_trades,
            "total_trades": len(self.trade_history),
            "sharpe_ratio": metrics.sharpe_ratio,
            "win_rate": metrics.win_rate,
            "max_position_value": self.risk_config.max_position_value,
            "max_drawdown_percent": self.risk_config.max_drawdown_percent
        }
    
    def calculate_position_size(
        self,
        entry_price: float,
        account_balance: Optional[float] = None,
        risk_percent: Optional[float] = None,
        stop_loss_percent: Optional[float] = None
    ) -> float:
        """
        计算合适的仓位大小
        
        Args:
            account_balance: 账户余额，默认使用当前权益
            risk_percent: 风险百分比，默认使用配置值
            stop_loss_percent: 止损百分比，默认使用配置值
            entry_price: 入场价格
            
        Returns:
            float: 建议的仓位大小
        """
        balance = account_balance or self.current_equity
        risk_pct = risk_percent or self.risk_config.stop_loss_percent
        sl_pct = stop_loss_percent or self.risk_config.stop_loss_percent
        
        return self.risk_calculator.calculate_position_size(
            balance, risk_pct, sl_pct, entry_price
        )
    
    def adjust_risk_params(self, **kwargs) -> None:
        """
        调整风险参数
        
        Args:
            **kwargs: 风险参数键值对
        """
        for key, value in kwargs.items():
            if hasattr(self.risk_config, key):
                setattr(self.risk_config, key, value)
                self.logger.info(f"Adjusted risk param {key} to {value}")
            else:
                self.logger.warning(f"Unknown risk param {key}")
    
    def reset_daily_trade_counter(self) -> None:
        """
        重置每日交易计数器
        """
        today = datetime.now().strftime("%Y-%m-%d")
        if today in self.daily_trades:
            self.daily_trades[today] = 0
            self.logger.info("Reset daily trade counter")