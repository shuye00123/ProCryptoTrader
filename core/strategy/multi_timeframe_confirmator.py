"""
多时间框架技术指标确认器

使用不同时间框架（15m/1h/1d）的技术指标确认初步突破信号：
- 15分钟：SMA 5/15、布林带、RSI
- 1小时：EMA 12/26、MACD、成交量趋势
- 1日：趋势方向、关键支撑阻力位
- 确认规则：至少2个时间框架、3个指标确认
"""

import logging
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from core.strategy.base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


class MultiTimeframeConfirmator:
    """
    多时间框架技术指标确认器

    职责：
    - 对初步突破信号进行多时间框架确认
    - 计算不同时间框架的技术指标
    - 应用确认规则返回最终信号
    """

    def __init__(self, data_fetcher=None, config: Dict = None):
        """
        初始化多时间框架确认器

        Args:
            data_fetcher: 数据获取器（用于获取多时间框架K线数据）
            config: 配置字典
        """
        self.data_fetcher = data_fetcher
        self.config = config or {}

        # 默认配置：每个时间框架需要哪些指标
        self.timeframe_configs = {
            '15m': {
                'indicators': ['SMA_5_15', 'BOLLINGER', 'RSI'],
                'weights': {'SMA_5_15': 0.4, 'BOLLINGER': 0.3, 'RSI': 0.3},
                'enabled': True
            },
            '1h': {
                'indicators': ['EMA_12_26', 'MACD', 'VOLUME_TREND'],
                'weights': {'EMA_12_26': 0.4, 'MACD': 0.4, 'VOLUME_TREND': 0.2},
                'enabled': True
            },
            '1d': {
                'indicators': ['TREND_DIRECTION', 'KEY_LEVELS'],
                'weights': {'TREND_DIRECTION': 0.6, 'KEY_LEVELS': 0.4},
                'enabled': False  # 默认禁用日线确认（可选）
            }
        }

        # 确认规则
        self.min_timeframes = config.get('min_timeframes', 2)  # 至少2个时间框架
        self.min_indicators = config.get('min_indicators', 3)  # 至少3个指标

        # 指标阈值
        self.thresholds = {
            'rsi_min': config.get('rsi_min', 30),
            'rsi_max': config.get('rsi_max', 70),
            'bb_position_min': config.get('bb_position_min', 0.7),
            'volume_ratio_min': config.get('volume_ratio_min', 1.5),
            'momentum_min': config.get('momentum_min', 0.002)
        }

        logger.info(f"[MultiTimeframeConfirmator] 初始化完成")
        logger.info(f"[MultiTimeframeConfirmator] 确认规则: 至少{self.min_timeframes}个时间框架, {self.min_indicators}个指标")

    async def confirm_breakout(self, preliminary: Signal, symbol: str,
                               multi_timeframe_data: Dict[str, pd.DataFrame]) -> Optional[Signal]:
        """
        使用多时间框架技术指标确认初步突破

        Args:
            preliminary: 初步突破信号
            symbol: 交易对符号
            multi_timeframe_data: 多时间框架K线数据
                {'15m': DataFrame, '1h': DataFrame, '1d': DataFrame}

        Returns:
            确认后的最终信号，如果未通过确认则返回None
        """
        confirmations = []
        confirmed_timeframes = set()

        try:
            # === 15分钟K线确认 ===
            if '15m' in multi_timeframe_data and self.timeframe_configs['15m']['enabled']:
                confirm_15m = await self._check_timeframe(
                    symbol, '15m', preliminary, multi_timeframe_data['15m']
                )
                if confirm_15m:
                    confirmations.extend(confirm_15m)
                    confirmed_timeframes.add('15m')

            # === 1小时K线确认 ===
            if '1h' in multi_timeframe_data and self.timeframe_configs['1h']['enabled']:
                confirm_1h = await self._check_timeframe(
                    symbol, '1h', preliminary, multi_timeframe_data['1h']
                )
                if confirm_1h:
                    confirmations.extend(confirm_1h)
                    confirmed_timeframes.add('1h')

            # === 1日K线确认（可选，大趋势过滤） ===
            if '1d' in multi_timeframe_data and self.timeframe_configs['1d']['enabled']:
                confirm_1d = await self._check_timeframe(
                    symbol, '1d', preliminary, multi_timeframe_data['1d']
                )
                if confirm_1d:
                    confirmations.extend(confirm_1d)
                    confirmed_timeframes.add('1d')

            # === 确认规则 ===
            # 需要：至少N个时间框架有确认，且总确认数 >= M
            unique_timeframes = len(confirmed_timeframes)
            total_confirmations = len(confirmations)

            logger.debug(f"[{symbol}] 确认统计: {unique_timeframes}个时间框架, {total_confirmations}个指标确认")

            if unique_timeframes >= self.min_timeframes and total_confirmations >= self.min_indicators:
                # 通过确认，创建最终交易信号
                return self._create_confirmed_signal(preliminary, confirmations, confirmed_timeframes)

            logger.info(f"[{symbol}] 未通过确认: {unique_timeframes}/{self.min_timeframes} 时间框架, "
                       f"{total_confirmations}/{self.min_indicators} 指标")

            return None  # 未通过确认

        except Exception as e:
            logger.error(f"[{symbol}] 多时间框架确认时出错: {e}")
            return None

    async def _check_timeframe(self, symbol: str, timeframe: str,
                              signal: Signal, klines: pd.DataFrame) -> List[Dict]:
        """
        检查单个时间框架的指标

        Args:
            symbol: 交易对符号
            timeframe: 时间框架 ('15m', '1h', '1d')
            signal: 初步信号
            klines: K线数据

        Returns:
            确认列表: [{'timeframe': '15m', 'indicator': 'SMA_5_15', 'value': ..., 'weight': ...}]
        """
        confirmations = []

        try:
            # 检查数据长度
            min_length = 50
            if klines is None or len(klines) < min_length:
                logger.debug(f"[{symbol}] {timeframe}: 数据不足，需要至少{min_length}条")
                return []

            # 计算该时间框架的所有指标
            indicators = self._calculate_indicators(klines, timeframe)

            # 检查每个指标
            config = self.timeframe_configs.get(timeframe, {})
            weights = config.get('weights', {})

            for indicator_name in config.get('indicators', []):
                if self._check_indicator(indicator_name, indicators, signal):
                    confirmations.append({
                        'timeframe': timeframe,
                        'indicator': indicator_name,
                        'value': indicators.get(indicator_name),
                        'weight': weights.get(indicator_name, 0.5)
                    })
                    logger.debug(f"[{symbol}] {timeframe} {indicator_name} 确认通过: {indicators.get(indicator_name)}")

        except Exception as e:
            logger.error(f"[{symbol}] 检查{timeframe}指标时出错: {e}")

        return confirmations

    def _calculate_indicators(self, klines: pd.DataFrame, timeframe: str) -> Dict:
        """
        计算技术指标

        Args:
            klines: K线数据（OHLCV格式）
            timeframe: 时间框架

        Returns:
            技术指标字典 {indicator_name: value}
        """
        indicators = {}

        try:
            # === 15分钟指标 ===
            if timeframe == '15m':
                # SMA 5/15交叉
                sma5 = klines['close'].rolling(window=5).mean()
                sma15 = klines['close'].rolling(window=15).mean()
                indicators['SMA_5_15'] = {
                    'sma5': sma5.iloc[-1],
                    'sma15': sma15.iloc[-1],
                    'cross_above': sma5.iloc[-1] > sma15.iloc[-1]
                }

                # 布林带
                bb_period = 20
                bb_middle = klines['close'].rolling(window=bb_period).mean()
                bb_std = klines['close'].rolling(window=bb_period).std()
                bb_upper = bb_middle + 2 * bb_std
                bb_lower = bb_middle - 2 * bb_std

                bb_position = 0.5
                if (bb_upper.iloc[-1] - bb_lower.iloc[-1]) > 0:
                    bb_position = (klines['close'].iloc[-1] - bb_lower.iloc[-1]) / (
                        bb_upper.iloc[-1] - bb_lower.iloc[-1]
                    )

                indicators['BOLLINGER'] = {
                    'upper': bb_upper.iloc[-1],
                    'middle': bb_middle.iloc[-1],
                    'lower': bb_lower.iloc[-1],
                    'position': bb_position
                }

                # RSI
                rsi_period = 14
                delta = klines['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                indicators['RSI'] = rsi.iloc[-1]

            # === 1小时指标 ===
            elif timeframe == '1h':
                # EMA 12/26交叉
                ema12 = klines['close'].ewm(span=12).mean()
                ema26 = klines['close'].ewm(span=26).mean()
                indicators['EMA_12_26'] = {
                    'ema12': ema12.iloc[-1],
                    'ema26': ema26.iloc[-1],
                    'cross_above': ema12.iloc[-1] > ema26.iloc[-1]
                }

                # MACD
                exp1 = klines['close'].ewm(span=12).mean()
                exp2 = klines['close'].ewm(span=26).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9).mean()
                histogram = macd - signal

                indicators['MACD'] = {
                    'macd': macd.iloc[-1],
                    'signal': signal.iloc[-1],
                    'histogram': histogram.iloc[-1],
                    'bullish': histogram.iloc[-1] > 0
                }

                # 成交量趋势
                if 'volume' in klines.columns:
                    vol_ma = klines['volume'].rolling(window=20).mean()
                    vol_ratio = klines['volume'].iloc[-1] / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1.0
                    indicators['VOLUME_TREND'] = {
                        'current': klines['volume'].iloc[-1],
                        'ma': vol_ma.iloc[-1],
                        'ratio': vol_ratio
                    }

            # === 1日指标 ===
            elif timeframe == '1d':
                # 长期趋势方向（EMA 50/200）
                ema50 = klines['close'].ewm(span=50).mean()
                ema200 = klines['close'].ewm(span=200).mean()
                indicators['TREND_DIRECTION'] = {
                    'ema50': ema50.iloc[-1],
                    'ema200': ema200.iloc[-1],
                    'uptrend': ema50.iloc[-1] > ema200.iloc[-1]
                }

                # 关键支撑/阻力位（简化版）
                lookback = min(50, len(klines))
                resistance = klines['high'].iloc[-lookback:].max()
                support = klines['low'].iloc[-lookback:].min()

                indicators['KEY_LEVELS'] = {
                    'resistance': resistance,
                    'support': support,
                    'current_price': klines['close'].iloc[-1]
                }

        except Exception as e:
            logger.error(f"计算{timeframe}指标时出错: {e}")

        return indicators

    def _check_indicator(self, indicator_name: str, indicators: Dict,
                        signal: Signal) -> bool:
        """
        检查单个指标是否确认信号

        Args:
            indicator_name: 指标名称
            indicators: 指标数据字典
            signal: 交易信号

        Returns:
            True if指标确认信号，False otherwise
        """
        try:
            # === 15分钟指标检查 ===

            if indicator_name == 'SMA_5_15':
                data = indicators.get('SMA_5_15', {})
                # 价格在SMA5之上，SMA5在SMA15之上（金叉）
                return data.get('cross_above', False)

            elif indicator_name == 'BOLLINGER':
                data = indicators.get('BOLLINGER', {})
                # 价格在布林带上半部分（position > threshold）
                position = data.get('position', 0.5)
                return position > self.thresholds['bb_position_min']

            elif indicator_name == 'RSI':
                rsi = indicators.get('RSI', 50)
                # RSI在合理区间（避免超买超卖）
                return self.thresholds['rsi_min'] < rsi < self.thresholds['rsi_max']

            # === 1小时指标检查 ===

            elif indicator_name == 'EMA_12_26':
                data = indicators.get('EMA_12_26', {})
                # EMA12 > EMA26（金叉）
                return data.get('cross_above', False)

            elif indicator_name == 'MACD':
                data = indicators.get('MACD', {})
                # MACD histogram > 0（多头动能）
                return data.get('bullish', False)

            elif indicator_name == 'VOLUME_TREND':
                data = indicators.get('VOLUME_TREND', {})
                # 成交量放大
                return data.get('ratio', 1.0) > self.thresholds['volume_ratio_min']

            # === 1日指标检查 ===

            elif indicator_name == 'TREND_DIRECTION':
                data = indicators.get('TREND_DIRECTION', {})
                # 只在大趋势向上时做多
                if signal.signal_type == SignalType.OPEN_LONG:
                    return data.get('uptrend', False)
                elif signal.signal_type == SignalType.OPEN_SHORT:
                    return not data.get('uptrend', True)
                return True

            elif indicator_name == 'KEY_LEVELS':
                # 价格接近关键位置（简化版：总是返回true）
                # 后续可以增强为：检测突破支撑/阻力位
                return True

        except Exception as e:
            logger.error(f"检查{indicator_name}指标时出错: {e}")

        return False

    def _create_confirmed_signal(self, preliminary: Signal,
                                confirmations: List[Dict],
                                confirmed_timeframes: set) -> Signal:
        """
        创建确认后的最终交易信号

        Args:
            preliminary: 初步突破信号
            confirmations: 确认列表
            confirmed_timeframes: 已确认的时间框架集合

        Returns:
            最终确认信号
        """
        # 计算置信度（基于确认数量和权重）
        total_weight = sum(c['weight'] for c in confirmations)
        confidence_boost = min(0.3, total_weight * 0.1)  # 最多提升30%置信度

        new_confidence = min(1.0, preliminary.confidence + confidence_boost)

        # 构建原因描述
        timeframe_desc = ', '.join(sorted(confirmed_timeframes))
        indicator_desc = ', '.join([c['indicator'] for c in confirmations])

        reason = f"1s突破 + {len(confirmations)}个多时间框架确认 ({timeframe_desc}): {indicator_desc}"

        logger.info(f"[{preliminary.symbol}] ✅ 创建确认信号: 置信度 {new_confidence:.2f} (+{confidence_boost:.2f})")

        return Signal(
            signal_type=preliminary.signal_type,
            symbol=preliminary.symbol,
            price=preliminary.price,
            amount=preliminary.amount,
            confidence=new_confidence,
            stop_loss=preliminary.stop_loss,
            take_profit=preliminary.take_profit,
            metadata={
                'preliminary_signal': preliminary.to_dict(),
                'confirmations': confirmations,
                'confirmed_timeframes': list(confirmed_timeframes),
                'timeframe_count': len(confirmed_timeframes),
                'indicator_count': len(confirmations),
                'reason': reason,
                'strategy': 'MultiTimeframeBreakout'
            }
        )

    def get_confirmator_status(self) -> Dict[str, Any]:
        """获取确认器状态（用于监控）"""
        return {
            'timeframe_configs': self.timeframe_configs,
            'confirmation_rules': {
                'min_timeframes': self.min_timeframes,
                'min_indicators': self.min_indicators
            },
            'thresholds': self.thresholds
        }
