"""
K线处理器路由器

该模块实现K线数据按时间框架的路由分发，将1s K线路由到快速检测路径，
将15m/1h K线路由到指标更新路径，实现性能优化的核心逻辑。

核心特性:
1. 智能路由: 根据时间框架自动分发到对应处理器
2. 快速检测路径: 1s K线直接读取缓存，实现毫秒级响应
3. 指标更新路径: 15m/1h K线计算指标并更新缓存
4. 信号确认: 使用缓存指标对初步信号进行最终确认
5. 状态跟踪: 完整的处理日志和统计信息

作者: Claude Code
创建时间: 2026-01-12
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
import pandas as pd

from core.strategy.base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


class Kline:
    """
    K线数据结构

    Attributes:
        symbol: 交易对符号
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        timestamp: K线时间戳
        is_closed: K线是否已闭合
    """

    def __init__(
        self,
        symbol: str,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        timestamp: pd.Timestamp,
        is_closed: bool = True
    ):
        self.symbol = symbol
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.timestamp = timestamp
        self.is_closed = is_closed

    def __repr__(self):
        return (f"Kline({self.symbol}, O={self.open:.2f}, H={self.high:.2f}, "
                f"L={self.low:.2f}, C={self.close:.2f}, V={self.volume:.0f}, "
                f"closed={self.is_closed})")


class KlineProcessorRouter:
    """
    K线处理器路由器

    该类负责将WebSocket接收到的K线数据路由到适当的处理器：
    - 1s K线 → 快速突破检测路径（读取缓存的指标）
    - 15m/1h K线 → 指标更新路径（计算指标并更新缓存）

    Attributes:
        strategy: 策略实例引用
        process_stats: 处理统计信息

    Example:
        >>> router = KlineProcessorRouter(strategy)
        >>>
        >>> # 处理1s K线（快速检测）
        >>> await router.process_1s_kline(websocket_message)
        >>>
        >>> # 处理15m K线（指标更新）
        >>> await router.process_higher_tf_kline(websocket_message, '15m')
    """

    def __init__(self, strategy):
        """
        初始化K线处理器路由器

        Args:
            strategy: MultiTimeframeKlineBreakoutStrategy实例
        """
        self.strategy = strategy

        # 处理统计
        self.process_stats = {
            '1s': {'processed': 0, 'signals': 0, 'errors': 0},
            '15m': {'processed': 0, 'cache_updates': 0, 'errors': 0},
            '1h': {'processed': 0, 'cache_updates': 0, 'errors': 0}
        }

        logger.info("[KlineProcessorRouter] 初始化完成")

    async def process_1s_kline(self, msg: Dict):
        """
        处理1秒K线 - 快速检测路径

        该方法实现快速突破检测：
        1. 解析WebSocket消息为Kline对象
        2. 更新1s K线历史缓冲区
        3. 使用缓存的指标进行快速突破检测
        4. 生成初步信号
        5. 使用缓存指标进行最终确认
        6. 执行确认后的信号

        Args:
            msg: WebSocket消息字典

        Example:
            >>> await router.process_1s_kline(websocket_message)
        """
        try:
            # 1. 解析K线数据
            kline = self._parse_kline(msg)
            if not kline:
                return

            # 只处理闭合的K线
            if not kline.is_closed:
                return

            symbol = kline.symbol

            # 更新统计
            self.process_stats['1s']['processed'] += 1

            # 2. 更新1s K线历史（使用现有的kline_1s_buffer）
            if hasattr(self.strategy, 'kline_1s_buffer'):
                if symbol not in self.strategy.kline_1s_buffer:
                    from collections import deque
                    window_size = getattr(self.strategy.kline_detector, 'window_size', 200)
                    self.strategy.kline_1s_buffer[symbol] = deque(maxlen=window_size)
                self.strategy.kline_1s_buffer[symbol].append(kline)

            # 3. 获取缓存的更高时间框架指标（15m/1h）
            if hasattr(self.strategy, 'indicator_cache'):
                cached_indicators = await self.strategy.indicator_cache.get_cached_indicators_safe(
                    symbol, ['15m', '1h']
                )
            else:
                cached_indicators = {}

            # 4. 快速突破检测（不计算指标，只读取缓存）
            signal = await self._detect_breakout_fast(kline, symbol, cached_indicators)

            if signal:
                self.process_stats['1s']['signals'] += 1
                logger.info(
                    f"[1s K线] ⚡ 快速检测突破: {symbol}, "
                    f"价格={kline.close:.2f}, "
                    f"置信度={signal.confidence:.2f}, "
                    f"原因={signal.metadata.get('reason', 'N/A')}"
                )

                # 5. 使用缓存的指标进行最终确认
                if hasattr(self.strategy, 'confirm_with_cached_indicators'):
                    final_signal = self.strategy.confirm_with_cached_indicators(
                        signal, cached_indicators
                    )

                    if final_signal:
                        logger.info(
                            f"[1s K线] ✅ 最终交易信号: {symbol}, "
                            f"类型={final_signal.signal_type.value}, "
                            f"置信度={final_signal.confidence:.2f}, "
                            f"确认数量={len(final_signal.metadata.get('confirmations', []))}"
                        )

                        # 6. 执行信号（通过策略的信号处理机制）
                        if hasattr(self.strategy, '_execute_signal'):
                            await self.strategy._execute_signal(final_signal)

        except Exception as e:
            self.process_stats['1s']['errors'] += 1
            logger.error(f"[1s K线] 处理错误: {e}", exc_info=True)

    async def process_higher_tf_kline(self, msg: Dict, timeframe: str):
        """
        处理更高时间框架K线 - 指标更新路径

        该方法实现技术指标的计算和缓存更新：
        1. 解析WebSocket消息为Kline对象
        2. 只处理闭合的K线
        3. 更新该时间框架的K线历史
        4. 计算该时间框架的技术指标
        5. 更新缓存

        Args:
            msg: WebSocket消息字典
            timeframe: 时间框架 ('15m' 或 '1h')

        Example:
            >>> await router.process_higher_tf_kline(websocket_message, '15m')
        """
        try:
            # 1. 解析K线数据
            kline = self._parse_kline(msg)
            if not kline:
                return

            symbol = kline.symbol

            # 更新统计
            self.process_stats[timeframe]['processed'] += 1

            # 2. 只处理闭合的K线（指标只在K线闭合时更新）
            if not kline.is_closed:
                logger.debug(f"[{timeframe} K线] 未闭合，跳过: {symbol}")
                return

            logger.debug(
                f"[{timeframe} K线] 处理闭合K线: {symbol}, "
                f"价格={kline.close:.2f}, 成交量={kline.volume:.0f}"
            )

            # 3. 更新该时间框架的K线历史
            if hasattr(self.strategy, 'kline_history'):
                await self.strategy.update_kline_history(kline, timeframe)
            else:
                logger.warning(f"[{timeframe} K线] 策略缺少kline_history属性")

            # 4. 计算该时间框架的技术指标
            if hasattr(self.strategy, 'calculate_timeframe_indicators'):
                indicators = await self.strategy.calculate_timeframe_indicators(symbol, timeframe)

                if indicators:
                    # 5. 更新缓存
                    if hasattr(self.strategy, 'indicator_cache'):
                        await self.strategy.indicator_cache.update_indicators_async(
                            symbol, timeframe, indicators,
                            metadata={
                                'kline_close': kline.close,
                                'kline_timestamp': kline.timestamp.isoformat(),
                                'update_source': f'{timeframe}_kline_close'
                            }
                        )

                        self.process_stats[timeframe]['cache_updates'] += 1

                        logger.info(
                            f"[{timeframe} K线] ✅ 更新缓存: {symbol}, "
                            f"指标数量={len(indicators)}, "
                            f"指标={list(indicators.keys())[:5]}..."
                        )
                else:
                    logger.warning(f"[{timeframe} K线] 未计算出指标: {symbol}")
            else:
                logger.warning(f"[{timeframe} K线] 策略缺少calculate_timeframe_indicators方法")

        except Exception as e:
            self.process_stats[timeframe]['errors'] += 1
            logger.error(f"[{timeframe} K线] 处理错误: {e}", exc_info=True)

    def _parse_kline(self, msg: Dict) -> Optional[Kline]:
        """
        解析WebSocket消息为Kline对象

        Args:
            msg: WebSocket消息字典

        Returns:
            Kline对象，如果解析失败返回None

        Example:
            >>> kline = router._parse_kline(websocket_message)
            >>> print(kline.close)
        """
        try:
            # 检查消息类型
            if not isinstance(msg, dict):
                return None

            # 检查事件类型
            event_type = msg.get('e')
            if event_type != 'kline':
                return None

            # 提取K线数据
            kline_data = msg.get('k', {})
            if not kline_data:
                return None

            # 创建Kline对象
            kline = Kline(
                symbol=kline_data.get('s', ''),
                open=float(kline_data.get('o', 0)),
                high=float(kline_data.get('h', 0)),
                low=float(kline_data.get('l', 0)),
                close=float(kline_data.get('c', 0)),
                volume=float(kline_data.get('v', 0)),
                timestamp=pd.to_datetime(kline_data.get('t', 0), unit='ms'),
                is_closed=kline_data.get('x', False)
            )

            return kline

        except Exception as e:
            logger.error(f"[KlineProcessorRouter] 解析K线失败: {e}")
            return None

    async def _detect_breakout_fast(
        self,
        kline: Kline,
        symbol: str,
        cached_indicators: Dict[str, Dict]
    ) -> Optional[Signal]:
        """
        快速突破检测（1s K线路径）

        该方法不计算指标，只读取缓存的指标值，实现快速检测。

        Args:
            kline: K线对象
            symbol: 交易对符号
            cached_indicators: 缓存的指标 {'15m': {...}, '1h': {...}}

        Returns:
            Signal对象，如果没有检测到突破返回None
        """
        try:
            # 使用策略的KlineBreakoutDetector检测
            if hasattr(self.strategy, 'kline_detector'):
                # 构建更高时间框架数据格式（模拟DataFrame结构）
                higher_tf_data = self._build_higher_tf_data_from_cache(cached_indicators)

                # 调用量价突破检测器
                signal = self.strategy.kline_detector.detect_breakout(
                    kline, symbol, higher_tf_data
                )

                if signal:
                    # 更新信号统计
                    if hasattr(self.strategy, 'signal_stats'):
                        self.strategy.signal_stats['preliminary_signals'] += 1

                return signal
            else:
                logger.warning(f"[1s K线] 策略缺少kline_detector")
                return None

        except Exception as e:
            logger.error(f"[1s K线] 快速检测失败: {e}")
            return None

    def _build_higher_tf_data_from_cache(
        self,
        cached_indicators: Dict[str, Dict]
    ) -> Dict[str, pd.DataFrame]:
        """
        从缓存指标构建更高时间框架数据结构

        该方法将缓存的指标值转换为KlineBreakoutDetector期望的格式。

        Args:
            cached_indicators: 缓存的指标 {'15m': {...}, '1h': {...}}

        Returns:
            DataFrame字典 {timeframe: DataFrame}
        """
        result = {}

        for tf, indicators in cached_indicators.items():
            # 创建一个单行的DataFrame（包含最新指标值）
            df = pd.DataFrame([indicators])

            # 添加必要的列（如果不存在）
            if 'close' not in df.columns:
                # 尝试从缓存元数据中获取最新收盘价
                df['close'] = indicators.get('kline_close', 0)

            result[tf] = df

        return result

    def get_processing_statistics(self) -> Dict[str, Any]:
        """
        获取处理统计信息

        Returns:
            包含各时间框架处理统计的字典
        """
        return {
            '1s': self.process_stats['1s'].copy(),
            '15m': self.process_stats['15m'].copy(),
            '1h': self.process_stats['1h'].copy(),
            'total_processed': sum(
                stats['processed'] for stats in self.process_stats.values()
            ),
            'total_signals': self.process_stats['1s']['signals'],
            'total_cache_updates': (
                self.process_stats['15m']['cache_updates'] +
                self.process_stats['1h']['cache_updates']
            ),
            'total_errors': sum(
                stats['errors'] for stats in self.process_stats.values()
            )
        }

    def print_statistics(self):
        """打印处理统计信息（用于调试）"""
        stats = self.get_processing_statistics()

        print("\n" + "=" * 80)
        print("K线处理器路由统计")
        print("=" * 80)

        print("\n1s K线处理（快速检测）:")
        print(f"  处理数量: {stats['1s']['processed']}")
        print(f"  信号数量: {stats['1s']['signals']}")
        print(f"  错误数量: {stats['1s']['errors']}")

        print("\n15m K线处理（指标更新）:")
        print(f"  处理数量: {stats['15m']['processed']}")
        print(f"  缓存更新: {stats['15m']['cache_updates']}")
        print(f"  错误数量: {stats['15m']['errors']}")

        print("\n1h K线处理（指标更新）:")
        print(f"  处理数量: {stats['1h']['processed']}")
        print(f"  缓存更新: {stats['1h']['cache_updates']}")
        print(f"  错误数量: {stats['1h']['errors']}")

        print("\n总计:")
        print(f"  总处理数: {stats['total_processed']}")
        print(f"  总信号数: {stats['total_signals']}")
        print(f"  总缓存更新: {stats['total_cache_updates']}")
        print(f"  总错误数: {stats['total_errors']}")

        # 计算信号率
        if stats['1s']['processed'] > 0:
            signal_rate = stats['1s']['signals'] / stats['1s']['processed']
            print(f"  信号率: {signal_rate:.2%}")

        print("=" * 80 + "\n")

    def reset_statistics(self):
        """重置处理统计"""
        for tf in self.process_stats:
            self.process_stats[tf] = {
                'processed': 0,
                'signals': 0 if tf == '1s' else 0,
                'cache_updates': 0 if tf != '1s' else 0,
                'errors': 0
            }

        logger.info("[KlineProcessorRouter] 统计信息已重置")


# 辅助函数
def validate_kline_message(msg: Dict) -> bool:
    """
    验证K线消息格式

    Args:
        msg: WebSocket消息字典

    Returns:
        bool: 消息是否有效
    """
    if not isinstance(msg, dict):
        return False

    # 检查事件类型
    if msg.get('e') != 'kline':
        return False

    # 检查K线数据
    kline_data = msg.get('k', {})
    if not kline_data:
        return False

    # 检查必需字段
    required_fields = ['s', 'o', 'h', 'l', 'c', 'v', 't', 'x']
    for field in required_fields:
        if field not in kline_data:
            return False

    return True


def extract_kline_info(msg: Dict) -> Dict[str, Any]:
    """
    从WebSocket消息提取K线信息（用于调试）

    Args:
        msg: WebSocket消息字典

    Returns:
        包含K线关键信息的字典
    """
    if not validate_kline_message(msg):
        return {}

    kline_data = msg.get('k', {})

    return {
        'symbol': kline_data.get('s'),
        'open': float(kline_data.get('o', 0)),
        'high': float(kline_data.get('h', 0)),
        'low': float(kline_data.get('l', 0)),
        'close': float(kline_data.get('c', 0)),
        'volume': float(kline_data.get('v', 0)),
        'timestamp': pd.to_datetime(kline_data.get('t', 0), unit='ms'),
        'is_closed': kline_data.get('x', False)
    }
