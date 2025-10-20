#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略模块
"""

import unittest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.strategy.grid_strategy import GridStrategy
from core.strategy.martingale_strategy import MartingaleStrategy
from core.strategy.dual_ma_strategy import DualMovingAverageStrategy
from core.strategy.base_strategy import SignalType


class TestStrategies(unittest.TestCase):
    """策略测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建测试数据
        dates = pd.date_range(start="2023-01-01", periods=100, freq="1h")
        prices = np.cumsum(np.random.randn(100) * 0.01) + 100
        
        self.test_data = pd.DataFrame({
            "timestamp": dates,
            "open": prices,
            "high": prices + np.random.rand(100) * 0.5,
            "low": prices - np.random.rand(100) * 0.5,
            "close": prices,
            "volume": np.random.randint(100, 1000, 100)
        })
    
    def test_grid_strategy_initialization(self):
        """测试网格策略初始化"""
        config = {
            "grid_count": 10,
            "grid_range_pct": 0.1,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = GridStrategy(config)
        
        # 验证参数设置
        self.assertEqual(strategy.grid_count, 10)
        self.assertEqual(strategy.grid_range_pct, 0.1)
        self.assertEqual(strategy.symbols, ["BTC/USDT"])
    
    def test_grid_strategy_initialize(self):
        """测试网格策略初始化数据"""
        config = {
            "grid_count": 10,
            "grid_range_pct": 0.1,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = GridStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 验证网格价格
        self.assertIsNotNone(strategy.grid_prices.get("BTC/USDT"))
        self.assertEqual(len(strategy.grid_prices["BTC/USDT"]), strategy.grid_count + 1)
        
        # 验证网格订单
        self.assertIsNotNone(strategy.grid_orders.get("BTC/USDT"))
    
    def test_grid_strategy_generate_signals(self):
        """测试网格策略生成信号"""
        config = {
            "grid_count": 10,
            "grid_range_pct": 0.1,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = GridStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 生成信号
        signals = strategy.generate_signals({"BTC/USDT": self.test_data})
        
        # 验证信号类型
        for signal in signals:
            self.assertIn(signal.signal_type, [SignalType.OPEN_LONG, SignalType.OPEN_SHORT, 
                                             SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT])
    
    def test_martingale_strategy_initialization(self):
        """测试马丁格尔策略初始化"""
        config = {
            "base_order_size": 0.001,
            "multiplier": 2.0,
            "max_orders": 10,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = MartingaleStrategy(config)
        
        # 验证参数设置
        self.assertEqual(strategy.config.get("base_order_size"), 0.001)
        self.assertEqual(strategy.config.get("multiplier"), 2.0)
        self.assertEqual(strategy.config.get("max_orders"), 10)
        self.assertEqual(strategy.symbols, ["BTC/USDT"])
    
    def test_martingale_strategy_initialize(self):
        """测试马丁格尔策略初始化数据"""
        config = {
            "base_order_size": 0.001,
            "multiplier": 2.0,
            "max_orders": 10,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = MartingaleStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 验证初始状态
        self.assertIsNotNone(strategy.current_data.get("BTC/USDT"))
    
    def test_martingale_strategy_generate_signals(self):
        """测试马丁格尔策略生成信号"""
        config = {
            "base_order_size": 0.001,
            "multiplier": 2.0,
            "max_orders": 10,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = MartingaleStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 生成信号
        signals = strategy.generate_signals({"BTC/USDT": self.test_data})
        
        # 验证信号类型
        for signal in signals:
            self.assertIn(signal.signal_type, [SignalType.OPEN_LONG, SignalType.OPEN_SHORT, 
                                             SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT])
    
    def test_dual_ma_strategy_initialization(self):
        """测试双均线策略初始化"""
        config = {
            "short_period": 10,
            "long_period": 20,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = DualMovingAverageStrategy(config)
        
        # 验证参数设置
        self.assertEqual(strategy.config.get("short_period"), 10)
        self.assertEqual(strategy.config.get("long_period"), 20)
        self.assertEqual(strategy.symbols, ["BTC/USDT"])
    
    def test_dual_ma_strategy_initialize(self):
        """测试双均线策略初始化数据"""
        config = {
            "short_period": 10,
            "long_period": 20,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = DualMovingAverageStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 验证指标计算
        self.assertIsNotNone(strategy.indicators.get("BTC/USDT"))
    
    def test_dual_ma_strategy_generate_signals(self):
        """测试双均线策略生成信号"""
        config = {
            "short_period": 10,
            "long_period": 20,
            "symbols": ["BTC/USDT"]
        }
        
        strategy = DualMovingAverageStrategy(config)
        # 使用update方法代替initialize
        strategy.update({"BTC/USDT": self.test_data})
        
        # 生成信号
        signals = strategy.generate_signals({"BTC/USDT": self.test_data})
        
        # 验证信号类型
        for signal in signals:
            self.assertIn(signal.signal_type, [SignalType.OPEN_LONG, SignalType.OPEN_SHORT, 
                                             SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT])
    
    def test_dual_ma_strategy_invalid_params(self):
        """测试双均线策略无效参数"""
        # 短期窗口大于长期窗口
        config = {
            "short_period": 30,
            "long_period": 10,
            "symbols": ["BTC/USDT"]
        }
        
        # 验证抛出异常
        with self.assertRaises(ValueError):
            DualMovingAverageStrategy(config)


if __name__ == "__main__":
    unittest.main()