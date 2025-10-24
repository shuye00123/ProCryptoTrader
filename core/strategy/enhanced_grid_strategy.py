#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强网格策略

支持做多/做空方向配置，优化信号生成逻辑
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

from .base_strategy import BaseStrategy, Signal, SignalType


class EnhancedGridStrategy(BaseStrategy):
    """
    增强网格策略

    支持做多/做空方向配置的网格交易策略
    """

    def __init__(self, config: Dict):
        """
        初始化增强网格策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 网格参数
        self.grid_count = config.get('grid_count', 10)
        self.grid_range_pct = config.get('grid_range_pct', 0.02)  # 网格范围百分比
        self.grid_spacing = None  # 网格间距，初始化时计算

        # 方向配置
        self.direction = config.get('direction', 'both')  # 'long', 'short', 'both'
        self.long_only = config.get('long_only', False)    # 仅做多
        self.short_only = config.get('short_only', False)  # 仅做空

        # 网格状态
        self.base_price = None  # 基准价格
        self.grid_prices = {}    # 网格价格 {symbol: [price1, price2, ...]}
        self.grid_orders = {}    # 网格订单状态 {symbol: {price: 'buy'/'sell'/'executed'}}
        self.executed_levels = {}  # 已执行的网格级别 {symbol: set()}

        # 价格追踪
        self.last_price = {}     # 上次价格 {symbol: price}
        self.price_history = {}  # 价格历史 {symbol: [price1, price2, ...]}

        # 信号生成配置
        self.min_price_change_pct = config.get('min_price_change_pct', 0.001)  # 最小价格变化百分比
        self.enable_grid_rebalance = config.get('enable_grid_rebalance', True)   # 启用网格重平衡
        self.grid_rebalance_threshold = config.get('grid_rebalance_threshold', 0.1)  # 网格重平衡阈值

        self.logger = logging.getLogger(f"{__name__}.{self.name}")

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """
        计算技术指标

        Args:
            data: 交易对数据字典 {symbol: DataFrame}

        Returns:
            技术指标字典 {symbol: {indicator_name: value}}
        """
        indicators = {}

        for symbol, df in data.items():
            if df.empty:
                continue

            symbol_indicators = {}

            # 计算基本统计指标
            if len(df) >= 5:
                symbol_indicators['current_price'] = df['close'].iloc[-1]
                symbol_indicators['price_change_1h'] = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) if len(df) >= 2 else 0
                symbol_indicators['price_change_24h'] = (df['close'].iloc[-1] / df['close'].iloc[-24] - 1) if len(df) >= 24 else 0
                symbol_indicators['price_volatility'] = df['close'].pct_change().std() if len(df) >= 2 else 0
                symbol_indicators['price_range'] = df['high'].max() - df['low'].min()
                symbol_indicators['price_range_pct'] = symbol_indicators['price_range'] / df['close'].mean() if df['close'].mean() > 0 else 0

                # 计算移动平均线
                if len(df) >= 10:
                    symbol_indicators['sma_10'] = df['close'].rolling(10).mean().iloc[-1]
                    symbol_indicators['price_above_sma_10'] = df['close'].iloc[-1] > symbol_indicators['sma_10']

                # 计算布林带
                if len(df) >= 20:
                    sma_20 = df['close'].rolling(20).mean().iloc[-1]
                    std_20 = df['close'].rolling(20).std().iloc[-1]
                    symbol_indicators['bb_upper'] = sma_20 + 2 * std_20
                    symbol_indicators['bb_lower'] = sma_20 - 2 * std_20
                    symbol_indicators['price_above_bb_upper'] = df['close'].iloc[-1] > symbol_indicators['bb_upper']
                    symbol_indicators['price_below_bb_lower'] = df['close'].iloc[-1] < symbol_indicators['bb_lower']

            indicators[symbol] = symbol_indicators

        return indicators

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        生成交易信号

        Args:
            data: 交易对数据字典 {symbol: DataFrame}

        Returns:
            交易信号列表
        """
        signals = []

        # 初始化网格（如果尚未初始化）
        self._initialize_grids_if_needed(data)

        for symbol, df in data.items():
            if df.empty or symbol not in self.grid_prices:
                continue

            current_price = df['close'].iloc[-1]
            last_price = self.last_price.get(symbol, current_price)

            # 更新价格历史
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(current_price)
            if len(self.price_history[symbol]) > 100:  # 保持最近100个价格点
                self.price_history[symbol] = self.price_history[symbol][-100:]

            # 检查是否需要重平衡网格
            if self.enable_grid_rebalance:
                self._check_grid_rebalance(symbol, current_price)

            # 生成网格信号
            grid_signals = self._generate_grid_signals(symbol, current_price, last_price)
            signals.extend(grid_signals)

            # 生成趋势信号（用于网格方向确认）
            trend_signals = self._generate_trend_signals(symbol, df)
            signals.extend(trend_signals)

            # 更新上次价格
            self.last_price[symbol] = current_price

        return signals

    def _initialize_grids_if_needed(self, data: Dict[str, pd.DataFrame]):
        """
        如果需要，初始化网格

        Args:
            data: 交易对数据字典
        """
        for symbol, df in data.items():
            if df.empty or symbol in self.grid_prices:
                continue

            current_price = df['close'].iloc[-1]

            # 使用当前价格作为基准价格初始化网格
            if self.base_price is None:
                self.base_price = current_price
                self.logger.info(f"初始化网格，基准价格: {self.base_price:.2f}")

            # 计算网格价格
            self._calculate_grid_prices(symbol, current_price)

            # 初始化网格订单状态
            self._initialize_grid_orders(symbol)

    def _calculate_grid_prices(self, symbol: str, base_price: float):
        """
        计算网格价格

        Args:
            symbol: 交易对
            base_price: 基准价格
        """
        # 计算网格范围
        grid_range = base_price * self.grid_range_pct

        # 计算网格间距
        self.grid_spacing = grid_range / self.grid_count

        # 生成网格价格（从下到上）
        lower_price = base_price - grid_range / 2
        upper_price = base_price + grid_range / 2

        grid_prices = np.linspace(lower_price, upper_price, self.grid_count + 1)
        self.grid_prices[symbol] = grid_prices.tolist()

        self.logger.info(f"{symbol} 网格价格: {[round(p, 2) for p in self.grid_prices[symbol]]}")

    def _initialize_grid_orders(self, symbol: str):
        """
        初始化网格订单状态

        Args:
            symbol: 交易对
        """
        if symbol not in self.grid_orders:
            self.grid_orders[symbol] = {}
            self.executed_levels[symbol] = set()

            # 根据方向配置初始化网格订单
            grid_prices = self.grid_prices[symbol]
            current_price = self.last_price.get(symbol, self.base_price)

            for i, price in enumerate(grid_prices):
                if self.direction == 'long' or self.long_only:
                    # 仅做多模式：低于当前价格的网格为买入，高于的为卖出
                    if price < current_price:
                        self.grid_orders[symbol][price] = 'buy'
                    else:
                        self.grid_orders[symbol][price] = 'sell'

                elif self.direction == 'short' or self.short_only:
                    # 仅做空模式：高于当前价格的网格为卖出，低于的为买入
                    if price > current_price:
                        self.grid_orders[symbol][price] = 'sell'
                    else:
                        self.grid_orders[symbol][price] = 'buy'

                else:  # both
                    # 双向模式：交替设置买卖
                    if i % 2 == 0:
                        self.grid_orders[symbol][price] = 'buy'
                    else:
                        self.grid_orders[symbol][price] = 'sell'

    def _generate_grid_signals(self, symbol: str, current_price: float, last_price: float) -> List[Signal]:
        """
        生成网格交易信号

        Args:
            symbol: 交易对
            current_price: 当前价格
            last_price: 上次价格

        Returns:
            交易信号列表
        """
        signals = []

        if symbol not in self.grid_prices:
            return signals

        grid_prices = self.grid_prices[symbol]
        price_change_pct = abs(current_price - last_price) / last_price if last_price > 0 else 0

        # 检查价格变化是否足够触发网格
        if price_change_pct < self.min_price_change_pct:
            return signals

        # 找到当前价格最近的网格线
        closest_grid_idx = None
        closest_distance = float('inf')

        for i, grid_price in enumerate(grid_prices):
            distance = abs(current_price - grid_price)
            if distance < closest_distance:
                closest_distance = distance
                closest_grid_idx = i

        if closest_grid_idx is None:
            return signals

        closest_grid_price = grid_prices[closest_grid_idx]
        grid_order_type = self.grid_orders[symbol].get(closest_grid_price)

        # 检查是否触发网格交易
        signals_triggered = False

        # 检查买入信号
        if grid_order_type == 'buy':
            if current_price <= closest_grid_price and last_price > closest_grid_price:
                # 价格从上方跌破网格线，执行买入
                if closest_grid_idx not in self.executed_levels[symbol]:
                    signal = self._create_signal(symbol, SignalType.OPEN_LONG, closest_grid_price)
                    signals.append(signal)
                    self.executed_levels[symbol].add(closest_grid_idx)

                    # 更新网格状态：买入后，该级别变为卖出级别
                    self.grid_orders[symbol][closest_grid_price] = 'sell'

                    # 更新相邻网格状态
                    if closest_grid_idx + 1 < len(grid_prices):
                        self.grid_orders[symbol][grid_prices[closest_grid_idx + 1]] = 'buy'

                    signals_triggered = True
                    self.logger.info(f"网格买入信号: {symbol} @ {closest_grid_price:.2f}")

        # 检查卖出信号
        elif grid_order_type == 'sell':
            if current_price >= closest_grid_price and last_price < closest_grid_price:
                # 价格从下方突破网格线，执行卖出
                if closest_grid_idx not in self.executed_levels[symbol]:
                    signal = self._create_signal(symbol, SignalType.OPEN_SHORT, closest_grid_price)
                    signals.append(signal)
                    self.executed_levels[symbol].add(closest_grid_idx)

                    # 更新网格状态：卖出后，该级别变为买入级别
                    self.grid_orders[symbol][closest_grid_price] = 'buy'

                    # 更新相邻网格状态
                    if closest_grid_idx - 1 >= 0:
                        self.grid_orders[symbol][grid_prices[closest_grid_idx - 1]] = 'sell'

                    signals_triggered = True
                    self.logger.info(f"网格卖出信号: {symbol} @ {closest_grid_price:.2f}")

        return signals

    def _generate_trend_signals(self, symbol: str, df: pd.DataFrame) -> List[Signal]:
        """
        生成趋势信号（用于确认网格方向）

        Args:
            symbol: 交易对
            df: 价格数据

        Returns:
            趋势信号列表
        """
        signals = []

        if len(df) < 10:
            return signals

        current_price = df['close'].iloc[-1]

        # 根据方向配置过滤信号
        if self.direction == 'long' or self.long_only:
            # 仅做多：检查是否有强烈的上升趋势信号
            if 'sma_10' in self.indicators.get(symbol, {}):
                sma_10 = self.indicators[symbol]['sma_10']
                if current_price > sma_10 * 1.02:  # 价格显著高于均线
                    signal = self._create_signal(symbol, SignalType.OPEN_LONG, current_price)
                    signal.confidence = 0.7  # 趋势确认信号
                    signals.append(signal)

        elif self.direction == 'short' or self.short_only:
            # 仅做空：检查是否有强烈的下降趋势信号
            if 'sma_10' in self.indicators.get(symbol, {}):
                sma_10 = self.indicators[symbol]['sma_10']
                if current_price < sma_10 * 0.98:  # 价格显著低于均线
                    signal = self._create_signal(symbol, SignalType.OPEN_SHORT, current_price)
                    signal.confidence = 0.7  # 趋势确认信号
                    signals.append(signal)

        return signals

    def _check_grid_rebalance(self, symbol: str, current_price: float):
        """
        检查是否需要重平衡网格

        Args:
            symbol: 交易对
            current_price: 当前价格
        """
        if self.base_price is None:
            return

        # 如果价格偏离基准价格超过阈值，重新计算网格
        price_deviation = abs(current_price - self.base_price) / self.base_price

        if price_deviation > self.grid_rebalance_threshold:
            self.logger.info(f"{symbol} 价格偏离基准价格 {price_deviation:.2%}，重新计算网格")

            # 重新计算网格
            self._calculate_grid_prices(symbol, current_price)
            self._initialize_grid_orders(symbol)

            # 更新基准价格
            self.base_price = current_price

    def _create_signal(self, symbol: str, signal_type: SignalType, price: float) -> Signal:
        """
        创建交易信号

        Args:
            symbol: 交易对
            signal_type: 信号类型
            price: 价格

        Returns:
            交易信号
        """
        # 根据方向配置调整信号类型
        if self.direction == 'long' or self.long_only:
            if signal_type == SignalType.OPEN_SHORT:
                signal_type = SignalType.CLOSE_SHORT  # 转换为平空信号
        elif self.direction == 'short' or self.short_only:
            if signal_type == SignalType.OPEN_LONG:
                signal_type = SignalType.CLOSE_LONG   # 转换为平多信号

        # 计算订单数量
        amount = self.position_size

        # 设置止损和止盈
        stop_loss = None
        take_profit = None

        if signal_type in [SignalType.OPEN_LONG, SignalType.OPEN_SHORT]:
            stop_loss_pct = self.stop_loss_pct
            take_profit_pct = self.take_profit_pct

            if signal_type == SignalType.OPEN_LONG:
                stop_loss = price * (1 - stop_loss_pct)
                take_profit = price * (1 + take_profit_pct)
            else:  # OPEN_SHORT
                stop_loss = price * (1 + stop_loss_pct)
                take_profit = price * (1 - take_profit_pct)

        # 创建信号
        signal = Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                'strategy': 'enhanced_grid',
                'direction': self.direction,
                'grid_count': self.grid_count,
                'grid_range_pct': self.grid_range_pct,
                'base_price': self.base_price
            }
        )

        return signal

    def get_grid_status(self, symbol: str) -> Dict:
        """
        获取网格状态

        Args:
            symbol: 交易对

        Returns:
            网格状态字典
        """
        if symbol not in self.grid_prices:
            return {
                'status': 'not_initialized',
                'message': '网格尚未初始化'
            }

        current_price = self.last_price.get(symbol, 0)
        grid_prices = self.grid_prices[symbol]

        # 找到当前价格所在的网格级别
        current_level = None
        for i, price in enumerate(grid_prices):
            if current_price <= price:
                current_level = i
                break

        return {
            'status': 'active',
            'base_price': self.base_price,
            'current_price': current_price,
            'grid_prices': grid_prices,
            'grid_count': len(grid_prices),
            'grid_range_pct': self.grid_range_pct,
            'current_level': current_level,
            'executed_levels': list(self.executed_levels.get(symbol, [])),
            'direction': self.direction,
            'grid_orders': self.grid_orders.get(symbol, {})
        }

    def reset(self):
        """重置策略状态"""
        super().reset()

        self.base_price = None
        self.grid_prices = {}
        self.grid_orders = {}
        self.executed_levels = {}
        self.last_price = {}
        self.price_history = {}