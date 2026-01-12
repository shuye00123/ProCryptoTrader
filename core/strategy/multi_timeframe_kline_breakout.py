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

        logger.info(f"[{self.name}] 策略初始化完成")
        logger.info(f"[{self.name}] 交易对: {self.binance_symbols}")
        logger.info(f"[{self.name}] 模式: {'回测' if self.is_backtest else '实盘'}")

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
                # 获取最新1秒K线
                latest_kline = self._df_row_to_kline(df.iloc[-1], binance_symbol)

                # 准备更高时间框架数据
                symbol_higher_tf_data = higher_timeframe_data.get(symbol, {}) if higher_timeframe_data else {}

                # === Layer 1: 1秒K线量价突破检测 ===
                preliminary_signal = self.kline_detector.detect_breakout(
                    latest_kline,
                    binance_symbol,
                    symbol_higher_tf_data  # 传递15m/1h数据用于布林带和支撑阻力检测
                )

                if preliminary_signal:
                    self.signal_stats['preliminary_signals'] += 1

                    logger.info(f"[{symbol}] ⚡ 初步量价突破信号: {preliminary_signal.signal_type.value}, "
                               f"强度: {preliminary_signal.confidence:.2f}, "
                               f"价格: {latest_kline.close:.6f}")

                    # === Layer 2: 多时间框架技术指标确认（可选） ===
                    # 由于Layer 1已经使用了更高时间框架的布林带和支撑阻力，
                    # 这里的确认可以简化或省略
                    confirmed_signal = self._confirm_with_indicators(preliminary_signal, symbol, binance_symbol)

                    if confirmed_signal:
                        self.signal_stats['confirmed_signals'] += 1

                        logger.info(f"[{symbol}] ✅ 最终交易信号: {confirmed_signal.signal_type.value}, "
                                   f"置信度: {confirmed_signal.confidence:.2f}, "
                                   f"原因: {confirmed_signal.reason}")

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
        启动1秒K线WebSocket订阅

        Args:
            api_key: Binance API密钥（公开数据不需要）
            api_secret: Binance API密钥秘密（公开数据不需要）
        """
        if self.ws_running:
            logger.warning(f"[{self.name}] WebSocket已在运行中")
            return

        try:
            from binance import BinanceSocketManager

            # 创建BinanceSocketManager（不需要API密钥即可获取公开K线数据）
            self.bsm = BinanceSocketManager(api_key, api_secret)

            # 构建订阅流
            streams = [f"{s.lower()}@kline_1s" for s in self.binance_symbols]

            logger.info(f"[{self.name}] 启动WebSocket订阅，流: {streams}")

            # 多路复用订阅
            self.kline_socket = self.bsm.multiplex_socket(streams)
            await self.kline_socket.__aenter__()

            self.ws_running = True

            # 启动K线处理任务
            self.ws_task = asyncio.create_task(self._process_kline_stream())

            logger.info(f"[{self.name}] ✅ WebSocket订阅启动成功")

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

    async def _process_kline_stream(self):
        """处理1秒K线数据流"""
        logger.info(f"[{self.name}] 开始处理K线数据流")

        try:
            async for msg in self.kline_socket:
                if not self.ws_running:
                    break

                # 处理K线消息
                await self._process_1s_kline(msg)

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] K线处理任务被取消")
        except Exception as e:
            logger.error(f"[{self.name}] 处理K线流时出错: {e}")
        finally:
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

                    # 触发信号处理（这里可以添加回调或事件系统）
                    # 例如：await self._execute_signal(confirmed_signal)
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

        Args:
            preliminary: 初步突破信号
            symbol: 原始交易对符号
            binance_symbol: Binance格式交易对符号

        Returns:
            确认后的最终信号，如果未通过确认则返回None
        """
        # 从indicators中获取已计算的指标
        if symbol not in self.indicators:
            logger.debug(f"[{symbol}] 没有技术指标数据，跳过确认")
            return None

        symbol_indicators = self.indicators[symbol]
        confirmations = []

        # === 15分钟级别确认 ===

        # 1. SMA交叉确认
        if symbol_indicators.get('sma_5_15_cross', False):
            confirmations.append({
                'timeframe': '15m',
                'indicator': 'SMA_5_15',
                'value': symbol_indicators.get('sma_5', 0)
            })

        # 2. 布林带位置确认（价格在上轨附近）
        bb_position = symbol_indicators.get('bb_position', 0.5)
        if bb_position > 0.7:  # 价格在布林带上半部分
            confirmations.append({
                'timeframe': '15m',
                'indicator': 'BOLLINGER',
                'value': bb_position
            })

        # 3. RSI确认（避免超买超卖）
        rsi = symbol_indicators.get('rsi', 50)
        if 30 < rsi < 70:  # RSI在合理区间
            confirmations.append({
                'timeframe': '15m',
                'indicator': 'RSI',
                'value': rsi
            })

        # 4. 价格动量确认
        return_5 = symbol_indicators.get('return_5', 0)
        if return_5 > 0.005:  # 5期收益率 > 0.5%
            confirmations.append({
                'timeframe': '15m',
                'indicator': 'MOMENTUM',
                'value': return_5
            })

        # === 确认规则 ===
        # 至少需要2个技术指标确认
        min_confirmations = 2

        if len(confirmations) >= min_confirmations:
            # 通过确认，创建最终信号
            return Signal(
                signal_type=preliminary.signal_type,
                symbol=preliminary.symbol,
                price=preliminary.price,
                amount=preliminary.amount,
                confidence=min(1.0, preliminary.confidence + 0.1),  # 提高置信度
                metadata={
                    'preliminary_signal': preliminary.to_dict(),
                    'confirmations': confirmations,
                    'reason': f"1s突破 + {len(confirmations)}个技术指标确认",
                    'strategy': self.name
                }
            )

        return None

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
