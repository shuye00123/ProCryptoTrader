"""
基于Tick数据的直接突破检测器
避免OHLCV聚合，直接在tick级别进行突破分析
"""

import collections
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging
import asyncio

from core.models.signal import Signal
from core.strategy.base_strategy import SignalType
from core.utils.webhook_util import WebhookUtil, WebhookConfig, WebhookPlatform, get_webhook, FEISHU_WEBHOOK_CONFIG


@dataclass
class TickData:
    """标准化Tick数据结构"""
    price: float
    volume: float
    timestamp: float
    side: Optional[str] = None  # buy/sell
    bid: Optional[float] = None
    ask: Optional[float] = None
    price_change: float = 0.0

    # 🔥 新增Binance关键字段映射
    last_quantity: Optional[float] = None    # Q字段: 最新交易数量
    vwap_24h: Optional[float] = None         # w字段: 24小时加权平均价
    trade_count_24h: Optional[int] = None     # n字段: 24小时交易次数
    price_change_percent: Optional[float] = None  # P字段: 价格变动百分比
    quote_volume: Optional[float] = None      # q字段: 24小时成交额


@dataclass
class DirectionScore:
    """方向评分结果"""
    buy_strength: float = 0.0      # 买入强度 [0,1]
    sell_strength: float = 0.0     # 卖出强度 [0,1]
    confidence: float = 0.0        # 总体置信度 [0,1]
    direction_bias: float = 0.0    # 方向偏向 [-1,1] (-1=强卖, +1=强买)
    algorithm: str = ""            # 算法名称
    metadata: Dict[str, Any] = None # 附加信息

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DirectionConsensus:
    """方向共识结果"""
    direction: str                 # 最终方向: BUY/SELL/HOLD
    consensus_score: float         # 共识强度 [0,1]
    confidence: float             # 整体置信度 [0,1]
    buy_algorithms: List[str]      # 支持买入的算法
    sell_algorithms: List[str]     # 支持卖出的算法
    conflicting_count: int         # 冲突算法数量
    penalty_factor: float          # 冲突惩罚系数

    def __post_init__(self):
        if self.buy_algorithms is None:
            self.buy_algorithms = []
        if self.sell_algorithms is None:
            self.sell_algorithms = []


class DirectionCoordinator:
    """方向协调和共识管理器"""

    def __init__(self, config: Dict):
        # 算法权重（完全可配置）
        self.algo_weights = config.get('algorithm_weights', {
            'STATISTICAL': 0.2,
            'MOMENTUM': 0.25,
            'CONSECUTIVE': 0.2,
            'VOLUME': 0.15,
            'PATH': 0.2
        })

        self.min_consensus_score = config.get('min_consensus_score', 0.6)
        self.conflict_penalty = config.get('conflict_penalty', 0.3)
        self.max_conflicting_algos = config.get('max_conflicting_algos', 2)
        self.min_confidence_threshold = config.get('min_confidence_threshold', 0.3)
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    def calculate_consensus(self, direction_scores: List[DirectionScore]) -> DirectionConsensus:
        """计算方向共识"""
        if not direction_scores:
            return DirectionConsensus(
                direction="HOLD",
                consensus_score=0.0,
                confidence=0.0,
                buy_algorithms=[],
                sell_algorithms=[],
                conflicting_count=0,
                penalty_factor=1.0
            )

        # 过滤低置信度信号
        valid_scores = [score for score in direction_scores if score.confidence >= self.min_confidence_threshold]

        if not valid_scores:
            self.logger.debug(f"[DEBUG] 所有信号置信度过低，跳过共识计算")
            return DirectionConsensus(
                direction="HOLD",
                consensus_score=0.0,
                confidence=0.0,
                buy_algorithms=[],
                sell_algorithms=[],
                conflicting_count=0,
                penalty_factor=1.0
            )

        # 加权计算买卖强度
        total_buy_weight = 0.0
        total_sell_weight = 0.0
        total_confidence = 0.0

        buy_algorithms = []
        sell_algorithms = []

        for score in valid_scores:
            weight = self.algo_weights.get(score.algorithm, 0.2)
            total_buy_weight += score.buy_strength * weight
            total_sell_weight += score.sell_strength * weight
            total_confidence += score.confidence * weight

            if score.buy_strength > score.sell_strength:
                buy_algorithms.append(score.algorithm)
            elif score.sell_strength > score.buy_strength:
                sell_algorithms.append(score.algorithm)

        # 计算共识强度
        weight_sum = sum(self.algo_weights.values())
        consensus_score = abs(total_buy_weight - total_sell_weight) / weight_sum

        # 冲突检测
        conflicting_count = min(len(buy_algorithms), len(sell_algorithms))

        # 应用冲突惩罚
        penalty_factor = 1.0
        if conflicting_count > self.max_conflicting_algos:
            penalty_factor = 1.0 - (self.conflict_penalty * conflicting_count / 5)

        # 最终共识
        final_consensus = consensus_score * penalty_factor

        # 确定方向
        if final_consensus >= self.min_consensus_score:
            if total_buy_weight > total_sell_weight:
                direction = "BUY"
            else:
                direction = "SELL"
        else:
            direction = "HOLD"  # 降低信号强度但不拒绝

        self.logger.debug(f"[DEBUG] 方向共识计算结果: {direction}, "
                        f"共识强度={final_consensus:.3f}, "
                        f"买入算法={buy_algorithms}, "
                        f"卖出算法={sell_algorithms}, "
                        f"冲突数={conflicting_count}")

        return DirectionConsensus(
            direction=direction,
            consensus_score=final_consensus,
            confidence=total_confidence / len(valid_scores),
            buy_algorithms=buy_algorithms,
            sell_algorithms=sell_algorithms,
            conflicting_count=conflicting_count,
            penalty_factor=penalty_factor
        )


class RealTimeQualityScorer:
    """
    实时信号质量评分器
    在信号生成的毫秒级评估质量，无需等待cluster完成
    """

    def __init__(self, config: Dict):
        """初始化质量评分器

        Args:
            config: 质量评分配置
                - quality_threshold: 质量阈值 (默认0.75)
                - cooldown_seconds: 冷却期秒数 (默认300)
                - weights: 各维度权重字典
        """
        self.quality_threshold = config.get('quality_threshold', 0.75)
        self.cooldown_seconds = config.get('cooldown_seconds', 300)

        # 质量评分权重
        self.weights = config.get('weights', {
            'algo_diversity': 0.20,      # 算法多样性
            'strength_consistency': 0.15, # 强度一致性
            'combined_strength': 0.25,    # 综合强度
            'volume_surge': 0.20,         # 成交量激增
            'price_momentum': 0.20        # 价格动量
        })

        self.last_execution_time = None
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    def calculate_quality_score(self, detection_list: List, tick_data, current_time, symbol: str) -> tuple:
        """
        计算信号质量分数（实时，无需等待cluster）

        Args:
            detection_list: [(algo_name, strength), ...] 检测列表
            tick_data: 当前tick数据
            current_time: 当前时间戳
            symbol: 交易对

        Returns:
            (quality_score, score_breakdown): 质量分数(0-1)和详细分数
        """

        scores = {}
        weights = self.weights

        # === 维度1: 算法多样性 ===
        unique_algos = len(set(d[0] for d in detection_list))
        algo_diversity_score = min(1.0, unique_algos / 5.0)  # 5个算法满分
        scores['algo_diversity'] = algo_diversity_score

        # === 维度2: 强度一致性 ===
        strengths = [d[1] for d in detection_list]
        strength_mean = np.mean(strengths)
        strength_std = np.std(strengths)
        strength_cv = strength_std / strength_mean if strength_mean > 0 else 1.0

        # 低变异系数 = 高一致性
        consistency_score = max(0.0, 1.0 - strength_cv)
        scores['strength_consistency'] = consistency_score

        # === 维度3: 综合强度 ===
        combined_strength = strength_mean
        # 归一化: 2.5是最低要求, 8.0是优秀
        strength_score = min(1.0, max(0.0, (combined_strength - 2.5) / (8.0 - 2.5)))
        scores['combined_strength'] = strength_score

        # === 维度4: 成交量激增 ===
        volume_detection = [d for d in detection_list if 'VOLUME' in d[0]]
        if volume_detection:
            volume_strength = volume_detection[0][1]
            # volume_strength = (volume_ratio + z_score) / 2
            volume_score = min(1.0, max(0.0, (volume_strength - 2.0) / 6.0))
        else:
            volume_score = 0.3  # 无成交量确认的惩罚
        scores['volume_surge'] = volume_score

        # === 维度5: 价格动量 ===
        statistical_detection = [d for d in detection_list if 'STATISTICAL' in d[0]]
        if statistical_detection:
            stat_strength = statistical_detection[0][1]
            # 高Z-score = 强突破
            momentum_score = min(1.0, max(0.0, (stat_strength - 2.5) / 5.0))
        else:
            momentum_score = 0.3  # 无统计确认的惩罚
        scores['price_momentum'] = momentum_score

        # 计算加权平均
        total_score = sum(scores[component] * weights.get(component, 0.2)
                          for component in scores.keys())
        total_weight = sum(weights.values())

        quality_score = total_score / total_weight if total_weight > 0 else 0.0

        score_breakdown = {
            'quality_score': quality_score,
            'algo_diversity': algo_diversity_score,
            'strength_consistency': consistency_score,
            'combined_strength': strength_score,
            'volume_surge': volume_score,
            'price_momentum': momentum_score,
            'unique_algos': unique_algos,
            'avg_strength': combined_strength,
            'strength_cv': strength_cv
        }

        return quality_score, score_breakdown

    def should_execute_signal(self, quality_score: float, current_time) -> tuple:
        """
        判断是否应该执行信号

        Args:
            quality_score: 质量分数
            current_time: 当前时间戳

        Returns:
            (should_execute, reason): (是否执行, 原因)
        """
        # 检查冷却期
        if self.last_execution_time is not None:
            if isinstance(current_time, (int, float)):
                time_since_last = (current_time - self.last_execution_time) / 1000.0
            else:
                time_since_last = (pd.Timestamp(current_time) -
                                   pd.Timestamp(self.last_execution_time)).total_seconds()

            if time_since_last < self.cooldown_seconds:
                remaining = self.cooldown_seconds - time_since_last
                return False, f'cooldown ({remaining:.0f}s remaining)'

        # 检查质量阈值
        if quality_score < self.quality_threshold:
            return False, f'low quality (score={quality_score:.2f} < {self.quality_threshold})'

        return True, f'high quality (score={quality_score:.2f})'

    def record_execution(self, current_time):
        """记录信号执行时间"""
        self.last_execution_time = current_time


# 设置日志
logger = logging.getLogger(__name__)
class TickBreakoutDetector:
    """基于tick数据的直接突破检测器"""

    def __init__(self,
                 window_size: int = 200,
                 min_breakout_strength: float = 2.0,
                 volume_threshold: float = 1.5,
                 consecutive_moves_threshold: int = 5,
                 enable_webhook: bool = True,
                 webhook_config: Optional[WebhookConfig] = None,
                 # 多重确认机制参数
                 require_multiple_confirmation: bool = False,
                 min_confirmation_count: int = 2,
                 confirmation_window: int = 1000,
                 # 冷却期参数
                 breakout_cooldown: int = 5000,  # 默认5秒，单位毫秒
                 # 方向协调机制参数
                 direction_coordination_enabled: bool = False,
                 direction_coordination_config: Optional[Dict] = None,
                 # 🔧 交易规模配置参数
                 trading_config: Optional[Dict] = None,
                 # 🔧 VOLUME算法优化参数
                 volume_config: Optional[Dict] = None,
                 # 🔧 PATH算法优化参数
                 path_config: Optional[Dict] = None,
                 # 🔥 实时质量评分配置参数
                 quality_scoring_enabled: bool = False,
                 quality_scoring_config: Optional[Dict] = None):

        self.window_size = window_size
        self.min_breakout_strength = min_breakout_strength
        self.volume_threshold = volume_threshold
        self.consecutive_moves_threshold = consecutive_moves_threshold

        # 动量检测相关参数
        self.momentum_ratio_threshold = 2.0  # 默认动量比率阈值

        # 🔧 VOLUME算法配置参数 - 使用配置文件或默认值
        volume_config = volume_config or {}
        self.volume_surge_threshold = volume_config.get('volume_surge_threshold', volume_threshold)
        self.volume_min_price_change = volume_config.get('min_price_change', 0.001)
        self.volume_min_avg_volume = volume_config.get('min_avg_volume', 10000)
        self.volume_min_data_points = volume_config.get('min_data_points', 10)

        # 🔧 PATH算法配置参数 - 使用配置文件或默认值
        path_config = path_config or {}
        self.path_breakout_threshold = path_config.get('breakout_threshold', 0.005)
        self.path_support_resistance_window = path_config.get('support_resistance_window', 20)
        self.path_min_data_points = path_config.get('min_data_points', 20)
        self.path_virtual_level_offset = path_config.get('virtual_level_offset', 0.002)

        # 🔧 交易规模配置
        self.trading_config = trading_config or {}
        self.target_trade_value_usdt = self.trading_config.get('target_trade_value_usdt', 100.0)
        self.min_trade_value_usdt = self.trading_config.get('min_trade_value_usdt', 50.0)
        self.max_trade_value_usdt = self.trading_config.get('max_trade_value_usdt', 500.0)
        self.max_total_value_usdt = self.trading_config.get('max_total_value_usdt', 1000.0)
        self.max_daily_value_usdt = self.trading_config.get('max_daily_value_usdt', 2000.0)

        # 多重确认机制参数
        self.require_multiple_confirmation = require_multiple_confirmation
        self.min_confirmation_count = min_confirmation_count
        self.confirmation_window = confirmation_window

        # 冷却期参数
        self.breakout_cooldown = breakout_cooldown

        # 确认窗口内收集的信号 - 每个交易对独立
        self.pending_signals = {}  # {symbol: [signals]}
        self.last_signal_collection_time = {}  # {symbol: timestamp}

        # 数据缓冲区 - 每个交易对独立管理
        self.tick_buffers = {}  # {symbol: deque}
        self.price_histories = {}  # {symbol: deque}
        self.volume_histories = {}  # {symbol: deque}
        self.price_change_histories = {}  # {symbol: deque}

        # 突破状态跟踪 - 每个交易对独立管理
        self.current_trends = {}  # {symbol: trend}  # 1: 上涨, -1: 下跌, 0: 无趋势
        self.consecutive_moves_counts = {}  # {symbol: count}
        # 每个交易对独立管理冷却期
        self.last_breakout_times = {}  # {symbol: last_breakout_time}
        # breakout_cooldown 已在构造函数中设置

        # 首先初始化logger
        self.logger = logging.getLogger(__name__)

        # 🔥 Webhook通知配置
        self.enable_webhook = enable_webhook
        self.webhook_config = webhook_config or FEISHU_WEBHOOK_CONFIG
        self.webhook = get_webhook(self.webhook_config) if enable_webhook else None

        # 🔥 方向协调机制配置
        self.direction_coordination_enabled = direction_coordination_enabled
        if self.direction_coordination_enabled:
            # 使用默认配置或提供自定义配置
            default_direction_config = {
                'algorithm_weights': {
                    'STATISTICAL': 0.2,
                    'MOMENTUM': 0.25,
                    'CONSECUTIVE': 0.2,
                    'VOLUME': 0.15,
                    'PATH': 0.2
                },
                'min_consensus_score': 0.6,
                'conflict_penalty': 0.3,
                'max_conflicting_algos': 2,
                'min_confidence_threshold': 0.3
            }

            final_config = direction_coordination_config or default_direction_config
            self.direction_coordinator = DirectionCoordinator(final_config)
            self.logger.info(f"Direction coordination enabled with config: {final_config}")
        else:
            self.direction_coordinator = None
            self.logger.info("Direction coordination disabled")

        # 🔥 实时质量评分配置
        self.quality_scoring_enabled = quality_scoring_enabled
        if self.quality_scoring_enabled:
            # 使用默认配置或提供自定义配置
            default_quality_config = {
                'quality_threshold': 0.75,
                'cooldown_seconds': 300,
                'weights': {
                    'algo_diversity': 0.20,
                    'strength_consistency': 0.15,
                    'combined_strength': 0.25,
                    'volume_surge': 0.20,
                    'price_momentum': 0.20
                }
            }

            final_quality_config = quality_scoring_config or default_quality_config
            self.quality_scorer = RealTimeQualityScorer(final_quality_config)
            self.logger.info(f"Quality scoring enabled with config: {final_quality_config}")
        else:
            self.quality_scorer = None
            self.logger.info("Quality scoring disabled")

        self.logger.info(f"TickBreakoutDetector initialized with webhook: {enable_webhook}")

    def _get_symbol_buffers(self, symbol: str):
        """获取或创建交易对的数据缓冲区"""
        if symbol not in self.tick_buffers:
            self.tick_buffers[symbol] = collections.deque(maxlen=self.window_size)
            self.price_histories[symbol] = collections.deque(maxlen=self.window_size)
            self.volume_histories[symbol] = collections.deque(maxlen=self.window_size)
            self.price_change_histories[symbol] = collections.deque(maxlen=self.window_size)

        return (
            self.tick_buffers[symbol],
            self.price_histories[symbol],
            self.volume_histories[symbol],
            self.price_change_histories[symbol]
        )

    def process_tick(self, raw_tick: dict, symbol: str = "UNKNOWN") -> Optional[Signal]:
        """处理单个tick数据并检测突破"""

        try:
            # 1. 数据标准化
            tick = self.normalize_tick_data(raw_tick, symbol)
            if not tick:
                self.logger.debug(f"[DEBUG] TICK失败 - {symbol}: 数据标准化失败")
                return None

            # 2. 噪音过滤
            if not self.filter_market_noise(tick, symbol):
                self.logger.debug(f"[DEBUG] TICK过滤 - {symbol}: 市场噪音过滤")
                return None

            # 3. 更新历史数据 (先更新数据再检查充足性)
            self.update_histories(tick, symbol)

            # 4. 数据充足性检查
            _, price_history, _, _ = self._get_symbol_buffers(symbol)
            if len(price_history) < 50:
                self.logger.debug(f"[DEBUG] TICK跳过 - {symbol}: 历史数据不足({len(price_history)}<50)")
                return None

            # 5. 每个交易对独立的冷却期检查
            current_time = tick.timestamp
            last_breakout_time = self.last_breakout_times.get(symbol, 0)
            cooldown_remaining = self.breakout_cooldown - (current_time - last_breakout_time)
            if cooldown_remaining > 0:
                self.logger.debug(f"[DEBUG] TICK跳过 - {symbol}: 冷却期剩余{cooldown_remaining/1000:.1f}秒")
                return None

            # 6. 多维度突破检测
            breakout_signal = self.detect_multi_dimensional_breakout(tick, symbol)

            if breakout_signal:
                self.last_breakout_times[symbol] = current_time  # 更新该交易对的冷却期
                self.logger.info(f"[SIGNAL] Tick突破信号生成: {symbol} - {breakout_signal.reason}")
                self.logger.debug(f"[SIGNAL] 信号详情: 类型={breakout_signal.signal_type}, "
                                 f"价格={breakout_signal.price}, "
                                 f"数量={breakout_signal.amount}, "
                                 f"置信度={breakout_signal.confidence:.2f}")
            else:
                self.logger.debug(f"[DEBUG] TICK完成 - {symbol}: 无突破信号")

            return breakout_signal

        except Exception as e:
            self.logger.error(f"Tick处理错误: {e}")
            return None

    def normalize_tick_data(self, raw_tick: dict, symbol: str) -> Optional[TickData]:
        """标准化tick数据 - 适配已转换的标准格式数据"""
        try:
            # 🔥 重构：处理标准格式数据（high_frequency_breakout.py中转换后的格式）
            # 实际传入的数据只有4个字段：price, volume, timestamp, side
            if 'price' in raw_tick:  # 标准格式（实际传入的数据格式）
                price = float(raw_tick['price'])
                volume = float(raw_tick.get('volume', 0))
                raw_timestamp = raw_tick.get('timestamp', datetime.now().timestamp() * 1000)

                # 🔥 计算24小时价格变化（基于历史数据）
                price_change = 0.0
                _, price_history, _, _ = self._get_symbol_buffers(symbol)
                if len(price_history) > 0:
                    price_change = price - price_history[-1]

            elif 'c' in raw_tick:  # Binance 24hr Ticker原始格式（用于测试）
                # 从Binance官方文档正确映射字段
                price = float(raw_tick['c'])           # c: 最新成交价格
                volume = float(raw_tick['v'])         # v: 24小时成交量
                raw_timestamp = raw_tick.get('E', datetime.now().timestamp() * 1000)  # E: 事件时间
                # 直接从'p'字段获取24小时价格变化
                price_change = float(raw_tick.get('p', '0'))  # p: 24小时价格变化
            else:
                return None

            # 🔥 修复时间戳单位验证和转换
            timestamp = self._validate_and_normalize_timestamp(raw_timestamp)

            # 🔥 重构：根据数据来源映射不同的字段
            if 'c' in raw_tick:  # Binance原始数据 - 包含所有Binance字段
                return TickData(
                    price=price,                                    # c字段: 最新成交价格
                    volume=volume,                                  # v字段: 24小时成交量
                    timestamp=timestamp,                            # E字段: 事件时间
                    side=raw_tick.get('side'),
                    bid=raw_tick.get('bid'),
                    ask=raw_tick.get('ask'),
                    price_change=price_change,                        # p字段: 24小时价格变化

                    # Binance关键字段映射
                    last_quantity=self._safe_float_convert(raw_tick.get('Q')),      # Q: 最新交易数量
                    vwap_24h=self._safe_float_convert(raw_tick.get('w')),           # w: 24小时加权平均价
                    trade_count_24h=self._safe_int_convert(raw_tick.get('n')),       # n: 24小时交易次数
                    price_change_percent=self._safe_float_convert(raw_tick.get('P')), # P: 价格变动百分比
                    quote_volume=self._safe_float_convert(raw_tick.get('q'))         # q: 24小时成交额
                )
            else:  # 标准格式数据 - 只有基础字段
                return TickData(
                    price=price,                                    # price字段
                    volume=volume,                                  # volume字段
                    timestamp=timestamp,                            # timestamp字段
                    side=raw_tick.get('side'),                       # side字段
                    bid=None,                                       # 标准格式无此字段
                    ask=None,                                       # 标准格式无此字段
                    price_change=price_change,                       # 计算的价格变化

                    # 标准格式下这些字段为None（无Binance扩展字段）
                    last_quantity=None,                              # 无Binance Q字段
                    vwap_24h=None,                                   # 无Binance w字段
                    trade_count_24h=None,                           # 无Binance n字段
                    price_change_percent=None,                        # 无Binance P字段
                    quote_volume=None                                # 无Binance q字段
                )

        except Exception as e:
            self.logger.error(f"Tick数据标准化失败: {e}")
            return None

    def _safe_float_convert(self, value: Any) -> Optional[float]:
        """安全的浮点数转换"""
        try:
            if value is None:
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int_convert(self, value: Any) -> Optional[int]:
        """安全的整数转换"""
        try:
            if value is None:
                return None
            return int(value)
        except (ValueError, TypeError):
            return None

    def _validate_and_normalize_timestamp(self, raw_timestamp: int) -> int:
        """验证并标准化时间戳为毫秒级"""
        try:
            current_time_ms = int(datetime.now().timestamp() * 1000)

            # 检查时间戳类型并转换
            if raw_timestamp < 1e12:  # 秒级时间戳（约332年前的秒数 < 1e12）
                timestamp_ms = raw_timestamp * 1000
                self.logger.debug(f"[TIMESTAMP] 检测到秒级时间戳 {raw_timestamp}，转换为毫秒级 {timestamp_ms}")
            elif raw_timestamp > 1e15:  # 可能是微秒级时间戳
                timestamp_ms = raw_timestamp // 1000
                self.logger.debug(f"[TIMESTAMP] 检测到微秒级时间戳 {raw_timestamp}，转换为毫秒级 {timestamp_ms}")
            else:  # 毫秒级时间戳
                timestamp_ms = raw_timestamp

            # 时间戳合理性验证
            time_diff = abs(timestamp_ms - current_time_ms)
            if time_diff > 24 * 3600 * 1000:  # 超过24小时
                self.logger.warning(f"[TIMESTAMP] 时间戳异常: {timestamp_ms}, 当前时间: {current_time_ms}, 差异: {time_diff/3600/1000:.1f}小时")
                # 使用当前时间作为备选
                self.logger.warning(f"[TIMESTAMP] 使用当前时间替代异常时间戳")
                timestamp_ms = current_time_ms
            elif time_diff > 3600 * 1000:  # 超过1小时
                self.logger.warning(f"[TIMESTAMP] 时间戳差异较大: {time_diff/3600/1000:.1f}小时，原始时间戳: {raw_timestamp}")

            return timestamp_ms

        except Exception as e:
            self.logger.error(f"[TIMESTAMP] 时间戳验证失败: {e}，使用当前时间")
            return int(datetime.now().timestamp() * 1000)

    def filter_market_noise(self, tick: TickData, symbol: str) -> bool:
        """过滤市场微观结构噪音"""

        # 1. 价格合理性检查
        if tick.price <= 0:
            self.logger.debug(f"[DEBUG] TICK过滤 价格合理性检查 - {symbol} {tick.price}: 市场噪音过滤")
            return False

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)

        # 2. 价格变动过小过滤 - 但允许第一个tick通过以初始化历史数据
        if len(price_history) > 0:  # 只有在有历史数据时才检查价格变动
            if abs(tick.price_change) < 0.00001:  # 最小变动价位
                self.logger.debug(f"[DEBUG] TICK过滤 价格变动过小过滤 - {symbol} {tick.price_change}: 市场噪音过滤")
                return False
            # 🔧 修复：允许微小的价格变动以满足数据建立需要
            if abs(tick.price_change) < 0.0001 and len(price_history) < 5:  # 前5个tick更宽松
                self.logger.debug(f"[DEBUG] TICK过滤 初始化阶段 - {symbol} {tick.price_change}: 允许微小变动")
                # 强制通过，允许建立历史数据
                pass

        # 🔧 修复：完全通过前10个tick用于初始化
        if len(price_history) < 10:
            self.logger.debug(f"[DEBUG] TICK过滤 初始化阶段 - {symbol} 第{len(price_history)+1}个tick，强制通过")
            return True

        # 3. 异常成交量过滤
        if tick.volume < 0:
            self.logger.debug(f"[DEBUG] TICK过滤 异常成交量过滤 - {symbol} {tick.volume}: 市场噪音过滤")
            return False

        # 4. 时间戳合理性检查（统一使用毫秒级时间戳）
        current_time_ms = datetime.now().timestamp() * 1000
        if abs(tick.timestamp - current_time_ms) > 60000 * 1000:  # 超过1分钟（注意单位是毫秒）
                        return False

        return True

    def update_histories(self, tick: TickData, symbol: str):
        """更新历史数据"""
        tick_buffer, price_history, volume_history, price_change_history = self._get_symbol_buffers(symbol)

        tick_buffer.append(tick)
        price_history.append(tick.price)

        # 🔥 修复：统一使用last_quantity进行实时成交量检测
        # 使用最新单笔交易量进行历史记录，避免24小时累计值的数量级问题
        volume_history.append(tick.last_quantity if tick.last_quantity is not None else 0.0)  # 最新单笔交易量

        # 🔥 修复：价格变化使用百分比，更标准化
        price_change_history.append(tick.price_change_percent if tick.price_change_percent is not None else 0.0)  # 24小时价格变化百分比

        # 更新趋势跟踪 - 每个交易对独立
        if symbol not in self.current_trends:
            self.current_trends[symbol] = 0
            self.consecutive_moves_counts[symbol] = 0

        if tick.price_change > 0:
            if self.current_trends[symbol] == 1:
                # 同向继续，增加计数
                self.consecutive_moves_counts[symbol] += 1
                self.logger.debug(f"[DEBUG] 连续上涨计数更新 {symbol}: {self.consecutive_moves_counts[symbol]}")
            else:
                # 趋势改变，开始新趋势的第一次计数
                self.current_trends[symbol] = 1
                self.consecutive_moves_counts[symbol] = 1
                self.logger.debug(f"[DEBUG] 趋势改变为上涨 {symbol}: 计数重置为1")
        elif tick.price_change < 0:
            if self.current_trends[symbol] == -1:
                # 同向继续，增加计数
                self.consecutive_moves_counts[symbol] += 1
                self.logger.debug(f"[DEBUG] 连续下跌计数更新 {symbol}: {self.consecutive_moves_counts[symbol]}")
            else:
                # 趋势改变，开始新趋势的第一次计数
                self.current_trends[symbol] = -1
                self.consecutive_moves_counts[symbol] = 1
                self.logger.debug(f"[DEBUG] 趋势改变为下跌 {symbol}: 计数重置为1")
        else:
            # 无变动时，重置趋势和计数
            self.current_trends[symbol] = 0
            self.consecutive_moves_counts[symbol] = 0
            self.logger.debug(f"[DEBUG] 价格无变动 {symbol}: 趋势和计数重置为0")

    def detect_multi_dimensional_breakout(self, tick: TickData, symbol: str = "UNKNOWN") -> Optional[Signal]:
        """多维度突破检测 - 支持多重确认机制和方向协调"""

        current_time = tick.timestamp

        # 🔥 检查是否启用方向协调机制
        if self.direction_coordination_enabled:
            return self._detect_multi_dimensional_breakout_with_direction_coordination(tick, symbol)

        # 如果不需要多重确认，使用原有逻辑
        if not self.require_multiple_confirmation:
            return self._detect_single_breakout(tick, symbol)

        # 多重确认机制
        detections = []

        # [DEBUG] 详细调试输出 - Tick基础信息
        self.logger.debug(f"[DEBUG] TICK检测开始 - {symbol}: "
                         f"价格={tick.price:.2f}, "
                         f"变动={tick.price_change:+.2f}, "
                         f"成交量={tick.volume:.0f}, "
                         f"连续={self.consecutive_moves_counts.get(symbol, 0)}")

        # 收集所有检测算法的结果
        detection_results = []

        # 1. 统计突破检测
        stat_result = self.detect_statistical_breakout(tick, symbol)
        if stat_result:
            strength = self._calculate_detection_strength(tick, "STATISTICAL", symbol)
            detections.append(("STATISTICAL", strength))
            detection_results.append(f"STATISTICAL突破(强度:{strength:.2f})")
        else:
            detection_results.append("STATISTICAL:未触发")

        # 2. 动量突破检测
        momentum_result = self.detect_momentum_breakout(tick, symbol)
        if momentum_result:
            strength = self._calculate_detection_strength(tick, "MOMENTUM", symbol)
            detections.append(("MOMENTUM", strength))
            detection_results.append(f"MOMENTUM突破(强度:{strength:.2f})")
        else:
            detection_results.append("MOMENTUM:未触发")

        # 3. 连续变动突破检测
        consecutive_result = self.detect_consecutive_moves_breakout(tick, symbol)
        if consecutive_result:
            strength = self._calculate_detection_strength(tick, "CONSECUTIVE", symbol)
            detections.append(("CONSECUTIVE", strength))
            detection_results.append(f"CONSECUTIVE突破(强度:{strength:.2f})")
        else:
            detection_results.append("CONSECUTIVE:未触发")

        # 4. 成交量突破检测
        volume_result = self.detect_volume_breakout(tick, symbol)
        if volume_result:
            strength = self._calculate_detection_strength(tick, "VOLUME", symbol)
            detections.append(("VOLUME", strength))
            detection_results.append(f"VOLUME突破(强度:{strength:.2f})")
        else:
            detection_results.append("VOLUME:未触发")

        # 5. 价格路径突破检测
        path_breakout = self.detect_path_breakout(tick, symbol)
        if path_breakout:
            strength = self._calculate_detection_strength(tick, "PATH", symbol)
            detections.append((f"PATH_{path_breakout}", strength))
            detection_results.append(f"PATH突破({path_breakout},强度:{strength:.2f})")
        else:
            detection_results.append("PATH:未触发")

        # [DEBUG] 输出所有检测结果
        self.logger.debug(f"[DEBUG] 总计触发算法: {len(detections)}/{5}, 需要最少确认: {self.min_confirmation_count}")

        # 检查是否满足最小确认数量
        if len(detections) < self.min_confirmation_count:
            return None

        # 清理过期信号 - 每个交易对独立
        self._clean_expired_signals(current_time, symbol)

        # 添加新检测到的信号 - 每个交易对独立
        if symbol not in self.pending_signals:
            self.pending_signals[symbol] = []

        for detection_type, strength in detections:
            logger.debug(f"信号信息: {detection_type},{strength}")
            self.pending_signals[symbol].append({
                'type': detection_type,
                'strength': strength,
                'tick': tick,
                'symbol': symbol,
                'timestamp': current_time
            })

        # 检查确认窗口内的信号数量 - 每个交易对独立
        if len(self.pending_signals[symbol]) >= self.min_confirmation_count:
            # 计算综合强度
            total_strength = sum(d['strength'] for d in self.pending_signals[symbol])
            avg_strength = total_strength / len(self.pending_signals[symbol])

            # 检查最小强度要求
            if avg_strength >= self.min_breakout_strength:
                # 生成最终确认信号 - 每个交易对独立
                combined_types = "+".join([d['type'] for d in self.pending_signals[symbol]])
                self.logger.info(f"[DEBUG] 检测算法结果 - {symbol}: {', '.join(detection_results)}")

                # 🔥 实时质量评分 - 在信号生成时立即评估质量
                if self.quality_scoring_enabled and self.quality_scorer:
                    # 准备检测列表（去重）
                    unique_detections = list(set((d['type'], d['strength']) for d in self.pending_signals[symbol]))

                    # 计算质量分数
                    quality_score, score_breakdown = self.quality_scorer.calculate_quality_score(
                        unique_detections,
                        tick,
                        current_time,
                        symbol
                    )

                    # 判断是否应该执行
                    should_execute, reason = self.quality_scorer.should_execute_signal(
                        quality_score,
                        current_time
                    )

                    self.logger.info(f"[QUALITY] {symbol} - Score: {quality_score:.3f}, "
                                   f"Decision: {should_execute}, Reason: {reason}")

                    # 输出详细分数
                    self.logger.debug(f"[QUALITY] Breakdown - "
                                     f"Diversity: {score_breakdown['algo_diversity']:.2f}, "
                                     f"Consistency: {score_breakdown['strength_consistency']:.2f}, "
                                     f"Strength: {score_breakdown['combined_strength']:.2f}, "
                                     f"Volume: {score_breakdown['volume_surge']:.2f}, "
                                     f"Momentum: {score_breakdown['price_momentum']:.2f}")

                    # 只执行高质量信号
                    if not should_execute:
                        self.logger.info(f"[FILTERED] Signal filtered by quality scoring: {reason}")
                        return None

                    # 记录执行时间（用于冷却期）
                    self.quality_scorer.record_execution(current_time)

                    # 在signal metadata中添加质量评分信息
                    # 通过修改create_breakout_signal的metadata参数
                    quality_metadata = {
                        'quality_score': quality_score,
                        'quality_breakdown': score_breakdown,
                        'quality_threshold': self.quality_scorer.quality_threshold
                    }
                else:
                    quality_metadata = {}

                signal = self.create_breakout_signal(
                    tick,
                    f"MULTI_CONFIRMED_{self.min_confirmation_count}ALGOS",
                    symbol,
                    combined_types,
                    avg_strength
                )

                # 添加质量评分metadata到signal
                if signal and quality_metadata:
                    signal.metadata.update(quality_metadata)

                # 🔥 webhook推送：只有通过质量评分的信号才发送webhook通知
                if self.enable_webhook and self.webhook and signal:
                    # 构建action和reason用于webhook
                    action = "UPWARD_BREAKOUT" if signal.signal_type == SignalType.OPEN_LONG else "DOWNWARD_BREAKOUT"
                    reason = f"MULTI_CONFIRMED_{self.min_confirmation_count}ALGOS"

                    self.logger.info(f"[WEBHOOK] Sending notification for high-quality signal: "
                                   f"{symbol}, Quality={quality_score:.3f}")
                    self._send_webhook_notification(signal, tick, reason, action, symbol)

                return signal

        return None

    def _detect_single_breakout(self, tick: TickData, symbol: str) -> Optional[Signal]:
        """单一突破检测（原有逻辑）"""
        # 1. 统计突破检测
        if self.detect_statistical_breakout(tick, symbol):
            return self.create_breakout_signal(tick, "STATISTICAL", symbol)

        # 2. 动量突破检测
        if self.detect_momentum_breakout(tick, symbol):
            return self.create_breakout_signal(tick, "MOMENTUM", symbol)

        # 3. 连续变动突破
        if self.detect_consecutive_moves_breakout(tick, symbol):
            return self.create_breakout_signal(tick, "CONSECUTIVE", symbol)

        # 4. 成交量突破检测
        if self.detect_volume_breakout(tick, symbol):
            return self.create_breakout_signal(tick, "VOLUME", symbol)

        # 5. 价格路径突破检测
        path_breakout = self.detect_path_breakout(tick, symbol)
        if path_breakout:
            return self.create_breakout_signal(tick, f"PATH_{path_breakout}", symbol)

        return None

    def _calculate_detection_strength(self, tick: TickData, detection_type: str, symbol: str) -> float:
        """计算检测强度"""
        base_strength = 1.0

        if detection_type == "STATISTICAL":
            # 基于价格偏离度
            _, price_history, _, _ = self._get_symbol_buffers(symbol)
            prices = list(price_history)
            if len(prices) > 0:
                mean_price = np.mean(prices)
                std_price = np.std(prices)
                if std_price > 0:
                    price_deviation = abs(tick.price - mean_price) / std_price
                    base_strength = min(price_deviation / 3.0, 3.0)  # 标准化到0-3

        elif detection_type == "MOMENTUM":
            # 基于动量比率
            _, _, _, price_change_history = self._get_symbol_buffers(symbol)
            price_changes = list(price_change_history)
            if len(price_changes) >= 20:
                short_momentum = np.mean(price_changes[-5:])
                long_momentum = np.mean(price_changes[-20:])
                if long_momentum != 0:
                    momentum_ratio = abs(short_momentum / long_momentum)
                    base_strength = min(momentum_ratio / 3.0, 3.0)

        elif detection_type == "CONSECUTIVE":
            # 基于连续变动次数
            base_strength = min(self.consecutive_moves_counts.get(symbol, 0) / 5.0, 3.0)

        elif detection_type == "VOLUME":
            # 🔥 修复：基于滑动窗口成交量激增，使用对数强度计算
            _, _, volume_history, _ = self._get_symbol_buffers(symbol)
            volumes = list(volume_history)
            if len(volumes) >= self.volume_min_data_points:
                # 🔥 使用滑动窗口计算平均值
                window_size = self.volume_min_data_points
                recent_volumes = volumes[-window_size:]
                avg_volume = np.mean(recent_volumes)

                if avg_volume > 0 and tick.volume > 0:
                    volume_ratio = tick.volume / avg_volume
                    # 🔧 优化：使用对数计算，更合理的强度映射
                    if volume_ratio > 1.0:
                        base_strength = min(np.log(volume_ratio) / np.log(1.5), 3.0)  # 以1.5为底的对数
                    else:
                        base_strength = 0.0

        elif detection_type.startswith("PATH"):
            # 基于路径突破
            base_strength = 1.5  # 路径突破给予中等强度

        return base_strength

    def _clean_expired_signals(self, current_time: float, symbol: str):
        """清理过期的信号 - 每个交易对独立"""
        if symbol not in self.pending_signals:
            self.pending_signals[symbol] = []

        cutoff_time = current_time - self.confirmation_window
        self.pending_signals[symbol] = [
            s for s in self.pending_signals[symbol]
            if s['timestamp'] > cutoff_time
        ]

    def detect_statistical_breakout(self, tick: TickData, symbol: str) -> bool:
        """基于统计的突破检测"""

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)
        prices = list(price_history)

        # 计算统计指标
        mean_price = np.mean(prices)
        std_price = np.std(prices)

        if std_price == 0:
            self.logger.debug(f"   STATISTICAL: 标准差为0，跳过检测")
            return False

        # 价格偏离度
        price_deviation = abs(tick.price - mean_price) / std_price

        # 自适应阈值
        volatility = std_price / mean_price if mean_price > 0 else 0
        adaptive_threshold = self.calculate_adaptive_threshold(volatility)

        result = price_deviation > adaptive_threshold

        self.logger.debug(f"   STATISTICAL详情: "
                         f"均值={mean_price:.2f}, "
                         f"标准差={std_price:.2f}, "
                         f"偏离度={price_deviation:.2f}, "
                         f"阈值={adaptive_threshold:.2f}, "
                         f"触发={result}")

        return result

    def _detect_statistical_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """统计突破方向检测 - 保留方向信息"""

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)
        prices = list(price_history)

        # 计算统计指标
        mean_price = np.mean(prices)
        std_price = np.std(prices)

        if std_price == 0:
            return DirectionScore(algorithm="STATISTICAL", confidence=0.0)

        # 🔥 保留方向信息，不使用abs()
        price_deviation = (tick.price - mean_price) / std_price

        # 自适应阈值
        volatility = std_price / mean_price if mean_price > 0 else 0
        adaptive_threshold = self.calculate_adaptive_threshold(volatility)

        if abs(price_deviation) > adaptive_threshold:
            strength = min(abs(price_deviation) / 3.0, 1.0)
            confidence = strength * 0.8

            # 🔥 确定方向
            if price_deviation > 0:
                buy_strength = strength
                sell_strength = 0.0
                direction_bias = strength
                direction_desc = "向上突破"
            else:
                buy_strength = 0.0
                sell_strength = strength
                direction_bias = -strength
                direction_desc = "向下突破"

            self.logger.debug(f"   STATISTICAL方向: {direction_desc}, "
                            f"偏离度={price_deviation:.2f}, "
                            f"强度={strength:.3f}, "
                            f"置信度={confidence:.3f}")

            return DirectionScore(
                buy_strength=buy_strength,
                sell_strength=sell_strength,
                confidence=confidence,
                direction_bias=direction_bias,
                algorithm="STATISTICAL",
                metadata={
                    'price_deviation': price_deviation,
                    'threshold': adaptive_threshold,
                    'mean_price': mean_price,
                    'std_price': std_price,
                    'direction': direction_desc
                }
            )

        return DirectionScore(algorithm="STATISTICAL", confidence=0.0)

    def detect_momentum_breakout(self, tick: TickData, symbol: str) -> bool:
        """基于动量的突破检测"""

        # 获取该交易对的历史数据
        _, _, _, price_change_history = self._get_symbol_buffers(symbol)
        price_changes = list(price_change_history)
        if len(price_changes) < 20:
            self.logger.debug(f"   MOMENTUM: 数据不足({len(price_changes)}<20)，跳过检测")
            return False

        # 短期动量 vs 长期动量
        short_momentum = np.mean(price_changes[-5:])  # 最近5个变动
        long_momentum = np.mean(price_changes[-20:])  # 最近20个变动

        if long_momentum == 0:
            self.logger.debug(f"   MOMENTUM: 长期动量为0，跳过检测")
            return False

        momentum_ratio = abs(short_momentum / long_momentum)

        # 动量加速
        result = momentum_ratio > self.momentum_ratio_threshold and abs(short_momentum) > 0.1

        self.logger.debug(f"   MOMENTUM详情: "
                         f"短期动量={short_momentum:.4f}, "
                         f"长期动量={long_momentum:.4f}, "
                         f"比率={momentum_ratio:.2f}, "
                         f"阈值={self.momentum_ratio_threshold:.2f}, "
                         f"触发={result}")

        return result

    def _detect_momentum_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """动量突破方向检测 - 保留动量方向"""

        # 获取该交易对的历史数据
        _, _, _, price_change_history = self._get_symbol_buffers(symbol)
        price_changes = list(price_change_history)

        if len(price_changes) < 20:
            return DirectionScore(algorithm="MOMENTUM", confidence=0.0)

        # 🔥 保留动量方向，不使用abs()
        short_momentum = np.mean(price_changes[-5:])  # 最近5个变动
        long_momentum = np.mean(price_changes[-20:])  # 最近20个变动

        if long_momentum == 0:
            return DirectionScore(algorithm="MOMENTUM", confidence=0.0)

        momentum_ratio = abs(short_momentum / long_momentum)

        if momentum_ratio > self.momentum_ratio_threshold and abs(short_momentum) > 0.1:
            strength = min(momentum_ratio / 3.0, 1.0)
            confidence = strength * 0.85

            # 🔥 根据动量方向确定买卖强度
            if short_momentum > 0:
                buy_strength = strength
                sell_strength = 0.0
                direction_bias = strength
                direction_desc = "正向动量加速"
            else:
                buy_strength = 0.0
                sell_strength = strength
                direction_bias = -strength
                direction_desc = "负向动量加速"

            self.logger.debug(f"   MOMENTUM方向: {direction_desc}, "
                            f"短期动量={short_momentum:.4f}, "
                            f"长期动量={long_momentum:.4f}, "
                            f"比率={momentum_ratio:.2f}, "
                            f"强度={strength:.3f}")

            return DirectionScore(
                buy_strength=buy_strength,
                sell_strength=sell_strength,
                confidence=confidence,
                direction_bias=direction_bias,
                algorithm="MOMENTUM",
                metadata={
                    'short_momentum': short_momentum,
                    'long_momentum': long_momentum,
                    'ratio': momentum_ratio,
                    'direction': direction_desc
                }
            )

        return DirectionScore(algorithm="MOMENTUM", confidence=0.0)

    def detect_consecutive_moves_breakout(self, tick: TickData, symbol: str) -> bool:
        """连续同向变动突破检测"""

        # 使用per-symbol的连续变动计数
        result = self.consecutive_moves_counts.get(symbol, 0) >= self.consecutive_moves_threshold

        self.logger.debug(f"   CONSECUTIVE详情: "
                         f"当前连续={self.consecutive_moves_counts.get(symbol, 0)}, "
                         f"阈值={self.consecutive_moves_threshold}, "
                         f"触发={result}")

        return result

    def detect_volume_breakout(self, tick: TickData, symbol: str) -> bool:
        """
        🔥 革命性的成交量突破检测 - 适配Binance All Market Tickers Stream
        支持多种检测策略：24小时总成交量 + 最新交易数量激增 + 交易频率分析
        """

        
        # 获取该交易对的历史数据
        _, _, volume_history, _ = self._get_symbol_buffers(symbol)
        volumes = list(volume_history)

        # 🔧 使用配置化的数据要求
        if len(volumes) < self.volume_min_data_points:
            return False

        # 🔥 多维度成交量检测
        detection_signals = []

        # 🔥 实时交易量激增检测（统一基于last_quantity）
        if tick.last_quantity is not None and tick.last_quantity > 0:
            # 使用滑动窗口检测last_quantity激增
            quantity_signal = self._detect_total_volume_surge(tick, symbol, volumes)
            if quantity_signal:
                detection_signals.append(f"实时交易量激增({tick.last_quantity:.4f})")

            # 使用独立历史检测last_quantity激增
            self._detect_last_quantity_surge(tick, symbol)  # 更新内部历史记录

        # 3. 🔥 交易频率激增检测（基于24小时交易次数）
        if tick.trade_count_24h is not None:
            frequency_signal = self._detect_trade_frequency_surge(tick, symbol)
            if frequency_signal:
                detection_signals.append(f"交易频率激增({tick.trade_count_24h}次)")

        # 4. 🔥 成交额激增检测（基于q字段）- 仅当有Binance扩展字段时
        if tick.quote_volume is not None:
            quote_volume_signal = self._detect_quote_volume_surge(tick, symbol, volumes)
            if quote_volume_signal:
                detection_signals.append(f"成交额激增(${tick.quote_volume:,.0f})")

        # 5. 🔥 价格成交量协同激增检测（适用于标准格式，无Binance扩展字段时）
        if tick.last_quantity is None and tick.quote_volume is None:
            price_volume_signal = self._detect_price_volume_surge(tick, symbol, volumes)
            if price_volume_signal:
                detection_signals.append(f"价格成交量协同激增")

        # 6. 🔥 价格变动确认（所有检测的必要条件）
        price_change_ok = self._check_price_change_requirement(tick)
        if not price_change_ok:
            self.logger.debug(f"   VOLUME: 价格变动不足，跳过所有成交量检测")
            return False

        # 🔥 最终决策：任一检测策略触发即认为成交量突破
        result = len(detection_signals) > 0

        if result:
            detection_reasons = ", ".join(detection_signals)

        return result

    def _detect_total_volume_surge(self, tick: TickData, symbol: str, volumes: List[float]) -> bool:
        """🔥 修复：实时交易量激增检测（基于last_quantity）"""
        # 关键修复：使用last_quantity进行实时检测，避免数量级不匹配问题

        # 检查当前tick是否有last_quantity数据
        if tick.last_quantity is None or tick.last_quantity <= 0:
            return False

        # 滑动窗口检测
        window_size = self.volume_min_data_points

        # 如果数据不足，跳过检测
        if len(volumes) < window_size + 1:
            return False

        # 🔥 关键修复：使用last_quantity历史数据进行比较
        historical_quantities = volumes[-(window_size + 1):-1]  # 排除当前tick
        mean_quantity = np.mean(historical_quantities)

        # 🔥 修复：动态最小成交量调整（针对last_quantity）
        min_realistic_quantity = 0.01  # 最小合理的单笔交易量
        if mean_quantity < min_realistic_quantity:
            # 如果历史平均值太小，任何正常交易都算激增
            return tick.last_quantity > min_realistic_quantity

        # 🔥 修复：计算当前last_quantity相对历史平均的激增比率
        quantity_ratio = tick.last_quantity / mean_quantity
        return quantity_ratio > self.volume_surge_threshold

    def _detect_last_quantity_surge(self, tick: TickData, symbol: str) -> bool:
        """🔥 最新交易数量激增检测（实时性最强）"""
        # 获取历史最新交易数量数据（如果有）
        if not hasattr(self, '_last_quantity_histories'):
            self._last_quantity_histories = {}

        if symbol not in self._last_quantity_histories:
            self._last_quantity_histories[symbol] = []

        history = self._last_quantity_histories[symbol]
        history.append(tick.last_quantity)
        if len(history) > 20:  # 保留最近20次的数据
            history.pop(0)

        # 计算最近交易数量的平均值
        if len(history) < 5:
            return False

        avg_quantity = np.mean(history[:-1])  # 不包括当前值
        if avg_quantity == 0:
            # 如果历史平均为0，任何交易都是激增
            return tick.last_quantity > 0

        # 当前交易量相对于历史平均的倍数
        quantity_ratio = tick.last_quantity / avg_quantity

        # 🔥 降低阈值，因为这是实时交易数据
        return quantity_ratio > 2.0  # 2倍激增

    def _detect_trade_frequency_surge(self, tick: TickData, symbol: str) -> bool:
        """🔥 交易频率激增检测（基于24小时交易次数）"""
        if not hasattr(self, '_trade_count_histories'):
            self._trade_count_histories = {}

        if symbol not in self._trade_count_histories:
            self._trade_count_histories[symbol] = []

        history = self._trade_count_histories[symbol]
        history.append(tick.trade_count_24h)
        if len(history) > 10:  # 保留最近10次的数据
            history.pop(0)

        # 检查交易次数增长
        if len(history) < 2:
            return False

        # 计算交易次数增长率
        current_count = tick.trade_count_24h
        previous_count = history[-2]

        if previous_count == 0:
            # 如果之前没有交易记录，任何交易都是激增
            return current_count > 0
        elif current_count > previous_count:
            # 交易次数增长
            growth_rate = (current_count - previous_count) / previous_count
            return growth_rate > 0.05  # 5%的增长率

        return False

    def _detect_quote_volume_surge(self, tick: TickData, symbol: str, volumes: List[float]) -> bool:
        """🔥 成交额激增检测（基于q字段：24小时成交额）"""
        if not hasattr(self, '_quote_volume_histories'):
            self._quote_volume_histories = {}

        if symbol not in self._quote_volume_histories:
            self._quote_volume_histories[symbol] = []

        history = self._quote_volume_histories[symbol]
        history.append(tick.quote_volume)
        if len(history) > 10:
            history.pop(0)

        if len(history) < 5:
            return False

        # 计算平均成交额
        avg_quote_volume = np.mean(history[:-1])

        if avg_quote_volume == 0:
            return tick.quote_volume > 0

        quote_volume_ratio = tick.quote_volume / avg_quote_volume
        return quote_volume_ratio > 1.5  # 成交额1.5倍激增

    def _check_price_change_requirement(self, tick: TickData) -> bool:
        """检查价格变动是否满足要求"""
        # 🔥 修复：使用24小时价格变化百分比字段，而不是重新计算
        if tick.price_change_percent is not None:
            price_change_pct = abs(tick.price_change_percent)  # 已经是百分比形式
        else:
            # 后备方案：使用price_change计算
            if abs(tick.price_change) < 1e-10 or tick.price <= 0:
                price_change_pct = 0.0
            else:
                price_change_pct = abs(tick.price_change) / tick.price * 100  # 转换为百分比

        return price_change_pct > (self.volume_min_price_change * 100)  # 配置是小数，需要转换为百分比

    def _detect_price_volume_surge(self, tick: TickData, symbol: str, volumes: List[float]) -> bool:
        """🔥 价格成交量协同激增检测 - 适用于标准格式数据"""
        # 基于价格变动和成交量的协同激增检测
        if len(volumes) < self.volume_min_data_points:
            return False

        # 计算成交量激增
        window_size = min(self.volume_min_data_points, len(volumes))
        recent_volumes = volumes[-window_size:]
        mean_volume = np.mean(recent_volumes)

        if mean_volume == 0:
            return False

        volume_ratio = tick.volume / mean_volume

        # 🔧 修复：使用相对最小成交量检查，避免不同币种流动性差异问题
        if self.volume_min_avg_volume > 0:
            max_historical_volume = max(volumes) if volumes else 0
            if max_historical_volume < self.volume_min_avg_volume:
                adjusted_min_volume = max_historical_volume * 0.8
                if mean_volume < adjusted_min_volume:
                    return False
            else:
                if mean_volume < self.volume_min_avg_volume:
                    return False

        # 同时检查价格变动和成交量激增
        price_change_ok = self._check_price_change_requirement(tick)
        volume_ok = volume_ratio > self.volume_surge_threshold

        return price_change_ok and volume_ok

    def _detect_volume_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """🔥 修复：实时交易量突破方向检测 - 统一基于last_quantity"""

        # 检查last_quantity数据
        if tick.last_quantity is None or tick.last_quantity <= 0:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        # 获取该交易对的历史数据
        _, price_history, volume_history, _ = self._get_symbol_buffers(symbol)
        volumes = list(volume_history)
        prices = list(price_history)

        # 🔧 使用配置化的数据要求
        if len(volumes) < self.volume_min_data_points or len(prices) == 0:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        # 🔥 修复：使用last_quantity滑动窗口
        window_size = self.volume_min_data_points

        # 🔥 关键修复：使用历史last_quantity数据，排除当前tick
        if len(volumes) < window_size + 1:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        historical_quantities = volumes[-(window_size + 1):-1]  # 排除当前tick
        mean_quantity = np.mean(historical_quantities)

        # 🔥 修复：动态最小成交量调整（针对last_quantity）
        min_realistic_quantity = 0.01
        if mean_quantity < min_realistic_quantity:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        # 🔥 修复：使用last_quantity计算激增比率
        if mean_quantity == 0:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        quantity_ratio = tick.last_quantity / mean_quantity

        # 🔥 修复：使用相对最小成交量检查，避免不同币种流动性差异问题
        if mean_quantity == 0:
            return DirectionScore(algorithm="VOLUME", confidence=0.0)

        # 🔥 修复：检测激增条件
        price_change_ok = self._check_price_change_requirement(tick)
        volume_ok = quantity_ratio > self.volume_surge_threshold

        # 🔥 修复：使用last_quantity进行检测，price_change使用绝对值
        min_price_change_pct = self.volume_min_price_change * 100  # 转换为百分比
        volume_ok = quantity_ratio > self.volume_surge_threshold
        price_ok = abs(tick.price_change) > min_price_change_pct

        if volume_ok and price_ok:
            # 🔥 成交量权重稍低，主要依赖价格方向
            strength = min(quantity_ratio / 3.0, 1.0) * 0.7
            confidence = strength * 0.6

            # 🔥 根据价格变动方向确定买卖强度
            if tick.price_change > 0:
                buy_strength = strength
                sell_strength = 0.0
                direction_bias = strength
                direction_desc = "量价齐升"
            else:
                buy_strength = 0.0
                sell_strength = strength
                direction_bias = -strength
                direction_desc = "放量下跌"

            self.logger.debug(f"   VOLUME滑动窗口方向: {direction_desc}, "
                            f"窗口大小={window_size}, "
                            f"比率={quantity_ratio:.2f}, "
                            f"窗口均值={mean_quantity:.4f}, "
                            f"窗口范围=[{min(historical_quantities):.4f}, {max(historical_quantities):.4f}], "
                            f"价格变动={tick.price_change:.4f}, "
                            f"强度={strength:.3f}")

            return DirectionScore(
                buy_strength=buy_strength,
                sell_strength=sell_strength,
                confidence=confidence,
                direction_bias=direction_bias,
                algorithm="VOLUME",
                metadata={
                    'quantity_ratio': quantity_ratio,
                    'price_change': tick.price_change,
                    'mean_quantity': mean_quantity,
                    'window_size': window_size,
                    'window_min': min(historical_quantities),
                    'window_max': max(historical_quantities),
                    'direction': direction_desc,
                    'threshold_pct': min_price_change_pct
                }
            )

        return DirectionScore(algorithm="VOLUME", confidence=0.0)

    def _detect_consecutive_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """连续同向变动突破检测 - 方向感知版本"""

        # 获取当前连续变动状态
        current_count = self.consecutive_moves_counts.get(symbol, 0)
        current_trend = self.current_trends.get(symbol, 0)  # 1: 上涨, -1: 下跌, 0: 无趋势

        if current_count >= self.consecutive_moves_threshold:
            strength = min(current_count / 10.0, 1.0)  # 归一化到0-1
            confidence = strength * 0.75

            # 🔥 根据趋势方向确定买卖强度
            if current_trend > 0:  # 上涨趋势
                buy_strength = strength
                sell_strength = 0.0
                direction_bias = strength
                direction_desc = f"连续上涨{current_count}次"
            elif current_trend < 0:  # 下跌趋势
                buy_strength = 0.0
                sell_strength = strength
                direction_bias = -strength
                direction_desc = f"连续下跌{current_count}次"
            else:
                return DirectionScore(algorithm="CONSECUTIVE", confidence=0.0)

            self.logger.debug(f"   CONSECUTIVE方向: {direction_desc}, "
                            f"当前趋势={current_trend}, "
                            f"强度={strength:.3f}")

            return DirectionScore(
                buy_strength=buy_strength,
                sell_strength=sell_strength,
                confidence=confidence,
                direction_bias=direction_bias,
                algorithm="CONSECUTIVE",
                metadata={
                    'consecutive_count': current_count,
                    'trend': current_trend,
                    'direction': direction_desc
                }
            )

        return DirectionScore(algorithm="CONSECUTIVE", confidence=0.0)

    def _detect_path_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """价格路径突破方向检测 - 方向感知版本"""

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)
        prices = list(price_history)

        if len(prices) < 50:
            return DirectionScore(algorithm="PATH", confidence=0.0)

        # 寻找关键价格水平
        current_price = tick.price

        # 计算支撑阻力位
        resistance = self.calculate_resistance_level(prices, current_price)
        support = self.calculate_support_level(prices, current_price)

        result = None
        strength = 1.5 / 3.0  # 路径突破给予中等强度
        confidence = strength * 0.9

        if resistance and current_price > resistance * 1.001:
            result = f"RESISTANCE_{resistance:.2f}"
            buy_strength = strength
            sell_strength = 0.0
            direction_bias = strength
            direction_desc = "向上突破阻力位"
        elif support and current_price < support * 0.999:
            result = f"SUPPORT_{support:.2f}"
            buy_strength = 0.0
            sell_strength = strength
            direction_bias = -strength
            direction_desc = "向下突破支撑位"
        else:
            return DirectionScore(algorithm="PATH", confidence=0.0)

        self.logger.debug(f"   PATH方向: {direction_desc}, "
                        f"当前价格={current_price:.2f}, "
                        f"突破位={resistance if resistance else support:.2f}, "
                        f"强度={strength:.3f}")

        return DirectionScore(
            buy_strength=buy_strength,
            sell_strength=sell_strength,
            confidence=confidence,
            direction_bias=direction_bias,
            algorithm="PATH",
            metadata={
                'breakout_type': result,
                'resistance': resistance,
                'support': support,
                'current_price': current_price,
                'direction': direction_desc
            }
        )

    def _detect_with_direction(self, tick: TickData, algorithm: str, symbol: str) -> DirectionScore:
        """统一的方向感知检测接口"""

        if algorithm == "STATISTICAL":
            return self._detect_statistical_direction(tick, symbol)
        elif algorithm == "MOMENTUM":
            return self._detect_momentum_direction(tick, symbol)
        elif algorithm == "CONSECUTIVE":
            return self._detect_consecutive_direction(tick, symbol)
        elif algorithm == "VOLUME":
            return self._detect_volume_direction(tick, symbol)
        elif algorithm == "PATH":
            return self._detect_path_direction(tick, symbol)
        else:
            self.logger.warning(f"未知的算法类型: {algorithm}")
            return DirectionScore(algorithm=algorithm, confidence=0.0)

    def detect_path_breakout(self, tick: TickData, symbol: str) -> Optional[str]:
        """基于价格路径的突破检测 - 优化版"""

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)
        prices = list(price_history)

        # 🔧 使用配置化的数据要求
        if len(prices) < self.path_min_data_points:
            return None

        # 寻找关键价格水平
        current_price = tick.price

        # 计算支撑阻力位
        resistance = self.calculate_resistance_level_optimized(prices, current_price)
        support = self.calculate_support_level_optimized(prices, current_price)

        # 🔧 使用配置化的突破阈值（默认0.5%，降低突破难度）
        breakout_threshold = 1 + self.path_breakout_threshold  # 例如1.005 = 0.5%突破
        breakdown_threshold = 1 - self.path_breakout_threshold   # 例如0.995 = 0.5%突破

        # 突破检测
        result = None
        if resistance and current_price > resistance * breakout_threshold:
            result = f"RESISTANCE_{resistance:.6f}"
        elif support and current_price < support * breakdown_threshold:
            result = f"SUPPORT_{support:.6f}"

        resistance_str = f"{resistance:.6f}" if resistance else "None"
        support_str = f"{support:.6f}" if support else "None"

        self.logger.debug(f"   PATH详情(优化): "
                         f"当前={current_price:.6f}, "
                         f"阻力={resistance_str}, "
                         f"支撑={support_str}, "
                         f"突破阈值={self.path_breakout_threshold:.3f}, "
                         f"突破={result or 'None'}")

        return result

    def _detect_path_direction(self, tick: TickData, symbol: str) -> DirectionScore:
        """基于价格路径的方向突破检测 - 优化版"""

        # 获取该交易对的历史数据
        _, price_history, _, _ = self._get_symbol_buffers(symbol)
        prices = list(price_history)

        # 🔧 使用配置化的数据要求
        if len(prices) < self.path_min_data_points:
            return DirectionScore(algorithm="PATH", confidence=0.0)

        # 寻找关键价格水平
        current_price = tick.price

        # 🔧 使用优化的支撑阻力位计算
        resistance = self.calculate_resistance_level_optimized(prices, current_price)
        support = self.calculate_support_level_optimized(prices, current_price)

        # 突破检测和方向评分
        breakout_strength = 0.0
        direction_bias = 0.0
        reason = ""

        # 🔧 使用配置化的突破阈值（默认0.5%）
        breakout_threshold = 1 + self.path_breakout_threshold
        breakdown_threshold = 1 - self.path_breakout_threshold

        # 🔥 市场分析：检测平坦市场和虚拟支撑阻力位
        price_variance = np.var(prices) if len(prices) > 1 else 0
        price_range = max(prices) - min(prices) if len(prices) > 1 else 0
        price_range_pct = (price_range / min(prices)) * 100 if min(prices) > 0 else 0

        # 检测是否为平坦市场
        is_flat_market = price_range_pct < 0.1  # 价格变化小于0.1%

        # 如果是平坦市场，生成虚拟支撑阻力位
        if is_flat_market:
            # 基于历史平均价格和典型波动率生成虚拟支撑阻力位
            avg_price = np.mean(prices) if prices else current_price
            virtual_offset = avg_price * 0.001  # 0.1%的虚拟偏移

            virtual_resistance = avg_price + virtual_offset
            virtual_support = avg_price - virtual_offset

            # 使用虚拟支撑阻力位进行突破检测
            if current_price > virtual_resistance:
                breakout_direction = "UP"
                strength = min((current_price - virtual_resistance) / virtual_offset, 1.0)

                return DirectionScore(
                    buy_strength=strength,
                    sell_strength=0.0,
                    confidence=strength * 0.9,
                    direction_bias=strength,
                    algorithm="PATH",
                    metadata={
                        'breakout_type': 'virtual_resistance',
                        'virtual_resistance': virtual_resistance,
                        'virtual_support': virtual_support,
                        'price_range_pct': price_range_pct,
                        'strength': strength
                    }
                )

            elif current_price < virtual_support:
                breakout_direction = "DOWN"
                strength = min((virtual_support - current_price) / virtual_offset, 1.0)

                return DirectionScore(
                    buy_strength=0.0,
                    sell_strength=strength,
                    confidence=strength * 0.9,
                    direction_bias=-strength,
                    algorithm="PATH",
                    metadata={
                        'breakout_type': 'virtual_support',
                        'virtual_resistance': virtual_resistance,
                        'virtual_support': virtual_support,
                        'price_range_pct': price_range_pct,
                        'strength': strength
                    }
                )

            else:
                return DirectionScore(algorithm="PATH", confidence=0.0)

        if resistance and current_price > resistance * breakout_threshold:
            breakout_strength = (current_price - resistance) / resistance * 100
            direction_bias = min(breakout_strength / 2.0, 1.0)
            reason = f"Resistance突破_{resistance:.6f}" if resistance else "Resistance突破"

        elif support and current_price < support * breakdown_threshold:
            breakout_strength = (support - current_price) / support * 100
            direction_bias = -min(breakout_strength / 2.0, 1.0)
            reason = f"Support突破_{support:.6f}" if support else "Support突破"
        else:
            # 未检测到突破
            breakout_strength = 0.0
            direction_bias = 0.0
            reason = ""

        # 🔧 使用配置化的最小突破强度检查
        min_breakout_strength_pct = self.path_breakout_threshold * 100  # 转换为百分比

        if breakout_strength > min_breakout_strength_pct:
            strength = min(breakout_strength / 5.0, 1.0)
            confidence = strength * 0.9

            # 根据方向确定买卖强度
            if direction_bias > 0:  # 向上突破
                buy_strength = strength
                sell_strength = 0.0
                direction_desc = reason
            else:  # 向下突破
                buy_strength = 0.0
                sell_strength = strength
                direction_desc = reason

            self.logger.debug(f"   PATH方向: {direction_desc}, "
                            f"当前={current_price:.2f}, "
                            f"强度={strength:.3f}, "
                            f"突破={breakout_strength:.2f}%")

            return DirectionScore(
                buy_strength=buy_strength,
                sell_strength=sell_strength,
                confidence=confidence,
                direction_bias=direction_bias,
                algorithm="PATH",
                metadata={
                    'reason': reason,
                    'breakout_strength': breakout_strength,
                    'support': support,
                    'resistance': resistance,
                    'direction': direction_desc
                }
            )

        support_str = f"{support:.2f}" if support else "None"
        resistance_str = f"{resistance:.2f}" if resistance else "None"
        self.logger.debug(f"   PATH: 无有效突破 (支撑={support_str}, 阻力={resistance_str})")
        return DirectionScore(algorithm="PATH", confidence=0.0)

    def calculate_resistance_level(self, prices: List[float], current_price: float) -> Optional[float]:
        """计算阻力位"""

        # 寻找近期高点
        window = min(50, len(prices))
        recent_prices = prices[-window:]

        # 找到局部最高点
        local_maxima = []
        for i in range(2, len(recent_prices) - 2):
            if (recent_prices[i] > recent_prices[i-1] and
                recent_prices[i] > recent_prices[i-2] and
                recent_prices[i] > recent_prices[i+1] and
                recent_prices[i] > recent_prices[i+2]):
                local_maxima.append(recent_prices[i])

        if not local_maxima:
            return None

        # 返回最低的阻力位（最接近当前价格的）
        resistance_levels = [level for level in local_maxima if level > current_price]

        return min(resistance_levels) if resistance_levels else None

    def calculate_support_level(self, prices: List[float], current_price: float) -> Optional[float]:
        """计算支撑位"""

        # 寻找近期低点
        window = min(50, len(prices))
        recent_prices = prices[-window:]

        # 找到局部最低点
        local_minima = []
        for i in range(2, len(recent_prices) - 2):
            if (recent_prices[i] < recent_prices[i-1] and
                recent_prices[i] < recent_prices[i-2] and
                recent_prices[i] < recent_prices[i+1] and
                recent_prices[i] < recent_prices[i+2]):
                local_minima.append(recent_prices[i])

        if not local_minima:
            return None

        # 返回最高的支撑位（最接近当前价格的）
        support_levels = [level for level in local_minima if level < current_price]

        return max(support_levels) if support_levels else None

    def calculate_resistance_level_optimized(self, prices: List[float], current_price: float) -> Optional[float]:
        """优化的阻力位计算 - 更宽松的条件"""

        if len(prices) < 3:  # 降低最小数据点要求
            return None

        # 🔧 使用更宽松的局部极值定义（连续3个点而不是5个）
        recent_prices = prices[-min(30, len(prices)):]  # 使用更小的窗口

        local_maxima = []
        for i in range(1, len(recent_prices) - 1):
            if (recent_prices[i] >= recent_prices[i-1] and
                recent_prices[i] >= recent_prices[i+1]):
                local_maxima.append(recent_prices[i])

        if not local_maxima:
            # 🔧 如果没有严格的局部极值，使用最高点
            local_maxima.append(max(recent_prices))

        # 🔧 修复：返回最低的阻力位（最接近当前价格的）
        resistance_levels = [level for level in local_maxima if level > current_price]
        if resistance_levels:
            return min(resistance_levels)
        else:
            # 🔧 如果没有更高的阻力位，使用最近的最大值加上虚拟偏移
            recent_max = max(recent_prices)
            return recent_max * (1 + self.path_virtual_level_offset)

    def calculate_support_level_optimized(self, prices: List[float], current_price: float) -> Optional[float]:
        """优化的支撑位计算 - 更宽松的条件"""

        if len(prices) < 3:  # 降低最小数据点要求
            return None

        # 🔧 使用更宽松的局部极值定义（连续3个点而不是5个）
        recent_prices = prices[-min(30, len(prices)):]  # 使用更小的窗口

        local_minima = []
        for i in range(1, len(recent_prices) - 1):
            if (recent_prices[i] <= recent_prices[i-1] and
                recent_prices[i] <= recent_prices[i+1]):
                local_minima.append(recent_prices[i])

        if not local_minima:
            # 🔧 如果没有严格的局部极值，使用最低点
            local_minima.append(min(recent_prices))

        # 🔧 修复：返回最高的支撑位（最接近当前价格的）
        support_levels = [level for level in local_minima if level < current_price]
        if support_levels:
            return max(support_levels)
        else:
            # 🔧 如果没有更低的支撑位，使用最近的最小值减去虚拟偏移
            recent_min = min(recent_prices)
            return recent_min * (1 - self.path_virtual_level_offset)

    def calculate_adaptive_threshold(self, volatility: float) -> float:
        """自适应突破阈值"""

        base_threshold = self.min_breakout_strength

        # 根据波动率调整阈值
        if volatility > 0.02:  # 高波动市场
            return base_threshold * 1.5
        elif volatility > 0.01:  # 中等波动
            return base_threshold * 1.2
        elif volatility < 0.005:  # 低波动市场
            return base_threshold * 0.8
        else:
            return base_threshold

    def create_breakout_signal(self, tick: TickData, reason: str, symbol: str = "UNKNOWN",
                           combined_types: str = None, avg_strength: float = None) -> Signal:
        """创建突破信号"""

        # 确定信号方向
        if tick.price_change > 0:
            signal_type = SignalType.OPEN_LONG  # 🔧 修复：使用正确的信号类型
            action = "UPWARD_BREAKOUT"
        elif tick.price_change < 0:
            signal_type = SignalType.OPEN_SHORT  # 🔧 修复：使用正确的信号类型
            action = "DOWNWARD_BREAKOUT"
        else:
            return None

        # 计算信号强度
        strength = self.calculate_signal_strength(tick, reason, symbol)

        # 计算建议数量
        amount = self.calculate_position_size(tick, strength, symbol)

        # 创建信号对象
        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            amount=amount,
            price=tick.price,
            confidence=strength,
            strategy_name="TickBreakoutDetector",
            reason=f"{reason}_{action}",
            metadata={
                'tick_timestamp': tick.timestamp,
                'tick_volume': tick.volume,
                'tick_price_change': tick.price_change,
                'detection_method': reason,
                'consecutive_moves': self.consecutive_moves_counts.get(symbol, 0)
            }
        )

        # 🔧 webhook推送迁移：不在生成信号时推送，而是在质量评分确认后推送
        # webhook推送逻辑已迁移到 detect_multi_dimensional_breakout() 方法中

        return signal

    def _send_webhook_notification(self, signal: Signal, tick: TickData, reason: str, action: str, symbol: str):
        """发送突破信号webhook通知"""
        try:
            # 检查是否有运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行中的循环，使用同步方式
                self._send_webhook_sync(signal, tick, reason, action, symbol)
            except RuntimeError:
                # 没有运行中的循环，创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._async_webhook_notification(signal, tick, reason, action, symbol))
                finally:
                    loop.close()
        except Exception as e:
            self.logger.error(f"Failed to send webhook notification: {e}")

    def _send_webhook_sync(self, signal: Signal, tick: TickData, reason: str, action: str, symbol: str):
        """同步发送webhook通知（避免事件循环冲突）"""
        try:
            # 构建消息内容
            signal_type_text = "买入" if signal.signal_type == SignalType.OPEN_LONG else "卖出"
            reason_text = self._get_reason_chinese(reason)

            content = f"""[ALERT] Tick级别突破信号检测到

交易对: {signal.symbol}
信号方向: {signal_type_text}
当前价格: ${tick.price:.2f}
价格变动: {tick.price_change:+.2f}
检测算法: {reason_text}
检测时间: {datetime.fromtimestamp(tick.timestamp/1000).strftime('%H:%M:%S')}
置信度: {signal.confidence:.2%}

建议执行交易信号
策略: TickBreakoutDetector
"""

            # 同步发送消息
            try:
                # 直接使用HTTP请求发送，避免webhook服务状态问题
                import requests
                import json

                # 构造飞书消息格式
                message_data = {
                    "msg_type": "text",
                    "content": {
                        "text": content
                    }
                }

                # 直接HTTP POST请求
                response = requests.post(
                    self.webhook.config.url,
                    json=message_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )

                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get('code') == 0:
                        self.logger.info(f"Webhook通知发送成功: {signal.symbol} {signal_type_text}")
                    else:
                        self.logger.error(f"飞书API错误: {response_data}")
                else:
                    self.logger.error(f"HTTP错误: {response.status_code}")

            except Exception as e:
                self.logger.error(f"HTTP webhook发送失败: {e}")
                # 尝试备用方案：使用webhook实例
                if hasattr(self.webhook, 'send_message_sync'):
                    self.webhook.send_message_sync(content)
                else:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.webhook.send_message(content))
                        future.result(timeout=10)

            self.logger.info(f"Webhook通知已发送: {signal.symbol} {signal_type_text}")

        except Exception as e:
            self.logger.error(f"同步webhook发送失败: {e}")

    async def _async_webhook_notification(self, signal: Signal, tick: TickData, reason: str, action: str, symbol: str):
        """异步发送webhook通知"""
        try:
            # 确保webhook服务已启动
            if not hasattr(self.webhook, '_running') or not self.webhook._running:
                await self.webhook.start()

            # 构建消息内容
            signal_type_text = "买入" if signal.signal_type == SignalType.OPEN_LONG else "卖出"
            reason_text = self._get_reason_chinese(reason)

            content = f"""🚀 Tick级别突破信号检测到
📈 交易对: {signal.symbol}
📊 信号类型: {signal_type_text} ({action})
💰 当前价格: ${tick.price:.6f}
📈 价格变动: {tick.price_change:+.6f}
🎯 信号强度: {signal.confidence:.2%}
[DEBUG] 检测方法: {reason_text}
📊 成交量: {tick.volume:.2f}
🔄 连续变动: {self.consecutive_moves_counts.get(symbol, 0)}次
🤖 策略: TickBreakoutDetector
⏰ 时间: {datetime.fromtimestamp(tick.timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')}"""

            # 发送交易信号通知
            signal_timestamp = datetime.fromtimestamp(tick.timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')
            await self.webhook.send_trading_signal(
                symbol=signal.symbol,
                signal_type=signal_type_text,
                price=tick.price,
                confidence=signal.confidence,
                strategy_name="TickBreakoutDetector",
                timestamp=signal_timestamp
            )

            # 同时发送详细通知
            await self.webhook.send_message(content)

            self.logger.info(f"✅ Webhook notification sent for {signal.symbol} {signal_type_text} signal")

        except Exception as e:
            self.logger.error(f"Failed to send webhook notification: {e}")

    def _get_reason_chinese(self, reason: str) -> str:
        """获取检测方法的中文名称"""
        reason_map = {
            "STATISTICAL": "统计突破",
            "MOMENTUM": "动量突破",
            "CONSECUTIVE": "连续变动突破",
            "VOLUME": "成交量突破",
            "RESISTANCE": "阻力位突破",
            "SUPPORT": "支撑位突破"
        }
        return reason_map.get(reason, reason)

    def calculate_signal_strength(self, tick: TickData, reason: str, symbol: str) -> float:
        """计算信号强度"""

        base_strength = 0.6

        # 根据检测方法调整强度
        if reason == "STATISTICAL":
            _, price_history, _, _ = self._get_symbol_buffers(symbol)
            prices = list(price_history)
            mean_price = np.mean(prices)
            std_price = np.std(prices)
            deviation = abs(tick.price - mean_price) / std_price if std_price > 0 else 0
            strength = min(0.9, base_strength + deviation * 0.1)

        elif reason == "MOMENTUM":
            strength = 0.8  # 动量突破强度较高

        elif reason == "CONSECUTIVE":
            # 连续变动次数越多，强度越高
            strength = min(0.9, base_strength + self.consecutive_moves_counts.get(symbol, 0) * 0.05)

        elif reason == "VOLUME":
            # 🔥 修复：使用滑动窗口计算成交量比率
            _, _, volume_history, _ = self._get_symbol_buffers(symbol)
            volumes = list(volume_history)
            if len(volumes) >= self.volume_min_data_points:
                window_size = self.volume_min_data_points
                recent_volumes = volumes[-window_size:]
                mean_volume = np.mean(recent_volumes)
                volume_ratio = tick.volume / mean_volume if mean_volume > 0 else 0
                strength = min(0.9, base_strength + volume_ratio * 0.1)
            else:
                strength = base_strength  # 数据不足时使用基础强度

        else:
            strength = base_strength

        return min(1.0, strength)

    def calculate_position_size(self, tick: TickData, strength: float, symbol: str) -> float:
        """计算建议持仓数量 - 基于配置化目标金额的改进版本"""

        # 🔧 使用配置化的目标金额价值
        target_value_usdt = self.target_trade_value_usdt

        # 根据信号强度调整金额价值
        adjusted_value_usdt = target_value_usdt * strength

        # 根据成交量调整 (最大2倍放大) - 🔥 使用滑动窗口
        _, _, volume_history, _ = self._get_symbol_buffers(symbol)
        volume_factor = 1.0
        if len(volume_history) >= self.volume_min_data_points:
            window_size = self.volume_min_data_points
            recent_volumes = list(volume_history)[-window_size:]
            avg_volume = np.mean(recent_volumes)
            if avg_volume > 0:
                volume_ratio = tick.volume / avg_volume
                volume_factor = min(2.0, max(1.0, volume_ratio))

        # 最终交易金额 (USDT等值)
        final_value_usdt = adjusted_value_usdt * volume_factor

        # 🔧 应用交易规模限制
        final_value_usdt = max(self.min_trade_value_usdt,
                              min(self.max_trade_value_usdt, final_value_usdt))

        # 🔧 关键修复：根据当前价格计算实际数量
        actual_amount = final_value_usdt / tick.price if tick.price > 0 else 0.0

        # 安全检查：确保数量合理
        min_amount = 0.000001  # 最小数量
        if actual_amount < min_amount:
            actual_amount = min_amount

        self.logger.debug(f"   数量计算: 目标价值=${target_value_usdt:.2f}, "
                         f"强度={strength:.3f}, "
                         f"成交量因子={volume_factor:.2f}, "
                         f"最终价值=${final_value_usdt:.2f}, "
                         f"价格=${tick.price:.4f}, "
                         f"计算数量={actual_amount:.6f}")

        return actual_amount

    def get_detector_statistics(self, symbol: str = None) -> Dict[str, Any]:
        """获取检测器统计信息"""

        if symbol:
            # 返回指定symbol的统计信息
            _, price_history, _, _ = self._get_symbol_buffers(symbol)
            if len(price_history) == 0:
                return {}
            prices = list(price_history)

            return {
                'symbol': symbol,
                'tick_count': len(prices),
                'current_price': prices[-1] if prices else 0,
                'price_range': {
                    'min': min(prices),
                    'max': max(prices),
                    'mean': np.mean(prices),
                    'std': np.std(prices)
                },
                'consecutive_moves': self.consecutive_moves_counts.get(symbol, 0)
            }
        else:
            # 返回所有symbol的汇总统计
            stats = {
                'symbols': list(self.tick_buffers.keys()),
                'total_symbols': len(self.tick_buffers),
                'symbol_stats': {}
            }

            for sym in self.tick_buffers.keys():
                stats['symbol_stats'][sym] = self.get_detector_statistics(sym)

            return stats

    def _detect_multi_dimensional_breakout_with_direction_coordination(
        self, tick: TickData, symbol: str
    ) -> Optional[Signal]:
        """带方向协调的多维度突破检测"""

        current_time = tick.timestamp

        self.logger.debug(f"[DEBUG] 🔥 方向协调检测开始 - {symbol}: "
                        f"价格={tick.price:.2f}, "
                        f"变动={tick.price_change:+.2f}, "
                        f"成交量={tick.volume:.0f}")

        # 1. 收集所有算法的方向评分
        direction_scores = []
        active_algorithms = []

        algorithms = ["STATISTICAL", "MOMENTUM", "CONSECUTIVE", "VOLUME", "PATH"]

        for algorithm in algorithms:
            try:
                score = self._detect_with_direction(tick, algorithm, symbol)
                if score.confidence > 0.3:  # 最小置信度阈值
                    direction_scores.append(score)
                    active_algorithms.append(algorithm)

                    self.logger.debug(f"   {algorithm}: 方向评分获取成功, "
                                    f"买入={score.buy_strength:.3f}, "
                                    f"卖出={score.sell_strength:.3f}, "
                                    f"置信度={score.confidence:.3f}")
                else:
                    self.logger.debug(f"   {algorithm}: 置信度过低({score.confidence:.3f}), 跳过")

            except Exception as e:
                self.logger.debug(f"   {algorithm}: 检测失败: {e}")

        if not direction_scores:
            self.logger.debug(f"[DEBUG] 没有有效的方向评分，跳过信号生成")
            return None

        self.logger.debug(f"[DEBUG] 收集到 {len(direction_scores)} 个有效方向评分: "
                        f"{[s.algorithm for s in direction_scores]}")

        # 2. 方向协调计算
        consensus = self.direction_coordinator.calculate_consensus(direction_scores)

        self.logger.debug(f"[DEBUG] 方向共识结果: {consensus.direction}, "
                        f"共识强度={consensus.consensus_score:.3f}, "
                        f"置信度={consensus.confidence:.3f}, "
                        f"买入算法={consensus.buy_algorithms}, "
                        f"卖出算法={consensus.sell_algorithms}, "
                        f"冲突数={consensus.conflicting_count}")

        # 3. 多重确认机制集成方向协调
        if self.require_multiple_confirmation:
            # 添加到确认窗口
            self._add_directional_signal_to_window(symbol, consensus, tick, current_time)

            # 检查确认窗口内的信号数量
            if not self._check_window_direction_consensus(symbol, current_time):
                self.logger.debug(f"[DEBUG] 确认窗口内信号不足，跳过")
                return None

        # 4. 生成信号
        if consensus.direction != "HOLD":
            return self._create_direction_aware_signal(tick, consensus, symbol)
        else:
            self.logger.debug(f"[DEBUG] 方向共识为HOLD，不生成信号")
            return None

    def _add_directional_signal_to_window(self, symbol: str, consensus: DirectionConsensus, tick: TickData, timestamp: float):
        """添加方向信号到确认窗口"""

        if symbol not in self.pending_signals:
            self.pending_signals[symbol] = []

        # 清理过期信号
        self._clean_expired_signals(timestamp, symbol)

        # 添加新的共识信号（默认为未使用）
        self.pending_signals[symbol].append({
            'consensus': consensus,
            'tick': tick,
            'timestamp': timestamp,
            'used': False  # 🔥 添加使用状态标记，默认为未使用
        })

        self.logger.debug(f"[DEBUG] 添加方向信号到确认窗口 {symbol}: "
                        f"方向={consensus.direction}, "
                        f"窗口内信号数={len(self.pending_signals[symbol])}")

    def _check_window_direction_consensus(self, symbol: str, current_time: float) -> bool:
        """检查确认窗口内的方向共识"""

        if symbol not in self.pending_signals:
            return False

        # 清理过期信号
        self._clean_expired_signals(current_time, symbol)

        # 🔥 只计算未使用的信号，防止重复计数
        unused_signals = [s for s in self.pending_signals[symbol] if not s.get('used', False)]

        # 检查未使用信号数量是否达到最小确认数
        if len(unused_signals) < self.min_confirmation_count:
            self.logger.debug(f"[DEBUG] 未使用信号不足 {symbol}: "
                            f"{len(unused_signals)}/{self.min_confirmation_count}")
            return False

        # 分析窗口内的方向一致性（仅使用未使用信号）
        buy_votes = sum(1 for s in unused_signals if s['consensus'].direction == "BUY")
        sell_votes = sum(1 for s in unused_signals if s['consensus'].direction == "SELL")
        total_votes = buy_votes + sell_votes

        if total_votes == 0:
            self.logger.debug(f"[DEBUG] 没有有效方向信号 {symbol}")
            return False

        # 计算窗口内的方向一致性
        direction_consistency = max(buy_votes, sell_votes) / total_votes

        # 至少需要70%的方向一致性
        min_consistency = 0.7

        result = direction_consistency >= min_consistency

        # 🔥 如果通过检查，标记这些信号为已使用
        if result:
            for signal in unused_signals:
                signal['used'] = True
            self.logger.debug(f"[DEBUG] 标记 {len(unused_signals)} 个信号为已使用 {symbol}")

        self.logger.debug(f"[DEBUG] 窗口方向共识检查 {symbol}: "
                        f"未使用信号={len(unused_signals)}, "
                        f"买入={buy_votes}, 卖出={sell_votes}, "
                        f"一致性={direction_consistency:.3f}, "
                        f"阈值={min_consistency:.3f}, "
                        f"通过={result}")

        return result

    def _create_direction_aware_signal(self, tick: TickData, consensus: DirectionConsensus, symbol: str) -> Signal:
        """创建基于方向共识的交易信号"""

        # 根据共识方向确定信号类型
        if consensus.direction == "BUY":
            signal_type = SignalType.OPEN_LONG
            action = "DIRECTION_COORDINATED_BUY"
        elif consensus.direction == "SELL":
            signal_type = SignalType.OPEN_SHORT
            action = "DIRECTION_COORDINATED_SELL"
        else:
            return None

        # 构建原因描述
        algorithms_info = []
        if consensus.buy_algorithms:
            algorithms_info.append(f"买入算法:{','.join(consensus.buy_algorithms)}")
        if consensus.sell_algorithms:
            algorithms_info.append(f"卖出算法:{','.join(consensus.sell_algorithms)}")

        reason = f"方向协调共识({action}):{','.join(algorithms_info)}"

        # 计算信号强度 - 基于共识强度和置信度
        signal_strength = (consensus.consensus_score + consensus.confidence) / 2.0

        # 🔧 修复：计算建议数量，避免0数量信号
        calculated_amount = self.calculate_position_size(tick, signal_strength, symbol)

        signal = Signal(
            signal_type=signal_type,
            symbol=symbol,
            amount=calculated_amount,  # 🔧 修复：使用计算出的数量
            price=tick.price,
            confidence=signal_strength,
            reason=reason,
            metadata={
                'consensus': consensus,
                'action': action,
                'direction_coordination': True,
                'detection_algorithms': consensus.buy_algorithms + consensus.sell_algorithms,
                'conflicting_algorithms': consensus.conflicting_count,
                'tick_data': {
                    'price': tick.price,
                    'volume': tick.volume,
                    'timestamp': tick.timestamp,
                    'price_change': tick.price_change
                }
            }
        )

        # 🔥 发送webhook通知 - 修复缺失的webhook调用
        if self.enable_webhook and self.webhook:
            self._send_webhook_notification(signal, tick, reason, action, symbol)

        return signal