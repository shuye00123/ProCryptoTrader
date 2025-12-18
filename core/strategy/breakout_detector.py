"""
突破检测器 - 高频突破策略核心算法

实现多维度的突破检测算法，包括价格突破、成交量激增、波动率放大等
检测机制，为高频交易提供准确的信号识别。

核心算法:
1. 价格突破检测 - 基于技术指标和动态阈值
2. 成交量激增检测 - 基于统计异常检测
3. 波动率放大检测 - 基于历史波动率比较
4. 综合信号融合 - 多维度信号加权融合
"""

import asyncio
import logging
import time
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..data.realtime_processor import ProcessedTickerData
from ..models.breakout_signal import (
    BreakoutSignal, SignalType, TradingDirection, TechnicalIndicators,
    SignalMetrics, create_price_breakout_signal, create_volume_surge_signal
)

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class DetectionConfig:
    """检测配置参数"""
    # 检测开关
    enabled: bool = True  # 是否启用检测器

    # 价格突破检测
    price_breakout_period: int = 300        # 价格突破检测窗口（秒）
    price_breakout_threshold: float = 0.02  # 价格突破阈值（2%）
    min_price_change: float = 0.005         # 最小价格变化（0.5%）

    # 成交量激增检测
    volume_surge_window: int = 600          # 成交量检测窗口（秒）
    volume_surge_multiplier: float = 3.0    # 成交量激增倍数
    min_volume_threshold: float = 100000    # 最小成交量阈值

    # 波动率检测
    volatility_window: int = 900            # 波动率检测窗口（秒）
    volatility_threshold: float = 2.0       # 波动率放大倍数
    min_volatility: float = 0.001          # 最小波动率

    # 信号融合
    signal_combination_weights: Dict[str, float] = None
    min_combined_strength: float = 0.6     # 最小综合信号强度
    signal_cooldown_period: int = 60       # 信号冷却期（秒）

    def __post_init__(self):
        """初始化后处理"""
        if self.signal_combination_weights is None:
            self.signal_combination_weights = {
                'price_breakout': 0.4,
                'volume_surge': 0.35,
                'volatility_expansion': 0.25
            }


class BreakoutDetector:
    """突破检测器

    实现多维度突破检测算法，为高频交易策略提供信号支持
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化突破检测器

        Args:
            config: 检测配置参数
        """
        # 过滤只支持的字段
        supported_fields = set(DetectionConfig.__dataclass_fields__.keys())
        filtered_config = {k: v for k, v in (config or {}).items() if k in supported_fields}

        # 记录不支持的配置字段
        unsupported_fields = set((config or {}).keys()) - supported_fields
        if unsupported_fields:
            logger.warning(f"BreakoutDetector不支持以下配置字段，将被忽略: {unsupported_fields}")

        # 配置参数
        self.config = DetectionConfig(**filtered_config)

        # 数据缓存
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1800))  # 30分钟
        self.volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=3600))  # 60分钟
        self.volatility_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1800))

        # 信号历史
        self.signal_history: Dict[str, List[BreakoutSignal]] = defaultdict(list)
        self.last_signal_time: Dict[str, datetime] = {}

        # 检测统计
        self.stats = {
            'total_signals': 0,
            'price_breakout_signals': 0,
            'volume_surge_signals': 0,
            'volatility_expansion_signals': 0,
            'combined_signals': 0,
            'symbols_monitored': 0,
            'detection_time_avg': 0.0,
            'last_detection_time': None
        }

        # 性能监控
        self.detection_times = deque(maxlen=1000)

        logger.info("突破检测器初始化完成")

    async def detect_breakouts(self, processed_data: ProcessedTickerData) -> List[BreakoutSignal]:
        """
        检测突破信号

        Args:
            processed_data: 处理后的Ticker数据

        Returns:
            检测到的突破信号列表
        """
        start_time = time.time()

        # 检查检测器是否启用
        if not self.config.enabled:
            logger.debug(f"突破检测器已禁用，跳过 {processed_data.symbol} 的检测")
            return []

        try:
            # 1. 更新历史数据
            self._update_history_data(processed_data)

            # 2. 分别检测各种类型的突破
            price_signals = await self._detect_price_breakout(processed_data)
            volume_signals = await self._detect_volume_surge(processed_data)
            volatility_signals = await self._detect_volatility_expansion(processed_data)

            # 3. 信号融合
            combined_signals = await self._combine_signals(
                processed_data, price_signals, volume_signals, volatility_signals
            )

            # 4. 信号过滤和验证
            filtered_signals = await self._filter_signals(processed_data.symbol, combined_signals)

            # 5. 更新统计信息
            detection_time = time.time() - start_time
            self._update_stats(detection_time, len(filtered_signals), processed_data.symbol)

            return filtered_signals

        except Exception as e:
            logger.error(f"突破检测失败 {processed_data.symbol}: {e}")
            return []

    def _update_history_data(self, data: ProcessedTickerData):
        """更新历史数据缓存"""
        symbol = data.symbol
        timestamp = data.timestamp.timestamp()

        # 更新价格历史
        self.price_history[symbol].append({
            'price': data.price,
            'timestamp': timestamp,
            'sma_5m': data.sma_5m,
            'sma_15m': data.sma_15m
        })

        # 更新成交量历史
        self.volume_history[symbol].append({
            'volume': data.volume,
            'timestamp': timestamp,
            'volume_sma_10m': data.volume_sma_10m
        })

        # 更新波动率历史
        self.volatility_history[symbol].append({
            'volatility': data.volatility_5m,
            'timestamp': timestamp
        })

    async def _detect_price_breakout(self, data: ProcessedTickerData) -> List[BreakoutSignal]:
        """检测价格突破"""
        signals = []
        symbol = data.symbol
        current_price = data.price

        # 获取历史价格数据
        price_data = list(self.price_history[symbol])
        if len(price_data) < 60:  # 至少需要1分钟数据
            return signals

        # 1. 技术指标突破检测
        # 检查是否突破移动平均线
        if data.sma_5m > 0 and data.sma_15m > 0:
            # 价格突破5分钟均线
            if current_price > data.sma_5m * (1 + self.config.min_price_change):
                strength = self._calculate_breakout_strength(symbol, current_price, data.sma_5m, 'above')
                if strength > 0.5:
                    signal = create_price_breakout_signal(symbol, current_price,
                                                      self._create_indicators(data), strength)
                    signal.reason = "价格突破5分钟移动平均线"
                    signal.direction = TradingDirection.LONG
                    signals.append(signal)

            # 价格跌破5分钟均线
            elif current_price < data.sma_5m * (1 - self.config.min_price_change):
                strength = self._calculate_breakout_strength(symbol, current_price, data.sma_5m, 'below')
                if strength > 0.5:
                    signal = create_price_breakout_signal(symbol, current_price,
                                                      self._create_indicators(data), strength)
                    signal.reason = "价格跌破5分钟移动平均线"
                    signal.direction = TradingDirection.SHORT
                    signals.append(signal)

        # 2. 动态阻力位/支撑位突破检测
        resistance, support = self._calculate_dynamic_levels(symbol, current_price)

        if current_price > resistance * (1 + self.config.min_price_change):
            strength = min((current_price - resistance) / resistance * 10, 1.0)
            signal = create_price_breakout_signal(symbol, current_price,
                                              self._create_indicators(data), strength)
            signal.reason = f"价格突破阻力位 {resistance:.2f}"
            signal.direction = TradingDirection.LONG
            signal.indicators.resistance_level = resistance
            signals.append(signal)

        elif current_price < support * (1 - self.config.min_price_change):
            strength = min((support - current_price) / support * 10, 1.0)
            signal = create_price_breakout_signal(symbol, current_price,
                                              self._create_indicators(data), strength)
            signal.reason = f"价格跌破支撑位 {support:.2f}"
            signal.direction = TradingDirection.SHORT
            signal.indicators.support_level = support
            signals.append(signal)

        return signals

    async def _detect_volume_surge(self, data: ProcessedTickerData) -> List[BreakoutSignal]:
        """检测成交量激增"""
        signals = []
        symbol = data.symbol
        current_volume = data.volume

        # 检查最小成交量阈值
        if current_volume < self.config.min_volume_threshold:
            return signals

        # 计算成交量比率
        volume_ratio = data.volume_surge_ratio if data.volume_surge_ratio > 1 else 1.0

        # 成交量激增检测
        if volume_ratio >= self.config.volume_surge_multiplier:
            strength = min((volume_ratio - self.config.volume_surge_multiplier) /
                          self.config.volume_surge_multiplier, 1.0)

            # 确定交易方向（通常基于价格动量）
            price_momentum = self._calculate_price_momentum(symbol, data.price)
            direction = TradingDirection.LONG if price_momentum > 0 else TradingDirection.SHORT

            signal = create_volume_surge_signal(symbol, data.price, volume_ratio, strength)
            signal.direction = direction
            signal.reason = f"成交量激增 {volume_ratio:.1f} 倍"

            # 根据价格动量调整目标价格
            if direction == TradingDirection.LONG:
                signal.target_price = data.price * (1 + 0.01 * strength)
                signal.stop_loss_price = data.price * (1 - 0.008 * strength)
            else:
                signal.target_price = data.price * (1 - 0.01 * strength)
                signal.stop_loss_price = data.price * (1 + 0.008 * strength)

            signals.append(signal)

        return signals

    async def _detect_volatility_expansion(self, data: ProcessedTickerData) -> List[BreakoutSignal]:
        """检测波动率放大"""
        signals = []
        symbol = data.symbol
        current_volatility = data.volatility_5m

        # 检查最小波动率阈值
        if current_volatility < self.config.min_volatility:
            return signals

        # 计算波动率比率
        volatility_ratio = data.volatility_ratio if data.volatility_ratio > 1 else 1.0

        # 波动率放大检测
        if volatility_ratio >= self.config.volatility_threshold:
            strength = min((volatility_ratio - self.config.volatility_threshold) /
                          self.config.volatility_threshold, 1.0)

            # 波动率放大通常意味着趋势可能开始或加速
            # 需要结合价格动量判断方向
            price_momentum = self._calculate_price_momentum(symbol, data.price)
            direction = TradingDirection.LONG if price_momentum > 0 else TradingDirection.SHORT

            indicators = self._create_indicators(data)
            metrics = SignalMetrics(
                strength=strength,
                confidence=0.5 + strength * 0.2,
                reliability=0.6,
                urgency=0.7,
                risk_score=0.6 + strength * 0.2  # 波动率放大风险较高
            )

            signal = BreakoutSignal(
                symbol=symbol,
                signal_type=SignalType.VOLATILITY_EXPANSION,
                timestamp=datetime.now(),
                direction=direction,
                indicators=indicators,
                metrics=metrics,
                reason=f"波动率放大 {volatility_ratio:.1f} 倍",
                description=f"当前波动率相比历史均值放大{volatility_ratio:.1f}倍",
                trigger_price=data.price,
                target_price=data.price * (1 + 0.015 * strength) if direction == TradingDirection.LONG
                           else data.price * (1 - 0.015 * strength),
                stop_loss_price=data.price * (1 - 0.01 * strength) if direction == TradingDirection.LONG
                              else data.price * (1 + 0.01 * strength),
                tags=['volatility_expansion', 'trend']
            )

            signals.append(signal)

        return signals

    async def _combine_signals(self, data: ProcessedTickerData,
                             price_signals: List[BreakoutSignal],
                             volume_signals: List[BreakoutSignal],
                             volatility_signals: List[BreakoutSignal]) -> List[BreakoutSignal]:
        """融合多种信号"""
        all_signals = price_signals + volume_signals + volatility_signals

        # 如果没有信号或只有一个信号，直接返回
        if len(all_signals) <= 1:
            return all_signals

        # 多信号融合逻辑
        combined_signals = []

        # 1. 按方向分组
        long_signals = [s for s in all_signals if s.direction == TradingDirection.LONG]
        short_signals = [s for s in all_signals if s.direction == TradingDirection.SHORT]

        # 2. 为每个方向创建综合信号
        for direction, signals in [(TradingDirection.LONG, long_signals),
                                  (TradingDirection.SHORT, short_signals)]:
            if len(signals) >= 2:  # 至少两个同向信号才融合
                combined_signal = self._create_combined_signal(data, signals, direction)
                if combined_signal:
                    combined_signals.append(combined_signal)
            else:
                # 单一信号直接保留
                combined_signals.extend(signals)

        return combined_signals

    def _create_combined_signal(self, data: ProcessedTickerData,
                              signals: List[BreakoutSignal],
                              direction: TradingDirection) -> Optional[BreakoutSignal]:
        """创建综合突破信号"""
        if not signals:
            return None

        # 计算加权强度
        total_strength = 0.0
        total_weight = 0.0
        signal_types = []

        for signal in signals:
            weight = self.config.signal_combination_weights.get(
                signal.signal_type.value, 0.33)
            total_strength += signal.metrics.strength * weight
            total_weight += weight
            signal_types.append(signal.signal_type.value)

        # 归一化强度
        combined_strength = total_strength / total_weight if total_weight > 0 else 0

        # 检查最小强度要求
        if combined_strength < self.config.min_combined_strength:
            return None

        # 创建综合指标
        indicators = self._create_indicators(data)

        # 创建综合信号指标
        metrics = SignalMetrics(
            strength=combined_strength,
            confidence=np.mean([s.metrics.confidence for s in signals]),
            reliability=np.mean([s.metrics.reliability for s in signals]),
            urgency=max([s.metrics.urgency for s in signals]),  # 取最高紧急度
            risk_score=np.mean([s.metrics.risk_score for s in signals])
        )

        # 计算综合目标价格和止损价格
        target_prices = [s.target_price for s in signals if s.target_price > 0]
        stop_losses = [s.stop_loss_price for s in signals if s.stop_loss_price > 0]

        target_price = np.mean(target_prices) if target_prices else data.price * 1.02
        stop_loss_price = np.mean(stop_losses) if stop_losses else data.price * 0.99

        combined_signal = BreakoutSignal(
            symbol=data.symbol,
            signal_type=SignalType.COMBINED_BREAKOUT,
            timestamp=datetime.now(),
            direction=direction,
            indicators=indicators,
            metrics=metrics,
            reason=f"综合突破信号: {', '.join(signal_types)}",
            description=f"融合{len(signals)}个突破信号: {', '.join(signal_types)}",
            trigger_price=data.price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            tags=['combined', 'multi_signal'] + signal_types,
            metadata={
                'original_signals': len(signals),
                'signal_types': signal_types,
                'component_strengths': [s.metrics.strength for s in signals]
            }
        )

        return combined_signal

    async def _filter_signals(self, symbol: str, signals: List[BreakoutSignal]) -> List[BreakoutSignal]:
        """过滤信号"""
        filtered_signals = []

        for signal in signals:
            # 1. 信号有效性检查
            if not signal.is_valid():
                continue

            # 2. 冷却期检查
            if not self._check_cooldown_period(symbol):
                logger.debug(f"信号冷却期，跳过 {symbol} 的信号")
                continue

            # 3. 信号质量检查
            if signal.get_signal_quality_score() < 0.5:
                continue

            # 4. 重复信号检查
            if self._is_duplicate_signal(symbol, signal):
                continue

            filtered_signals.append(signal)

        # 5. 信号优先级排序
        filtered_signals.sort(key=lambda s: s.get_signal_quality_score(), reverse=True)

        # 6. 记录信号
        if filtered_signals:
            self._record_signals(symbol, filtered_signals)

        return filtered_signals

    def _check_cooldown_period(self, symbol: str) -> bool:
        """检查信号冷却期"""
        last_time = self.last_signal_time.get(symbol)
        if not last_time:
            return True

        time_diff = (datetime.now() - last_time).total_seconds()
        return time_diff >= self.config.signal_cooldown_period

    def _is_duplicate_signal(self, symbol: str, signal: BreakoutSignal) -> bool:
        """检查是否为重复信号"""
        recent_signals = self.signal_history.get(symbol, [])
        current_time = datetime.now()

        # 检查最近60秒内的信号
        for recent_signal in recent_signals:
            if ((current_time - recent_signal.timestamp).total_seconds() < 60 and
                recent_signal.signal_type == signal.signal_type and
                abs(recent_signal.trigger_price - signal.trigger_price) / signal.trigger_price < 0.01):
                return True

        return False

    def _record_signals(self, symbol: str, signals: List[BreakoutSignal]):
        """记录信号"""
        self.signal_history[symbol].extend(signals)
        self.last_signal_time[symbol] = datetime.now()

        # 限制信号历史长度
        if len(self.signal_history[symbol]) > 100:
            self.signal_history[symbol] = self.signal_history[symbol][-50:]

    def _calculate_breakout_strength(self, symbol: str, current_price: float,
                                   reference_price: float, direction: str) -> float:
        """计算突破强度"""
        if direction == 'above':
            strength = (current_price - reference_price) / reference_price
        else:
            strength = (reference_price - current_price) / reference_price

        # 结合价格动量
        momentum = self._calculate_price_momentum(symbol, current_price)
        adjusted_strength = strength * (1 + abs(momentum))

        return min(adjusted_strength, 1.0)

    def _calculate_price_momentum(self, symbol: str, current_price: float) -> float:
        """计算价格动量"""
        price_data = list(self.price_history[symbol])
        if len(price_data) < 30:  # 至少需要30个数据点
            return 0.0

        recent_prices = [item['price'] for item in price_data[-30:]]
        price_changes = np.diff(recent_prices)

        # 计算动量（简单平均变化率）
        momentum = np.mean(price_changes) / current_price if current_price > 0 else 0.0

        return momentum

    def _calculate_dynamic_levels(self, symbol: str, current_price: float) -> Tuple[float, float]:
        """计算动态阻力位和支撑位"""
        price_data = list(self.price_history[symbol])
        if len(price_data) < 60:
            # 数据不足时使用当前价格的百分比
            return current_price * 1.02, current_price * 0.98

        recent_prices = [item['price'] for item in price_data[-300:]]  # 5分钟数据

        # 计算阻力位（近期高点的平均值）
        highs = []
        for i in range(1, len(recent_prices) - 1):
            if recent_prices[i] > recent_prices[i-1] and recent_prices[i] > recent_prices[i+1]:
                highs.append(recent_prices[i])

        resistance = np.mean(highs) if highs else max(recent_prices)

        # 计算支撑位（近期低点的平均值）
        lows = []
        for i in range(1, len(recent_prices) - 1):
            if recent_prices[i] < recent_prices[i-1] and recent_prices[i] < recent_prices[i+1]:
                lows.append(recent_prices[i])

        support = np.mean(lows) if lows else min(recent_prices)

        return resistance, support

    def _create_indicators(self, data: ProcessedTickerData) -> TechnicalIndicators:
        """从处理后的数据创建技术指标"""
        return TechnicalIndicators(
            current_price=data.price,
            sma_5m=data.sma_5m,
            sma_15m=data.sma_15m,
            price_position=data.price_breakout_strength,
            current_volume=data.volume,
            volume_sma_10m=data.volume_sma_10m,
            volume_ratio=data.volume_surge_ratio,
            current_volatility=data.volatility_5m,
            volatility_ratio=data.volatility_ratio,
            price_momentum=0.0,  # 需要单独计算
            volume_momentum=0.0,  # 需要单独计算
            resistance_level=0.0,  # 需要单独计算
            support_level=0.0      # 需要单独计算
        )

    def _update_stats(self, detection_time: float, signal_count: int, symbol: str):
        """更新检测统计信息"""
        self.detection_times.append(detection_time)
        self.stats['detection_time_avg'] = np.mean(list(self.detection_times))
        self.stats['last_detection_time'] = datetime.now()
        self.stats['total_signals'] += signal_count
        self.stats['symbols_monitored'] = len(self.price_history)

    def get_signal_history(self, symbol: str, limit: Optional[int] = None) -> List[BreakoutSignal]:
        """获取信号历史"""
        history = self.signal_history.get(symbol, [])
        if limit:
            return history[-limit:]
        return history

    def get_detection_stats(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        stats = self.stats.copy()

        # 添加详细的统计信息
        if self.detection_times:
            stats['detection_time_max'] = max(self.detection_times)
            stats['detection_time_min'] = min(self.detection_times)
            stats['detection_time_p95'] = np.percentile(list(self.detection_times), 95)

        # 信号类型统计
        total_signals = stats['total_signals']
        if total_signals > 0:
            stats['price_breakout_ratio'] = stats['price_breakout_signals'] / total_signals
            stats['volume_surge_ratio'] = stats['volume_surge_signals'] / total_signals
            stats['volatility_expansion_ratio'] = stats['volatility_expansion_signals'] / total_signals
            stats['combined_signal_ratio'] = stats['combined_signals'] / total_signals

        return stats

    def clear_signal_history(self, symbol: Optional[str] = None):
        """清理信号历史"""
        if symbol:
            self.signal_history.pop(symbol, None)
            self.last_signal_time.pop(symbol, None)
            logger.info(f"已清理 {symbol} 的信号历史")
        else:
            self.signal_history.clear()
            self.last_signal_time.clear()
            logger.info("已清理所有信号历史")

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_signals': 0,
            'price_breakout_signals': 0,
            'volume_surge_signals': 0,
            'volatility_expansion_signals': 0,
            'combined_signals': 0,
            'symbols_monitored': 0,
            'detection_time_avg': 0.0,
            'last_detection_time': None
        }
        self.detection_times.clear()
        logger.info("统计信息已重置")


# 示例使用
async def example_usage():
    """示例用法"""
    from ..data.realtime_processor import ProcessedTickerData

    # 创建突破检测器
    detector = BreakoutDetector()

    # 模拟处理后的数据
    processed_data = ProcessedTickerData(
        symbol="BTCUSDT",
        timestamp=datetime.now(),
        price=50000.0,
        volume=1000000,
        price_change=1000.0,
        price_change_pct=2.0,
        sma_5m=49500.0,
        sma_15m=49000.0,
        volume_sma_10m=500000,
        volatility_5m=0.02,
        price_breakout_strength=0.8,
        volume_surge_ratio=2.0,
        volatility_ratio=2.5,
        data_quality_score=0.95,
        anomaly_detected=False
    )

    # 检测突破信号
    signals = await detector.detect_breakouts(processed_data)

    print(f"检测到 {len(signals)} 个突破信号:")
    for i, signal in enumerate(signals, 1):
        print(f"\n信号 {i}:")
        print(f"  类型: {signal.signal_type.value}")
        print(f"  方向: {signal.direction.value}")
        print(f"  强度: {signal.metrics.strength:.3f}")
        print(f"  原因: {signal.reason}")
        print(f"  质量评分: {signal.get_signal_quality_score():.3f}")

    # 打印检测统计
    stats = detector.get_detection_stats()
    print(f"\n检测统计: {stats}")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    asyncio.run(example_usage())