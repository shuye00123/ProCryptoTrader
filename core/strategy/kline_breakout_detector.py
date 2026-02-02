"""
基于1秒K线数据的快速突破检测器 (Layer 1)

重新设计：纯粹的1s K线快速检测，不依赖更高时间框架数据

核心逻辑：
- 成交量激增检测：1s成交量 vs 历史1s平均成交量
- 价格动量检测：价格变化率和加速度
- 连续变动检测：连续同向价格变动
- 价格路径突破：基于1s数据的局部支撑阻力

注意：这是Layer 1检测器，只负责生成初步信号。
      多时间框架技术指标确认由Layer 2 (MultiTimeframeConfirmator) 负责。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
from collections import deque
import pandas as pd
import numpy as np

from core.strategy.base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


# ============================================================================
# 类常量定义（替代魔术数字）
# ============================================================================

class DetectionConstants:
    """检测器常量定义"""

    # 成交量检测权重
    VOLUME_SCORE_WEIGHT = 0.30
    VOLUME_HALF_THRESHOLD_RATIO = 0.5
    VOLUME_FULL_THRESHOLD_MULTIPLIER = 1.0
    VOLUME_PARTIAL_THRESHOLD_MULTIPLIER = 0.5

    # 动量检测权重
    MOMENTUM_SCORE_WEIGHT = 0.30
    MOMENTUM_CHANGE_SCORE = 0.3
    MOMENTUM_DIRECTION_SCORE = 0.3
    MOMENTUM_ACCELERATION_SCORE = 0.4

    # 连续变动检测权重
    CONSECUTIVE_SCORE_WEIGHT = 0.20
    CONSECUTIVE_FULL_THRESHOLD_RATIO = 1.0
    CONSECUTIVE_PARTIAL_THRESHOLD_RATIO = 0.6

    # 路径突破检测权重
    PATH_SCORE_WEIGHT = 0.20
    PATH_FULL_SCORE = 1.0
    PATH_PARTIAL_SCORE = 0.5
    PATH_PROXIMITY_MULTIPLIER = 5.0

    # 信号生成条件
    MIN_STRONG_DETECTIONS = 2
    DETECTION_SCORE_THRESHOLD = 0.5

    # 默认值
    DEFAULT_WINDOW_SIZE = 200
    DEFAULT_VOLUME_SURGE_THRESHOLD = 3.0
    DEFAULT_VOLUME_WINDOW = 50
    DEFAULT_MOMENTUM_THRESHOLD = 0.0005
    DEFAULT_MOMENTUM_WINDOW = 10
    DEFAULT_CONSECUTIVE_MOVES_THRESHOLD = 5
    DEFAULT_MIN_MOVE_THRESHOLD = 0.0001
    DEFAULT_PATH_WINDOW = 20
    DEFAULT_PATH_BREAKOUT_THRESHOLD = 0.0002
    DEFAULT_MIN_SIGNAL_STRENGTH = 0.6
    DEFAULT_SIGNAL_AMOUNT = 0.01


# ============================================================================
# 数据结构定义
# ============================================================================


@dataclass
class Kline:
    """1秒K线数据结构"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float                  # ✅ 真实1秒K线的总成交量
    timestamp: datetime = None

    def __post_init__(self):
        # 计算价格变化
        self.price_change = self.close - self.open
        if self.open != 0:
            self.price_change_pct = (self.price_change / self.open) * 100
        else:
            self.price_change_pct = 0.0


class KlineBreakoutDetector:
    """
    基于1秒K线的快速突破检测器 (Layer 1)

    重新设计：纯粹的1s快速检测，不依赖更高时间框架数据

    核心特性：
    - 成交量激增：检测异常放量
    - 价格动量：检测价格加速度
    - 连续变动：检测连续同向变动
    - 路径突破：检测局部支撑阻力
    """

    def __init__(self, config: Dict):
        """
        初始化1秒K线快速突破检测器

        Args:
            config: 配置字典
                - volume_surge_threshold: 成交量激增阈值（默认3.0x）
                - volume_window: 成交量平均窗口（默认50条）
                - momentum_threshold: 价格动量阈值（默认0.05%）
                - momentum_window: 动量计算窗口（默认10条）
                - consecutive_moves_threshold: 连续变动次数（默认5次）
                - path_window: 路径检测窗口（默认20条）
                - min_signal_strength: 最小信号强度（默认0.6）
        """
        # 成交量分析参数
        self.volume_surge_threshold = config.get(
            'volume_surge_threshold',
            DetectionConstants.DEFAULT_VOLUME_SURGE_THRESHOLD
        )
        self.volume_window = config.get(
            'volume_window',
            DetectionConstants.DEFAULT_VOLUME_WINDOW
        )

        # 价格动量参数
        self.momentum_threshold = config.get(
            'momentum_threshold',
            DetectionConstants.DEFAULT_MOMENTUM_THRESHOLD
        )
        self.momentum_window = config.get(
            'momentum_window',
            DetectionConstants.DEFAULT_MOMENTUM_WINDOW
        )

        # 连续变动参数
        self.consecutive_moves_threshold = config.get(
            'consecutive_moves_threshold',
            DetectionConstants.DEFAULT_CONSECUTIVE_MOVES_THRESHOLD
        )
        self.min_move_threshold = config.get(
            'min_move_threshold',
            DetectionConstants.DEFAULT_MIN_MOVE_THRESHOLD
        )

        # 路径突破参数
        self.path_window = config.get(
            'path_window',
            DetectionConstants.DEFAULT_PATH_WINDOW
        )
        self.path_breakout_threshold = config.get(
            'path_breakout_threshold',
            DetectionConstants.DEFAULT_PATH_BREAKOUT_THRESHOLD
        )

        # 信号强度参数
        self.min_signal_strength = config.get(
            'min_signal_strength',
            DetectionConstants.DEFAULT_MIN_SIGNAL_STRENGTH
        )

        # 历史数据缓冲（用于计算指标）
        self.window_size = max(
            self.volume_window,
            self.momentum_window,
            self.consecutive_moves_threshold + 1,
            self.path_window
        )
        self.kline_history: Dict[str, deque] = {}

        logger.info("[KlineBreakoutDetector] 1s快速突破检测器初始化完成")
        logger.info("  职责: Layer 1 - 纯粹的1s K线快速检测")
        logger.info(f"  成交量阈值: {self.volume_surge_threshold}x")
        logger.info(f"  动量阈值: {self.momentum_threshold*100:.3f}%")
        logger.info(f"  连续变动: {self.consecutive_moves_threshold}次")
        logger.info(f"  路径窗口: {self.path_window}条")

    # ========================================================================
    # 输入验证方法
    # ========================================================================

    def _validate_input(self, kline: Kline, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        验证输入参数的有效性

        Args:
            kline: 1秒K线数据
            symbol: 交易对符号

        Returns:
            (is_valid, error_message): 验证结果和错误消息
        """
        if kline is None:
            return False, "Kline数据为空"

        if not symbol or not isinstance(symbol, str):
            return False, f"无效的交易对符号: {symbol}"

        # 验证价格数据
        if not all([
            isinstance(kline.open, (int, float)) and kline.open > 0,
            isinstance(kline.high, (int, float)) and kline.high > 0,
            isinstance(kline.low, (int, float)) and kline.low > 0,
            isinstance(kline.close, (int, float)) and kline.close > 0,
        ]):
            return False, f"价格数据无效: O={kline.open}, H={kline.high}, L={kline.low}, C={kline.close}"

        # 验证OHLC逻辑
        if kline.high < kline.low:
            return False, f"OHLC逻辑错误: high({kline.high}) < low({kline.low})"

        if kline.high < max(kline.open, kline.close):
            return False, f"OHLC逻辑错误: high({kline.high}) < max(open, close)"

        if kline.low > min(kline.open, kline.close):
            return False, f"OHLC逻辑错误: low({kline.low}) > min(open, close)"

        # 验证成交量
        if not isinstance(kline.volume, (int, float)) or kline.volume < 0:
            return False, f"成交量无效: {kline.volume}"

        return True, None

    def _has_sufficient_data(self, symbol: str, required_length: Optional[int] = None) -> bool:
        """
        检查是否有足够的历史数据

        Args:
            symbol: 交易对符号
            required_length: 需要的最小数据长度，默认使用momentum_window

        Returns:
            是否有足够数据
        """
        if required_length is None:
            required_length = self.momentum_window

        history = self.kline_history.get(symbol)
        return history is not None and len(history) >= required_length

    def detect_breakout(
        self,
        kline: Kline,
        symbol: str,
        higher_timeframe_data: Optional[Dict[str, pd.DataFrame]] = None
    ) -> Optional[Signal]:
        """
        检测1秒K线快速突破 (Layer 1)

        重要：此方法不再使用higher_timeframe_data参数（保留仅为兼容性）
                  更高时间框架的技术指标确认由Layer 2负责

        Args:
            kline: 1秒K线数据
            symbol: 交易对符号
            higher_timeframe_data: 已废弃，不再使用（保留仅为兼容性）

        Returns:
            Signal: 初步突破信号（如果检测到突破），否则None
        """
        try:
            # 1. 输入验证
            is_valid, error_msg = self._validate_input(kline, symbol)
            if not is_valid:
                logger.warning(f"[{symbol}] 输入验证失败: {error_msg}")
                return None

            # 2. 更新K线历史
            self._update_kline_history(kline, symbol)

            # 3. 检查数据充足性
            if not self._has_sufficient_data(symbol):
                return None

            # 4. 计算各维度检测得分
            detection_scores = self._calculate_detection_scores(kline, symbol)

            # 5. 计算综合信号强度
            signal_strength = self._calculate_signal_strength(detection_scores)

            # 6. 判断是否生成信号
            if self._should_generate_signal(detection_scores, signal_strength):
                return self._create_preliminary_signal(
                    kline, symbol, signal_strength, detection_scores
                )

            return None

        except Exception as e:
            logger.error(f"[{symbol}] Layer 1检测失败: {e}")
            return None

    # ========================================================================
    # 检测得分计算方法
    # ========================================================================

    def _calculate_detection_scores(
        self,
        kline: Kline,
        symbol: str
    ) -> Dict[str, float]:
        """
        计算各维度的检测得分

        Args:
            kline: 1秒K线数据
            symbol: 交易对符号

        Returns:
            包含各维度得分的字典
        """
        return {
            'volume_score': self._detect_volume_surge(kline, symbol),
            'momentum_score': self._detect_price_momentum(kline, symbol),
            'consecutive_score': self._detect_consecutive_moves(kline, symbol),
            'path_score': self._detect_path_breakout(kline, symbol)
        }

    def _calculate_signal_strength(self, detection_scores: Dict[str, float]) -> float:
        """
        计算综合信号强度

        Args:
            detection_scores: 各维度检测得分

        Returns:
            综合信号强度 [0, 1]
        """
        signal_strength = (
            detection_scores['volume_score'] * DetectionConstants.VOLUME_SCORE_WEIGHT +
            detection_scores['momentum_score'] * DetectionConstants.MOMENTUM_SCORE_WEIGHT +
            detection_scores['consecutive_score'] * DetectionConstants.CONSECUTIVE_SCORE_WEIGHT +
            detection_scores['path_score'] * DetectionConstants.PATH_SCORE_WEIGHT
        )
        # 添加total_strength到scores中以便后续使用
        detection_scores['total_strength'] = signal_strength
        return signal_strength

    def _should_generate_signal(
        self,
        detection_scores: Dict[str, float],
        signal_strength: float
    ) -> bool:
        """
        判断是否应该生成信号

        Args:
            detection_scores: 各维度检测得分
            signal_strength: 综合信号强度

        Returns:
            是否生成信号
        """
        # 检查最小信号强度
        if signal_strength < self.min_signal_strength:
            return False

        # 检查强检测数量（至少需要2个检测方法得分>0.5）
        strong_detections = sum([
            detection_scores['volume_score'] > DetectionConstants.DETECTION_SCORE_THRESHOLD,
            detection_scores['momentum_score'] > DetectionConstants.DETECTION_SCORE_THRESHOLD,
            detection_scores['consecutive_score'] > DetectionConstants.DETECTION_SCORE_THRESHOLD,
            detection_scores['path_score'] > DetectionConstants.DETECTION_SCORE_THRESHOLD
        ])

        return strong_detections >= DetectionConstants.MIN_STRONG_DETECTIONS

    def _update_kline_history(self, kline: Kline, symbol: str):
        """更新K线历史数据"""
        if symbol not in self.kline_history:
            self.kline_history[symbol] = deque(maxlen=self.window_size)

        self.kline_history[symbol].append(kline)

    def _detect_volume_surge(self, kline: Kline, symbol: str) -> float:
        """
        检测成交量激增

        Returns:
            评分 [0, 1]
        """
        try:
            history = self.kline_history.get(symbol)
            if not history or len(history) < self.volume_window:
                return 0.0

            # 计算历史平均成交量
            recent_volumes = [k.volume for k in list(history)[-self.volume_window:]]
            avg_volume = np.mean(recent_volumes)

            if avg_volume == 0:
                return 0.0

            # 当前成交量倍数
            volume_ratio = kline.volume / avg_volume

            # 评分：使用阈值平滑
            if volume_ratio >= self.volume_surge_threshold:
                # 达到阈值倍数 = 1.0分
                score = DetectionConstants.VOLUME_FULL_THRESHOLD_MULTIPLIER
            elif volume_ratio >= self.volume_surge_threshold * DetectionConstants.VOLUME_HALF_THRESHOLD_RATIO:
                # 达到一半阈值 = 0.5分
                score = DetectionConstants.VOLUME_PARTIAL_THRESHOLD_MULTIPLIER
            else:
                # 低于阈值 = 0分
                score = 0.0

            if score > 0:
                logger.debug(f"[{symbol}] 成交量激增: {volume_ratio:.2f}x (评分:{score:.2f})")

            return score

        except Exception as e:
            logger.error(f"[{symbol}] 成交量检测失败: {e}")
            return 0.0

    def _detect_price_momentum(self, kline: Kline, symbol: str) -> float:
        """
        检测价格动量

        计算短期动量和加速度

        Returns:
            评分 [0, 1]
        """
        try:
            history = self.kline_history.get(symbol)
            if not history or len(history) < self.momentum_window:
                return 0.0

            # 转换为列表
            klines = list(history)

            # 计算短期价格变化
            if len(klines) >= 3:
                # 1期变化
                change_1 = (klines[-1].close - klines[-2].close) / klines[-2].close

                # 3期平均变化（动量）
                change_3 = (klines[-1].close - klines[-4].close) / klines[-4].close if len(klines) >= 4 else change_1

                # 加速度（动量的变化）
                if len(klines) >= 8:
                    momentum_1 = (klines[-4].close - klines[-5].close) / klines[-5].close
                    momentum_2 = (klines[-1].close - klines[-4].close) / klines[-4].close
                    acceleration = momentum_2 - momentum_1
                else:
                    acceleration = 0

                # 评分逻辑
                score = 0.0

                # 大幅价格变化
                if abs(change_1) > self.momentum_threshold:
                    score += DetectionConstants.MOMENTUM_CHANGE_SCORE

                # 动量方向一致
                if (change_1 > 0 and change_3 > 0) or (change_1 < 0 and change_3 < 0):
                    score += DetectionConstants.MOMENTUM_DIRECTION_SCORE

                # 加速度支持
                if (change_1 > 0 and acceleration > 0) or (change_1 < 0 and acceleration < 0):
                    score += DetectionConstants.MOMENTUM_ACCELERATION_SCORE

                score = min(score, 1.0)

                if score > 0.5:
                    logger.debug(f"[{symbol}] 价格动量: 变化={change_1*100:.3f}%, "
                               f"动量={change_3*100:.3f}%, 加速={acceleration*100:.3f}% "
                               f"(评分:{score:.2f})")

                return score

            return 0.0

        except Exception as e:
            logger.error(f"[{symbol}] 动量检测失败: {e}")
            return 0.0

    def _detect_consecutive_moves(self, kline: Kline, symbol: str) -> float:
        """
        检测连续同向价格变动

        Returns:
            评分 [0, 1]
        """
        try:
            history = self.kline_history.get(symbol)
            if not history or len(history) < self.consecutive_moves_threshold + 1:
                return 0.0

            klines = list(history)

            # 统计连续同向变动次数
            consecutive_up = 0
            consecutive_down = 0

            for i in range(len(klines) - 1, -1, -1):
                change = klines[i].close - klines[i].open

                if change > 0 and self.min_move_threshold > 0:
                    if change / klines[i].open > self.min_move_threshold:
                        consecutive_up += 1
                        consecutive_down = 0
                    else:
                        break
                elif change < 0 and self.min_move_threshold > 0:
                    if abs(change) / klines[i].open > self.min_move_threshold:
                        consecutive_down += 1
                        consecutive_up = 0
                    else:
                        break
                else:
                    break

            consecutive_moves = max(consecutive_up, consecutive_down)

            # 评分
            if consecutive_moves >= self.consecutive_moves_threshold:
                # 达到阈值 = 1.0分
                score = DetectionConstants.CONSECUTIVE_FULL_THRESHOLD_RATIO
            elif consecutive_moves >= self.consecutive_moves_threshold * DetectionConstants.CONSECUTIVE_PARTIAL_THRESHOLD_RATIO:
                # 达到60%阈值 = 0.5分
                score = 0.5
            else:
                score = 0.0

            if score > 0:
                logger.debug(f"[{symbol}] 连续变动: {consecutive_moves}次 "
                           f"{'向上' if consecutive_up > consecutive_down else '向下'} "
                           f"(评分:{score:.2f})")

            return score

        except Exception as e:
            logger.error(f"[{symbol}] 连续变动检测失败: {e}")
            return 0.0

    def _detect_path_breakout(self, kline: Kline, symbol: str) -> float:
        """
        检测价格路径突破（局部支撑阻力）

        基于最近N条1s K线检测局部支撑阻力位突破

        Returns:
            评分 [0, 1]
        """
        try:
            history = self.kline_history.get(symbol)
            if not history or len(history) < self.path_window:
                return 0.0

            klines = list(history)[-self.path_window:]

            # 计算局部高低点
            highs = [k.high for k in klines]
            lows = [k.low for k in klines]

            local_high = max(highs[:-1]) if len(highs) > 1 else klines[-1].high
            local_low = min(lows[:-1]) if len(lows) > 1 else klines[-1].low

            current_price = kline.close

            score = 0.0

            # 突破局部高点
            if current_price > local_high * (1 + self.path_breakout_threshold):
                score = DetectionConstants.PATH_FULL_SCORE
                logger.debug(f"[{symbol}] 路径突破: 突破局部高点 {local_high:.6f}")

            # 突破局部低点
            elif current_price < local_low * (1 - self.path_breakout_threshold):
                score = DetectionConstants.PATH_FULL_SCORE
                logger.debug(f"[{symbol}] 路径突破: 突破局部低点 {local_low:.6f}")

            # 接近关键位（0.5分）
            elif abs(current_price - local_high) / local_high < self.path_breakout_threshold * DetectionConstants.PATH_PROXIMITY_MULTIPLIER:
                score = DetectionConstants.PATH_PARTIAL_SCORE
            elif abs(current_price - local_low) / local_low < self.path_breakout_threshold * DetectionConstants.PATH_PROXIMITY_MULTIPLIER:
                score = DetectionConstants.PATH_PARTIAL_SCORE

            return score

        except Exception as e:
            logger.error(f"[{symbol}] 路径突破检测失败: {e}")
            return 0.0

    def _create_preliminary_signal(
        self,
        kline: Kline,
        symbol: str,
        strength: float,
        details: Dict
    ) -> Signal:
        """
        创建初步突破信号 (Layer 1)

        Args:
            kline: 1秒K线
            symbol: 交易对
            strength: 信号强度
            details: 检测详情

        Returns:
            Signal: 初步信号
        """
        # 确定方向（基于价格变化）
        if kline.price_change > 0:
            signal_type = SignalType.OPEN_LONG
            direction = "BUY"
        else:
            signal_type = SignalType.OPEN_SHORT
            direction = "SELL"

        # 构建原因描述
        reasons = []
        if details['volume_score'] > 0.5:
            reasons.append("成交量激增")
        if details['momentum_score'] > 0.5:
            reasons.append("价格动量")
        if details['consecutive_score'] > 0.5:
            reasons.append("连续变动")
        if details['path_score'] > 0.5:
            reasons.append("路径突破")

        reason = f"Layer 1快速突破: {', '.join(reasons)}, 强度={strength:.2f}"

        logger.info(f"[{symbol}] ⚡ Layer 1初步信号: {direction}, "
                   f"强度={strength:.2f}, "
                   f"价格={kline.close:.6f}, "
                   f"变化={kline.price_change_pct:.3f}%")

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=kline.close,
            amount=DetectionConstants.DEFAULT_SIGNAL_AMOUNT,  # 简化版，后续由策略计算
            confidence=strength,
            metadata={
                'reason': reason,
                'layer': 'layer1',
                'kline_timestamp': kline.timestamp.isoformat(),
                'open': kline.open,
                'high': kline.high,
                'low': kline.low,
                'close': kline.close,
                'volume': kline.volume,
                'price_change_pct': kline.price_change_pct,
                'detection_details': details
            }
        )

    def get_detector_status(self, symbol: str) -> Dict[str, Any]:
        """获取检测器状态（用于监控）"""
        history = self.kline_history.get(symbol)

        if not history:
            return {
                'symbol': symbol,
                'window_size': self.window_size,
                'current_size': 0,
                'ready': False
            }

        klines = list(history)

        # 计算当前统计信息
        volumes = [k.volume for k in klines]
        closes = [k.close for k in klines]

        return {
            'symbol': symbol,
            'window_size': self.window_size,
            'current_size': len(klines),
            'ready': len(klines) >= self.momentum_window,
            'latest_price': klines[-1].close if klines else None,
            'price_mean': np.mean(closes) if closes else None,
            'price_std': np.std(closes) if len(closes) > 1 else None,
            'volume_mean': np.mean(volumes) if volumes else None,
            'latest_volume': klines[-1].volume if klines else None,
            'layer': 'layer1_fast_detection'
        }
