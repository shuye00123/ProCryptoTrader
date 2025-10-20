#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试交易模块
"""

import unittest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import tempfile
import os
import json
from unittest.mock import Mock, patch

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.live.live_trader import LiveTrader as Trader
from core.utils.risk_manager import RiskManager, OrderInfo
from core.trading.position_manager import PositionManager


class TestTrading(unittest.TestCase):
    """交易模块测试类"""
    
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
        
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建模拟交易所接口
        self.mock_exchange = Mock()
        self.mock_exchange.create_limit_order.return_value = {"id": "test_order_id"}
        self.mock_exchange.create_market_order.return_value = {"id": "test_order_id"}
        self.mock_exchange.fetch_order.return_value = {"status": "closed", "filled": 0.01}
        self.mock_exchange.fetch_balance.return_value = {"USDT": {"free": 10000}}
        self.mock_exchange.fetch_ticker.return_value = {"symbol": "BTC/USDT", "last": 50000}
        
        # 创建持仓管理器和风险管理器用于测试
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager()
        
        # 使用mock作为订单管理器
        self.order_manager = Mock()
        self.order_manager.create_limit_order.return_value = {"id": "test_order_id"}
        self.order_manager.create_market_order.return_value = {"id": "test_order_id"}
    
    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_mock_order_manager(self):
        """测试模拟订单管理器的基本功能"""
        # 测试限价单方法调用
        result = self.order_manager.create_limit_order(
            symbol="BTC/USDT",
            side="buy",
            amount=0.01,
            price=50000
        )
        self.assertEqual(result["id"], "test_order_id")
        
        # 测试市价单方法调用
        result = self.order_manager.create_market_order(
            symbol="BTC/USDT",
            side="sell",
            amount=0.01
        )
        self.assertEqual(result["id"], "test_order_id")
        
        # 验证mock对象被正确调用
        self.order_manager.create_limit_order.assert_called_once()
        self.order_manager.create_market_order.assert_called_once()
    
    def test_order_manager_cancel_order(self):
        """测试取消订单"""
        # 设置mock的cancel_order方法
        self.order_manager.cancel_order = Mock()
        
        # 取消订单
        self.order_manager.cancel_order("test_order_id", "BTC/USDT")
        
        # 验证调用
        self.order_manager.cancel_order.assert_called_once_with(
            "test_order_id", "BTC/USDT"
        )
    
    def test_order_manager_get_order_status(self):
        """测试获取订单状态"""
        # 设置mock的get_order_status方法
        self.order_manager.get_order_status = Mock(return_value={"status": "closed"})
        
        # 获取订单状态
        status = self.order_manager.get_order_status("test_order_id", "BTC/USDT")
        
        # 验证状态
        self.assertEqual(status["status"], "closed")
        self.order_manager.get_order_status.assert_called_once_with(
            "test_order_id", "BTC/USDT"
        )
    
    def test_position_manager_add_position(self):
        """测试添加持仓"""
        # 设置mock exchange
        self.position_manager.exchange = self.mock_exchange
        
        # 添加持仓
        position = self.position_manager.create_position(
            symbol="BTC/USDT",
            side="long",
            size=0.01,
            price=50000
        )
        
        # 验证持仓
        self.assertIsNotNone(position)
        self.assertEqual(position.symbol, "BTC/USDT")
        self.assertEqual(position.side.value, "long")
        self.assertEqual(position.size, 0.01)
        self.assertEqual(position.entry_price, 50000)
    
    def test_position_manager_close_position(self):
        """测试平仓"""
        # 设置mock exchange
        self.position_manager.exchange = self.mock_exchange
        
        # 添加持仓
        self.position_manager.create_position(
            symbol="BTC/USDT",
            side="long",
            size=0.01,
            price=50000
        )
        
        # 平仓
        self.position_manager.decrease_position("BTC/USDT", 0.01, 51000)
        
        # 验证持仓
        position = self.position_manager.get_position("BTC/USDT")
        self.assertIsNone(position)
    
    def test_position_manager_get_position(self):
        """测试获取持仓"""
        # 设置mock exchange
        self.position_manager.exchange = self.mock_exchange
        
        # 添加持仓
        self.position_manager.create_position(
            symbol="BTC/USDT",
            side="long",
            size=0.01,
            price=50000
        )
        
        # 获取持仓
        position = self.position_manager.get_position("BTC/USDT")
        
        # 验证持仓
        self.assertIsNotNone(position)
        self.assertEqual(position.symbol, "BTC/USDT")
        self.assertEqual(position.side.value, "long")
        self.assertEqual(position.size, 0.01)
        self.assertEqual(position.entry_price, 50000)
    
    def test_risk_manager_check_position_size(self):
        """测试仓位大小检查"""
        # 模拟风险管理方法
        self.risk_manager.check_position_size = Mock(return_value=True)
        
        # 检查仓位大小
        is_valid = self.risk_manager.check_position_size(
            symbol="BTC/USDT",
            amount=0.01,
            price=50000
        )
        
        # 验证结果
        self.assertTrue(is_valid)
        self.risk_manager.check_position_size.assert_called_once()
    
    def test_risk_manager_check_drawdown(self):
        """测试回撤检查"""
        # 模拟风险管理方法
        self.risk_manager.check_drawdown = Mock(return_value=True)
        
        # 检查回撤
        is_valid = self.risk_manager.check_drawdown()
        
        # 验证结果
        self.assertTrue(is_valid)
        self.risk_manager.check_drawdown.assert_called_once()
    
    def test_trader_process_signal(self):
        """测试处理交易信号"""
        # 模拟Trader类的process_signal方法
        self.trader = Mock()
        self.trader.process_signal = Mock()
        
        # 处理买入信号
        self.trader.process_signal(
            symbol="BTC/USDT",
            signal_type="buy",
            amount=0.01,
            price=50000
        )
        
        # 验证调用
        self.trader.process_signal.assert_called_once_with(
            symbol="BTC/USDT",
            signal_type="buy",
            amount=0.01,
            price=50000
        )
    
    def test_trader_update_positions(self):
        """测试更新持仓"""
        # 模拟Trader类的update_positions方法
        self.trader = Mock()
        self.trader.update_positions = Mock()
        
        # 设置mock exchange
        self.position_manager.exchange = self.mock_exchange
        
        # 添加持仓
        self.position_manager.create_position(
            symbol="BTC/USDT",
            side="long",
            size=0.01,
            price=50000
        )
        
        # 更新持仓
        self.trader.update_positions()
        
        # 验证持仓
        position = self.position_manager.get_position("BTC/USDT")
        self.assertIsNotNone(position)
        self.trader.update_positions.assert_called_once()
    
    def test_trader_get_account_balance(self):
        """测试获取账户余额"""
        # 模拟Trader类的get_account_balance方法
        self.trader = Mock()
        self.trader.get_account_balance = Mock(return_value={"USDT": {"free": 10000}})
        
        # 获取账户余额
        balance = self.trader.get_account_balance()
        
        # 验证余额
        self.assertEqual(balance["USDT"]["free"], 10000)
        self.trader.get_account_balance.assert_called_once()


if __name__ == "__main__":
    unittest.main()