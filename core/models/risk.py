"""
风险管理数据模型

统一系统中所有的风险相关数据结构，包括风险级别、风险指标和风险配置。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RiskLevel(Enum):
    """风险等级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"
    CRITICAL = "critical"


class RiskMetricType(Enum):
    """风险指标类型"""
    SHARPE_RATIO = "sharpe_ratio"
    SORTINO_RATIO = "sortino_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    VALUE_AT_RISK = "value_at_risk"
    EXPECTED_SHORTFALL = "expected_shortfall"
    VOLATILITY = "volatility"
    BETA = "beta"
    ALPHA = "alpha"
    INFORMATION_RATIO = "information_ratio"
    TREYNOR_RATIO = "treynor_ratio"
    CALMAR_RATIO = "calmar_ratio"


@dataclass
class RiskMetrics:
    """
    风险指标数据类

    包含各种量化风险指标，用于评估交易策略的风险水平。
    """
    sharpe_ratio: float = 0.0                     # 夏普比率
    sortino_ratio: float = 0.0                    # 索提诺比率
    max_drawdown: float = 0.0                       # 最大回撤
    value_at_risk_95: float = 0.0                   # 95% VaR
    expected_shortfall_95: float = 0.0             # 95% ES
    volatility: float = 0.0                          # 波动率
    beta: float = 0.0                               # Beta值
    alpha: float = 0.0                              # Alpha值
    information_ratio: float = 0.0                  # 信息比率
    treynor_ratio: float = 0.0                      # 特雷诺比率
    calmar_ratio: float = 0.0                        # 卡玛比率
    win_rate: float = 0.0                            # 胜率
    profit_factor: float = 0.0                       # 盈利因子
    kelly_ratio: float = 0.0                         # 凯利比率
    trading_frequency: float = 0.0                   # 交易频率
    total_trades: int = 0                            # 总交易次数
    profitable_trades: int = 0                       # 盈利交易次数
    losing_trades: int = 0                          # 亏损交易次数
    avg_profit: float = 0.0                          # 平均盈利
    avg_loss: float = 0.0                           # 平均亏损
    avg_trade_duration: float = 0.0                  # 平均持仓时间
    largest_profit: float = 0.0                       # 最大盈利
    largest_loss: float = 0.0                        # 最大亏损
    profit_loss_ratio: float = 0.0                    # 盈亏比
    recovery_factor: float = 0.0                      # 恢复因子
    var_timeframe: str = "1d"                        # VaR时间框架
    confidence_level: float = 0.95                    # 置信水平
    timestamp: datetime = field(default_factory=datetime.now)  # 计算时间
    strategy_name: Optional[str] = None               # 策略名称
    symbol: Optional[str] = None                      # 交易对
    timeframe: Optional[str] = None                   # 时间框架

    def __post_init__(self):
        """初始化后处理"""
        # 计算派生指标
        if self.total_trades > 0:
            self.win_rate = (self.profitable_trades / self.total_trades) * 100

        if self.avg_loss > 0:
            self.profit_loss_ratio = self.avg_profit / self.avg_loss

        # 确保风险指标在合理范围内
        self.max_drawdown = abs(self.max_drawdown)
        self.value_at_risk_95 = abs(self.value_at_risk_95)

    @property
    def risk_level(self) -> RiskLevel:
        """根据指标评估风险等级"""
        risk_score = 0

        # 基于最大回撤评估
        if self.max_drawdown >= 0.50:  # 50%
            risk_score += 5
        elif self.max_drawdown >= 0.30:  # 30%
            risk_score += 4
        elif self.max_drawdown >= 0.20:  # 20%
            risk_score += 3
        elif self.max_drawdown >= 0.10:  # 10%
            risk_score += 2
        elif self.max_drawdown >= 0.05:  # 5%
            risk_score += 1

        # 基于夏普比率评估
        if self.sharpe_ratio < -1:
            risk_score += 3
        elif self.sharpe_ratio < 0:
            risk_score += 2
        elif self.sharpe_ratio < 1:
            risk_score += 1

        # 基于VaR评估
        if self.value_at_risk_95 >= 0.20:  # 20%
            risk_score += 3
        elif self.value_at_risk_95 >= 0.10:  # 10%
            risk_score += 2
        elif self.value_at_risk_95 >= 0.05:  # 5%
            risk_score += 1

        # 基于胜率评估
        if self.win_rate < 0.30:  # 30%
            risk_score += 2
        elif self.win_rate < 0.40:  # 40%
            risk_score += 1

        # 确定风险等级
        if risk_score >= 8:
            return RiskLevel.CRITICAL
        elif risk_score >= 6:
            return RiskLevel.EXTREME
        elif risk_score >= 4:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    @property
    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.avg_profit > 0 and self.profit_loss_ratio > 1.0

    @property
    def is_high_risk(self) -> bool:
        """是否高风险"""
        return self.risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME, RiskLevel.CRITICAL]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'value_at_risk_95': self.value_at_risk_95,
            'expected_shortfall_95': self.expected_shortfall_95,
            'volatility': self.volatility,
            'beta': self.beta,
            'alpha': self.alpha,
            'information_ratio': self.information_ratio,
            'treynor_ratio': self.treynor_ratio,
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'kelly_ratio': self.kelly_ratio,
            'trading_frequency': self.trading_frequency,
            'total_trades': self.total_trades,
            'profitable_trades': self.profitable_trades,
            'losing_trades': self.losing_trades,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'avg_trade_duration': self.avg_trade_duration,
            'largest_profit': self.largest_profit,
            'largest_loss': self.largest_loss,
            'profit_loss_ratio': self.profit_loss_ratio,
            'recovery_factor': self.recovery_factor,
            'var_timeframe': self.var_timeframe,
            'confidence_level': self.confidence_level,
            'timestamp': self.timestamp.isoformat(),
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'risk_level': self.risk_level.value,
            'is_profitable': self.is_profitable,
            'is_high_risk': self.is_high_risk
        }


@dataclass
class RiskConfig:
    """
    风险配置数据类

    定义各种风险控制的参数和阈值。
    """
    # 资金风险控制
    max_position_value: float = 10000.0             # 最大持仓价值
    max_loss_percent: float = 2.0                     # 最大亏损百分比(%)
    max_drawdown_percent: float = 10.0                 # 最大回撤百分比(%)
    risk_reward_ratio: float = 1.5                      # 风险回报比

    # 交易频率控制
    max_trades_per_day: int = 10                       # 每日最大交易次数
    max_concurrent_trades: int = 5                      # 最大并发交易数
    min_trade_interval: int = 60                         # 最小交易间隔(秒)

    # 止损止盈配置
    stop_loss_percent: float = 1.0                       # 止损百分比(%)
    take_profit_percent: float = 2.0                     # 止盈百分比(%)
    trailing_stop_percent: Optional[float] = None        # 追踪止损百分比(%)
    trailing_stop_activation_percent: float = 1.0        # 追踪止损激活百分比

    # 单个交易风险控制
    max_position_size_per_trade: float = 1000.0          # 单笔交易最大持仓价值
    max_leverage: float = 1.0                           # 最大杠杆倍数
    max_position_percent_per_trade: float = 0.1         # 单个交易最大比例
    min_position_size: float = 0.001                     # 最小持仓大小

    # 策略风险控制
    enable_position_limits: bool = True                  # 是否启用仓位限制
    enable_drawdown_control: bool = True                 # 是否启用回撤控制
    enable_frequency_control: bool = True                # 是否启用频率控制
    enable_correlation_control: bool = False           # 是否启用相关性控制
    enable_volatility_adjustment: bool = False         # 是否启用波动率调整

    # 高级风险控制
    max_portfolio_heat: float = 0.8                      # 最大组合热度
    max_sector_exposure: float = 0.5                     # 最大行业敞口
    max_single_symbol_exposure: float = 0.3               # 单个标的最大敞口
    max_correlation_threshold: float = 0.7                 # 最大相关性阈值
    volatility_threshold: float = 0.5                      # 波动率阈值

    # 紧急控制
    emergency_stop_enabled: bool = True                   # 是否启用紧急停止
    emergency_stop_loss_percent: float = 15.0             # 紧急停止亏损百分比
    auto_reduce_position: bool = False                   # 是否自动减仓
    max_consecutive_losses: int = 5                       # 最大连续亏损次数

    # 监控设置
    risk_update_interval: int = 60                        # 风险更新间隔(秒)
    alert_thresholds: Dict[str, float] = field(default_factory=dict)  # 告警阈值

    def __post_init__(self):
        """初始化后处理"""
        # 设置默认告警阈值
        default_alerts = {
            'max_drawdown_warning': 8.0,      # 最大回撤警告
            'daily_loss_warning': 1.5,       # 日亏损警告
            'consecutive_loss_warning': 3,   # 连续亏损警告
            'leverage_warning': 5.0,          # 杠杆警告
            'position_value_warning': 8000.0  # 持仓价值警告
        }

        for key, value in default_alerts.items():
            if key not in self.alert_thresholds:
                self.alert_thresholds[key] = value

    def validate(self) -> List[str]:
        """验证配置的有效性"""
        errors = []

        if self.max_position_value <= 0:
            errors.append("max_position_value must be positive")

        if self.max_loss_percent <= 0 or self.max_loss_percent > 100:
            errors.append("max_loss_percent must be between 0 and 100")

        if self.max_drawdown_percent <= 0 or self.max_drawdown_percent > 100:
            errors.append("max_drawdown_percent must be between 0 and 100")

        if self.risk_reward_ratio <= 0:
            errors.append("risk_reward_ratio must be positive")

        if self.max_trades_per_day <= 0:
            errors.append("max_trades_per_day must be positive")

        if self.max_concurrent_trades <= 0:
            errors.append("max_concurrent_trades must be positive")

        if self.max_leverage < 1:
            errors.append("max_leverage must be at least 1")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'max_position_value': self.max_position_value,
            'max_loss_percent': self.max_loss_percent,
            'max_drawdown_percent': self.max_drawdown_percent,
            'risk_reward_ratio': self.risk_reward_ratio,
            'max_trades_per_day': self.max_trades_per_day,
            'max_concurrent_trades': self.max_concurrent_trades,
            'min_trade_interval': self.min_trade_interval,
            'stop_loss_percent': self.stop_loss_percent,
            'take_profit_percent': self.take_profit_percent,
            'trailing_stop_percent': self.trailing_stop_percent,
            'trailing_stop_activation_percent': self.trailing_stop_activation_percent,
            'max_position_size_per_trade': self.max_position_size_per_trade,
            'max_leverage': self.max_leverage,
            'max_position_percent_per_trade': self.max_position_percent_per_trade,
            'min_position_size': self.min_position_size,
            'enable_position_limits': self.enable_position_limits,
            'enable_drawdown_control': self.enable_drawdown_control,
            'enable_frequency_control': self.enable_frequency_control,
            'enable_correlation_control': self.enable_correlation_control,
            'enable_volatility_adjustment': self.enable_volatility_adjustment,
            'max_portfolio_heat': self.max_portfolio_heat,
            'max_sector_exposure': self.max_sector_exposure,
            'max_single_symbol_exposure': self.max_single_symbol_exposure,
            'max_correlation_threshold': self.max_correlation_threshold,
            'volatility_threshold': self.volatility_threshold,
            'emergency_stop_enabled': self.emergency_stop_enabled,
            'emergency_stop_loss_percent': self.emergency_stop_loss_percent,
            'auto_reduce_position': self.auto_reduce_position,
            'max_consecutive_losses': self.max_consecutive_losses,
            'risk_update_interval': self.risk_update_interval,
            'alert_thresholds': self.alert_thresholds
        }


# 便利函数
def create_conservative_config() -> RiskConfig:
    """创建保守型风险配置"""
    return RiskConfig(
        max_loss_percent=1.0,
        max_drawdown_percent=5.0,
        stop_loss_percent=0.5,
        max_leverage=2.0,
        max_trades_per_day=5,
        emergency_stop_loss_percent=10.0
    )


def create_aggressive_config() -> RiskConfig:
    """创建激进型风险配置"""
    return RiskConfig(
        max_loss_percent=5.0,
        max_drawdown_percent=20.0,
        stop_loss_percent=2.0,
        max_leverage=10.0,
        max_trades_per_day=50,
        emergency_stop_loss_percent=25.0
    )


@dataclass
class Risk:
    """
    通用风险数据类

    为测试和一般用途提供的统一风险数据结构。
    """
    level: RiskLevel = RiskLevel.LOW
    metrics: RiskMetrics = field(default_factory=RiskMetrics)
    config: RiskConfig = field(default_factory=RiskConfig)
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def is_high_risk(self) -> bool:
        """判断是否为高风险"""
        return self.level in [RiskLevel.HIGH, RiskLevel.EXTREME, RiskLevel.CRITICAL]

    def get_risk_score(self) -> float:
        """获取风险分数 (0-1)"""
        risk_scores = {
            RiskLevel.LOW: 0.2,
            RiskLevel.MEDIUM: 0.4,
            RiskLevel.HIGH: 0.7,
            RiskLevel.EXTREME: 0.9,
            RiskLevel.CRITICAL: 1.0
        }
        return risk_scores.get(self.level, 0.5)