#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单移动平均策略
用于测试回测系统
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.strategy.base_strategy import BaseStrategy, Signal, SignalType

class SimpleMAStrategy(BaseStrategy):
    """
    简单移动平均策略
    当短期均线上穿长期均线时买入，下穿时卖出
    """

    def __init__(self, config: dict):
        """
        初始化策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 策略参数
        self.short_window = config.get('short_window', 10)
        self.long_window = config.get('long_window', 30)
        self.symbol = config.get('symbol', 'BTC/USDT')

        # 策略状态
        self.short_ma = None
        self.long_ma = None
        self.position = False  # 是否有持仓

        print(f"初始化简单移动平均策略:")
        print(f"  短期窗口: {self.short_window}")
        print(f"  长期窗口: {self.long_window}")
        print(f"  交易对: {self.symbol}")

    def calculate_indicators(self, data: dict) -> dict:
        """
        计算技术指标

        Args:
            data: 交易对数据字典

        Returns:
            技术指标字典
        """
        indicators = {}

        for symbol, df in data.items():
            if symbol not in indicators:
                indicators[symbol] = {}

            if len(df) >= self.long_window:
                # 计算移动平均线
                indicators[symbol]['short_ma'] = df['close'].rolling(window=self.short_window).mean()
                indicators[symbol]['long_ma'] = df['close'].rolling(window=self.long_window).mean()
                indicators[symbol]['price'] = df['close']
            else:
                indicators[symbol]['short_ma'] = pd.Series([np.nan] * len(df))
                indicators[symbol]['long_ma'] = pd.Series([np.nan] * len(df))
                indicators[symbol]['price'] = df['close']

        return indicators

    def generate_signals(self, data: dict) -> list:
        """
        根据行情数据生成交易信号

        Args:
            data: 交易对数据字典

        Returns:
            交易信号列表
        """
        signals = []

        # 获取当前交易对的数据
        if self.symbol not in data:
            return signals

        df = data[self.symbol]

        if df.empty or len(df) < self.long_window:
            return signals

        # 首先计算指标
        indicators = self.calculate_indicators(data)
        symbol_indicators = indicators.get(self.symbol, {})

        if 'short_ma' not in symbol_indicators or 'long_ma' not in symbol_indicators:
            return signals

        # 获取最新的指标值
        current_price = df['close'].iloc[-1]
        short_ma = symbol_indicators['short_ma'].iloc[-1]
        long_ma = symbol_indicators['long_ma'].iloc[-1]

        # 检查是否有有效的均线值
        if pd.isna(short_ma) or pd.isna(long_ma):
            return signals

        # 计算前一个交易日的均线值
        prev_short_ma = symbol_indicators['short_ma'].iloc[-2] if len(symbol_indicators['short_ma']) >= 2 else np.nan
        prev_long_ma = symbol_indicators['long_ma'].iloc[-2] if len(symbol_indicators['long_ma']) >= 2 else np.nan

        if pd.isna(prev_short_ma) or pd.isna(prev_long_ma):
            return signals

        # 生成交易信号
        # 金叉：短期均线上穿长期均线，买入信号
        if (prev_short_ma <= prev_long_ma) and (short_ma > long_ma) and not self.position:
            signal = Signal(
                signal_type=SignalType.OPEN_LONG,
                symbol=self.symbol,
                price=current_price,
                amount=0.1,  # 使用10%资金
                confidence=0.7
            )
            signals.append(signal)
            self.position = True
            print(f"{df.index[-1]}: 买入信号 - 价格: {current_price:.2f}, 短期MA: {short_ma:.2f}, 长期MA: {long_ma:.2f}")

        # 死叉：短期均线下穿长期均线，卖出信号
        elif (prev_short_ma >= prev_long_ma) and (short_ma < long_ma) and self.position:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=current_price,
                amount=1.0,  # 全部卖出
                confidence=0.7
            )
            signals.append(signal)
            self.position = False
            print(f"{df.index[-1]}: 卖出信号 - 价格: {current_price:.2f}, 短期MA: {short_ma:.2f}, 长期MA: {long_ma:.2f}")

        return signals

    def initialize(self, config: dict):
        """
        初始化策略（用于回测开始前）

        Args:
            config: 回测配置
        """
        print(f"策略初始化完成")
        print(f"初始资金: {config.get('initial_balance', 10000):.2f}")
        print(f"交易对: {config.get('symbols', [])}")
        print(f"时间范围: {config.get('start_date')} 至 {config.get('end_date')}")

# 为了兼容回测引擎，需要创建一个适配器
class BacktestCompatibleStrategy(BaseStrategy):
    """
    兼容回测引擎的策略适配器
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.ma_strategy = SimpleMAStrategy(config)
        self.last_signal_type = None

    def calculate_indicators(self, data: dict) -> dict:
        return self.ma_strategy.calculate_indicators(data)

    def generate_signals(self, data: dict) -> list:
        signals = []

        # 获取策略信号
        ma_signals = self.ma_strategy.generate_signals(data)

        # 转换信号类型以兼容回测引擎
        for signal in ma_signals:
            if signal.signal_type == SignalType.OPEN_LONG:
                # 转换为兼容的信号类型
                compatible_signal = Signal(
                    signal_type=SignalType.OPEN_LONG,
                    symbol=signal.symbol,
                    price=signal.price,
                    amount=signal.amount,
                    confidence=signal.confidence
                )
                signals.append(compatible_signal)
            elif signal.signal_type == SignalType.CLOSE_LONG:
                # 转换为兼容的信号类型
                compatible_signal = Signal(
                    signal_type=SignalType.CLOSE_LONG,
                    symbol=signal.symbol,
                    price=signal.price,
                    amount=signal.amount,
                    confidence=signal.confidence
                )
                signals.append(compatible_signal)

        return signals

    def update(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        更新策略状态并生成信号

        Args:
            data: 交易对数据字典

        Returns:
            交易信号列表
        """
        return self.generate_signals(data)

    def initialize(self, config: dict):
        self.ma_strategy.initialize(config)