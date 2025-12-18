"""
高频风险管理 - 高频突破策略专用风险控制模块

针对高频交易的特殊风险需求，实现多层次、动态的风险控制机制，
包括实时资金管理、仓位控制、止损管理、紧急停止等功能。

核心功能:
1. 实时资金暴露监控
2. 动态仓位大小计算
3. 多层次止损管理
4. 紧急风险控制
5. 性能监控和统计
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import numpy as np

from ..models.breakout_signal import BreakoutSignal, TradingDirection

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """风险限制配置"""
    max_position_size: float = 0.05           # 最大单笔仓位比例 (5%)
    max_total_exposure: float = 0.2          # 最大总暴露比例 (20%)
    max_positions: int = 10                  # 最大持仓数量
    max_daily_loss: float = 0.05             # 最大日亏损比例 (5%)
    max_consecutive_losses: int = 5          # 最大连续亏损次数
    max_drawdown: float = 0.15               # 最大回撤比例 (15%)

    # 止损配置
    stop_loss_pct: float = 0.01              # 基础止损比例 (1%)
    trailing_stop_pct: float = 0.015         # 移动止损比例 (1.5%)
    take_profit_pct: float = 0.02            # 基础止盈比例 (2%)

    # 动态风险调整
    volatility_adjustment: bool = True        # 是否根据波动率调整
    correlation_adjustment: bool = True       # 是否根据相关性调整
    performance_adjustment: bool = True      # 是否根据表现调整

    # 紧急停止条件
    emergency_stop_loss: float = 0.08        # 紧急止损比例 (8%)
    max_error_rate: float = 0.1              # 最大错误率 (10%)
    max_latency_ms: int = 1000               # 最大延迟 (毫秒)


@dataclass
class PositionRisk:
    """持仓风险信息"""
    symbol: str
    entry_price: float
    current_price: float
    size: float
    side: str  # 'long' or 'short'
    unrealized_pnl: float
    unrealized_pnl_pct: float
    risk_score: float
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_price: float
    entry_time: datetime
    last_update_time: datetime
    consecutive_losses: int = 0


@dataclass
class RiskMetrics:
    """风险指标"""
    current_exposure: float = 0.0          # 当前暴露
    daily_pnl: float = 0.0                 # 日盈亏
    total_pnl: float = 0.0                  # 总盈亏
    max_drawdown: float = 0.0              # 最大回撤
    current_drawdown: float = 0.0           # 当前回撤
    win_rate: float = 0.0                   # 胜率
    profit_factor: float = 0.0              # 盈亏比
    sharpe_ratio: float = 0.0                # 夏普比率
    risk_score: float = 0.0                 # 综合风险评分
    trading_errors: int = 0                 # 交易错误数
    latency_avg_ms: float = 0.0             # 平均延迟


class HighFrequencyRiskManager:
    """高频风险管理器

    专门为高频突破策略设计的风险管理系统
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化风险管理器

        Args:
            config: 风险配置参数
        """
        # 风险限制
        self.limits = RiskLimits(**config.get('risk', {}))

        # 资金管理
        self.initial_balance: float = 0.0
        self.current_balance: float = 0.0
        self.available_balance: float = 0.0
        self.reserved_balance: float = 0.0

        # 持仓风险跟踪
        self.position_risks: Dict[str, PositionRisk] = {}
        self.active_symbols: set = set()

        # 风险指标
        self.metrics = RiskMetrics()

        # 交易统计
        self.trade_history: List[Dict] = []
        self.daily_trades: List[Dict] = []
        self.recent_losses: deque = deque(maxlen=self.limits.max_consecutive_losses)

        # 性能监控
        self.performance_data = deque(maxlen=1000)  # 保留最近1000个交易的数据
        self.latency_data = deque(maxlen=100)       # 保留最近100次操作的延迟
        self.error_log = deque(maxlen=100)          # 保留最近100个错误

        # 紧急状态
        self.emergency_stop: bool = False
        self.emergency_reason: str = ""
        self.emergency_time: Optional[datetime] = None

        # 相关性矩阵（用于分散风险）
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}

        logger.info("高频风险管理器初始化完成")

    def set_initial_balance(self, balance: float):
        """设置初始资金"""
        self.initial_balance = balance
        self.current_balance = balance
        self.available_balance = balance
        logger.info(f"设置初始资金: {balance}")

    def check_risk_limits(self, symbol: str, positions: Dict) -> bool:
        """
        检查风险限制

        Args:
            symbol: 交易对符号
            positions: 当前持仓

        Returns:
            是否通过风险检查
        """
        if self.emergency_stop:
            logger.warning(f"紧急停止状态，拒绝交易: {self.emergency_reason}")
            return False

        try:
            # 1. 紧急停止检查
            if self._check_emergency_conditions():
                return False

            # 2. 资金暴露检查
            if not self._check_exposure_limits(symbol):
                return False

            # 3. 持仓数量检查
            if not self._check_position_limits(positions):
                return False

            # 4. 连续亏损检查
            if not self._check_consecutive_losses():
                return False

            # 5. 延迟检查
            if not self._check_latency_limits():
                return False

            # 6. 错误率检查
            if not self._check_error_rate_limits():
                return False

            return True

        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            self.log_error("Risk check failed", str(e))
            return False

    def calculate_position_size(self, signal: BreakoutSignal, total_balance: float) -> float:
        """
        计算建议仓位大小

        Args:
            signal: 突破信号
            total_balance: 总资金

        Returns:
            建议仓位大小（资金比例）
        """
        try:
            # 基础仓位大小
            base_size = self.limits.max_position_size

            # 根据信号强度调整
            signal_adjustment = 0.5 + signal.metrics.strength * 0.5  # 0.5-1.0
            adjusted_size = base_size * signal_adjustment

            # 根据信号置信度调整
            confidence_adjustment = signal.metrics.confidence
            adjusted_size *= confidence_adjustment

            # 根据风险评分调整
            if signal.metrics.risk_score > 0.7:
                adjusted_size *= 0.7  # 高风险减少30%
            elif signal.metrics.risk_score < 0.3:
                adjusted_size *= 1.2  # 低风险增加20%

            # 波动率调整
            if self.limits.volatility_adjustment:
                volatility_adjustment = self._calculate_volatility_adjustment(signal)
                adjusted_size *= volatility_adjustment

            # 相关性调整
            if self.limits.correlation_adjustment and signal.symbol in self.active_symbols:
                correlation_adjustment = self._calculate_correlation_adjustment(signal.symbol)
                adjusted_size *= correlation_adjustment

            # 表现调整
            if self.limits.performance_adjustment:
                performance_adjustment = self._calculate_performance_adjustment()
                adjusted_size *= performance_adjustment

            # 限制在合理范围内
            max_size = self.limits.max_position_size
            min_size = total_balance * 0.001  # 最小0.1%仓位

            final_size = max(min(adjusted_size, max_size), min_size)

            logger.debug(f"仓位计算 {signal.symbol}: "
                        f"基础={base_size:.3f}, "
                        f"信号调整={signal_adjustment:.3f}, "
                        f"置信度调整={confidence_adjustment:.3f}, "
                        f"最终={final_size:.3f}")

            return final_size

        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return 0.0  # 出错时返回0，拒绝交易

    def update_position_risk(self, symbol: str, entry_price: float, current_price: float,
                           size: float, side: str):
        """更新持仓风险信息"""
        try:
            # 计算盈亏
            if side == 'long':
                unrealized_pnl = (current_price - entry_price) * size
                unrealized_pnl_pct = (current_price - entry_price) / entry_price
            else:  # short
                unrealized_pnl = (entry_price - current_price) * size
                unrealized_pnl_pct = (entry_price - current_price) / entry_price

            # 计算止损止盈价格
            stop_loss_price = self._calculate_stop_loss(entry_price, side, current_price)
            take_profit_price = self._calculate_take_profit(entry_price, side)
            trailing_stop_price = self._calculate_trailing_stop(current_price, side, unrealized_pnl_pct)

            # 计算风险评分
            risk_score = self._calculate_position_risk_score(symbol, unrealized_pnl_pct)

            position_risk = PositionRisk(
                symbol=symbol,
                entry_price=entry_price,
                current_price=current_price,
                size=size,
                side=side,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                risk_score=risk_score,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                trailing_stop_price=trailing_stop_price,
                entry_time=datetime.now(),
                last_update_time=datetime.now()
            )

            self.position_risks[symbol] = position_risk
            self.active_symbols.add(symbol)

            # 更新综合指标
            self._update_risk_metrics()

            logger.debug(f"更新持仓风险 {symbol}: "
                        f"盈亏={unrealized_pnl_pct:.2%}, "
                        f"风险评分={risk_score:.2f}")

        except Exception as e:
            logger.error(f"更新持仓风险失败 {symbol}: {e}")

    def should_close_position(self, symbol: str) -> Tuple[bool, str]:
        """
        判断是否应该平仓

        Args:
            symbol: 交易对符号

        Returns:
            (是否平仓, 原因)
        """
        if symbol not in self.position_risks:
            return False, ""

        position = self.position_risks[symbol]

        try:
            # 1. 止损检查
            if position.side == 'long':
                if position.current_price <= position.stop_loss_price:
                    return True, f"触发止损: {position.current_price:.2f} <= {position.stop_loss_price:.2f}"
            else:  # short
                if position.current_price >= position.stop_loss_price:
                    return True, f"触发止损: {position.current_price:.2f} >= {position.stop_loss_price:.2f}"

            # 2. 移动止损检查
            if position.side == 'long':
                if position.current_price <= position.trailing_stop_price:
                    return True, f"触发移动止损: {position.current_price:.2f} <= {position.trailing_stop_price:.2f}"
            else:  # short
                if position.current_price >= position.trailing_stop_price:
                    return True, f"触发移动止损: {position.current_price:.2f} >= {position.trailing_stop_price:.2f}"

            # 3. 止盈检查
            if position.side == 'long':
                if position.current_price >= position.take_profit_price:
                    return True, f"触发止盈: {position.current_price:.2f} >= {position.take_profit_price:.2f}"
            else:  # short
                if position.current_price <= position.take_profit_price:
                    return True, f"触发止盈: {position.current_price:.2f} <= {position.take_profit_price:.2f}"

            # 4. 紧急平仓检查
            if self.emergency_stop:
                return True, f"紧急停止: {self.emergency_reason}"

            # 5. 时间止损（持仓时间过长）
            holding_duration = (datetime.now() - position.entry_time).total_seconds()
            if holding_duration > 3600:  # 1小时
                return True, f"时间止损: 持仓{holding_duration/60:.1f}分钟"

            # 6. 风险评分过高
            if position.risk_score > 0.8:
                return True, f"风险评分过高: {position.risk_score:.2f}"

            return False, ""

        except Exception as e:
            logger.error(f"平仓判断失败 {symbol}: {e}")
            return False, ""

    def close_position(self, symbol: str, exit_price: float, reason: str):
        """平仓处理"""
        try:
            if symbol not in self.position_risks:
                logger.warning(f"尝试平仓不存在的持仓: {symbol}")
                return

            position = self.position_risks[symbol]

            # 计算实际盈亏
            if position.side == 'long':
                realized_pnl = (exit_price - position.entry_price) * position.size
                realized_pnl_pct = (exit_price - position.entry_price) / position.entry_price
            else:  # short
                realized_pnl = (position.entry_price - exit_price) * position.size
                realized_pnl_pct = (position.entry_price - exit_price) / position.entry_price

            # 更新资金
            self.current_balance += realized_pnl
            self.available_balance += realized_pnl + position.size * position.entry_price

            # 记录交易
            trade_record = {
                'symbol': symbol,
                'side': position.side,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'size': position.size,
                'realized_pnl': realized_pnl,
                'realized_pnl_pct': realized_pnl_pct,
                'entry_time': position.entry_time,
                'exit_time': datetime.now(),
                'duration': (datetime.now() - position.entry_time).total_seconds(),
                'reason': reason
            }

            self.trade_history.append(trade_record)
            self.daily_trades.append(trade_record)

            # 更新连续亏损统计
            if realized_pnl < 0:
                self.recent_losses.append(realized_pnl)
                position.consecutive_losses += 1
            else:
                self.recent_losses.clear()
                position.consecutive_losses = 0

            # 更新性能数据
            self.performance_data.append({
                'timestamp': datetime.now(),
                'pnl': realized_pnl,
                'pnl_pct': realized_pnl_pct,
                'balance': self.current_balance,
                'exposure': self.metrics.current_exposure
            })

            # 移除持仓
            del self.position_risks[symbol]
            self.active_symbols.discard(symbol)

            # 更新指标
            self._update_risk_metrics()

            logger.info(f"平仓完成 {symbol}: "
                       f"盈亏={realized_pnl_pct:.2%}, "
                       f"原因={reason}, "
                       f"余额={self.current_balance:.2f}")

        except Exception as e:
            logger.error(f"平仓处理失败 {symbol}: {e}")

    # 私有方法
    def _check_emergency_conditions(self) -> bool:
        """检查紧急停止条件"""
        # 检查最大亏损
        daily_loss = abs(self.metrics.daily_pnl) / self.initial_balance
        if daily_loss >= self.limits.max_daily_loss:
            self._trigger_emergency_stop(f"日亏损超过限制: {daily_loss:.2%} >= {self.limits.max_daily_loss:.2%}")
            return True

        # 检查最大回撤
        if self.metrics.current_drawdown >= self.limits.max_drawdown:
            self._trigger_emergency_stop(f"回撤超过限制: {self.metrics.current_drawdown:.2%} >= {self.limits.max_drawdown:.2%}")
            return True

        # 检查紧急止损
        total_loss = abs(self.metrics.total_pnl) / self.initial_balance
        if total_loss >= self.limits.emergency_stop_loss:
            self._trigger_emergency_stop(f"触发紧急止损: {total_loss:.2%} >= {self.limits.emergency_stop_loss:.2%}")
            return True

        return False

    def _check_exposure_limits(self, symbol: str) -> bool:
        """检查资金暴露限制"""
        current_exposure = self.metrics.current_exposure
        return current_exposure < self.limits.max_total_exposure

    def _check_position_limits(self, positions: Dict) -> bool:
        """检查持仓数量限制"""
        current_positions = len(positions)
        return current_positions < self.limits.max_positions

    def _check_consecutive_losses(self) -> bool:
        """检查连续亏损限制"""
        return len(self.recent_losses) < self.limits.max_consecutive_losses

    def _check_latency_limits(self) -> bool:
        """检查延迟限制"""
        if self.latency_data:
            avg_latency = np.mean(list(self.latency_data))
            return avg_latency <= self.limits.max_latency_ms
        return True

    def _check_error_rate_limits(self) -> bool:
        """检查错误率限制"""
        if self.error_log:
            recent_errors = len([e for e in self.error_log
                               if (datetime.now() - e['timestamp']).total_seconds() < 3600])
            total_operations = len(self.performance_data)
            if total_operations > 0:
                error_rate = recent_errors / total_operations
                return error_rate <= self.limits.max_error_rate
        return True

    def _trigger_emergency_stop(self, reason: str):
        """触发紧急停止"""
        self.emergency_stop = True
        self.emergency_reason = reason
        self.emergency_time = datetime.now()
        logger.critical(f"触发紧急停止: {reason}")

    def _calculate_volatility_adjustment(self, signal: BreakoutSignal) -> float:
        """计算波动率调整因子"""
        current_volatility = signal.indicators.current_volatility
        volatility_ratio = signal.indicators.volatility_ratio

        if volatility_ratio > 2.0:  # 高波动率
            return 0.7  # 减少30%
        elif volatility_ratio > 1.5:  # 中等波动率
            return 0.85  # 减少15%
        elif volatility_ratio < 0.5:  # 低波动率
            return 1.2  # 增加20%
        else:
            return 1.0  # 不调整

    def _calculate_correlation_adjustment(self, symbol: str) -> float:
        """计算相关性调整因子"""
        if symbol not in self.correlation_matrix:
            return 1.0

        # 计算与现有持仓的平均相关性
        correlations = []
        for other_symbol in self.active_symbols:
            if other_symbol in self.correlation_matrix[symbol]:
                correlations.append(abs(self.correlation_matrix[symbol][other_symbol]))

        if correlations:
            avg_correlation = np.mean(correlations)
            # 相关性越高，仓位越小
            adjustment = 1.0 - (avg_correlation * 0.3)
            return max(adjustment, 0.5)  # 最小调整到50%

        return 1.0

    def _calculate_performance_adjustment(self) -> float:
        """计算表现调整因子"""
        if len(self.performance_data) < 10:
            return 1.0

        # 计算最近的胜率
        recent_data = list(self.performance_data)[-20:]
        wins = sum(1 for d in recent_data if d['pnl'] > 0)
        win_rate = wins / len(recent_data)

        # 根据胜率调整
        if win_rate > 0.7:
            return 1.2  # 表现好，增加20%
        elif win_rate > 0.5:
            return 1.0  # 正常表现
        elif win_rate > 0.3:
            return 0.8  # 表现差，减少20%
        else:
            return 0.5  # 表现很差，减少50%

    def _calculate_stop_loss(self, entry_price: float, side: str, current_price: float) -> float:
        """计算止损价格"""
        if side == 'long':
            return entry_price * (1 - self.limits.stop_loss_pct)
        else:  # short
            return entry_price * (1 + self.limits.stop_loss_pct)

    def _calculate_take_profit(self, entry_price: float, side: str) -> float:
        """计算止盈价格"""
        if side == 'long':
            return entry_price * (1 + self.limits.take_profit_pct)
        else:  # short
            return entry_price * (1 - self.limits.take_profit_pct)

    def _calculate_trailing_stop(self, current_price: float, side: str, pnl_pct: float) -> float:
        """计算移动止损价格"""
        if pnl_pct > 0.01:  # 盈利超过1%时启动移动止损
            if side == 'long':
                return current_price * (1 - self.limits.trailing_stop_pct)
            else:  # short
                return current_price * (1 + self.limits.trailing_stop_pct)
        else:
            return self._calculate_stop_loss(current_price, side, current_price)

    def _calculate_position_risk_score(self, symbol: str, pnl_pct: float) -> float:
        """计算持仓风险评分"""
        # 基于盈亏计算风险评分
        if pnl_pct < -0.05:  # 亏损超过5%
            return 0.9
        elif pnl_pct < -0.02:  # 亏损2%-5%
            return 0.6 + abs(pnl_pct) * 6  # 0.6-0.9
        elif pnl_pct < 0:  # 小幅亏损
            return 0.3 + abs(pnl_pct) * 15  # 0.3-0.6
        elif pnl_pct < 0.02:  # 小幅盈利
            return 0.3
        else:  # 大幅盈利
            return 0.2

    def _update_risk_metrics(self):
        """更新风险指标"""
        try:
            # 计算当前暴露
            total_exposure = 0.0
            for position in self.position_risks.values():
                exposure = abs(position.size * position.current_price)
                total_exposure += exposure

            if self.current_balance > 0:
                self.metrics.current_exposure = total_exposure / self.current_balance

            # 计算日盈亏
            today = datetime.now().date()
            self.metrics.daily_pnl = sum(
                trade['realized_pnl'] for trade in self.daily_trades
                if trade['exit_time'].date() == today
            )

            # 计算总盈亏
            self.metrics.total_pnl = sum(trade['realized_pnl'] for trade in self.trade_history)

            # 计算当前回撤
            if len(self.performance_data) > 0:
                peak_balance = max(d['balance'] for d in self.performance_data)
                current_balance = self.current_balance
                self.metrics.current_drawdown = (peak_balance - current_balance) / peak_balance
                self.metrics.max_drawdown = max(self.metrics.max_drawdown, self.metrics.current_drawdown)

            # 计算胜率
            if len(self.trade_history) > 0:
                wins = sum(1 for trade in self.trade_history if trade['realized_pnl'] > 0)
                self.metrics.win_rate = wins / len(self.trade_history)

            # 计算盈亏比
            winning_trades = [t for t in self.trade_history if t['realized_pnl'] > 0]
            losing_trades = [t for t in self.trade_history if t['realized_pnl'] < 0]

            if losing_trades:
                avg_win = np.mean([t['realized_pnl'] for t in winning_trades]) if winning_trades else 0
                avg_loss = abs(np.mean([t['realized_pnl'] for t in losing_trades]))
                self.metrics.profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

            # 计算综合风险评分
            risk_factors = [
                self.metrics.current_exposure / self.limits.max_total_exposure,
                abs(self.metrics.daily_pnl) / (self.initial_balance * self.limits.max_daily_loss),
                self.metrics.current_drawdown / self.limits.max_drawdown,
                len(self.recent_losses) / self.limits.max_consecutive_losses
            ]
            self.metrics.risk_score = np.mean(risk_factors)

            # 更新平均延迟
            if self.latency_data:
                self.metrics.latency_avg_ms = np.mean(list(self.latency_data))

        except Exception as e:
            logger.error(f"更新风险指标失败: {e}")

    def log_latency(self, operation: str, latency_ms: float):
        """记录延迟"""
        self.latency_data.append(latency_ms)
        logger.debug(f"延迟记录 {operation}: {latency_ms:.2f}ms")

    def log_error(self, operation: str, error_message: str):
        """记录错误"""
        self.error_log.append({
            'timestamp': datetime.now(),
            'operation': operation,
            'error': error_message
        })
        self.metrics.trading_errors += 1

    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        return {
            'limits': {
                'max_position_size': self.limits.max_position_size,
                'max_total_exposure': self.limits.max_total_exposure,
                'max_positions': self.limits.max_positions,
                'max_daily_loss': self.limits.max_daily_loss,
                'max_drawdown': self.limits.max_drawdown
            },
            'metrics': {
                'current_exposure': self.metrics.current_exposure,
                'daily_pnl': self.metrics.daily_pnl,
                'total_pnl': self.metrics.total_pnl,
                'current_drawdown': self.metrics.current_drawdown,
                'max_drawdown': self.metrics.max_drawdown,
                'win_rate': self.metrics.win_rate,
                'profit_factor': self.metrics.profit_factor,
                'risk_score': self.metrics.risk_score
            },
            'balance': {
                'initial': self.initial_balance,
                'current': self.current_balance,
                'available': self.available_balance,
                'reserved': self.reserved_balance
            },
            'positions': {
                'count': len(self.position_risks),
                'symbols': list(self.active_symbols),
                'details': {symbol: {
                    'side': pos.side,
                    'size': pos.size,
                    'pnl_pct': pos.unrealized_pnl_pct,
                    'risk_score': pos.risk_score
                } for symbol, pos in self.position_risks.items()}
            },
            'emergency_status': {
                'is_stopped': self.emergency_stop,
                'reason': self.emergency_reason,
                'time': self.emergency_time.isoformat() if self.emergency_time else None
            },
            'performance': {
                'total_trades': len(self.trade_history),
                'daily_trades': len(self.daily_trades),
                'recent_losses': len(self.recent_losses),
                'avg_latency_ms': self.metrics.latency_avg_ms,
                'error_count': self.metrics.trading_errors
            }
        }

    def reset_daily_stats(self):
        """重置日统计"""
        self.daily_trades.clear()
        logger.info("日统计已重置")

    def reset_emergency_stop(self):
        """重置紧急停止状态"""
        self.emergency_stop = False
        self.emergency_reason = ""
        self.emergency_time = None
        logger.info("紧急停止状态已重置")


# 示例使用
def example_usage():
    """示例用法"""
    config = {
        'risk': {
            'max_position_size': 0.05,
            'max_total_exposure': 0.2,
            'max_positions': 10,
            'max_daily_loss': 0.05,
            'stop_loss_pct': 0.01,
            'take_profit_pct': 0.02
        }
    }

    # 创建风险管理器
    risk_manager = HighFrequencyRiskManager(config)
    risk_manager.set_initial_balance(10000.0)

    # 模拟持仓
    risk_manager.update_position_risk(
        symbol="BTCUSDT",
        entry_price=50000.0,
        current_price=50500.0,
        size=0.1,
        side="long"
    )

    # 检查平仓条件
    should_close, reason = risk_manager.should_close_position("BTCUSDT")
    print(f"是否应该平仓 BTCUSDT: {should_close}, 原因: {reason}")

    # 获取风险报告
    report = risk_manager.get_risk_report()
    print(f"\n风险报告:")
    print(f"当前暴露: {report['metrics']['current_exposure']:.2%}")
    print(f"风险评分: {report['metrics']['risk_score']:.2f}")
    print(f"持仓数量: {report['positions']['count']}")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    example_usage()