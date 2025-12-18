#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正确的网格策略实现

严格按照网格交易的核心逻辑：低买高卖
解决之前版本中出现的"高买低卖"问题
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

from .base_strategy import BaseStrategy, Signal, SignalType


class CorrectGridStrategy(BaseStrategy):
    """
    修复版正确网格策略

    核心修复：
    1. 修复网格穿越方向错误：价格下跌应该买入，价格上涨应该卖出
    2. 修复价格数据范围问题：确保正确加载2024年全年数据
    3. 使用当前市场价格初始化网格，避免基准价格过低
    """

    def __init__(self, config: Dict):
        """初始化策略"""
        super().__init__(config)

        # 网格参数
        self.grid_count = config.get('grid_count', 50)
        self.grid_range_pct = config.get('grid_range_pct', 0.20)
        self.position_unit_pct = config.get('position_unit_pct', 0.02)

        # 初始化建仓参数
        self.enable_initial_position = config.get('enable_initial_position', True)
        self.initial_position_ratio = config.get('initial_position_ratio', 0.5)  # 建仓比例
        self.initial_position_pct = config.get('initial_position_pct', 0.1)  # 初始仓位占总资金比例

        # 趋势过滤参数
        self.ma_short = config.get('ma_short', 3)
        self.ma_long = config.get('ma_long', 8)

        # 风险管理参数
        self.max_position_pct = config.get('max_position_pct', 0.8)

        # 网格状态
        self.base_price = None
        self.grid_prices = {}
        self.last_price = {}
        self.grid_positions = {}
        self.grid_initialized = {}

        # 持仓管理
        self.positions = {}

        # 趋势状态
        self.trend_state = {}

        # 调试统计
        self.debug_stats = {
            'total_signals': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'price_updates': 0,
            'grid_resets': 0,
            'data_errors': 0
        }

        # 多时间框架数据缓存
        self.data_cache = {}

        self.logger = logging.getLogger(__name__)

    def initialize(self, config: Dict) -> None:
        """初始化策略"""
        self.logger.info("=== 初始化优化版正确网格策略 ===")

        self.initial_balance = config.get('initial_balance', 10000)
        self.symbols = config.get('symbols', [])

        print(f"[OPTIMIZED] 策略初始化:")
        print(f"  初始资金: {self.initial_balance}")
        print(f"  交易对: {self.symbols}")
        print(f"  网格数量: {self.grid_count}")
        print(f"  网格范围: {self.grid_range_pct:.1%}")
        print(f"  每份仓位: {self.position_unit_pct:.1%}")
        print(f"  初始化建仓: {'开启' if self.enable_initial_position else '关闭'}")
        if self.enable_initial_position:
            print(f"  建仓比例: {self.initial_position_ratio:.1%}")
            print(f"  初始仓位: {self.initial_position_pct:.1%}")

        # 初始化状态
        for symbol in self.symbols:
            self.positions[symbol] = {
                'trades': [],
                'current_position': 0,
                'avg_cost': 0,
                'total_cost': 0
            }
            self.grid_positions[symbol] = {}
            self.last_price[symbol] = None
            self.trend_state[symbol] = {'direction': 'neutral', 'strength': 0.5}
            self.grid_initialized[symbol] = False

        self.logger.info(f"策略初始化完成，覆盖 {len(self.symbols)} 个交易对")

    def build_initial_position(self, symbol: str, current_price: float, current_time: pd.Timestamp) -> List[Signal]:
        """构建初始仓位"""
        if not self.enable_initial_position:
            return []

        # 计算要建立的网格数量（一半网格）
        grids_to_build = int(self.grid_count * self.initial_position_ratio)

        # 选择中心网格线附近的网格进行建仓
        grid_prices = self.grid_prices.get(symbol, [])
        if not grid_prices:
            return []

        # 选择中心附近的网格线
        center_idx = len(grid_prices) // 2
        start_idx = max(0, center_idx - grids_to_build // 2)
        end_idx = min(len(grid_prices), center_idx + grids_to_build // 2)

        signals = []
        total_value = 0
        target_value = self.initial_balance * self.initial_position_pct

        print(f"[INITIAL] {symbol} 开始建仓:")
        print(f"  当前价格: {current_price:.2f}")
        print(f"  目标仓位价值: {target_value:.2f}")
        print(f"  建仓网格数: {grids_to_build}")

        # 为选定的网格建立初始仓位
        for i in range(start_idx, end_idx):
            grid_price = grid_prices[i]

            # 计算该网格的仓位大小
            grid_value = target_value / (end_idx - start_idx)
            quantity = grid_value / current_price

            # 创建买入信号
            signal = Signal(
                signal_type=SignalType.OPEN_LONG,
                symbol=symbol,
                price=current_price,
                amount=quantity,
                confidence=1.0,
                metadata={
                    'grid_price': grid_price,
                    'crossing_type': 'initial_position',
                    'current_price': current_price,
                    'current_time': str(current_time),
                    'strategy_type': 'optimized_grid',
                    'debug_info': f'初始建仓: 网格{grid_price:.2f}, 市场价{current_price:.2f}, 数量{quantity:.6f}'
                }
            )
            signals.append(signal)

            # 记录网格持仓
            self.grid_positions[symbol][grid_price] += quantity
            total_value += grid_value

            print(f"[INITIAL] {symbol} 建仓买入: 网格={grid_price:.2f}, 市场价={current_price:.2f}, 数量={quantity:.6f}")

        print(f"[INITIAL] {symbol} 建仓完成: 总价值={total_value:.2f}, 预期网格数={end_idx-start_idx}")
        return signals

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """计算技术指标"""
        indicators = {}
        for symbol, df in data.items():
            if df.empty:
                continue

            symbol_indicators = {}
            if len(df) >= 5:
                symbol_indicators['current_price'] = df['close'].iloc[-1]
                symbol_indicators['price_change_1h'] = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) if len(df) >= 2 else 0
                symbol_indicators['price_volatility'] = df['close'].pct_change().std() if len(df) >= 2 else 0

                if len(df) >= 10:
                    symbol_indicators['sma_10'] = df['close'].rolling(10).mean().iloc[-1]
                    symbol_indicators['price_above_sma_10'] = df['close'].iloc[-1] > symbol_indicators['sma_10']

            indicators[symbol] = symbol_indicators

        return indicators

    def _cache_multi_timeframe_data(self, data: Dict[str, pd.DataFrame]) -> None:
        """缓存多时间框架数据"""
        for symbol_key, df in data.items():
            if '_' in symbol_key:
                symbol = symbol_key.rsplit('_', 1)[0]
                timeframe = symbol_key.split('_')[-1]
            else:
                symbol = symbol_key
                timeframe = self._detect_timeframe(df)

            if symbol not in self.data_cache:
                self.data_cache[symbol] = {}

            self.data_cache[symbol][timeframe] = df.copy()

    def _detect_timeframe(self, df: pd.DataFrame) -> str:
        """检测数据的时间框架"""
        if len(df) < 2:
            return 'unknown'

        time_diff = df.index[1] - df.index[0]
        if time_diff.days >= 1:
            return '1d'
        elif time_diff.seconds >= 3600:
            return '1h'
        elif time_diff.seconds >= 900:
            return '15m'
        else:
            return '5m'

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """生成交易信号"""
        signals = []
        self._cache_multi_timeframe_data(data)

        # 整理数据
        symbol_data = {}
        for symbol_key, df in data.items():
            if '_' in symbol_key:
                symbol = symbol_key.rsplit('_', 1)[0]
                timeframe = symbol_key.split('_')[-1]
            else:
                symbol = symbol_key
                timeframe = 'unknown'

            if symbol not in symbol_data:
                symbol_data[symbol] = {}
            symbol_data[symbol][timeframe] = df

        # 为每个符号生成信号
        for symbol, data_dict in symbol_data.items():
            # 优先使用15m数据
            df = data_dict.get('15m')
            if df is None or len(df) < 2:
                # 如果没有15m，尝试其他时间框架
                for timeframe in ['1h', '1d']:
                    if timeframe in data_dict and len(data_dict[timeframe]) > 1:
                        df = data_dict[timeframe]
                        break

            if df is None or len(df) < 2:
                continue

            # 初始化网格（如果还没有初始化）
            if not self.grid_initialized.get(symbol, False):
                self._initialize_symbol_with_data(symbol, df)
                # 网格初始化后立即建仓
                current_price = df['close'].iloc[-1]
                current_time = df.index[-1]
                initial_signals = self.build_initial_position(symbol, current_price, current_time)
                signals.extend(initial_signals)
                # 更新最后价格
                self.last_price[symbol] = current_price
                continue

            current_price = df['close'].iloc[-1]
            prev_price = self.last_price.get(symbol, current_price)
            current_time = df.index[-1]

            # 调试信息
            self.debug_stats['price_updates'] += 1
            if self.debug_stats['price_updates'] % 1000 == 0:
                print(f"[OPTIMIZED] {symbol} 价格更新 #{self.debug_stats['price_updates']}: {current_price:.2f} @ {current_time}")

            # 验证价格变化
            if abs(current_price - prev_price) / prev_price < 0.0001:
                continue

            # 检查基本风险控制
            if not self._check_basic_risk(symbol, current_price):
                self.last_price[symbol] = current_price
                continue

            # 更新趋势分析
            self._update_trend_analysis(symbol)

            # 生成正确的网格信号
            grid_signals = self._generate_fixed_grid_signals(symbol, current_price, prev_price, current_time)
            signals.extend(grid_signals)

            # 更新最后价格
            self.last_price[symbol] = current_price

        self.debug_stats['total_signals'] = len(signals)
        return signals

    def _initialize_symbol_with_data(self, symbol: str, df: pd.DataFrame) -> None:
        """使用数据初始化网格"""
        if len(df) == 0:
            self.debug_stats['data_errors'] += 1
            print(f"[ERROR] {symbol} 数据为空，跳过初始化")
            return

        current_price = df['close'].iloc[-1]
        current_time = df.index[-1]

        print(f"[FIXED] {symbol} 网格初始化:")
        print(f"  当前时间: {current_time}")
        print(f"  当前价格: {current_price:.2f}")
        print(f"  数据范围: {df.index[0]} 到 {df.index[-1]}")
        print(f"  价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")

        # 使用当前价格作为网格中心
        self.base_price = current_price
        self.last_price[symbol] = current_price

        # 计算网格层级
        self._calculate_grid_levels(symbol)

        # 标记为已初始化
        self.grid_initialized[symbol] = True

        print(f"[FIXED] {symbol} 网格初始化完成: 基准价格 {self.base_price:.2f}")

    def _calculate_grid_levels(self, symbol: str) -> None:
        """计算网格层级"""
        if self.base_price is None:
            return

        # 生成均匀分布的网格价格
        grid_prices = []
        half_range = self.grid_range_pct / 2

        for i in range(self.grid_count):
            # 从基准价格向下50%到向上50%范围
            price_pct = -half_range + (i * self.grid_range_pct / (self.grid_count - 1))
            price = self.base_price * (1 + price_pct)
            grid_prices.append(price)

        grid_prices.sort()
        self.grid_prices[symbol] = grid_prices

        # 初始化网格持仓记录
        self.grid_positions[symbol] = {price: 0 for price in grid_prices}

        print(f"[FIXED] {symbol} 网格价格范围: {grid_prices[0]:.2f} - {grid_prices[-1]:.2f}")
        print(f"[FIXED] {symbol} 网格间距: {(grid_prices[1] - grid_prices[0]):.4f} ({(grid_prices[1] - grid_prices[0])/grid_prices[0]*100:.3f}%)")

    def _update_trend_analysis(self, symbol: str) -> None:
        """更新趋势分析"""
        if symbol not in self.data_cache or '1d' not in self.data_cache[symbol]:
            return

        df_daily = self.data_cache[symbol]['1d']
        if len(df_daily) < self.ma_long:
            return

        # 计算移动平均线
        ma_short = df_daily['close'].rolling(self.ma_short).mean().iloc[-1]
        ma_long = df_daily['close'].rolling(self.ma_long).mean().iloc[-1]
        current_price = df_daily['close'].iloc[-1]

        # 判断趋势方向
        if current_price > ma_short > ma_long:
            direction = 'bullish'
            strength = min(0.9, (current_price - ma_long) / ma_long)
        elif current_price < ma_short < ma_long:
            direction = 'bearish'
            strength = min(0.9, (ma_long - current_price) / ma_long)
        else:
            direction = 'neutral'
            strength = 0.5

        self.trend_state[symbol] = {'direction': direction, 'strength': strength}

    
    def _generate_fixed_grid_signals(self, symbol: str, current_price: float, prev_price: float, current_time: pd.Timestamp) -> List[Signal]:
        """生成最终修复版网格信号 - 解决初始化建仓冲突问题

        修复的关键问题：
        1. 防止初始化建仓后立即触发卖出
        2. 只在真正穿越网格线时交易
        3. 确保卖出价格高于买入价格（止盈逻辑）
        4. 避免微小波动触发过多交易
        """
        signals = []

        if symbol not in self.grid_prices:
            return signals

        grid_prices = self.grid_prices[symbol]
        grid_positions = self.grid_positions[symbol]
        trend_info = self.trend_state[symbol]

        # 防止价格变化过小导致的频繁交易
        price_change_pct = abs(current_price - prev_price) / prev_price
        if price_change_pct < 0.001:  # 价格变化小于0.1%时不交易
            return signals

        # 计算当前价格在网格中的位置
        current_grids_above = [gp for gp in grid_prices if current_price > gp]
        current_grids_below = [gp for gp in grid_prices if current_price < gp]
        prev_grids_above = [gp for gp in grid_prices if prev_price > gp]
        prev_grids_below = [gp for gp in grid_prices if prev_price < gp]

        # === 最终修复后的网格穿越逻辑 ===

        # 价格上涨穿越网格线 -> 卖出（止盈）
        newly_crossed_grids_up = set(prev_grids_below) - set(current_grids_below)
        for grid_price in sorted(newly_crossed_grids_up):
            if grid_positions[grid_price] > 0:
                quantity = grid_positions[grid_price]

                # 【关键修复】确保卖出价格高于网格价格（止盈逻辑）
                if current_price <= grid_price * 1.001:  # 价格必须高于网格价格至少0.1%
                    print(f"[FIXED] {symbol} 跳过亏损卖出: 网格={grid_price:.2f}, 市场价={current_price:.2f} (价格过低)")
                    continue

                # 智能卖出策略：根据趋势和持仓时间调整
                sell_multiplier = 1.0

                # 1. 趋势增强：在上涨趋势中分批卖出
                if trend_info['direction'] == 'bullish':
                    if trend_info['strength'] > 0.7:
                        sell_multiplier = 0.7  # 强势上涨时保留部分仓位
                    elif trend_info['strength'] > 0.5:
                        sell_multiplier = 0.85  # 中等上涨时部分卖出

                # 2. 计算实际卖出数量
                actual_sell_quantity = min(quantity, quantity * sell_multiplier)

                # 计算预期盈利
                position_info = self.positions[symbol]
                if position_info['avg_cost'] > 0:
                    expected_pnl_pct = (current_price - position_info['avg_cost']) / position_info['avg_cost']

                    # 如果盈利超过3%，全部卖出
                    if expected_pnl_pct > 0.03:
                        actual_sell_quantity = quantity
                        sell_multiplier = 1.0

                signal = Signal(
                    signal_type=SignalType.CLOSE_LONG,
                    symbol=symbol,
                    price=current_price,
                    amount=actual_sell_quantity,
                    confidence=0.8,
                    metadata={
                        'grid_price': grid_price,
                        'crossing_type': 'upward_sell',
                        'trend_direction': trend_info['direction'],
                        'trend_strength': trend_info['strength'],
                        'sell_multiplier': sell_multiplier,
                        'expected_pnl_pct': expected_pnl_pct if position_info['avg_cost'] > 0 else 0,
                        'current_price': current_price,
                        'current_time': str(current_time),
                        'strategy_type': 'final_fixed_grid',
                        'debug_info': f'最终卖出: 网格{grid_price:.2f}, 市场价{current_price:.2f}, 比例{sell_multiplier:.1%}'
                    }
                )
                signals.append(signal)
                self.debug_stats['sell_signals'] += 1

                # 更新网格持仓
                grid_positions[grid_price] -= actual_sell_quantity
                if grid_positions[grid_price] < 0.001:
                    grid_positions[grid_price] = 0

                print(f"[FINAL] {symbol} 卖出: 网格={grid_price:.2f}, 市场价={current_price:.2f}, 数量={actual_sell_quantity:.6f}, 盈利={(expected_pnl_pct if position_info['avg_cost'] > 0 else 0):.2%}")

        # 价格下跌穿越网格线 -> 买入（低吸）
        newly_crossed_grids_down = set(prev_grids_above) - set(current_grids_above)
        for grid_price in sorted(newly_crossed_grids_down):
            # 检查该网格位置是否已有持仓（避免重复建仓）
            if grid_positions[grid_price] > 0:
                print(f"[FINAL] {symbol} 跳过重复建仓: 网格={grid_price:.2f} 已有持仓={grid_positions[grid_price]:.6f}")
                continue

            # 【关键修复】确保买入价格低于网格价格（低吸逻辑）
            if current_price >= grid_price * 0.999:  # 价格必须低于网格价格至少0.1%
                print(f"[FINAL] {symbol} 跳过追高买入: 网格={grid_price:.2f}, 市场价={current_price:.2f} (价格过高)")
                continue

            # 智能风险管理
            should_buy = True
            quantity_multiplier = 1.0

            # 1. 趋势过滤
            if trend_info['direction'] == 'bearish':
                if trend_info['strength'] > 0.8:
                    should_buy = False  # 强烈下跌趋势不买入
                elif trend_info['strength'] > 0.6:
                    quantity_multiplier = 0.5  # 中等下跌趋势减半买入

            # 2. 位置调整：在网格下半部分增加买入量
            grid_index = grid_prices.index(grid_price)
            grid_center = len(grid_prices) // 2
            if grid_index < grid_center:
                quantity_multiplier *= 1.5

            # 3. 仓位限制检查
            position_info = self.positions[symbol]
            current_value = position_info['current_position'] * current_price
            max_value = self.initial_balance * self.max_position_pct

            if should_buy and current_value < max_value * 0.8:
                quantity = self._calculate_position_size(symbol, current_price) * quantity_multiplier

                signal = Signal(
                    signal_type=SignalType.OPEN_LONG,
                    symbol=symbol,
                    price=current_price,
                    amount=quantity,
                    confidence=0.8,
                    metadata={
                        'grid_price': grid_price,
                        'crossing_type': 'downward_buy',
                        'trend_direction': trend_info['direction'],
                        'trend_strength': trend_info['strength'],
                        'quantity_multiplier': quantity_multiplier,
                        'current_price': current_price,
                        'current_time': str(current_time),
                        'strategy_type': 'final_fixed_grid',
                        'debug_info': f'最终买入: 网格{grid_price:.2f}, 市场价{current_price:.2f}, 倍数={quantity_multiplier:.1f}x'
                    }
                )
                signals.append(signal)
                self.debug_stats['buy_signals'] += 1

                # 记录网格持仓
                grid_positions[grid_price] += quantity

                print(f"[FINAL] {symbol} 买入: 网格={grid_price:.2f}, 市场价={current_price:.2f}, 数量={quantity:.6f}, 倍数={quantity_multiplier:.1f}x")

        return signals

    def _check_basic_risk(self, symbol: str, current_price: float) -> bool:
        """基本风险检查"""
        position_info = self.positions[symbol]

        # 检查最大仓位限制
        current_value = position_info['current_position'] * current_price
        max_value = self.initial_balance * self.max_position_pct

        if current_value >= max_value:
            return False

        return True

    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """计算仓位大小"""
        base_value = self.initial_balance * self.position_unit_pct
        quantity = base_value / price
        return quantity

    def _should_buy(self, symbol: str, grid_price: float, current_price: float, last_price: float) -> bool:
        """判断是否应该买入"""
        # 价格下跌到网格线或以下
        return (current_price <= grid_price and
                (last_price > grid_price or self.last_price.get(symbol) is None))

    def _should_sell(self, symbol: str, grid_price: float, current_price: float, last_price: float) -> bool:
        """判断是否应该卖出"""
        # 价格上涨到网格线或以上
        return (current_price >= grid_price and
                (last_price < grid_price or self.last_price.get(symbol) is None))

    def _can_buy(self, symbol: str, grid_price: float) -> bool:
        """判断是否可以买入"""
        position_info = self.positions[symbol]

        # 检查是否已有更低价格的买入
        for bought_price in position_info['bought_grids']:
            if bought_price < grid_price:
                return False  # 已有更低价格买入，不能再买更高价格

        return True

    def _can_sell(self, symbol: str, grid_price: float) -> bool:
        """判断是否可以卖出"""
        position_info = self.positions[symbol]

        # 必须有更低价格的买入持仓
        for bought_price in position_info['bought_grids']:
            if bought_price < grid_price and position_info['current_position'] > 0:
                return True  # 有更低价格买入，可以卖出

        return False

    def _create_buy_signal(self, symbol: str, price: float, level: int) -> Signal:
        """创建买入信号"""
        return Signal(
            signal_type=SignalType.OPEN_LONG,
            symbol=symbol,
            price=price,
            amount=self.position_size,
            stop_loss=price * (1 - self.stop_loss_pct),
            take_profit=price * (1 + self.take_profit_pct),
            metadata={
                'strategy': 'correct_grid',
                'grid_level': level,
                'grid_price': price,
                'action': 'buy'
            }
        )

    def _create_sell_signal(self, symbol: str, price: float, level: int) -> Signal:
        """创建卖出信号"""
        return Signal(
            signal_type=SignalType.CLOSE_LONG,
            symbol=symbol,
            price=price,
            amount=self.position_size,
            metadata={
                'strategy': 'correct_grid',
                'grid_level': level,
                'grid_price': price,
                'action': 'sell'
            }
        )

    def _execute_buy(self, symbol: str, price: float, level: int, signal: Signal):
        """执行买入操作"""
        position_info = self.positions[symbol]
        grid_levels = self.grid_levels[symbol]

        # 更新持仓信息
        position_info['bought_grids'].append(price)
        position_info['current_position'] += signal.amount

        # 更新平均成本
        total_cost = position_info.get('avg_cost', 0) * (position_info['current_position'] - signal.amount) + price * signal.amount
        position_info['avg_cost'] = total_cost / position_info['current_position']

        # 标记网格已执行
        grid_levels[level]['executed'] = True
        grid_levels[level]['executed_time'] = datetime.now()
        grid_levels[level]['position_size'] = signal.amount

        self.logger.info(f"执行买入: {symbol} @ {price:.2f}, 持仓数量: {position_info['current_position']:.3f}")

    def _execute_sell(self, symbol: str, price: float, level: int, signal: Signal):
        """执行卖出操作"""
        position_info = self.positions[symbol]
        grid_levels = self.grid_levels[symbol]

        # 找到对应的买入价格
        bought_price = None
        for bp in position_info['bought_grids']:
            if bp < price:
                bought_price = bp
                break

        if bought_price:
            # 计算盈亏
            pnl = (price - bought_price) / bought_price * 100

            # 更新持仓信息
            position_info['current_position'] -= signal.amount
            if position_info['current_position'] <= 0:
                position_info['current_position'] = 0
                position_info['avg_cost'] = 0
                position_info['bought_grids'] = []  # 清空买入记录

            self.logger.info(f"执行卖出: {symbol} @ {price:.2f}, 买入价格: {bought_price:.2f}, 盈亏: {pnl:.2f}%")

        # 标记网格已执行
        grid_levels[level]['executed'] = True
        grid_levels[level]['executed_time'] = datetime.now()

    def _check_grid_rebalance(self, symbol: str, current_price: float):
        """检查网格重平衡"""
        if self.base_price is None:
            return

        price_deviation = abs(current_price - self.base_price) / self.base_price

        if price_deviation > self.grid_rebalance_threshold:
            self.logger.info(f"{symbol} 价格偏离 {price_deviation:.2%}，重平衡网格")

            # 重平衡网格
            self._calculate_grid_levels(symbol, current_price)

            # 更新基准价格
            self.base_price = current_price

    def get_grid_status(self, symbol: str) -> Dict:
        """获取网格状态"""
        if symbol not in self.grid_levels:
            return {'status': 'not_initialized'}

        position_info = self.positions[symbol]
        current_price = self.last_price.get(symbol, 0)

        return {
            'status': 'active',
            'base_price': self.base_price,
            'current_price': current_price,
            'grid_count': len(self.grid_prices.get(symbol, [])),
            'current_position': position_info['current_position'],
            'avg_cost': position_info.get('avg_cost', 0),
            'bought_grids': position_info['bought_grids'],
            'executed_levels': [level for level, info in self.grid_levels[symbol].items() if info['executed']]
        }

    def on_fill(self, signal: Signal, fill_price: float, fill_quantity: float, commission: float) -> None:
        """处理成交回报"""
        symbol = signal.symbol
        position_info = self.positions[symbol]

        if signal.signal_type == SignalType.OPEN_LONG:
            # 记录买入交易
            trade = {
                'buy_price': fill_price,
                'quantity': fill_quantity,
                'buy_time': signal.timestamp,
                'sell_price': None,
                'sell_time': None,
                'pnl': 0.0,
                'debug_info': signal.metadata.get('debug_info', '')
            }
            position_info['trades'].append(trade)

            # 更新持仓
            position_info['current_position'] += fill_quantity
            position_info['total_cost'] += fill_price * fill_quantity
            position_info['avg_cost'] = position_info['total_cost'] / position_info['current_position']

            print(f"[FIXED] {symbol} 买入成交: {fill_price:.2f} x {fill_quantity:.6f} ({signal.metadata.get('debug_info', '')})")

        elif signal.signal_type == SignalType.CLOSE_LONG:
            if position_info['current_position'] == 0:
                return

            # 计算盈亏
            pnl_per_unit = fill_price - position_info['avg_cost']
            total_pnl = pnl_per_unit * fill_quantity - commission
            pnl_pct = pnl_per_unit / position_info['avg_cost']

            # 更新交易记录
            remaining_sell = fill_quantity
            for trade in position_info['trades']:
                if trade['sell_price'] is None and remaining_sell > 0:
                    sell_qty = min(trade['quantity'], remaining_sell)
                    trade_pnl = (fill_price - trade['buy_price']) * sell_qty - commission * (sell_qty / fill_quantity)
                    trade['sell_price'] = fill_price
                    trade['sell_time'] = signal.timestamp
                    trade['pnl'] = trade_pnl / (trade['buy_price'] * sell_qty)
                    remaining_sell -= sell_qty

            # 更新持仓
            position_info['current_position'] -= fill_quantity
            position_info['total_cost'] -= position_info['avg_cost'] * fill_quantity

            if position_info['current_position'] > 0:
                position_info['avg_cost'] = position_info['total_cost'] / position_info['current_position']
            else:
                position_info['current_position'] = 0
                position_info['avg_cost'] = 0
                position_info['total_cost'] = 0

            print(f"[FIXED] {symbol} 卖出成交: {fill_price:.2f} x {fill_quantity:.6f}, 盈亏={pnl_pct:.2%} ({total_pnl:.2f}) ({signal.metadata.get('debug_info', '')})")

    def get_strategy_state(self) -> Dict:
        """获取策略状态"""
        state = {
            'strategy_name': 'CorrectGridStrategy',
            'debug_stats': self.debug_stats,
            'base_price': self.base_price,
            'grid_count': self.grid_count,
            'grid_range_pct': self.grid_range_pct,
            'positions': {}
        }

        for symbol in self.positions:
            position_info = self.positions[symbol]
            completed_trades = [t for t in position_info['trades'] if t['sell_price'] is not None]

            state['positions'][symbol] = {
                'current_position': position_info['current_position'],
                'avg_cost': position_info['avg_cost'],
                'pending_trades': len(position_info['trades']) - len(completed_trades),
                'completed_trades': len(completed_trades)
            }

        return state

    def reset(self):
        """重置策略状态"""
        super().reset()

        self.base_price = None
        self.grid_prices = {}
        self.grid_positions = {}
        self.grid_initialized = {}
        self.positions = {}
        self.last_price = {}
        self.trend_state = {}
        self.data_cache = {}
        self.debug_stats = {
            'total_signals': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'price_updates': 0,
            'grid_resets': 0,
            'data_errors': 0
        }