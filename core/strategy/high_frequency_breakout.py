"""
高频突破策略 - 基于实时数据流的突破交易策略

继承BaseStrategy，实现基于WebSocket实时数据的高频突破交易策略。
该策略集成了实时数据处理、多维突破检测、智能信号管理等功能，
专为秒级高频交易设计。

核心特性:
1. 实时数据处理和分析
2. 多维度突破检测
3. 智能信号管理和过滤
4. 动态风险控制
5. 自适应参数调整
"""

import asyncio
import logging
import time
import json  # 可能用于处理timestamp
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque

import numpy as np

from .base_strategy import BaseStrategy, Signal, SignalType
from ..data.websocket_client import BinanceWebSocketClient, TickerData
from ..data.realtime_processor import RealtimeDataProcessor, ProcessedTickerData
from .breakout_detector import BreakoutDetector
from ..models.breakout_signal import BreakoutSignal, TradingDirection, SignalType as BreakoutSignalType
from .high_frequency_risk import HighFrequencyRiskManager
from .tick_breakout_detector import TickBreakoutDetector, TickData

# 设置日志
logger = logging.getLogger(__name__)


class HighFrequencyBreakoutStrategy(BaseStrategy):
    """高频突破策略

    基于实时数据流的秒级高频交易策略，集成WebSocket数据获取、
    突破检测、风险控制等功能模块。
    """

    def __init__(self, config: Dict):
        """
        初始化高频突破策略

        Args:
            config: 策略配置参数
        """
        # 调用父类初始化
        super().__init__(config)

        
        # 策略特定配置
        self.max_position_size = config.get('max_position_size', 0.05)  # 5%
        self.max_total_exposure = config.get('max_total_exposure', 0.2)  # 20%
        self.signal_cooldown = config.get('signal_cooldown', 60)  # 60秒冷却
        self.max_positions = config.get('max_positions', 10)

        # 实时数据处理组件
        self.data_processor = RealtimeDataProcessor(
            max_symbols=config.get('max_symbols', 1000),
            price_window_size=config.get('price_window_size', 300),
            volume_window_size=config.get('volume_window_size', 600),
            anomaly_threshold=config.get('anomaly_threshold', 3.0)
        )

        # 原有突破检测器（基于OHLCV数据）
        breakout_config = config.get('strategy', {}).get('breakout', {})
        breakout_enabled = breakout_config.get('enabled', True)

        
        if breakout_enabled:
            self.breakout_detector = BreakoutDetector(breakout_config)
            logger.info("OHLCV突破检测器已启用")
        else:
            self.breakout_detector = None
            logger.info("OHLCV突破检测器已禁用")

        # 新增：Tick级别突破检测器（直接处理tick数据）
        tick_config = config.get('strategy', {}).get('tick_breakout', {})

        # 🔧 修复：正确传递direction_coordination配置
        direction_coordination_config = tick_config.get('direction_coordination', {})
        direction_coordination_enabled = direction_coordination_config.get('enabled', False)

        # 🔧 读取交易规模配置
        trading_config = config.get('trading', {})

        # 🔧 读取VOLUME和PATH算法的优化配置
        volume_config = tick_config.get('volume_breakout', {})
        path_config = tick_config.get('path_breakout', {})

        self.tick_breakout_detector = TickBreakoutDetector(
            window_size=tick_config.get('window_size', 200),
            min_breakout_strength=tick_config.get('min_breakout_strength', 2.0),
            volume_threshold=tick_config.get('volume_threshold', 1.5),
            consecutive_moves_threshold=tick_config.get('consecutive_moves_threshold', 5),
            require_multiple_confirmation=tick_config.get('require_multiple_confirmation', False),
            min_confirmation_count=tick_config.get('min_confirmation_count', 2),
            confirmation_window=tick_config.get('confirmation_window', 1000),
            breakout_cooldown=tick_config.get('breakout_cooldown', 5000),  # 从配置文件读取，默认5秒
            direction_coordination_enabled=direction_coordination_enabled,  # 🔧 修复：传递方向协调配置
            direction_coordination_config=direction_coordination_config,  # 🔧 修复：传递完整配置
            trading_config=trading_config,  # 🔧 交易规模配置
            volume_config=volume_config,    # 🔧 VOLUME算法优化配置
            path_config=path_config          # 🔧 PATH算法优化配置
        )

        # Tick数据缓冲区
        self.tick_buffer = deque(maxlen=1000)
        self.tick_processing_enabled = tick_config.get('enabled', True)

        # 风险管理器
        self.risk_manager = HighFrequencyRiskManager(config)

        # 🔥 修改：WebSocket配置 - 支持从exchange或websocket段读取testnet
        exchange_config = config.get('exchange', {})
        websocket_config = config.get('websocket', {})

        # 优先使用websocket.testnet，其次使用exchange.testnet，最后默认False（主网）
        testnet_value = websocket_config.get('testnet', exchange_config.get('testnet', False))

        self.ws_config = {
            'testnet': testnet_value,
            'max_reconnects': websocket_config.get('reconnect_attempts', 10),
            'reconnect_interval': websocket_config.get('reconnect_delay', 5000) / 1000
        }

        # 日志输出（便于调试）
        logger.info(f"🔧 WebSocket配置: testnet={self.ws_config['testnet']}")

        # 🔥 订阅白名单配置（主网消息量控制）
        websocket_subscribe_config = config.get('websocket_subscribe', {})
        self.subscribe_whitelist = None

        if websocket_subscribe_config.get('enabled', False):
            whitelist = websocket_subscribe_config.get('whitelist', [])
            if whitelist:
                self.subscribe_whitelist = whitelist
                logger.info(f"🔒 订阅白名单已启用: {len(whitelist)} 个交易对")
            else:
                logger.warning("⚠️  websocket_subscribe.enabled=true 但whitelist为空，将订阅所有交易对")
        else:
            logger.info("📡 订阅白名单未启用，将订阅所有交易对")

        # 实时数据处理状态
        self.is_running = False
        self.processing_task = None

        # 🔥 批量处理优化配置（从配置文件读取）
        performance_config = config.get('performance', {})
        self.performance_config = performance_config  # 保存为实例变量，供后续方法使用
        self.enable_batch_processing = performance_config.get('enable_batch_processing', True)  # 默认启用
        self.ticker_buffer: Dict[str, deque] = {}
        self.ticker_buffer_max_size = performance_config.get('ticker_buffer_max_size', 50)  # 每个symbol最多缓存50条
        self.batch_processing_interval = performance_config.get('batch_processing_interval', 1.0)  # 批量处理间隔（秒）
        self.last_batch_process_time = time.time()

        if self.enable_batch_processing:
            logger.info(f"✅ 批量处理模式已启用: 缓冲大小={self.ticker_buffer_max_size}, 处理间隔={self.batch_processing_interval}秒")
        else:
            logger.info("📡 实时处理模式（每个ticker立即处理）")

        # 信号管理
        self.active_signals: Dict[str, List[BreakoutSignal]] = defaultdict(list)
        self.signal_history: List[BreakoutSignal] = []
        self.last_signal_time: Dict[str, datetime] = {}

        # 策略状态统计
        self.strategy_stats = {
            'start_time': None,
            'signals_generated': 0,
            'signals_executed': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'current_exposure': 0.0,
            'processing_errors': 0,
            'last_update_time': None
        }

        # 自适应参数
        self.adaptive_params = {
            'base_position_size': self.position_size,
            'current_volatility_regime': 'normal',
            'recent_performance': [],
            'parameter_adjustment_frequency': 3600,  # 1小时调整一次
            'last_adjustment_time': datetime.now()
        }

        logger.info(f"高频突破策略初始化完成: {self.name}")

    async def initialize(self, initial_balance: float = 10000.0):
        """初始化策略（异步版本）"""
        # 直接设置初始余额，不调用父类的initialize
        self.initial_balance = initial_balance
        self.is_initialized = True

        # 设置初始余额到风险管理器
        self.risk_manager.set_initial_balance(initial_balance)

        # 启动WebSocket连接
        await self._start_websocket_connection()

        # 初始化策略统计
        self.strategy_stats['start_time'] = datetime.now()

        logger.info(f"高频突破策略启动完成，初始余额: {initial_balance}")

    async def start_async_processing(self):
        """启动异步数据处理（由HighFrequencyTrader调用）"""
        try:
            # 检查是否已经初始化
            if not self.strategy_stats['start_time']:
                await self.initialize()

            # 设置运行状态
            self.is_running = True

            # 启动WebSocket连接（如果还没有启动）
            if not self.ws_client or not self.processing_task:
                await self._start_websocket_connection()

            logger.info("高频策略异步处理启动...")
            logger.info(f"✅ Tick突破检测已启用: {self.tick_processing_enabled}")

            # 显示多重确认机制状态
            tick_config = self.config.get('tick_breakout', {})
            multiple_confirmation = tick_config.get('require_multiple_confirmation', False)
            if multiple_confirmation:
                min_count = tick_config.get('min_confirmation_count', 2)
                window = tick_config.get('confirmation_window', 1000)
                logger.info(f"✅ 多重信号确认已启用: 需要至少{min_count}个算法在{window}ms内确认")
            else:
                logger.info("⚠️ 多重信号确认未启用: 使用单一算法检测")

            logger.info(f"✅ WebSocket连接已建立: {self.ws_client is not None}")
            logger.info(f"✅ 数据处理任务已启动: {self.processing_task is not None}")
            return True

        except Exception as e:
            logger.error(f"启动异步处理失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _start_websocket_connection(self):
        """启动WebSocket连接"""
        try:
            # 🔥 添加：清晰的日志输出当前网络
            network = "testnet" if self.ws_config['testnet'] else "mainnet"
            logger.info(f"🔌 正在连接到Binance {network}...")

            # 创建WebSocket客户端
            self.ws_client = BinanceWebSocketClient(
                testnet=self.ws_config['testnet'],  # 🔥 使用配置值
                max_reconnects=self.ws_config.get('max_reconnects', 10),
                reconnect_interval=self.ws_config.get('reconnect_interval', 5),
                subscribe_whitelist=self.subscribe_whitelist,  # 🔥 传递订阅白名单
                max_queue_size=self.performance_config.get('sdk_max_queue_size', 10000)  # 🔥 传递SDK队列大小
            )

            logger.info(f"✅ WebSocket客户端已创建 (network={network})")

            # 添加回调函数
            self.ws_client.add_ticker_callback(self._on_ticker_data)
            self.ws_client.add_error_callback(self._on_websocket_error)

            # 启动连接（在后台运行）
            self.is_running = True
            self.processing_task = asyncio.create_task(self._run_websocket())

            logger.info("WebSocket连接已启动")

        except Exception as e:
            logger.error(f"启动WebSocket连接失败: {e}")
            raise

    async def _run_websocket(self):
        """运行WebSocket连接"""
        try:
            await self.ws_client.connect_all_ticker()
        except Exception as e:
            logger.error(f"WebSocket运行异常: {e}")
            self.is_running = False

    def _on_ticker_data(self, ticker_data: TickerData):
        """处理接收到的Ticker数据 - 支持批量处理和实时处理模式"""
        try:
            if not self.is_running:
                return

            # 🔥 根据配置选择处理模式
            if self.enable_batch_processing:
                # 批量处理模式：缓存ticker数据，减少task创建
                symbol = ticker_data.symbol

                # 初始化symbol的buffer
                if symbol not in self.ticker_buffer:
                    self.ticker_buffer[symbol] = deque(maxlen=self.ticker_buffer_max_size)

                # 添加到buffer（自动淘汰旧数据）
                self.ticker_buffer[symbol].append(ticker_data)

                # 🔥 检查是否需要触发批量处理
                current_time = time.time()
                time_since_last_process = current_time - self.last_batch_process_time

                # 触发条件：
                # 1. 达到处理间隔
                # 2. 或者某个symbol buffer满了
                should_process = (
                    time_since_last_process >= self.batch_processing_interval or
                    any(len(buffer) >= self.ticker_buffer_max_size for buffer in self.ticker_buffer.values())
                )

                if should_process:
                    # 只创建一个task处理所有缓存的ticker
                    asyncio.create_task(self._process_ticker_batch_async())
                    self.last_batch_process_time = current_time
            else:
                # 实时处理模式：每个ticker立即处理（原有逻辑）
                asyncio.create_task(self._process_ticker_async(ticker_data))

        except Exception as e:
            logger.error(f"处理Ticker数据失败: {e}")
            self.strategy_stats['processing_errors'] += 1

    def _on_websocket_error(self, error: Exception):
        """处理WebSocket错误"""
        logger.error(f"WebSocket错误: {error}")
        self.strategy_stats['processing_errors'] += 1

    async def _process_ticker_async(self, ticker_data: TickerData):
        """异步处理Ticker数据 - 集成Tick级别突破检测"""
        try:
            # 1. 数据预处理
            logger.debug(f"传入数据 {ticker_data}")
            processed_data = await self.data_processor.process_ticker_data(ticker_data)
            if not processed_data or processed_data.anomaly_detected:
                return
            logger.debug(f"处理后数据 {processed_data}")
            # 2. 突破检测 - 双重检测机制
            all_signals = []

            # 2.1 原有突破检测器（基于OHLCV数据）
            if self.breakout_detector is not None:
                breakout_signals = await self.breakout_detector.detect_breakouts(processed_data)
                if breakout_signals:
                    all_signals.extend(breakout_signals)
            # else:
                # logger.debug("OHLCV突破检测器已禁用，跳过检测")

            # 2.2 Tick级别突破检测（直接处理tick数据）
            if self.tick_processing_enabled:
                tick_signal = await self._process_tick_breakout_detection(ticker_data)
                if tick_signal:
                    all_signals.append(tick_signal)

            # 3. 信号处理
            if all_signals:
                # 合并和过滤信号
                filtered_signals = await self._filter_and_merge_signals(all_signals)
                await self._handle_breakout_signals(filtered_signals)

            # 4. 自适应参数调整
            await self._adaptive_parameter_adjustment(ticker_data.symbol)

        except Exception as e:
            logger.error(f"异步处理Ticker数据失败 {ticker_data.symbol}: {e}")
            self.strategy_stats['processing_errors'] += 1

    async def _process_ticker_batch_async(self):
        """批量处理缓存的Ticker数据 - 性能优化核心"""
        try:
            if not self.ticker_buffer:
                return

            # 获取所有缓存的ticker数据
            all_tickers = []
            for symbol, ticker_deque in self.ticker_buffer.items():
                # 取出所有ticker
                while ticker_deque:
                    all_tickers.append(ticker_deque.popleft())

            if not all_tickers:
                return

            logger.debug(f"🔄 批量处理 {len(all_tickers)} 条ticker数据，覆盖 {len(set(t.symbol for t in all_tickers))} 个交易对")

            # 批量处理所有ticker
            for ticker_data in all_tickers:
                try:
                    # 调用原有的单个ticker处理逻辑
                    await self._process_ticker_async(ticker_data)
                except Exception as e:
                    logger.error(f"批量处理中单ticker失败 {ticker_data.symbol}: {e}")
                    continue

            logger.debug(f"✅ 批量处理完成，处理了 {len(all_tickers)} 条ticker")

        except Exception as e:
            logger.error(f"批量处理Ticker数据失败: {e}")
            self.strategy_stats['processing_errors'] += 1

    async def _process_tick_breakout_detection(self, ticker_data: TickerData) -> Optional[BreakoutSignal]:
        """处理Tick级别突破检测"""
        try:
            # 🔥 修复：正确使用TickerData的字段创建TickData，基于Binance官方字段映射
            tick = TickData(
                price=ticker_data.price,                           # 最新价格 (c字段)
                volume=ticker_data.volume,                         # 24小时成交量 (v字段) - 用于历史成交量对比
                timestamp=ticker_data.event_time or int(time.time() * 1000),  # WebSocket事件时间 (E字段)
                side=None,                                         # Ticker数据无side字段
                bid=None,                                         # Ticker数据无bid字段
                ask=None,                                         # Ticker数据无ask字段
                price_change=ticker_data.price_change,             # 24小时价格变化 (p字段)

                # 🔥 正确映射Binance扩展字段
                last_quantity=ticker_data.last_quantity,           # Q字段：最新一笔交易的成交量 - 实时性最强
                vwap_24h=ticker_data.weighted_avg_price,          # w字段：24小时加权平均价
                trade_count_24h=ticker_data.count,                # n字段：24小时交易次数
                price_change_percent=ticker_data.price_change_percent,  # P字段：24小时价格变化百分比
                quote_volume=ticker_data.quote_volume,             # q字段：24小时成交额
            )

            # 2. 噪音过滤（使用TickBreakoutDetector的方法）
            if not self.tick_breakout_detector.filter_market_noise(tick, ticker_data.symbol):
                logger.debug(f"[DEBUG] TICK过滤 - {ticker_data.symbol}: 市场噪音过滤")
                return None

            # 3. 更新历史数据 (先更新数据再检查充足性)
            self.tick_breakout_detector.update_histories(tick, ticker_data.symbol)

            # 4. 数据充足性检查
            _, price_history, _, _ = self.tick_breakout_detector._get_symbol_buffers(ticker_data.symbol)
            if len(price_history) < 50:
                logger.debug(f"[DEBUG] TICK跳过 - {ticker_data.symbol}: 历史数据不足({len(price_history)}<50)")
                return None

            # 5. 冷却期检查
            current_time = tick.timestamp
            last_breakout_time = self.tick_breakout_detector.last_breakout_times.get(ticker_data.symbol, 0)
            cooldown_remaining = self.tick_breakout_detector.breakout_cooldown - (current_time - last_breakout_time)
            if cooldown_remaining > 0:
                logger.debug(f"[DEBUG] TICK跳过 - {ticker_data.symbol}: 冷却期剩余{cooldown_remaining/1000:.1f}秒")
                return None

            # 6. 添加到tick缓冲区
            self.tick_buffer.append({
                'symbol': ticker_data.symbol,
                'price': ticker_data.price,
                'volume': ticker_data.volume,
                'timestamp': tick.timestamp,
                'tick_data': tick  # 保存原始TickerData引用
            })

            # 7. 使用Tick突破检测器的多维度检测方法
            tick_signal = self.tick_breakout_detector.detect_multi_dimensional_breakout(tick, ticker_data.symbol)

            # 8. 如果检测到突破信号，转换为BreakoutSignal
            if tick_signal:
                breakout_signal = self._convert_tick_signal_to_breakout_signal(
                    tick_signal, ticker_data.symbol
                )
                if breakout_signal:
                    logger.info(f"Tick级别突破检测成功: {ticker_data} - {ticker_data.symbol} - {tick_signal.reason} - {tick_signal.confidence}")
                    return breakout_signal

            return None

        except Exception as e:
            logger.error(f"Tick突破检测失败 {ticker_data.symbol}: {e}")
            return None

    def _convert_tick_signal_to_breakout_signal(self, tick_signal: Signal, symbol: str) -> Optional[BreakoutSignal]:
        """将Tick信号转换为BreakoutSignal"""
        try:
            # 创建BreakoutSignal - 修复SignalType枚举兼容性
            # TickBreakoutDetector使用base_strategy.SignalType
            is_buy_signal = True  # 默认为买入信号
            if hasattr(tick_signal.signal_type, 'value'):
                signal_value = tick_signal.signal_type.value
                if signal_value in ["open_short", "increase_short", "close_long"]:
                    is_buy_signal = False
            else:
                signal_str = str(tick_signal.signal_type).upper()
                if "SHORT" in signal_str or "CLOSE_LONG" in signal_str:
                    is_buy_signal = False

            direction = TradingDirection.LONG if is_buy_signal else TradingDirection.SHORT

            # 创建技术指标和信号指标
            from ..models.breakout_signal import TechnicalIndicators, SignalMetrics

            indicators = TechnicalIndicators(
                current_price=tick_signal.price or tick_signal.current_price
            )

            metrics = SignalMetrics(
                confidence=tick_signal.confidence or 0.5,
                strength=tick_signal.confidence or 0.5
            )

            # 确定信号类型（适配不同的SignalType枚举）
            # TickBreakoutDetector使用base_strategy.SignalType
            signal_value = tick_signal.signal_type.value if hasattr(tick_signal.signal_type, 'value') else str(tick_signal.signal_type)

            if signal_value in ["open_long", "increase_long"]:
                signal_type = BreakoutSignalType.PRICE_BREAKOUT
            elif signal_value in ["open_short", "increase_short"]:
                signal_type = BreakoutSignalType.VOLUME_SURGE
            else:
                signal_type = BreakoutSignalType.PRICE_BREAKOUT  # 默认使用价格突破

            breakout_signal = BreakoutSignal(
                symbol=symbol,
                signal_type=signal_type,
                timestamp=tick_signal.timestamp,
                direction=direction,
                indicators=indicators,
                metrics=metrics,
                trigger_price=tick_signal.price or tick_signal.price,  # TickBreakoutDetector的Signal有price字段
                reason=tick_signal.reason or "Tick突破检测",
                metadata=tick_signal.metadata or {}
            )

            # 设置tick特有的元数据
            tick_metadata = {
                'detection_method': 'TICK_BREAKOUT',
                'tick_reason': tick_signal.reason,
                'detector_type': 'TickBreakoutDetector'
            }
            breakout_signal.metadata.update(tick_metadata)

            return breakout_signal

        except Exception as e:
            logger.error(f"转换Tick信号失败: {e}")
            return None

    async def _filter_and_merge_signals(self, signals: List[BreakoutSignal]) -> List[BreakoutSignal]:
        """过滤和合并突破信号"""
        if not signals:
            return []

        # 按信号类型和时间分组
        grouped_signals = {}
        for signal in signals:
            key = f"{signal.symbol}_{signal.direction}"
            if key not in grouped_signals:
                grouped_signals[key] = []
            grouped_signals[key].append(signal)

        # 为每个组选择最佳信号
        filtered_signals = []
        for key, group_signals in grouped_signals.items():
            # 选择置信度最高的信号
            best_signal = max(group_signals, key=lambda s: s.metrics.confidence)

            # 合并其他信号的元数据
            other_signals = [s for s in group_signals if s != best_signal]
            if other_signals:
                combined_metadata = best_signal.metadata.copy()
                for other in other_signals:
                    combined_metadata.update({
                        f"secondary_{k}": v for k, v in other.metadata.items()
                    })
                best_signal.metadata = combined_metadata

                # 提高综合置信度
                best_signal.metrics.confidence = min(1.0, best_signal.metrics.confidence * 1.1)

            filtered_signals.append(best_signal)

        return filtered_signals

    async def _handle_breakout_signals(self, signals: List[BreakoutSignal]):
        """处理突破信号"""
        for signal in signals:
            try:
                # 1. 风险检查
                if not self._check_signal_risk(signal):
                    continue

                # 2. 转换为标准信号
                trading_signal = self._convert_to_trading_signal(signal)

                if trading_signal:
                    # 3. 记录信号
                    self._record_signal(signal)

                    # 4. 发送信号到执行系统
                    await self._execute_signal(trading_signal)

            except Exception as e:
                logger.error(f"处理突破信号失败 {signal.symbol}: {e}")

    def _check_signal_risk(self, signal: BreakoutSignal) -> bool:
        """检查信号风险"""
        # 1. 信号质量检查
        if signal.get_signal_quality_score() < 0.6:
            return False

        # 2. 冷却期检查
        last_time = self.last_signal_time.get(signal.symbol)
        if last_time and (datetime.now() - last_time).total_seconds() < self.signal_cooldown:
            return False

        # 3. 风险管理器检查
        if not self.risk_manager.check_risk_limits(signal.symbol, self.positions):
            return False

        # 4. 资金使用率检查
        current_exposure = self._calculate_current_exposure()
        if current_exposure >= self.max_total_exposure:
            return False

        return True

    def _convert_to_trading_signal(self, breakout_signal: BreakoutSignal) -> Optional[Signal]:
        """将突破信号转换为交易信号"""
        try:
            # 确定信号类型
            if breakout_signal.direction == TradingDirection.LONG:
                if self.has_position(breakout_signal.symbol):
                    position = self.get_position(breakout_signal.symbol)
                    if position.side == 'short':
                        signal_type = SignalType.CLOSE_SHORT
                        amount = min(position.amount, breakout_signal.calculate_position_size(self.initial_balance))
                    else:
                        signal_type = SignalType.INCREASE_LONG
                        amount = breakout_signal.calculate_position_size(self.initial_balance)
                else:
                    signal_type = SignalType.OPEN_LONG
                    amount = breakout_signal.calculate_position_size(self.initial_balance)
            else:  # SHORT
                if self.has_position(breakout_signal.symbol):
                    position = self.get_position(breakout_signal.symbol)
                    if position.side == 'long':
                        signal_type = SignalType.CLOSE_LONG
                        amount = min(position.amount, breakout_signal.calculate_position_size(self.initial_balance))
                    else:
                        signal_type = SignalType.INCREASE_SHORT
                        amount = breakout_signal.calculate_position_size(self.initial_balance)
                else:
                    signal_type = SignalType.OPEN_SHORT
                    amount = breakout_signal.calculate_position_size(self.initial_balance)

            # 创建标准交易信号
            trading_signal = Signal(
                signal_type=signal_type,
                symbol=breakout_signal.symbol,
                price=breakout_signal.trigger_price,
                amount=amount,
                confidence=breakout_signal.metrics.confidence,
                stop_loss=breakout_signal.stop_loss_price,
                take_profit=breakout_signal.target_price,
                metadata={
                    'strategy': 'high_frequency_breakout',
                    'breakout_type': breakout_signal.signal_type.value,
                    'signal_strength': breakout_signal.metrics.strength,
                    'quality_score': breakout_signal.get_signal_quality_score(),
                    'breakout_signal': breakout_signal.to_dict()
                }
            )

            return trading_signal

        except Exception as e:
            logger.error(f"转换突破信号失败 {breakout_signal.symbol}: {e}")
            return None

    def _record_signal(self, signal: BreakoutSignal):
        """记录信号"""
        # 记录到历史
        self.signal_history.append(signal)
        self.active_signals[signal.symbol].append(signal)
        self.last_signal_time[signal.symbol] = signal.timestamp

        # 更新统计
        self.strategy_stats['signals_generated'] += 1

        # 限制历史长度
        if len(self.signal_history) > 10000:
            self.signal_history = self.signal_history[-5000:]

        # 限制活跃信号长度
        if len(self.active_signals[signal.symbol]) > 100:
            self.active_signals[signal.symbol] = self.active_signals[signal.symbol][-50]

    async def _execute_signal(self, signal: Signal):
        """执行交易信号 - 使用fast execution engine"""
        try:
            # 检查是否有执行引擎
            if hasattr(self, 'execution_engine') and self.execution_engine:
                # 使用快速执行引擎执行交易
                execution_result = await self.execution_engine.execute_signal(signal)

                if execution_result and execution_result.is_successful():
                    logger.info(f"✅ 交易执行成功: {signal.signal_type.value} {signal.symbol} "
                               f"数量: {signal.amount:.6f} 价格: {signal.price:.2f}")
                    self.strategy_stats['successful_trades'] += 1
                else:
                    logger.error(f"❌ 交易执行失败: {signal.signal_type.value} {signal.symbol}")
                    self.strategy_stats['failed_trades'] += 1
            else:
                # 回退到模拟执行（当没有执行引擎时）
                logger.info(f"🔄 模拟交易信号: {signal.signal_type.value} {signal.symbol} "
                           f"数量: {signal.amount:.6f} 价格: {signal.price:.2f}")

                # 模拟更新持仓
                self._simulate_position_update(signal)

            # 记录信号到历史
            self.signals_history.append(signal)

            # 更新执行统计
            self.strategy_stats['signals_executed'] += 1

        except Exception as e:
            logger.error(f"执行交易信号失败: {e}")
            self.strategy_stats['failed_trades'] += 1

    def _simulate_position_update(self, signal: Signal):
        """模拟持仓更新（用于测试和回退场景）"""
        try:
            if signal.signal_type in [SignalType.OPEN_LONG, SignalType.INCREASE_LONG]:
                # 模拟多头开仓或加仓
                if not self.has_position(signal.symbol):
                    self.add_position(signal.symbol, 'long', signal.amount, signal.price)
                else:
                    # 加仓逻辑
                    current_position = self.get_position(signal.symbol)
                    total_amount = current_position.amount + signal.amount
                    avg_price = ((current_position.entry_price * current_position.amount) +
                                (signal.price * signal.amount)) / total_amount
                    current_position.amount = total_amount
                    current_position.entry_price = avg_price

            elif signal.signal_type in [SignalType.OPEN_SHORT, SignalType.INCREASE_SHORT]:
                # 模拟空头开仓或加仓
                if not self.has_position(signal.symbol):
                    self.add_position(signal.symbol, 'short', signal.amount, signal.price)
                else:
                    current_position = self.get_position(signal.symbol)
                    total_amount = current_position.amount + signal.amount
                    avg_price = ((current_position.entry_price * current_position.amount) +
                                (signal.price * signal.amount)) / total_amount
                    current_position.amount = total_amount
                    current_position.entry_price = avg_price

            elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                # 模拟平仓
                if self.has_position(signal.symbol):
                    position = self.get_position(signal.symbol)
                    if ((signal.signal_type == SignalType.CLOSE_LONG and position.side == 'long') or
                        (signal.signal_type == SignalType.CLOSE_SHORT and position.side == 'short')):
                        # 计算盈亏
                        if position.side == 'long':
                            pnl = (signal.price - position.entry_price) * position.amount
                        else:
                            pnl = (position.entry_price - signal.price) * position.amount

                        # 更新统计
                        self.strategy_stats['total_pnl'] += pnl

                        # 移除持仓
                        self.remove_position(signal.symbol)

        except Exception as e:
            logger.error(f"模拟持仓更新失败: {e}")

    def _calculate_current_exposure(self) -> float:
        """计算当前资金暴露"""
        total_exposure = 0.0

        for position in self.positions.values():
            exposure = abs(position.amount * position.current_price)
            total_exposure += exposure

        if self.initial_balance > 0:
            return total_exposure / self.initial_balance
        return 0.0

    async def _adaptive_parameter_adjustment(self, symbol: str):
        """自适应参数调整"""
        current_time = datetime.now()

        # 检查是否需要调整
        if ((current_time - self.adaptive_params['last_adjustment_time']).total_seconds() <
            self.adaptive_params['parameter_adjustment_frequency']):
            return

        try:
            # 获取近期表现
            if self.breakout_detector is not None:
                recent_signals = self.breakout_detector.get_signal_history(symbol, limit=20)
            else:
                recent_signals = []

            if len(recent_signals) >= 10:
                # 计算成功率
                success_count = sum(1 for s in recent_signals if s.metrics.historical_success_rate > 0.5)
                success_rate = success_count / len(recent_signals)

                # 根据表现调整参数
                if success_rate < 0.3:  # 表现不佳
                    # 减少仓位大小
                    self.adaptive_params['base_position_size'] *= 0.9
                    logger.info(f"降低仓位大小至 {self.adaptive_params['base_position_size']:.3f}")

                elif success_rate > 0.7:  # 表现优秀
                    # 适度增加仓位大小
                    self.adaptive_params['base_position_size'] *= 1.05
                    self.adaptive_params['base_position_size'] = min(
                        self.adaptive_params['base_position_size'], self.max_position_size
                    )
                    logger.info(f"提升仓位大小至 {self.adaptive_params['base_position_size']:.3f}")

            # 更新调整时间
            self.adaptive_params['last_adjustment_time'] = current_time

        except Exception as e:
            logger.error(f"自适应参数调整失败: {e}")

    # 重写父类方法
    async def update(self, data: Dict[str, Any]) -> List[Signal]:
        """更新策略状态（重写父类方法）"""
        # 高频策略主要通过WebSocket实时数据处理，这里基本不需要执行
        return []

    async def generate_signals(self, data: Dict[str, Any]) -> List[Signal]:
        """生成交易信号（重写父类方法）"""
        # 高频策略主要通过WebSocket实时数据处理，这里基本不需要执行
        return []

    async def calculate_indicators(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """计算技术指标（重写父类方法）"""
        # 高频策略的指标计算在实时处理器中完成
        return {}

    async def shutdown(self):
        """关闭策略"""
        logger.info("正在关闭高频突破策略")

        # 停止WebSocket连接
        self.is_running = False

        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        if self.ws_client:
            await self.ws_client.disconnect()

        # 清理数据
        self.data_processor.clear_cache()
        if self.breakout_detector is not None:
            self.breakout_detector.clear_signal_history()

        logger.info("高频突破策略已关闭")

    def get_strategy_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        status = super().get_status()

        # 添加高频策略特定信息
        status.update({
            'strategy_type': 'high_frequency_breakout',
            'is_running': self.is_running,
            'websocket_connected': self.ws_client.is_connected if self.ws_client else False,
            'active_signals_count': sum(len(signals) for signals in self.active_signals.values()),
            'current_exposure': self._calculate_current_exposure(),
            'adaptive_position_size': self.adaptive_params['base_position_size']
        })

        # 添加统计信息
        status['strategy_stats'] = self.strategy_stats.copy()
        status['data_processor_stats'] = self.data_processor.get_stats()
        if self.breakout_detector is not None:
            status['breakout_detector_stats'] = self.breakout_detector.get_detection_stats()
        else:
            status['breakout_detector_stats'] = {'enabled': False}

        return status

    def get_signal_analysis(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取信号分析"""
        if symbol:
            # 特定交易对的信号分析
            signals = self.active_signals.get(symbol, [])
            history = self.breakout_detector.get_signal_history(symbol) if self.breakout_detector is not None else []

            return {
                'symbol': symbol,
                'active_signals_count': len(signals),
                'recent_signals': [s.to_dict() for s in history[-10:]],
                'signal_frequency': len(history) / max(1, len(history) * 60),  # 每分钟信号数
                'average_signal_strength': np.mean([s.metrics.strength for s in history]) if history else 0
            }
        else:
            # 整体信号分析
            total_signals = len(self.signal_history)
            if total_signals > 0:
                signal_types = {}
                for signal in self.signal_history:
                    signal_type = signal.signal_type.value
                    signal_types[signal_type] = signal_types.get(signal_type, 0) + 1

                return {
                    'total_signals': total_signals,
                    'signal_types_distribution': signal_types,
                    'average_signal_strength': np.mean([s.metrics.strength for s in self.signal_history]),
                    'success_rate': np.mean([s.metrics.historical_success_rate for s in self.signal_history]),
                    'signals_per_minute': total_signals / max(1, (datetime.now() - self.strategy_stats['start_time']).total_seconds() / 60)
                }
            else:
                return {
                    'total_signals': 0,
                    'signal_types_distribution': {},
                    'average_signal_strength': 0,
                    'success_rate': 0,
                    'signals_per_minute': 0
                }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        current_time = datetime.now()
        runtime = (current_time - self.strategy_stats['start_time']).total_seconds() if self.strategy_stats['start_time'] else 0

        metrics = {
            'runtime_seconds': runtime,
            'runtime_hours': runtime / 3600,
            'signals_generated': self.strategy_stats['signals_generated'],
            'signals_executed': self.strategy_stats['signals_executed'],
            'signal_execution_rate': (self.strategy_stats['signals_executed'] /
                                     max(1, self.strategy_stats['signals_generated'])),
            'successful_trades': self.strategy_stats['successful_trades'],
            'failed_trades': self.strategy_stats['failed_trades'],
            'trade_success_rate': (self.strategy_stats['successful_trades'] /
                                 max(1, self.strategy_stats['successful_trades'] + self.strategy_stats['failed_trades'])),
            'total_pnl': self.strategy_stats['total_pnl'],
            'current_exposure': self._calculate_current_exposure(),
            'processing_errors': self.strategy_stats['processing_errors'],
            'error_rate': self.strategy_stats['processing_errors'] / max(1, runtime) * 3600,  # 每小时错误数
        }

        # 添加每小时信号率
        if runtime > 0:
            metrics['signals_per_hour'] = self.strategy_stats['signals_generated'] / (runtime / 3600)
        else:
            metrics['signals_per_hour'] = 0

        return metrics


# 便利函数
async def create_high_frequency_breakout_strategy(config: Dict,
                                                initial_balance: float = 10000.0) -> HighFrequencyBreakoutStrategy:
    """创建高频突破策略实例的便利函数"""
    strategy = HighFrequencyBreakoutStrategy(config)
    await strategy.initialize(initial_balance)
    return strategy


# 示例使用
async def example_usage():
    """示例用法"""
    config = {
        'name': 'HighFrequencyBreakout_Example',
        'symbols': ['BTCUSDT', 'ETHUSDT'],
        'max_position_size': 0.05,
        'max_total_exposure': 0.2,
        'signal_cooldown': 60,
        'websocket': {
            'testnet': True,
            'max_reconnects': 5,
            'reconnect_interval': 3
        },
        'breakout': {
            'price_breakout_threshold': 0.02,
            'volume_surge_multiplier': 3.0,
            'volatility_threshold': 2.0
        }
    }

    try:
        # 创建策略
        strategy = await create_high_frequency_breakout_strategy(config, initial_balance=10000)

        # 运行一段时间
        logger.info("策略运行中...")
        await asyncio.sleep(30)  # 运行30秒

        # 获取状态
        status = strategy.get_strategy_status()
        print(f"策略状态: {status['strategy_type']}")
        print(f"运行状态: {status['is_running']}")
        print(f"WebSocket连接: {status['websocket_connected']}")
        print(f"信号生成数: {status['strategy_stats']['signals_generated']}")

        # 获取性能指标
        performance = strategy.get_performance_metrics()
        print(f"\n性能指标:")
        print(f"运行时间: {performance['runtime_hours']:.2f} 小时")
        print(f"信号执行率: {performance['signal_execution_rate']:.2%}")
        print(f"当前暴露: {performance['current_exposure']:.2%}")

    except Exception as e:
        logger.error(f"策略运行失败: {e}")
    finally:
        # 关闭策略
        if 'strategy' in locals():
            await strategy.shutdown()


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    asyncio.run(example_usage())