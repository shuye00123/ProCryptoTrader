"""
多时间框架K线突破策略

基于1秒K线数据的多时间框架确认突破策略：
- 使用1秒K线进行快速突破检测（替代ticker）
- 多时间框架技术指标确认（15m/1h/1d）
- 遵循BaseStrategy接口规范
- 集成python-binance WebSocket实时订阅
"""

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from core.strategy.base_strategy import BaseStrategy, Signal, SignalType, Position
from core.strategy.kline_breakout_detector import KlineBreakoutDetector, Kline

logger = logging.getLogger(__name__)


class MultiTimeframeKlineBreakoutStrategy(BaseStrategy):
    """
    多时间框架K线突破策略

    特性：
    - 使用1秒K线数据（不使用ticker）
    - 1秒K线快速突破检测
    - 多时间框架技术指标确认（15m/1h/1d）- Phase 2实现
    - 遵循BaseStrategy接口规范
    - python-binance WebSocket实时订阅

    架构：
    ┌─────────────────────────────────────┐
    │  MultiTimeframeKlineBreakoutStrategy│
    └─────────────────────────────────────┘
                 ↓
    ┌────────────┴────────────┐
    ↓                         ↓
    ┌─────────────────┐   ┌──────────────────┐
    │ KlineBreakout   │   │ MultiTimeframe   │
    │ Detector        │   │ Confirmator      │
    │ (1s K线检测)    │   │ (15m/1h/1d确认)  │
    └─────────────────┘   └──────────────────┘
    """

    def __init__(self, config: Dict):
        """
        初始化多时间框架K线突破策略

        Args:
            config: 策略配置字典
                - symbols: 交易对列表
                - kline_breakout: 1秒K线突破检测配置
                - multi_timeframe: 多时间框架确认配置（Phase 2）
        """
        super().__init__(config)

        # 策略名称
        self.name = "MultiTimeframeKlineBreakout"

        # 交易对配置（转换格式：BTC-USDT -> BTCUSDT）
        self.symbols = config.get('symbols', [])
        self.binance_symbols = [s.replace('-', '') for s in self.symbols]

        # ==================== 1秒K线突破检测器 ====================
        kline_config = config.get('strategy', {}).get('kline_breakout', {})
        self.kline_detector = KlineBreakoutDetector(kline_config)

        logger.info(f"[{self.name}] 1秒K线突破检测器初始化完成")

        # ==================== 多时间框架确认器（Phase 2实现） ====================
        # self.mt_confirmator = None  # Phase 2: MultiTimeframeConfirmator

        # ==================== 1秒K线数据缓冲 ====================
        # 用于实时检测（symbol -> deque of klines）
        self.kline_1s_buffer: Dict[str, deque] = {}

        # ==================== WebSocket连接管理 ====================
        self.bsm = None  # BinanceSocketManager
        self.kline_socket = None
        self.ws_running = False
        self.ws_task = None

        # ==================== 回测模式标志 ====================
        self.is_backtest = config.get('mode', 'paper') == 'backtest'

        # ==================== 信号统计 ====================
        self.signal_stats = {
            'preliminary_signals': 0,  # 初步信号数量
            'confirmed_signals': 0,    # 确认信号数量
            'total_klines_processed': 0  # 处理的K线总数
        }

        # ==================== 性能优化组件（Phase 0-3） ====================
        mode = config.get('mode', 'paper')

        if not self.is_backtest:
            # 实时模式：使用多时间框架订阅和缓存
            from core.strategy.unified_data_provider import create_data_provider
            from core.strategy.indicator_cache_manager import create_indicator_cache
            from core.strategy.multi_timeframe_subscriber import MultiTimeframeKlineSubscriber
            from core.strategy.kline_processor_router import KlineProcessorRouter

            # 统一数据提供者
            self.data_provider = create_data_provider(
                mode=mode,
                symbols=self.binance_symbols,
                timeframes=['1s', '15m', '1h']
            )

            # 指标缓存管理器
            self.indicator_cache = create_indicator_cache(mode='default')

            # 多时间框架订阅管理器
            self.mt_subscriber = MultiTimeframeKlineSubscriber(
                symbols=self.binance_symbols,
                timeframes=['1s', '15m', '1h'],
                config={
                    'max_reconnect_attempts': 5,
                    'reconnect_delay_ms': 1000,
                    'enable_stats': True
                }
            )

            # K线处理器路由器
            self.processor_router = KlineProcessorRouter(self)

            # K线历史存储（按时间框架）
            self.kline_history = {
                '1s': {},   # {symbol: deque} - 继续使用现有的kline_1s_buffer
                '15m': {},  # {symbol: deque}
                '1h': {}    # {symbol: deque}
            }

            logger.info(f"[{self.name}] ✅ 性能优化组件初始化完成")
            logger.info(f"[{self.name}] - 多时间框架订阅: 1s, 15m, 1h")
            logger.info(f"[{self.name}] - 指标缓存: 启用")
            logger.info(f"[{self.name}] - 处理器路由器: 已配置")
        else:
            # 回测模式：不使用优化组件，保持原有逻辑
            self.data_provider = None
            self.indicator_cache = None
            self.mt_subscriber = None
            self.processor_router = None
            self.kline_history = None

            logger.info(f"[{self.name}] 回测模式：跳过性能优化组件")

        logger.info(f"[{self.name}] 策略初始化完成")
        logger.info(f"[{self.name}] 交易对: {self.binance_symbols}")
        logger.info(f"[{self.name}] 模式: {'回测' if self.is_backtest else '实盘'}")

    # =========================================================================
    # 高频策略统一接口（与HighFrequencyBreakoutStrategy保持一致）
    # =========================================================================

    async def initialize(self, initial_balance: float = 10000.0):
        """
        异步初始化策略（与HighFrequencyBreakoutStrategy接口一致）

        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        logger.info(f"[{self.name}] 策略异步初始化完成")
        logger.info(f"[{self.name}] 初始余额: {initial_balance} USDT")

    async def start_async_processing(self):
        """
        启动异步数据处理（与HighFrequencyBreakoutStrategy接口一致）

        由HighFrequencyTrader调用，启动WebSocket订阅和信号处理
        """
        # 获取API密钥
        exchange_config = self.config.get('exchange', {})
        api_key = exchange_config.get('api_key') or None
        api_secret = exchange_config.get('api_secret') or None

        logger.info(f"[{self.name}] 启动异步数据处理...")

        # 启动WebSocket订阅
        await self.start_1s_kline_subscription(api_key, api_secret)

        # 保持运行，处理信号
        while self.ws_running:
            await asyncio.sleep(1)

    def set_execution_engine(self, execution_engine):
        """
        设置执行引擎（与HighFrequencyBreakoutStrategy接口一致）

        Args:
            execution_engine: 执行引擎实例（FastExecutionEngine）
        """
        self.execution_engine = execution_engine
        logger.info(f"[{self.name}] 执行引擎已设置")

    # =========================================================================
    # BaseStrategy抽象方法实现
    # =========================================================================

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """
        计算多时间框架技术指标

        Args:
            data: {symbol: DataFrame}，包含不同时间框架的OHLCV数据
                 注意：回测时会有15m/1h/1d数据，实时时只有1s数据

        Returns:
            {symbol: {indicator_name: value}}
        """
        indicators = {}

        for symbol, df in data.items():
            if df.empty or len(df) < 20:
                continue

            symbol_indicators = {}

            try:
                # === 1分钟级别指标 ===
                if len(df) >= 5:
                    # SMA 5/15交叉
                    sma5 = df['close'].rolling(window=5).mean()
                    sma15 = df['close'].rolling(window=15).mean()
                    symbol_indicators['sma_5_15_cross'] = sma5.iloc[-1] > sma15.iloc[-1]
                    symbol_indicators['sma_5'] = sma5.iloc[-1]
                    symbol_indicators['sma_15'] = sma15.iloc[-1]

                # === 趋势指标 ===
                if len(df) >= 20:
                    # 布林带
                    bb_middle = df['close'].rolling(window=20).mean()
                    bb_std = df['close'].rolling(window=20).std()
                    bb_upper = bb_middle + 2 * bb_std
                    bb_lower = bb_middle - 2 * bb_std

                    symbol_indicators['bb_upper'] = bb_upper.iloc[-1]
                    symbol_indicators['bb_middle'] = bb_middle.iloc[-1]
                    symbol_indicators['bb_lower'] = bb_lower.iloc[-1]
                    symbol_indicators['bb_position'] = (
                        (df['close'].iloc[-1] - bb_lower.iloc[-1]) /
                        (bb_upper.iloc[-1] - bb_lower.iloc[-1])
                    ) if (bb_upper.iloc[-1] - bb_lower.iloc[-1]) > 0 else 0.5

                # === 动量指标 ===
                if len(df) >= 14:
                    # RSI
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    symbol_indicators['rsi'] = rsi.iloc[-1]

                # === 价格动量 ===
                if len(df) >= 10:
                    # 1期收益率
                    symbol_indicators['return_1'] = df['close'].pct_change(1).iloc[-1]
                    # 5期收益率
                    symbol_indicators['return_5'] = df['close'].pct_change(5).iloc[-1]

                # === 成交量指标 ===
                if 'volume' in df.columns and len(df) >= 20:
                    vol_ma = df['volume'].rolling(window=20).mean()
                    symbol_indicators['volume_ratio'] = df['volume'].iloc[-1] / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1.0

            except Exception as e:
                logger.error(f"[{symbol}] 计算技术指标时出错: {e}")
                continue

            indicators[symbol] = symbol_indicators

        return indicators

    def generate_signals(self, data: Dict[str, pd.DataFrame], higher_timeframe_data: Dict[str, Dict[str, pd.DataFrame]] = None) -> List[Signal]:
        """
        生成交易信号

        流程：
        1. 获取最新的1秒K线数据
        2. 运行1秒K线量价突破检测（使用更高时间框架数据）
        3. 对初步信号进行多时间框架技术指标确认
        4. 返回确认通过的最终信号

        Args:
            data: {symbol: DataFrame}，包含1s K线数据
            higher_timeframe_data: {symbol: {timeframe: DataFrame}}，包含15m/1h数据
                例如: {'BTC-USDT': {'15m': DataFrame, '1h': DataFrame}}

        Returns:
            List[Signal] - 最终交易信号列表
        """
        signals = []

        for symbol, df in data.items():
            # 转换交易对格式（BTC-USDT -> BTCUSDT）
            binance_symbol = symbol.replace('-', '')

            # 检查数据长度
            if df.empty:
                continue

            min_length = self.kline_detector.volume_window  # 50条1秒K线用于计算平均成交量
            if len(df) < min_length:
                logger.debug(f"[{symbol}] 数据不足，需要至少{min_length}条，当前{len(df)}条")
                continue

            try:
                # ⭐ 关键修复：逐K线处理，模拟实时流
                # 只返回最后检测到的信号（或所有信号）
                for idx, row in df.iterrows():
                    kline = self._df_row_to_kline(row, binance_symbol)

                    # 准备更高时间框架数据
                    symbol_higher_tf_data = higher_timeframe_data.get(symbol, {}) if higher_timeframe_data else {}

                    # === Layer 1: 1秒K线量价突破检测 ===
                    preliminary_signal = self.kline_detector.detect_breakout(
                        kline,
                        binance_symbol,
                        symbol_higher_tf_data  # 传递15m/1h数据用于布林带和支撑阻力检测
                    )

                    if preliminary_signal:
                        self.signal_stats['preliminary_signals'] += 1

                        logger.info(f"[{symbol}] ⚡ 初步量价突破信号: {preliminary_signal.signal_type.value}, "
                                   f"强度: {preliminary_signal.confidence:.2f}, "
                                   f"价格: {kline.close:.6f}")

                        # === Layer 2: 多时间框架技术指标确认（可选） ===
                        # 由于Layer 1已经使用了更高时间框架的布林带和支撑阻力，
                        # 这里的确认可以简化或省略
                        confirmed_signal = self._confirm_with_indicators(preliminary_signal, symbol, binance_symbol)

                        if confirmed_signal:
                            self.signal_stats['confirmed_signals'] += 1

                            logger.info(f"[{symbol}] ✅ 最终交易信号: {confirmed_signal.signal_type.value}, "
                                       f"置信度: {confirmed_signal.confidence:.2f}, "
                                       f"原因: {confirmed_signal.metadata.get('reason', 'N/A')}")

                            signals.append(confirmed_signal)
                        else:
                            logger.info(f"[{symbol}] ❌ 未通过技术指标确认")

            except Exception as e:
                logger.error(f"[{symbol}] 处理K线数据时出错: {e}")
                continue

        return signals

    # =========================================================================
    # WebSocket实时订阅功能
    # =========================================================================

    async def start_1s_kline_subscription(self, api_key: str = None, api_secret: str = None):
        """
        启动多时间框架K线WebSocket订阅（优化版本）

        现在订阅：1s、15m、1h三个时间框架

        Args:
            api_key: Binance API密钥（公开数据不需要）
            api_secret: Binance API密钥秘密（公开数据不需要）
        """
        if self.ws_running:
            logger.warning(f"[{self.name}] WebSocket已在运行中")
            return

        # 检查是否使用优化组件
        if self.mt_subscriber and self.processor_router:
            # 使用新的多时间框架订阅管理器
            try:
                # 保存API密钥供重连使用
                self._api_key = api_key
                self._api_secret = api_secret

                # ==================== 注册处理器 ====================
                # 1s K线处理器（快速检测）
                self.mt_subscriber.register_handler(
                    '1s',
                    self.processor_router.process_1s_kline
                )

                # 15m K线处理器（指标更新）
                self.mt_subscriber.register_handler(
                    '15m',
                    lambda msg: self.processor_router.process_higher_tf_kline(msg, '15m')
                )

                # 1h K线处理器（指标更新）
                self.mt_subscriber.register_handler(
                    '1h',
                    lambda msg: self.processor_router.process_higher_tf_kline(msg, '1h')
                )

                # ==================== 启动所有订阅 ====================
                await self.mt_subscriber.start_all_subscriptions(api_key, api_secret)
                self.ws_running = True

                logger.info(f"[{self.name}] ✅ 多时间框架WebSocket订阅启动成功")
                logger.info(f"[{self.name}] 订阅时间框架: 1s, 15m, 1h")

            except Exception as e:
                logger.error(f"[{self.name}] 启动WebSocket订阅失败: {e}")
                raise
        else:
            # 使用原有的1s订阅方式（回测模式或未启用优化）
            try:
                from binance import BinanceSocketManager

                # 保存API密钥供重连使用
                self._api_key = api_key
                self._api_secret = api_secret

                # 创建BinanceSocketManager（不需要API密钥即可获取公开K线数据）
                self.bsm = BinanceSocketManager(api_key, api_secret)

                # 构建订阅流（仅1s）
                streams = [f"{s.lower()}@kline_1s" for s in self.binance_symbols]

                logger.info(f"[{self.name}] 启动WebSocket订阅（1s仅），流: {streams}")

                # 多路复用订阅
                self.kline_socket = self.bsm.multiplex_socket(streams)
                await self.kline_socket.__aenter__()

                self.ws_running = True

                # 启动K线处理任务
                self.ws_task = asyncio.create_task(self._process_kline_stream())

                logger.info(f"[{self.name}] ✅ WebSocket订阅启动成功（1s仅）")

            except Exception as e:
                logger.error(f"[{self.name}] 启动WebSocket订阅失败: {e}")
                raise

    async def stop_1s_kline_subscription(self):
        """停止1秒K线WebSocket订阅"""
        if not self.ws_running:
            return

        try:
            self.ws_running = False

            # 取消处理任务
            if self.ws_task and not self.ws_task.done():
                self.ws_task.cancel()
                try:
                    await self.ws_task
                except asyncio.CancelledError:
                    pass

            # 关闭WebSocket连接
            if self.kline_socket:
                await self.kline_socket.__aexit__(None, None, None)

            # 关闭BSM
            if self.bsm:
                await self.bsm.close()

            logger.info(f"[{self.name}] WebSocket订阅已停止")

        except Exception as e:
            logger.error(f"[{self.name}] 停止WebSocket订阅时出错: {e}")

    async def _restart_kline_subscription(self):
        """
        重启1秒K线WebSocket订阅（用于重连）

        注意：此方法假设已经初始化过bsm和api_key/api_secret
        """
        try:
            # 关闭旧的连接
            if self.kline_socket:
                try:
                    await self.kline_socket.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug(f"[{self.name}] 关闭旧socket时出错（可忽略）: {e}")

            if self.bsm:
                try:
                    await self.bsm.close()
                except Exception as e:
                    logger.debug(f"[{self.name}] 关闭旧BSM时出错（可忽略）: {e}")

            # 创建新的连接
            from binance import BinanceSocketManager

            # 获取API密钥（从配置或使用None表示公开数据）
            api_key = getattr(self, '_api_key', None)
            api_secret = getattr(self, '_api_secret', None)

            # 创建新的BinanceSocketManager
            self.bsm = BinanceSocketManager(api_key, api_secret)

            # 构建订阅流
            streams = [f"{s.lower()}@kline_1s" for s in self.binance_symbols]

            logger.info(f"[{self.name}] 重新建立WebSocket订阅，流: {streams}")

            # 多路复用订阅
            self.kline_socket = self.bsm.multiplex_socket(streams)
            await self.kline_socket.__aenter__()

            logger.info(f"[{self.name}] ✅ WebSocket重连成功，准备接收数据")

        except Exception as e:
            logger.error(f"[{self.name}] 重连WebSocket失败: {e}")
            raise

    async def _process_kline_stream(self):
        """处理1秒K线数据流（带自动重连机制）"""
        logger.info(f"[{self.name}] 开始处理K线数据流")

        retry_count = 0
        max_retries = 10  # 最大重试次数
        base_wait_time = 2  # 基础等待时间（秒）

        while retry_count < max_retries and self.ws_running:
            try:
                async for msg in self.kline_socket:
                    if not self.ws_running:
                        logger.info(f"[{self.name}] 收到停止信号，退出K线处理")
                        break

                    try:
                        # 处理K线消息
                        await self._process_1s_kline(msg)
                        # 成功处理消息，重置重试计数
                        retry_count = 0
                    except Exception as msg_error:
                        logger.warning(f"[{self.name}] 处理单条K线消息时出错: {msg_error}")
                        # 单条消息错误不中断整个流，继续处理下一条

                # 正常退出循环
                if not self.ws_running:
                    break

            except asyncio.CancelledError:
                logger.info(f"[{self.name}] K线处理任务被取消")
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"[{self.name}] WebSocket连接出错 (重试 {retry_count}/{max_retries}): {e}")

                if retry_count >= max_retries:
                    logger.error(f"[{self.name}] 达到最大重试次数({max_retries})，停止重连")
                    break

                # 指数退避：2^retry_count 秒，最大60秒
                wait_time = min(base_wait_time ** retry_count, 60)
                logger.info(f"[{self.name}] 等待 {wait_time} 秒后重连...")

                # 等待指定时间
                for _ in range(int(wait_time * 10)):  # 0.1秒检查一次
                    if not self.ws_running:
                        logger.info(f"[{self.name}] 收到停止信号，取消重连")
                        break
                    await asyncio.sleep(0.1)

                if not self.ws_running:
                    break

                # 尝试重新连接
                logger.info(f"[{self.name}] 尝试重新连接 WebSocket...")
                try:
                    await self._restart_kline_subscription()
                    logger.info(f"[{self.name}] ✅ WebSocket重连成功")
                    # 重连成功，创建新的kline_socket后继续循环
                    continue
                except Exception as reconnect_error:
                    logger.error(f"[{self.name}] WebSocket重连失败: {reconnect_error}")
                    # 继续下一次重试

        logger.info(f"[{self.name}] K线数据流处理结束")

    async def _process_1s_kline(self, msg: Dict):
        """
        处理1秒K线消息

        Args:
            msg: WebSocket消息
        """
        try:
            # 解析K线数据
            if 'e' not in msg or msg['e'] != 'kline':
                return

            kline_data = msg.get('k', {})
            if not kline_data:
                return

            # 只处理已完成的K线（避免重复处理）
            if not kline_data.get('x', False):  # x=true表示K线已关闭
                return

            # 提取K线数据
            symbol = kline_data['s']
            kline = Kline(
                symbol=symbol,
                open=float(kline_data['o']),
                high=float(kline_data['h']),
                low=float(kline_data['l']),
                close=float(kline_data['c']),
                volume=float(kline_data['v']),
                timestamp=pd.to_datetime(kline_data['t'], unit='ms')
            )

            self.signal_stats['total_klines_processed'] += 1

            # 触发突破检测
            await self._on_1s_kline_update(kline)

        except Exception as e:
            logger.error(f"处理K线消息时出错: {e}, 消息: {msg}")

    async def _on_1s_kline_update(self, kline: Kline):
        """
        处理1秒K线更新（实时模式）

        Args:
            kline: 1秒K线对象
        """
        try:
            symbol = kline.symbol

            # 更新K线缓冲区
            if symbol not in self.kline_1s_buffer:
                self.kline_1s_buffer[symbol] = deque(maxlen=self.kline_detector.window_size)

            self.kline_1s_buffer[symbol].append(kline)

            # === Layer 1: 1秒K线突破检测 ===
            preliminary_signal = self.kline_detector.detect_breakout(kline, symbol)

            if preliminary_signal:
                self.signal_stats['preliminary_signals'] += 1

                logger.info(f"[{symbol}] ⚡ 初步突破信号: {preliminary_signal.signal_type.value}, "
                           f"强度: {preliminary_signal.confidence:.2f}, "
                           f"价格: {kline.close:.6f}")

                # === Layer 2: 技术指标确认（简化版） ===
                # Phase 2将使用MultiTimeframeConfirmator
                confirmed_signal = await self._confirm_with_buffered_data(preliminary_signal, symbol)

                if confirmed_signal:
                    self.signal_stats['confirmed_signals'] += 1

                    logger.info(f"[{symbol}] ✅ 最终交易信号: {confirmed_signal.signal_type.value}, "
                               f"置信度: {confirmed_signal.confidence:.2f}, "
                               f"原因: {confirmed_signal.reason}")

                    # 执行交易信号
                    await self._execute_signal(confirmed_signal)
                else:
                    logger.info(f"[{symbol}] ❌ 未通过技术指标确认")

        except Exception as e:
            logger.error(f"[{kline.symbol}] 处理K线更新时出错: {e}")

    # =========================================================================
    # 信号确认逻辑（Phase 2将被MultiTimeframeConfirmator替代）
    # =========================================================================

    def _confirm_with_indicators(self, preliminary: Signal, symbol: str, binance_symbol: str) -> Optional[Signal]:
        """
        使用技术指标确认初步信号（同步版本，用于回测）

        注意：由于Layer 1（KlineBreakoutDetector）已经使用了15m/1h的布林带和支撑阻力
        进行量价结合的确认，这里直接返回初步信号，避免重复确认和架构矛盾。

        Args:
            preliminary: 初步突破信号
            symbol: 原始交易对符号
            binance_symbol: Binance格式交易对符号

        Returns:
            确认后的最终信号（直接返回初步信号）
        """
        # Layer 1已经做了充分的量价结合确认：
        # - 成交量激增检测（1s vs 历史）
        # - 布林带突破检测（1s价格 vs 15m/1h BB）
        # - 支撑阻力突破检测（1s价格 vs 15m/1h SR）
        #
        # 所以这里直接返回初步信号，不需要额外的技术指标确认
        # 这避免了使用1s K线指标进行确认的架构矛盾

        logger.debug(f"[{symbol}] 跳过技术指标确认，Layer 1已充分确认")

        # 直接返回初步信号，保留原有的元数据
        # 获取原始原因
        original_reason = preliminary.metadata.get('reason', "1s K线量价突破")

        return Signal(
            signal_type=preliminary.signal_type,
            symbol=preliminary.symbol,
            price=preliminary.price,
            amount=preliminary.amount,
            confidence=min(1.0, preliminary.confidence),  # 保持原置信度
            metadata={
                **preliminary.metadata,  # 保留Layer 1的详细元数据
                'strategy': self.name,
                'confirmation_method': 'layer1_only',  # 标记只使用了Layer 1确认
                'reason': f"{original_reason}（Layer 1已确认）"  # 在metadata中添加原因说明
            }
        )

    async def _confirm_with_buffered_data(self, preliminary: Signal, symbol: str) -> Optional[Signal]:
        """
        使用缓冲的K线数据进行确认（异步版本，用于实时）

        Args:
            preliminary: 初步突破信号
            symbol: 交易对符号

        Returns:
            确认后的最终信号，如果未通过确认则返回None
        """
        # 检查缓冲区是否有足够数据
        if symbol not in self.kline_1s_buffer:
            return None

        klines = list(self.kline_1s_buffer[symbol])
        if len(klines) < 20:
            return None

        # 计算简单技术指标
        confirmations = []

        # 1. 短期趋势确认（最近5个K线）
        if len(klines) >= 5:
            recent_closes = [k.close for k in klines[-5:]]
            if recent_closes[-1] > sum(recent_closes[:-1]) / (len(recent_closes) - 1):
                confirmations.append({
                    'timeframe': '1s',
                    'indicator': 'SHORT_TREND',
                    'value': 'UP'
                })

        # 2. 价格动量确认
        if len(klines) >= 10:
            momentum = (klines[-1].close - klines[-10].close) / klines[-10].close
            if momentum > 0.002:  # 0.2%动量
                confirmations.append({
                    'timeframe': '1s',
                    'indicator': 'MOMENTUM',
                    'value': momentum
                })

        # 3. 成交量确认
        if len(klines) >= 20:
            volumes = [k.volume for k in klines]
            avg_volume = sum(volumes) / len(volumes)
            vol_ratio = klines[-1].volume / avg_volume if avg_volume > 0 else 1.0
            if vol_ratio > 1.5:  # 成交量放大50%
                confirmations.append({
                    'timeframe': '1s',
                    'indicator': 'VOLUME_SURGE',
                    'value': vol_ratio
                })

        # 确认规则：至少需要2个确认
        if len(confirmations) >= 2:
            return Signal(
                signal_type=preliminary.signal_type,
                symbol=preliminary.symbol,
                price=preliminary.price,
                amount=preliminary.amount,
                confidence=min(1.0, preliminary.confidence + 0.1),
                metadata={
                    'preliminary_signal': preliminary.to_dict(),
                    'confirmations': confirmations,
                    'reason': f"1s突破 + {len(confirmations)}个实时技术指标确认",
                    'strategy': self.name
                }
            )

        return None

    # =========================================================================
    # 工具方法
    # =========================================================================

    def _df_row_to_kline(self, row, symbol: str) -> Kline:
        """
        将DataFrame行转换为Kline对象

        Args:
            row: DataFrame的一行
            symbol: 交易对符号

        Returns:
            Kline对象
        """
        return Kline(
            symbol=symbol,
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row.get('volume', 0)),
            timestamp=row.name if hasattr(row, 'name') else pd.Timestamp.now()
        )

    def get_signal_statistics(self) -> Dict[str, Any]:
        """获取信号统计信息"""
        return {
            'preliminary_signals': self.signal_stats['preliminary_signals'],
            'confirmed_signals': self.signal_stats['confirmed_signals'],
            'total_klines_processed': self.signal_stats['total_klines_processed'],
            'confirmation_rate': (
                self.signal_stats['confirmed_signals'] / max(self.signal_stats['preliminary_signals'], 1)
            )
        }

    def get_strategy_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        return {
            'name': self.name,
            'symbols': self.binance_symbols,
            'is_backtest': self.is_backtest,
            'websocket_running': self.ws_running,
            'kline_buffer_sizes': {
                symbol: len(buffer)
                for symbol, buffer in self.kline_1s_buffer.items()
            },
            'signal_statistics': self.get_signal_statistics(),
            'detector_status': {
                symbol: self.kline_detector.get_detector_status(symbol)
                for symbol in self.binance_symbols
            }
        }

    # =========================================================================
    # 性能优化方法（Phase 4新增）
    # =========================================================================

    async def detect_breakout_fast(
        self,
        kline: Kline,
        symbol: str
    ) -> Optional[Signal]:
        """
        快速突破检测（1s K线路径）

        不计算指标，只读取缓存的指标值，实现快速检测。

        Args:
            kline: K线对象
            symbol: 交易对符号

        Returns:
            Signal对象，如果没有检测到突破返回None
        """
        try:
            # 更新1s K线历史（继续使用现有的kline_1s_buffer）
            if symbol not in self.kline_1s_buffer:
                self.kline_1s_buffer[symbol] = deque(maxlen=self.kline_detector.window_size)
            self.kline_1s_buffer[symbol].append(kline)

            # 获取缓存的更高时间框架数据（15m/1h）
            if self.indicator_cache:
                cached_indicators = await self.indicator_cache.get_cached_indicators_safe(
                    symbol, ['15m', '1h']
                )
            else:
                cached_indicators = {}

            # 使用KlineBreakoutDetector检测（传入缓存的指标数据）
            signal = self.kline_detector.detect_breakout(
                kline, symbol, cached_indicators
            )

            if signal:
                self.signal_stats['preliminary_signals'] += 1
                logger.info(
                    f"[{symbol}] ⚡ 快速检测突破信号: {signal.signal_type.value}, "
                    f"强度: {signal.confidence:.2f}"
                )

            return signal

        except Exception as e:
            logger.error(f"[{symbol}] 快速检测失败: {e}")
            return None

    async def calculate_timeframe_indicators(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict[str, Any]:
        """
        计算特定时间框架的技术指标

        Args:
            symbol: 交易对符号
            timeframe: 时间框架 ('15m' 或 '1h')

        Returns:
            {indicator_name: value}
        """
        try:
            # 获取该时间框架的K线历史
            if not self.kline_history or timeframe not in self.kline_history:
                logger.warning(f"[{symbol}/{timeframe}] K线历史未初始化")
                return {}

            history = self.kline_history[timeframe].get(symbol)
            if not history or len(history) < 50:
                logger.warning(f"[{symbol}/{timeframe}] K线数据不足: {len(history) if history else 0}")
                return {}

            # 转换为DataFrame
            df = self._deque_to_dataframe(history)

            # 计算技术指标
            indicators = {}

            try:
                if timeframe == '15m':
                    # 15分钟指标
                    if len(df) >= 5:
                        sma5 = df['close'].rolling(window=5).mean()
                        sma15 = df['close'].rolling(window=15).mean()
                        indicators['sma_5_15_cross'] = sma5.iloc[-1] > sma15.iloc[-1]

                    # 布林带
                    if len(df) >= 20:
                        bb_middle = df['close'].rolling(window=20).mean()
                        bb_std = df['close'].rolling(window=20).std()
                        bb_upper = bb_middle + 2 * bb_std
                        bb_lower = bb_middle - 2 * bb_std
                        indicators['bb_upper'] = bb_upper.iloc[-1]
                        indicators['bb_lower'] = bb_lower.iloc[-1]

                        price = df['close'].iloc[-1]
                        indicators['bb_position'] = (
                            (price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])
                            if (bb_upper.iloc[-1] - bb_lower.iloc[-1]) > 0 else 0.5
                        )

                elif timeframe == '1h':
                    # 1小时指标
                    if len(df) >= 12:
                        ema12 = df['close'].ewm(span=12).mean()
                        ema26 = df['close'].ewm(span=26).mean()
                        indicators['ema_12_26_cross'] = ema12.iloc[-1] > ema26.iloc[-1]

                    # MACD
                    if len(df) >= 26:
                        ema12 = df['close'].ewm(span=12).mean()
                        ema26 = df['close'].ewm(span=26).mean()
                        macd = ema12 - ema26
                        signal = macd.ewm(span=9).mean()
                        indicators['macd_bullish'] = (macd.iloc[-1] - signal.iloc[-1]) > 0

                logger.debug(
                    f"[{symbol}/{timeframe}] 计算指标完成: {list(indicators.keys())}"
                )

            except Exception as e:
                logger.error(f"[{symbol}/{timeframe}] 计算指标时出错: {e}")
                return {}

            return indicators

        except Exception as e:
            logger.error(f"[{symbol}/{timeframe}] 指标计算失败: {e}")
            return {}

    async def update_kline_history(self, kline: Kline, timeframe: str):
        """
        更新指定时间框架的K线历史

        Args:
            kline: K线对象
            timeframe: 时间框架
        """
        symbol = kline.symbol

        if symbol not in self.kline_history[timeframe]:
            self.kline_history[timeframe][symbol] = deque(maxlen=200)

        self.kline_history[timeframe][symbol].append(kline)
        logger.debug(f"[{timeframe}] 更新{symbol}K线历史，当前数量: {len(self.kline_history[timeframe][symbol])}")

    def confirm_with_cached_indicators(
        self,
        preliminary: Signal,
        cached_indicators: Dict[str, Dict]
    ) -> Optional[Signal]:
        """
        使用缓存的指标确认信号

        Args:
            preliminary: 初步突破信号
            cached_indicators: {'15m': {...}, '1h': {...}}

        Returns:
            确认后的最终信号，如果未通过确认则返回None
        """
        confirmations = []

        # 检查15m指标
        if '15m' in cached_indicators:
            tf_15m = cached_indicators['15m']
            if tf_15m.get('sma_5_15_cross', False):
                confirmations.append({
                    'timeframe': '15m',
                    'indicator': 'SMA_5_15',
                    'value': tf_15m.get('sma_5_15_cross')
                })
            if tf_15m.get('bb_position', 0) > 0.8:
                confirmations.append({
                    'timeframe': '15m',
                    'indicator': 'BOLLINGER',
                    'value': tf_15m.get('bb_position')
                })

        # 检查1h指标
        if '1h' in cached_indicators:
            tf_1h = cached_indicators['1h']
            if tf_1h.get('ema_12_26_cross', False):
                confirmations.append({
                    'timeframe': '1h',
                    'indicator': 'EMA_12_26',
                    'value': tf_1h.get('ema_12_26_cross')
                })
            if tf_1h.get('macd_bullish', False):
                confirmations.append({
                    'timeframe': '1h',
                    'indicator': 'MACD',
                    'value': tf_1h.get('macd_bullish')
                })

        # 确认规则：至少2个指标
        if len(confirmations) >= 2:
            return Signal(
                signal_type=preliminary.signal_type,
                symbol=preliminary.symbol,
                price=preliminary.price,
                amount=preliminary.amount,
                confidence=min(1.0, preliminary.confidence + 0.1),
                metadata={
                    'preliminary': preliminary.to_dict(),
                    'confirmations': confirmations,
                    'cache_hit': True,
                    'reason': f"1s突破 + {len(confirmations)}个缓存指标确认"
                }
            )

        return None

    def _deque_to_dataframe(self, klines: deque) -> pd.DataFrame:
        """
        将K线 deque转换为DataFrame

        Args:
            klines: K线对象队列

        Returns:
            DataFrame with OHLCV data
        """
        data = {
            'open': [k.open for k in klines],
            'high': [k.high for k in klines],
            'low': [k.low for k in klines],
            'close': [k.close for k in klines],
            'volume': [k.volume for k in klines],
            'timestamp': [k.timestamp for k in klines]
        }

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)

        return df

    # =========================================================================
    # 信号执行逻辑（与HighFrequencyBreakoutStrategy统一）
    # =========================================================================

    async def _execute_signal(self, signal: Signal):
        """
        执行交易信号（异步版本）

        Args:
            signal: 交易信号
        """
        try:
            # 检查是否有执行引擎
            if hasattr(self, 'execution_engine') and self.execution_engine:
                logger.info(f"[{signal.symbol}] 📤 使用FastExecutionEngine执行信号: {signal.signal_type.value}")

                # 转换为ExecutionService的Signal格式
                from core.models.signal import Signal as ExecSignal
                from core.models.signal import SignalType as ExecSignalType

                # 映射信号类型
                signal_type_map = {
                    SignalType.OPEN_LONG: ExecSignalType.OPEN_LONG,
                    SignalType.OPEN_SHORT: ExecSignalType.OPEN_SHORT,
                    SignalType.CLOSE_LONG: ExecSignalType.CLOSE_LONG,
                    SignalType.CLOSE_SHORT: ExecSignalType.CLOSE_SHORT,
                }

                exec_signal_type = signal_type_map.get(signal.signal_type)

                if exec_signal_type:
                    exec_signal = ExecSignal(
                        symbol=signal.symbol,
                        signal_type=exec_signal_type,
                        amount=signal.amount,
                        price=signal.price,
                        confidence=signal.confidence,
                        reason=signal.reason
                    )

                    # 异步执行信号
                    result = await self.execution_engine.execute_signal(exec_signal)

                    if result and result.is_successful():
                        logger.info(f"[{signal.symbol}] ✅ 信号执行成功: {result.order_id if hasattr(result, 'order_id') else 'OK'}")
                    else:
                        logger.warning(f"[{signal.symbol}] ⚠️ 信号执行失败或被拒绝")
                else:
                    logger.warning(f"[{signal.symbol}] ⚠️ 不支持的信号类型: {signal.signal_type}")

            else:
                # 没有执行引擎，记录信号但不执行（模拟模式）
                logger.info(f"[{signal.symbol}] 📊 信号已生成（模拟模式，未执行）")
                logger.info(f"   类型: {signal.signal_type.value}")
                logger.info(f"   价格: {signal.price}")
                logger.info(f"   数量: {signal.amount}")
                logger.info(f"   置信度: {signal.confidence:.2f}")

        except Exception as e:
            logger.error(f"[{signal.symbol}] ❌ 执行信号时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
