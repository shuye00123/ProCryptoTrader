"""
突破信号数据模型 - 高频突破策略

定义了突破检测算法生成的信号数据结构，包含信号类型、强度、
相关指标等完整信息，为后续的策略决策提供数据支持。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import json


class SignalType(Enum):
    """突破信号类型"""
    PRICE_BREAKOUT = "price_breakout"          # 价格突破
    VOLUME_SURGE = "volume_surge"              # 成交量激增
    VOLATILITY_EXPANSION = "volatility_expansion"  # 波动率放大
    COMBINED_BREAKOUT = "combined_breakout"    # 综合突破信号


class SignalStrength(Enum):
    """信号强度等级"""
    WEAK = "weak"           # 弱信号 (0.3 - 0.5)
    MODERATE = "moderate"   # 中等信号 (0.5 - 0.7)
    STRONG = "strong"       # 强信号 (0.7 - 0.9)
    EXTREME = "extreme"     # 极强信号 (0.9 - 1.0)


class TradingDirection(Enum):
    """交易方向"""
    LONG = "long"       # 做多
    SHORT = "short"     # 做空
    NEUTRAL = "neutral" # 中性


@dataclass
class TechnicalIndicators:
    """技术指标数据"""
    # 价格指标
    current_price: float = 0.0
    sma_5m: float = 0.0           # 5分钟移动平均
    sma_15m: float = 0.0          # 15分钟移动平均
    price_position: float = 0.0   # 价格在近期区间的位置

    # 成交量指标
    current_volume: float = 0.0
    volume_sma_10m: float = 0.0   # 10分钟成交量均值
    volume_ratio: float = 1.0     # 当前成交量与均值比率

    # 波动率指标
    current_volatility: float = 0.0
    volatility_ratio: float = 1.0  # 当前波动率与历史均值比率

    # 动量指标
    price_momentum: float = 0.0    # 价格动量
    volume_momentum: float = 0.0   # 成交量动量

    # 支撑阻力位
    resistance_level: float = 0.0  # 阻力位
    support_level: float = 0.0     # 支撑位

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {
            'current_price': self.current_price,
            'sma_5m': self.sma_5m,
            'sma_15m': self.sma_15m,
            'price_position': self.price_position,
            'current_volume': self.current_volume,
            'volume_sma_10m': self.volume_sma_10m,
            'volume_ratio': self.volume_ratio,
            'current_volatility': self.current_volatility,
            'volatility_ratio': self.volatility_ratio,
            'price_momentum': self.price_momentum,
            'volume_momentum': self.volume_momentum,
            'resistance_level': self.resistance_level,
            'support_level': self.support_level
        }


@dataclass
class SignalMetrics:
    """信号质量指标"""
    strength: float = 0.0              # 信号强度 (0-1)
    confidence: float = 0.0            # 信号置信度 (0-1)
    reliability: float = 0.0           # 信号可靠性 (0-1)
    urgency: float = 0.0               # 信号紧急度 (0-1)

    # 历史表现指标
    historical_success_rate: float = 0.0  # 历史成功率
    average_profit: float = 0.0          # 平均利润
    max_loss: float = 0.0                # 最大损失

    # 风险指标
    risk_score: float = 0.0            # 风险评分 (0-1)
    reward_ratio: float = 0.0          # 收益风险比
    max_drawdown: float = 0.0          # 最大回撤

    def get_strength_level(self) -> SignalStrength:
        """获取信号强度等级"""
        if self.strength < 0.3:
            return SignalStrength.WEAK
        elif self.strength < 0.5:
            return SignalStrength.WEAK
        elif self.strength < 0.7:
            return SignalStrength.MODERATE
        elif self.strength < 0.9:
            return SignalStrength.STRONG
        else:
            return SignalStrength.EXTREME

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {
            'strength': self.strength,
            'confidence': self.confidence,
            'reliability': self.reliability,
            'urgency': self.urgency,
            'historical_success_rate': self.historical_success_rate,
            'average_profit': self.average_profit,
            'max_loss': self.max_loss,
            'risk_score': self.risk_score,
            'reward_ratio': self.reward_ratio,
            'max_drawdown': self.max_drawdown
        }


@dataclass
class BreakoutSignal:
    """突破信号数据结构

    包含突破检测算法生成的所有相关信息，为交易决策提供完整依据
    """
    symbol: str                           # 交易对符号
    signal_type: SignalType               # 信号类型
    timestamp: datetime                   # 信号生成时间
    direction: TradingDirection           # 交易方向

    # 技术指标
    indicators: TechnicalIndicators = field(default_factory=TechnicalIndicators)

    # 信号质量指标
    metrics: SignalMetrics = field(default_factory=SignalMetrics)

    # 信号描述
    reason: str = ""                      # 信号生成原因
    description: str = ""                 # 信号详细描述

    # 相关数据
    trigger_price: float = 0.0            # 触发价格
    target_price: float = 0.0             # 目标价格
    stop_loss_price: float = 0.0          # 止损价格

    # 时间窗口信息
    detection_window: int = 300          # 检测窗口（秒）
    expected_duration: int = 600          # 预期持续时间（秒）

    # 市场环境
    market_condition: str = "normal"      # 市场状况
    volatility_regime: str = "normal"     # 波动率状态

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        """验证信号有效性"""
        # 基础验证
        if not self.symbol or not self.indicators.current_price > 0:
            return False

        # 强度验证
        if self.metrics.strength < 0.3:  # 最低强度要求
            return False

        # 置信度验证
        if self.metrics.confidence < 0.4:  # 最低置信度要求
            return False

        # 价格合理性验证
        if (self.trigger_price <= 0 or
            self.target_price <= 0 or
            self.stop_loss_price <= 0):
            return False

        return True

    def get_signal_quality_score(self) -> float:
        """计算信号综合质量评分"""
        # 权重配置
        weights = {
            'strength': 0.3,
            'confidence': 0.25,
            'reliability': 0.2,
            'reward_ratio': 0.15,
            'urgency': 0.1
        }

        # 加权计算
        score = (
            self.metrics.strength * weights['strength'] +
            self.metrics.confidence * weights['confidence'] +
            self.metrics.reliability * weights['reliability'] +
            min(self.metrics.reward_ratio, 2.0) / 2.0 * weights['reward_ratio'] +  # 限制在0-2范围
            self.metrics.urgency * weights['urgency']
        )

        return min(score, 1.0)  # 确保不超过1.0

    def get_risk_adjusted_return(self) -> float:
        """计算风险调整后收益预期"""
        if self.metrics.risk_score == 0:
            return 0.0

        # 简单的风险调整收益计算
        expected_return = self.metrics.average_profit if self.metrics.average_profit > 0 else 0.01
        risk_adjusted = expected_return / (self.metrics.risk_score + 0.1)  # 避免除零

        return min(risk_adjusted, 1.0)

    def should_execute(self) -> bool:
        """判断是否应该执行此信号"""
        # 基础有效性检查
        if not self.is_valid():
            return False

        # 质量评分检查
        if self.get_signal_quality_score() < 0.6:
            return False

        # 风险收益比检查
        if self.get_risk_adjusted_return() < 0.5:
            return False

        # 紧急度检查
        if self.metrics.urgency < 0.3:
            return False

        return True

    def calculate_position_size(self, available_balance: float, risk_per_trade: float = 0.02) -> float:
        """计算建议仓位大小"""
        if not self.should_execute():
            return 0.0

        # 基于信号质量调整仓位大小
        quality_multiplier = self.get_signal_quality_score()
        risk_adjusted_size = available_balance * risk_per_trade * quality_multiplier

        # 基于风险调整
        if self.metrics.risk_score > 0.7:  # 高风险信号
            risk_adjusted_size *= 0.5
        elif self.metrics.risk_score < 0.3:  # 低风险信号
            risk_adjusted_size *= 1.5

        # 确保仓位大小合理
        max_position = available_balance * 0.1  # 最大10%仓位
        position_size = min(risk_adjusted_size, max_position)

        return max(position_size, available_balance * 0.001)  # 最小0.1%仓位

    def update_signal_performance(self, profit_loss: float, duration: int):
        """更新信号表现统计

        Args:
            profit_loss: 实际盈亏
            duration: 交易持续时间（秒）
        """
        # 更新历史表现指标
        if profit_loss > 0:
            self.metrics.historical_success_rate = (
                self.metrics.historical_success_rate * 0.9 + 0.1  # 简单的移动平均
            )

        # 更新平均利润
        self.metrics.average_profit = (
            self.metrics.average_profit * 0.8 + profit_loss * 0.2
        )

        # 更新最大损失
        if profit_loss < self.metrics.max_loss:
            self.metrics.max_loss = profit_loss

        # 基于表现调整置信度
        if profit_loss > 0:
            self.metrics.confidence = min(self.metrics.confidence * 1.01, 1.0)
        else:
            self.metrics.confidence = max(self.metrics.confidence * 0.99, 0.1)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'timestamp': self.timestamp.isoformat(),
            'direction': self.direction.value,
            'indicators': self.indicators.to_dict(),
            'metrics': self.metrics.to_dict(),
            'reason': self.reason,
            'description': self.description,
            'trigger_price': self.trigger_price,
            'target_price': self.target_price,
            'stop_loss_price': self.stop_loss_price,
            'detection_window': self.detection_window,
            'expected_duration': self.expected_duration,
            'market_condition': self.market_condition,
            'volatility_regime': self.volatility_regime,
            'metadata': self.metadata,
            'tags': self.tags,
            'is_valid': self.is_valid(),
            'quality_score': self.get_signal_quality_score(),
            'risk_adjusted_return': self.get_risk_adjusted_return(),
            'should_execute': self.should_execute()
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BreakoutSignal':
        """从字典创建BreakoutSignal实例"""
        # 转换时间戳
        if isinstance(data.get('timestamp'), str):
            timestamp = datetime.fromisoformat(data['timestamp'])
        else:
            timestamp = datetime.now()

        # 转换枚举类型
        signal_type = SignalType(data['signal_type'])
        direction = TradingDirection(data['direction'])

        # 创建技术指标
        indicators_data = data.get('indicators', {})
        indicators = TechnicalIndicators(**indicators_data)

        # 创建信号指标
        metrics_data = data.get('metrics', {})
        metrics = SignalMetrics(**metrics_data)

        return cls(
            symbol=data['symbol'],
            signal_type=signal_type,
            timestamp=timestamp,
            direction=direction,
            indicators=indicators,
            metrics=metrics,
            reason=data.get('reason', ''),
            description=data.get('description', ''),
            trigger_price=data.get('trigger_price', 0.0),
            target_price=data.get('target_price', 0.0),
            stop_loss_price=data.get('stop_loss_price', 0.0),
            detection_window=data.get('detection_window', 300),
            expected_duration=data.get('expected_duration', 600),
            market_condition=data.get('market_condition', 'normal'),
            volatility_regime=data.get('volatility_regime', 'normal'),
            metadata=data.get('metadata', {}),
            tags=data.get('tags', [])
        )

    def __str__(self) -> str:
        """字符串表示"""
        return (f"BreakoutSignal({self.symbol}, {self.signal_type.value}, "
                f"强度={self.metrics.strength:.2f}, 置信度={self.metrics.confidence:.2f}, "
                f"方向={self.direction.value})")

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"BreakoutSignal(symbol='{self.symbol}', "
                f"signal_type='{self.signal_type.value}', "
                f"direction='{self.direction.value}', "
                f"strength={self.metrics.strength:.3f}, "
                f"confidence={self.metrics.confidence:.3f}, "
                f"trigger_price={self.trigger_price})")


# 便利函数
def create_price_breakout_signal(symbol: str, current_price: float, indicators: TechnicalIndicators,
                               strength: float = 0.7) -> BreakoutSignal:
    """创建价格突破信号的便利函数"""
    metrics = SignalMetrics(
        strength=strength,
        confidence=0.6 + strength * 0.3,  # 基于强度计算置信度
        reliability=0.7,
        urgency=0.8,
        risk_score=0.4
    )

    # 确定突破方向
    if current_price > indicators.sma_5m:
        direction = TradingDirection.LONG
        target_price = current_price * 1.02  # 2%目标
        stop_loss_price = current_price * 0.99  # 1%止损
    else:
        direction = TradingDirection.SHORT
        target_price = current_price * 0.98
        stop_loss_price = current_price * 1.01

    return BreakoutSignal(
        symbol=symbol,
        signal_type=SignalType.PRICE_BREAKOUT,
        timestamp=datetime.now(),
        direction=direction,
        indicators=indicators,
        metrics=metrics,
        reason="价格突破关键技术位",
        description=f"价格{current_price}突破{indicators.sma_5m}移动平均线",
        trigger_price=current_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        tags=['price_breakout', 'technical']
    )


def create_volume_surge_signal(symbol: str, current_price: float, volume_ratio: float,
                             strength: float = 0.6) -> BreakoutSignal:
    """创建成交量激增信号的便利函数"""
    indicators = TechnicalIndicators(
        current_price=current_price,
        volume_ratio=volume_ratio
    )

    metrics = SignalMetrics(
        strength=strength,
        confidence=0.5 + strength * 0.2,
        reliability=0.6,
        urgency=0.9,  # 成交量激增通常紧急度较高
        risk_score=0.5
    )

    # 默认做多，可根据具体情况调整
    direction = TradingDirection.LONG

    return BreakoutSignal(
        symbol=symbol,
        signal_type=SignalType.VOLUME_SURGE,
        timestamp=datetime.now(),
        direction=direction,
        indicators=indicators,
        metrics=metrics,
        reason=f"成交量激增{volume_ratio:.1f}倍",
        description=f"交易量相比历史均值激增{volume_ratio:.1f}倍",
        trigger_price=current_price,
        target_price=current_price * 1.015,
        stop_loss_price=current_price * 0.995,
        tags=['volume_surge', 'momentum']
    )


# 示例使用
if __name__ == "__main__":
    # 创建技术指标
    indicators = TechnicalIndicators(
        current_price=50000.0,
        sma_5m=49500.0,
        sma_15m=49000.0,
        current_volume=1000000,
        volume_sma_10m=500000,
        volume_ratio=2.0
    )

    # 创建突破信号
    signal = create_price_breakout_signal(
        symbol="BTCUSDT",
        current_price=50000.0,
        indicators=indicators,
        strength=0.8
    )

    print(f"创建的突破信号: {signal}")
    print(f"信号有效性: {signal.is_valid()}")
    print(f"质量评分: {signal.get_signal_quality_score():.3f}")
    print(f"建议仓位: {signal.calculate_position_size(10000):.2f} (基于10000余额)")

    # 转换为JSON
    print(f"\nJSON表示:\n{signal.to_json()}")