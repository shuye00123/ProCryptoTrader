"""
基于1秒K线数据的量价突破检测器

核心逻辑：
- 量能分析：1秒K线成交量 vs 更高时间框架(15m/1h)平均成交量
- 价格突破：1秒K线价格 vs 更高时间框架(15m/1h)布林带上/下沿
- 支撑阻力：1秒K线价格 vs 更高时间框架(15m/1h)关键支撑/阻力位
- 综合判断：放量 + 突破 = 信号
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from core.strategy.base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


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
    基于1秒K线的量价突破检测器

    核心特性：
    - 量能分析：检测成交量异常放大
    - 价格突破：检测突破更高时间框架的关键位
    - 支撑阻力：检测突破支撑/阻力位
    """

    def __init__(self, config: Dict):
        """
        初始化1秒K线量价突破检测器

        Args:
            config: 配置字典
                - volume_surge_threshold: 成交量激增阈值（默认3.0x）
                - volume_window: 成交量平均窗口（默认50条）
                - bb_breakout_threshold: 布林带突破阈值（默认突破到带外0.2%）
                - support_resistance_window: 支撑阻力计算窗口（默认100条）
                - min_signal_strength: 最小信号强度（默认0.7）
        """
        # 量能分析参数
        self.volume_surge_threshold = config.get('volume_surge_threshold', 3.0)  # 3倍成交量
        self.volume_window = config.get('volume_window', 50)  # 50条K线平均

        # 价格突破参数
        self.bb_breakout_threshold = config.get('bb_breakout_threshold', 0.002)  # 0.2%突破缓冲
        self.bb_period = config.get('bb_period', 20)  # 布林带周期
        self.bb_std = config.get('bb_std', 2.0)  # 布林带标准差倍数

        # 支撑阻力参数
        self.support_resistance_window = config.get('support_resistance_window', 100)
        self.sr_touch_threshold = config.get('sr_touch_threshold', 0.001)  # 0.1%接触阈值

        # 信号强度参数
        self.min_signal_strength = config.get('min_signal_strength', 0.7)

        # 历史数据缓冲（用于计算指标）
        self.kline_history: Dict[str, list] = {}

        logger.info(f"[KlineBreakoutDetector] 量价突破检测器初始化完成")
        logger.info(f"  成交量阈值: {self.volume_surge_threshold}x")
        logger.info(f"  布林带参数: {self.bb_period}周期, {self.bb_std}倍标准差")
        logger.info(f"  支撑阻力窗口: {self.support_resistance_window}")

    def detect_breakout(
        self,
        kline: Kline,
        symbol: str,
        higher_timeframe_data: Optional[Dict[str, pd.DataFrame]] = None
    ) -> Optional[Signal]:
        """
        检测1秒K线量价突破

        Args:
            kline: 1秒K线数据
            symbol: 交易对符号
            higher_timeframe_data: 更高时间框架的数据
                {
                    '15m': DataFrame with OHLCV,
                    '1h': DataFrame with OHLCV
                }

        Returns:
            Signal: 突破信号（如果检测到突破），否则None
        """
        try:
            # 更新K线历史
            self._update_kline_history(kline, symbol)

            # 检查是否有足够数据
            if len(self.kline_history.get(symbol, [])) < self.volume_window:
                return None

            # 计算量能指标
            volume_analysis = self._analyze_volume_surge(kline, symbol)

            # 计算价格突破（使用更高时间框架数据）
            price_breakout = self._analyze_price_breakout(
                kline, symbol, higher_timeframe_data
            )

            # 综合判断
            signal_strength = 0.0
            breakout_reasons = []

            # 1. 量能分析（权重40%）
            if volume_analysis['is_surge']:
                signal_strength += 0.4
                breakout_reasons.append(
                    f"成交量激增{volume_analysis['volume_ratio']:.2f}x"
                )

            # 2. 布林带突破（权重35%）
            if price_breakout['bb_breakout']:
                signal_strength += 0.35
                breakout_reasons.append(
                    f"突破{price_breakout['bb_timeframe']}布林带"
                    f"({price_breakout['bb_position']})"
                )

            # 3. 支撑阻力突破（权重25%）
            if price_breakout['sr_breakout']:
                signal_strength += 0.25
                breakout_reasons.append(
                    f"突破{price_breakout['sr_type']}"
                    f"({price_breakout['sr_level']:.6f})"
                )

            # 判断是否生成信号
            if signal_strength >= self.min_signal_strength and len(breakout_reasons) >= 2:
                return self._create_signal(
                    kline, symbol, signal_strength, breakout_reasons,
                    volume_analysis, price_breakout
                )

            return None

        except Exception as e:
            logger.error(f"检测突破时发生错误: {e}")
            return None

    def _update_kline_history(self, kline: Kline, symbol: str):
        """更新K线历史数据"""
        if symbol not in self.kline_history:
            self.kline_history[symbol] = []

        self.kline_history[symbol].append(kline)

        # 保持历史长度在合理范围（最多1000条）
        if len(self.kline_history[symbol]) > 1000:
            self.kline_history[symbol] = self.kline_history[symbol][-1000:]

    def _analyze_volume_surge(self, kline: Kline, symbol: str) -> Dict:
        """
        分析成交量激增

        ✅ 修复：直接使用volume字段（真实1秒K线成交量）

        Args:
            kline: 1秒K线
            symbol: 交易对符号

        Returns:
            {
                'is_surge': bool,
                'volume_ratio': float,
                'current_volume': float,
                'avg_volume': float
            }
        """
        try:
            klines = self.kline_history[symbol]

            # ✅ 直接使用volume字段（真实1秒K线成交量）
            recent_volumes = [k.volume for k in klines[-self.volume_window:]]
            avg_volume = np.mean(recent_volumes) if recent_volumes else 0

            # 当前成交量（直接使用volume字段）
            current_vol = kline.volume

            if avg_volume > 0:
                volume_ratio = current_vol / avg_volume
            else:
                volume_ratio = 1.0

            # ✅ 使用3.0x阈值（经过验证的最优参数）
            is_surge = volume_ratio >= 3.0

            return {
                'is_surge': is_surge,
                'volume_ratio': volume_ratio,
                'current_volume': current_vol,
                'avg_volume': avg_volume
            }

        except Exception as e:
            logger.error(f"分析成交量时出错: {e}")
            return {
                'is_surge': False,
                'volume_ratio': 0.0,
                'current_volume': 0.0,
                'avg_volume': 0.0
            }

    def _analyze_price_breakout(
        self,
        kline: Kline,
        symbol: str,
        higher_tf_data: Optional[Dict[str, pd.DataFrame]]
    ) -> Dict:
        """
        分析价格突破（布林带、支撑阻力）

        Args:
            kline: 1秒K线
            symbol: 交易对符号
            higher_tf_data: 更高时间框架数据

        Returns:
            {
                'bb_breakout': bool,
                'bb_timeframe': str ('15m', '1h', or '1s'),
                'bb_position': str ('upper', 'lower', or None),
                'sr_breakout': bool,
                'sr_type': str ('resistance' or 'support'),
                'sr_level': float
            }
        """
        result = {
            'bb_breakout': False,
            'bb_timeframe': None,
            'bb_position': None,
            'sr_breakout': False,
            'sr_type': None,
            'sr_level': None
        }

        try:
            # 优先使用更高时间框架数据
            if higher_tf_data:
                # 检查15m布林带突破
                if '15m' in higher_tf_data:
                    bb_15m = self._check_bb_breakout(
                        kline, higher_tf_data['15m'], '15m'
                    )
                    if bb_15m['is_breakout']:
                        result['bb_breakout'] = True
                        result['bb_timeframe'] = '15m'
                        result['bb_position'] = bb_15m['position']
                        logger.debug(f"[{symbol}] 检测到15m布林带突破: {bb_15m}")

                # 如果15m没有突破，检查1h
                if not result['bb_breakout'] and '1h' in higher_tf_data:
                    bb_1h = self._check_bb_breakout(
                        kline, higher_tf_data['1h'], '1h'
                    )
                    if bb_1h['is_breakout']:
                        result['bb_breakout'] = True
                        result['bb_timeframe'] = '1h'
                        result['bb_position'] = bb_1h['position']
                        logger.debug(f"[{symbol}] 检测到1h布林带突破: {bb_1h}")

                # 检查支撑阻力位突破
                if '15m' in higher_tf_data:
                    sr_15m = self._check_sr_breakout(
                        kline, higher_tf_data['15m']
                    )
                    if sr_15m['is_breakout']:
                        result['sr_breakout'] = True
                        result['sr_type'] = sr_15m['type']
                        result['sr_level'] = sr_15m['level']
                        logger.debug(f"[{symbol}] 检测到15m支撑阻力突破: {sr_15m}")

            # 如果没有更高时间框架数据，使用1s历史数据计算
            if not result['bb_breakout'] and symbol in self.kline_history:
                klines = self.kline_history[symbol]
                if len(klines) >= self.bb_period:
                    # 构建1s数据的DataFrame
                    df_1s = pd.DataFrame([
                        {
                            'open': k.open,
                            'high': k.high,
                            'low': k.low,
                            'close': k.close,
                            'volume': k.volume
                        }
                        for k in klines
                    ])

                    bb_1s = self._check_bb_breakout(kline, df_1s, '1s')
                    if bb_1s['is_breakout']:
                        result['bb_breakout'] = True
                        result['bb_timeframe'] = '1s'
                        result['bb_position'] = bb_1s['position']
                        logger.debug(f"[{symbol}] 检测到1s布林带突破: {bb_1s}")

        except Exception as e:
            logger.error(f"分析价格突破时出错: {e}")

        return result

    def _check_bb_breakout(
        self,
        kline: Kline,
        df: pd.DataFrame,
        timeframe: str
    ) -> Dict:
        """
        检查布林带突破

        Args:
            kline: 1秒K线
            df: 更高时间框架的K线数据
            timeframe: 时间框架标识

        Returns:
            {
                'is_breakout': bool,
                'position': str ('upper' or 'lower'),
                'upper': float,
                'lower': float,
                'close': float
            }
        """
        try:
            if len(df) < self.bb_period:
                return {'is_breakout': False}

            # 计算布林带
            close = df['close']
            bb_middle = close.rolling(window=self.bb_period).mean()
            bb_std = close.rolling(window=self.bb_period).std()
            bb_upper = bb_middle + self.bb_std * bb_std
            bb_lower = bb_middle - self.bb_std * bb_std

            upper = bb_upper.iloc[-1]
            lower = bb_lower.iloc[-1]
            current_price = kline.close

            # 检查是否突破上轨
            if current_price > upper * (1 + self.bb_breakout_threshold):
                return {
                    'is_breakout': True,
                    'position': 'upper',
                    'upper': upper,
                    'lower': lower,
                    'close': current_price
                }

            # 检查是否突破下轨
            if current_price < lower * (1 - self.bb_breakout_threshold):
                return {
                    'is_breakout': True,
                    'position': 'lower',
                    'upper': upper,
                    'lower': lower,
                    'close': current_price
                }

            return {'is_breakout': False}

        except Exception as e:
            logger.error(f"检查布林带突破时出错: {e}")
            return {'is_breakout': False}

    def _check_sr_breakout(self, kline: Kline, df: pd.DataFrame) -> Dict:
        """
        检查支撑阻力位突破

        Args:
            kline: 1秒K线
            df: 更高时间框架的K线数据

        Returns:
            {
                'is_breakout': bool,
                'type': str ('resistance' or 'support'),
                'level': float
            }
        """
        try:
            window = min(len(df), self.support_resistance_window)
            if window < 20:
                return {'is_breakout': False}

            # 计算关键支撑阻力位
            recent_highs = df['high'].iloc[-window:].max()
            recent_lows = df['low'].iloc[-window:].min()

            current_price = kline.close

            # 检查阻力位突破
            if current_price > recent_highs * (1 + self.sr_touch_threshold):
                return {
                    'is_breakout': True,
                    'type': 'resistance',
                    'level': recent_highs
                }

            # 检查支撑位突破
            if current_price < recent_lows * (1 - self.sr_touch_threshold):
                return {
                    'is_breakout': True,
                    'type': 'support',
                    'level': recent_lows
                }

            return {'is_breakout': False}

        except Exception as e:
            logger.error(f"检查支撑阻力突破时出错: {e}")
            return {'is_breakout': False}

    def _create_signal(
        self,
        kline: Kline,
        symbol: str,
        strength: float,
        reasons: List[str],
        volume_analysis: Dict,
        price_breakout: Dict
    ) -> Signal:
        """创建突破信号"""

        # 确定方向
        if price_breakout.get('bb_position') == 'upper':
            signal_type = SignalType.OPEN_LONG
            direction = "BUY"
        elif price_breakout.get('bb_position') == 'lower':
            signal_type = SignalType.OPEN_SHORT
            direction = "SELL"
        elif price_breakout.get('sr_type') == 'resistance':
            signal_type = SignalType.OPEN_LONG
            direction = "BUY"
        elif price_breakout.get('sr_type') == 'support':
            signal_type = SignalType.OPEN_SHORT
            direction = "SELL"
        else:
            # 默认根据价格变化判断
            if kline.price_change > 0:
                signal_type = SignalType.OPEN_LONG
                direction = "BUY"
            else:
                signal_type = SignalType.OPEN_SHORT
                direction = "SELL"

        reason = f"1s K线量价突破: {', '.join(reasons)}, 强度={strength:.2f}"

        logger.info(f"[{symbol}] ⚡ 量价突破信号: {direction}, "
                   f"强度={strength:.2f}, "
                   f"价格={kline.close:.6f}, "
                   f"成交量={volume_analysis['volume_ratio']:.2f}x")

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=kline.close,
            amount=0.01,  # 简化版，后续由策略计算
            confidence=strength,
            metadata={
                'reason': reason,
                'kline_timestamp': kline.timestamp.isoformat(),
                'open': kline.open,
                'high': kline.high,
                'low': kline.low,
                'close': kline.close,
                'volume': kline.volume,
                'price_change_pct': kline.price_change_pct,
                'volume_analysis': volume_analysis,
                'price_breakout': price_breakout,
                'strength': strength
            }
        )

    def get_detector_status(self, symbol: str) -> Dict[str, Any]:
        """获取检测器状态（用于监控）"""
        if symbol not in self.kline_history:
            return {
                'symbol': symbol,
                'window_size': self.volume_window,
                'current_size': 0,
                'ready': False
            }

        klines = self.kline_history[symbol]

        # 计算当前统计信息
        volumes = [k.volume for k in klines]
        closes = [k.close for k in klines]

        return {
            'symbol': symbol,
            'window_size': self.volume_window,
            'current_size': len(klines),
            'ready': len(klines) >= self.volume_window,
            'latest_price': klines[-1].close if klines else None,
            'price_mean': np.mean(closes) if closes else None,
            'price_std': np.std(closes) if len(closes) > 1 else None,
            'volume_mean': np.mean(volumes) if volumes else None,
            'latest_volume': klines[-1].volume if klines else None
        }
