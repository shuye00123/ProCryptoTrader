"""
风控工具类模块

提供各种风险管理和控制工具，包括仓位管理、止损止盈、风险指标计算等。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

# 导入core.trading.position_manager中的PositionManager
from ..trading.position_manager import PositionManager as TradingPositionManager

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险级别枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: OrderSide
    size: float
    entry_price: float
    current_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def update_price(self, new_price: float):
        """更新当前价格并计算未实现盈亏"""
        self.current_price = new_price
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (new_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * self.size
    
    def close(self, close_price: float, size: Optional[float] = None) -> float:
        """
        平仓并计算已实现盈亏
        
        Args:
            close_price: 平仓价格
            size: 平仓数量，None表示全部平仓
            
        Returns:
            float: 已实现盈亏
        """
        close_size = size if size is not None else self.size
        
        if self.side == OrderSide.BUY:
            realized_pnl = (close_price - self.entry_price) * close_size
        else:
            realized_pnl = (self.entry_price - close_price) * close_size
        
        self.realized_pnl += realized_pnl
        self.size -= close_size
        
        return realized_pnl
    
    def get_pnl_percent(self) -> float:
        """获取盈亏百分比"""
        if self.entry_price == 0:
            return 0.0
        
        if self.side == OrderSide.BUY:
            return (self.current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - self.current_price) / self.entry_price * 100


@dataclass
class RiskMetrics:
    """风险指标"""
    total_exposure: float = 0.0  # 总敞口
    max_position_size: float = 0.0  # 最大持仓规模
    leverage: float = 1.0  # 杠杆倍数
    max_drawdown: float = 0.0  # 最大回撤
    var_95: float = 0.0  # 95% VaR
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    calmar_ratio: float = 0.0  # 卡玛比率
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈利因子
    kelly_ratio: float = 0.0  # 凯利比率
    risk_level: RiskLevel = RiskLevel.LOW  # 风险级别


class RiskCalculator:
    """风险计算器"""
    
    @staticmethod
    def calculate_var(returns: pd.Series, confidence_level: float = 0.05) -> float:
        """
        计算VaR（风险价值）
        
        Args:
            returns: 收益率序列
            confidence_level: 置信水平
            
        Returns:
            float: VaR值
        """
        if len(returns) == 0:
            return 0.0
        
        return np.percentile(returns, confidence_level * 100)
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: pd.Series) -> float:
        """
        计算最大回撤
        
        Args:
            equity_curve: 权益曲线
            
        Returns:
            float: 最大回撤
        """
        if len(equity_curve) == 0:
            return 0.0
        
        cumulative = (1 + equity_curve).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        
        return drawdown.min()
    
    @staticmethod
    def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        计算夏普比率
        
        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            
        Returns:
            float: 夏普比率
        """
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate
        
        if excess_returns.std() == 0:
            return 0.0
        
        return excess_returns.mean() / excess_returns.std() * np.sqrt(252)  # 年化
    
    @staticmethod
    def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        计算索提诺比率
        
        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            
        Returns:
            float: 索提诺比率
        """
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        return excess_returns.mean() / downside_returns.std() * np.sqrt(252)  # 年化
    
    @staticmethod
    def calculate_calmar_ratio(returns: pd.Series) -> float:
        """
        计算卡玛比率
        
        Args:
            returns: 收益率序列
            
        Returns:
            float: 卡玛比率
        """
        if len(returns) == 0:
            return 0.0
        
        total_return = (1 + returns).prod() - 1
        max_drawdown = RiskCalculator.calculate_max_drawdown(returns)
        
        if max_drawdown == 0:
            return 0.0
        
        return total_return / abs(max_drawdown)
    
    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> float:
        """
        计算胜率
        
        Args:
            trades: 交易记录列表
            
        Returns:
            float: 胜率
        """
        if not trades:
            return 0.0
        
        winning_trades = sum(1 for trade in trades if trade.get('pnl', 0) > 0)
        
        return winning_trades / len(trades)
    
    @staticmethod
    def calculate_profit_factor(trades: List[Dict]) -> float:
        """
        计算盈利因子
        
        Args:
            trades: 交易记录列表
            
        Returns:
            float: 盈利因子
        """
        if not trades:
            return 0.0
        
        gross_profit = sum(trade.get('pnl', 0) for trade in trades if trade.get('pnl', 0) > 0)
        gross_loss = sum(abs(trade.get('pnl', 0)) for trade in trades if trade.get('pnl', 0) < 0)
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    @staticmethod
    def calculate_kelly_ratio(trades: List[Dict]) -> float:
        """
        计算凯利比率
        
        Args:
            trades: 交易记录列表
            
        Returns:
            float: 凯利比率
        """
        if not trades:
            return 0.0
        
        win_rate = RiskCalculator.calculate_win_rate(trades)
        
        if win_rate == 0:
            return 0.0
        
        winning_trades = [trade for trade in trades if trade.get('pnl', 0) > 0]
        losing_trades = [trade for trade in trades if trade.get('pnl', 0) < 0]
        
        if not winning_trades or not losing_trades:
            return 0.0
        
        avg_win = sum(trade.get('pnl', 0) for trade in winning_trades) / len(winning_trades)
        avg_loss = sum(abs(trade.get('pnl', 0)) for trade in losing_trades) / len(losing_trades)
        
        if avg_loss == 0:
            return 0.0
        
        return win_rate - (1 - win_rate) * (avg_win / avg_loss)
    
    @staticmethod
    def calculate_position_size_kelly(capital: float, win_rate: float, 
                                    avg_win: float, avg_loss: float,
                                    leverage: float = 1.0) -> float:
        """
        使用凯利公式计算最优仓位大小
        
        Args:
            capital: 总资金
            win_rate: 胜率
            avg_win: 平均盈利
            avg_loss: 平均亏损
            leverage: 杠杆倍数
            
        Returns:
            float: 最优仓位大小
        """
        if avg_loss == 0:
            return 0.0
        
        # 凯利公式: f = (p * b - q) / b
        # 其中 p 是胜率, q 是败率, b 是盈亏比
        win_prob = win_rate
        lose_prob = 1 - win_rate
        win_loss_ratio = avg_win / avg_loss
        
        kelly_fraction = (win_prob * win_loss_ratio - lose_prob) / win_loss_ratio
        
        # 限制凯利比例在合理范围内
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # 限制在0-25%之间
        
        return capital * kelly_fraction * leverage
    
    @staticmethod
    def assess_risk_level(metrics: RiskMetrics) -> RiskLevel:
        """
        评估风险级别
        
        Args:
            metrics: 风险指标
            
        Returns:
            RiskLevel: 风险级别
        """
        # 定义风险阈值
        max_drawdown_thresholds = {
            RiskLevel.LOW: 0.05,      # 5%
            RiskLevel.MEDIUM: 0.10,   # 10%
            RiskLevel.HIGH: 0.20,     # 20%
        }
        
        leverage_thresholds = {
            RiskLevel.LOW: 2.0,
            RiskLevel.MEDIUM: 5.0,
            RiskLevel.HIGH: 10.0,
        }
        
        var_thresholds = {
            RiskLevel.LOW: 0.02,      # 2%
            RiskLevel.MEDIUM: 0.05,   # 5%
            RiskLevel.HIGH: 0.10,     # 10%
        }
        
        # 评估各项指标
        drawdown_level = RiskLevel.LOW
        for level, threshold in max_drawdown_thresholds.items():
            if abs(metrics.max_drawdown) > threshold:
                drawdown_level = level
        
        leverage_level = RiskLevel.LOW
        for level, threshold in leverage_thresholds.items():
            if metrics.leverage > threshold:
                leverage_level = level
        
        var_level = RiskLevel.LOW
        for level, threshold in var_thresholds.items():
            if abs(metrics.var_95) > threshold:
                var_level = level
        
        # 取最高风险级别
        risk_levels = [drawdown_level, leverage_level, var_level]
        
        if RiskLevel.CRITICAL in risk_levels:
            return RiskLevel.CRITICAL
        elif RiskLevel.HIGH in risk_levels:
            return RiskLevel.HIGH
        elif RiskLevel.MEDIUM in risk_levels:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW


class StopLossManager:
    
    def __init__(self):
        """初始化止损管理器"""
        self.stop_orders: Dict[str, Dict[int, Dict]] = {}  # {symbol: {position_index: stop_data}}
    
    def set_stop_loss(self, symbol: str, position_index: int, 
                     stop_price: float, stop_type: str = "fixed") -> bool:
        """
        设置止损
        
        Args:
            symbol: 交易对
            position_index: 持仓索引
            stop_price: 止损价格
            stop_type: 止损类型 ("fixed", "trailing", "percentage")
            
        Returns:
            bool: 是否成功设置
        """
        if symbol not in self.stop_orders:
            self.stop_orders[symbol] = {}
        
        self.stop_orders[symbol][position_index] = {
            'stop_price': stop_price,
            'stop_type': stop_type,
            'initial_price': stop_price,  # 用于追踪止损
            'highest_price': stop_price,  # 用于追踪止损
            'activated': False
        }
        
        logger.info(f"Set stop loss for {symbol}[{position_index}] at {stop_price} ({stop_type})")
        
        return True
    
    def update_trailing_stop(self, symbol: str, position_index: int, current_price: float):
        """
        更新追踪止损
        
        Args:
            symbol: 交易对
            position_index: 持仓索引
            current_price: 当前价格
        """
        if (symbol not in self.stop_orders or 
            position_index not in self.stop_orders[symbol]):
            return
        
        stop_data = self.stop_orders[symbol][position_index]
        
        if stop_data['stop_type'] == 'trailing':
            # 更新最高价
            if current_price > stop_data['highest_price']:
                stop_data['highest_price'] = current_price
                
                # 计算新的止损价格（这里使用5%的回撤作为示例）
                trailing_percent = 0.05
                new_stop_price = current_price * (1 - trailing_percent)
                
                if new_stop_price > stop_data['stop_price']:
                    stop_data['stop_price'] = new_stop_price
                    logger.info(f"Updated trailing stop for {symbol}[{position_index}] to {new_stop_price}")
    
    def check_stop_loss(self, symbol: str, position_index: int, 
                       current_price: float, position_side: OrderSide) -> bool:
        """
        检查是否触发止损
        
        Args:
            symbol: 交易对
            position_index: 持仓索引
            current_price: 当前价格
            position_side: 持仓方向
            
        Returns:
            bool: 是否触发止损
        """
        if (symbol not in self.stop_orders or 
            position_index not in self.stop_orders[symbol]):
            return False
        
        stop_data = self.stop_orders[symbol][position_index]
        stop_price = stop_data['stop_price']
        
        # 检查是否触发止损
        triggered = False
        if position_side == OrderSide.BUY and current_price <= stop_price:
            triggered = True
        elif position_side == OrderSide.SELL and current_price >= stop_price:
            triggered = True
        
        if triggered and not stop_data['activated']:
            stop_data['activated'] = True
            logger.warning(f"Stop loss triggered for {symbol}[{position_index}] at {current_price} (stop: {stop_price})")
        
        return triggered
    
    def remove_stop_loss(self, symbol: str, position_index: int) -> bool:
        """
        移除止损
        
        Args:
            symbol: 交易对
            position_index: 持仓索引
            
        Returns:
            bool: 是否成功移除
        """
        if (symbol not in self.stop_orders or 
            position_index not in self.stop_orders[symbol]):
            return False
        
        del self.stop_orders[symbol][position_index]
        
        if not self.stop_orders[symbol]:
            del self.stop_orders[symbol]
        
        logger.info(f"Removed stop loss for {symbol}[{position_index}]")
        
        return True

class RiskManager:
    """风险管理器"""
    
    def __init__(self, position_manager: TradingPositionManager,
                 stop_loss_manager: StopLossManager):
        """
        初始化风险管理器
        
        Args:
            position_manager: 仓位管理器
            stop_loss_manager: 止损管理器
        """
        self.position_manager = position_manager
        self.stop_loss_manager = stop_loss_manager
        self.risk_calculator = RiskCalculator()
        self.trade_history: List[Dict] = []
    
    def evaluate_risk(self, price_data: Dict[str, float]) -> RiskMetrics:
        """
        评估当前风险状况
        
        Args:
            price_data: 价格数据
            
        Returns:
            RiskMetrics: 风险指标
        """
        # 更新持仓价格
        self.position_manager.update_prices(price_data)
        
        # 计算基本指标
        total_exposure = self.position_manager.get_total_exposure()
        total_unrealized_pnl = self.position_manager.get_total_unrealized_pnl()
        total_realized_pnl = self.position_manager.get_total_realized_pnl()
        
        # 计算最大持仓规模
        max_position_size = 0.0
        for positions in self.position_manager.get_all_positions().values():
            for position in positions:
                position_value = position.size * position.current_price
                if position_value > max_position_size:
                    max_position_size = position_value
        
        # 计算杠杆倍数（假设总资金为100000）
        total_capital = 100000.0
        leverage = total_exposure / total_capital if total_capital > 0 else 1.0
        
        # 计算风险指标（如果有交易历史）
        max_drawdown = 0.0
        var_95 = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
        win_rate = 0.0
        profit_factor = 0.0
        kelly_ratio = 0.0
        
        if self.trade_history:
            # 提取收益率序列
            returns = pd.Series([trade.get('return', 0) for trade in self.trade_history])
            
            max_drawdown = self.risk_calculator.calculate_max_drawdown(returns)
            var_95 = self.risk_calculator.calculate_var(returns, 0.05)
            sharpe_ratio = self.risk_calculator.calculate_sharpe_ratio(returns)
            sortino_ratio = self.risk_calculator.calculate_sortino_ratio(returns)
            calmar_ratio = self.risk_calculator.calculate_calmar_ratio(returns)
            win_rate = self.risk_calculator.calculate_win_rate(self.trade_history)
            profit_factor = self.risk_calculator.calculate_profit_factor(self.trade_history)
            kelly_ratio = self.risk_calculator.calculate_kelly_ratio(self.trade_history)
        
        # 创建风险指标对象
        metrics = RiskMetrics(
            total_exposure=total_exposure,
            max_position_size=max_position_size,
            leverage=leverage,
            max_drawdown=max_drawdown,
            var_95=var_95,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            kelly_ratio=kelly_ratio
        )
        
        # 评估风险级别
        metrics.risk_level = self.risk_calculator.assess_risk_level(metrics)
        
        return metrics
    
    def check_risk_limits(self, metrics: RiskMetrics) -> List[str]:
        """
        检查风险限制
        
        Args:
            metrics: 风险指标
            
        Returns:
            List[str]: 风险警告列表
        """
        warnings = []
        
        # 检查总敞口
        if metrics.total_exposure > self.position_manager.max_total_exposure:
            warnings.append(f"Total exposure {metrics.total_exposure} exceeds limit {self.position_manager.max_total_exposure}")
        
        # 检查最大持仓规模
        if metrics.max_position_size > self.position_manager.max_position_size:
            warnings.append(f"Max position size {metrics.max_position_size} exceeds limit {self.position_manager.max_position_size}")
        
        # 检查杠杆倍数
        if metrics.leverage > 10.0:
            warnings.append(f"Leverage {metrics.leverage:.2f} is dangerously high")
        
        # 检查最大回撤
        if abs(metrics.max_drawdown) > 0.2:  # 20%
            warnings.append(f"Max drawdown {metrics.max_drawdown:.2%} is critical")
        
        # 检查VaR
        if abs(metrics.var_95) > 0.1:  # 10%
            warnings.append(f"VaR (95%) {metrics.var_95:.2%} is high")
        
        return warnings
    
    def add_trade_record(self, trade_data: Dict):
        """
        添加交易记录
        
        Args:
            trade_data: 交易数据
        """
        self.trade_history.append(trade_data)
    
    def get_risk_report(self, price_data: Dict[str, float]) -> Dict:
        """
        获取风险报告
        
        Args:
            price_data: 价格数据
            
        Returns:
            Dict: 风险报告
        """
        # 评估风险
        metrics = self.evaluate_risk(price_data)
        
        # 检查风险限制
        warnings = self.check_risk_limits(metrics)
        
        # 获取持仓信息
        positions = self.position_manager.get_all_positions()
        
        # 构建报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'risk_level': metrics.risk_level.value,
            'metrics': {
                'total_exposure': metrics.total_exposure,
                'max_position_size': metrics.max_position_size,
                'leverage': metrics.leverage,
                'max_drawdown': metrics.max_drawdown,
                'var_95': metrics.var_95,
                'sharpe_ratio': metrics.sharpe_ratio,
                'sortino_ratio': metrics.sortino_ratio,
                'calmar_ratio': metrics.calmar_ratio,
                'win_rate': metrics.win_rate,
                'profit_factor': metrics.profit_factor,
                'kelly_ratio': metrics.kelly_ratio
            },
            'warnings': warnings,
            'positions': {}
        }
        
        # 添加持仓信息
        for symbol, symbol_positions in positions.items():
            report['positions'][symbol] = []
            for position in symbol_positions:
                report['positions'][symbol].append({
                    'side': position.side.value,
                    'size': position.size,
                    'entry_price': position.entry_price,
                    'current_price': position.current_price,
                    'unrealized_pnl': position.unrealized_pnl,
                    'realized_pnl': position.realized_pnl,
                    'pnl_percent': position.get_pnl_percent()
                })
        
        return report