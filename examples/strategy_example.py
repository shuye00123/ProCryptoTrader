#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例策略：双均线策略
演示如何创建自定义策略
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from core.strategy.base_strategy import BaseStrategy, SignalType, Position
from core.utils.logger import get_logger

logger = get_logger("DualMovingAverageStrategy")


class DualMovingAverageStrategy(BaseStrategy):
    """
    双均线策略
    
    策略逻辑：
    1. 计算短期和长期移动平均线
    2. 当短期均线上穿长期均线时，产生买入信号
    3. 当短期均线下穿长期均线时，产生卖出信号
    4. 支持止损和止盈
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化策略
        
        Args:
            config: 策略配置参数
        """
        super().__init__(config)
        
        # 策略参数
        self.short_window = config.get("short_window", 10)
        self.long_window = config.get("long_window", 30)
        self.stop_loss = config.get("stop_loss", 0.05)  # 5% 止损
        self.take_profit = config.get("take_profit", 0.1)  # 10% 止盈
        self.position_size = config.get("position_size", 0.5)  # 50% 仓位
        
        # 验证参数
        if self.short_window >= self.long_window:
            raise ValueError("短期窗口必须小于长期窗口")
        
        # 策略状态
        self.short_ma = None
        self.long_ma = None
        self.last_signal = None
        self.entry_price = None
        
        logger.info(f"双均线策略初始化完成，短期窗口: {self.short_window}, 长期窗口: {self.long_window}")
    
    def initialize(self, data: pd.DataFrame) -> None:
        """
        初始化策略，计算指标
        
        Args:
            data: 历史数据
        """
        # 计算移动平均线
        data['short_ma'] = data['close'].rolling(window=self.short_window).mean()
        data['long_ma'] = data['close'].rolling(window=self.long_window).mean()
        
        # 计算交叉信号
        data['signal'] = 0
        data['signal'][self.short_window:] = np.where(
            data['short_ma'][self.short_window:] > data['long_ma'][self.short_window:], 1, 0
        )
        data['positions'] = data['signal'].diff()
        
        # 保存最后一行的指标值
        self.short_ma = data['short_ma'].iloc[-1]
        self.long_ma = data['long_ma'].iloc[-1]
        
        logger.info(f"策略初始化完成，短期MA: {self.short_ma:.4f}, 长期MA: {self.long_ma:.4f}")
    
    def generate_signals(self, data: pd.DataFrame) -> List[SignalType]:
        """
        生成交易信号
        
        Args:
            data: 最新数据
            
        Returns:
            交易信号列表
        """
        signals = []
        
        # 更新指标
        self._update_indicators(data)
        
        # 获取最新价格
        current_price = data['close'].iloc[-1]
        
        # 检查是否有持仓
        current_position = self.get_position()
        
        # 如果没有持仓，检查买入信号
        if current_position is None or current_position.size == 0:
            # 短期均线上穿长期均线，产生买入信号
            if self.short_ma > self.long_ma and (self.last_signal is None or self.last_signal == SignalType.SELL):
                signal = SignalType.BUY
                signals.append(signal)
                self.last_signal = signal
                self.entry_price = current_price
                logger.info(f"生成买入信号，价格: {current_price:.4f}")
        else:
            # 有持仓，检查卖出信号
            # 短期均线下穿长期均线，产生卖出信号
            if self.short_ma < self.long_ma and self.last_signal == SignalType.BUY:
                signal = SignalType.SELL
                signals.append(signal)
                self.last_signal = signal
                logger.info(f"生成卖出信号，价格: {current_price:.4f}")
            # 检查止损
            elif current_price <= self.entry_price * (1 - self.stop_loss):
                signal = SignalType.SELL
                signals.append(signal)
                self.last_signal = signal
                logger.info(f"触发止损，价格: {current_price:.4f}, 入场价: {self.entry_price:.4f}")
            # 检查止盈
            elif current_price >= self.entry_price * (1 + self.take_profit):
                signal = SignalType.SELL
                signals.append(signal)
                self.last_signal = signal
                logger.info(f"触发止盈，价格: {current_price:.4f}, 入场价: {self.entry_price:.4f}")
        
        return signals
    
    def _update_indicators(self, data: pd.DataFrame) -> None:
        """
        更新指标
        
        Args:
            data: 最新数据
        """
        # 更新移动平均线
        self.short_ma = data['close'].rolling(window=self.short_window).mean().iloc[-1]
        self.long_ma = data['close'].rolling(window=self.long_window).mean().iloc[-1]
    
    def calculate_position_size(self, signal: SignalType, price: float, balance: float) -> float:
        """
        计算仓位大小
        
        Args:
            signal: 交易信号
            price: 当前价格
            balance: 账户余额
            
        Returns:
            仓位大小
        """
        if signal == SignalType.BUY:
            # 使用固定比例的仓位
            return balance * self.position_size / price
        else:
            # 卖出时，卖出全部持仓
            current_position = self.get_position()
            if current_position:
                return current_position.size
            return 0
    
    def on_order_filled(self, order: Dict[str, Any]) -> None:
        """
        订单成交回调
        
        Args:
            order: 订单信息
        """
        symbol = order.get("symbol")
        side = order.get("side")
        amount = order.get("amount")
        price = order.get("price")
        
        if side == "buy":
            logger.info(f"买入订单成交: {symbol}, 数量: {amount}, 价格: {price:.4f}")
            # 更新持仓
            self.update_position(Position(
                symbol=symbol,
                size=amount,
                entry_price=price,
                entry_time=datetime.now()
            ))
        else:
            logger.info(f"卖出订单成交: {symbol}, 数量: {amount}, 价格: {price:.4f}")
            # 清空持仓
            self.update_position(None)


def main():
    """主函数，用于测试策略"""
    # 创建策略配置
    config = {
        "short_window": 10,
        "long_window": 30,
        "stop_loss": 0.05,
        "take_profit": 0.1,
        "position_size": 0.5
    }
    
    # 创建策略实例
    strategy = DualMovingAverageStrategy(config)
    
    # 生成测试数据
    dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
    prices = np.cumsum(np.random.randn(100) * 0.01) + 100
    data = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices + np.random.rand(100) * 0.5,
        "low": prices - np.random.rand(100) * 0.5,
        "close": prices,
        "volume": np.random.randint(1000, 10000, 100)
    })
    
    # 初始化策略
    strategy.initialize(data)
    
    # 测试信号生成
    signals = strategy.generate_signals(data)
    print(f"生成的信号: {signals}")
    
    # 测试仓位计算
    if signals:
        signal = signals[0]
        price = data['close'].iloc[-1]
        balance = 10000
        position_size = strategy.calculate_position_size(signal, price, balance)
        print(f"仓位大小: {position_size}")


if __name__ == "__main__":
    main()