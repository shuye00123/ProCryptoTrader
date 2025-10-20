#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试回测模块
"""

import unittest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import tempfile
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.backtest.backtester import Backtester
from core.backtest.metrics import MetricsCalculator
from core.backtest.report_generator import ReportGenerator
from core.strategy.grid_strategy import GridStrategy


class TestBacktest(unittest.TestCase):
    """回测测试类"""
    
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
        
        # 创建策略配置
        self.strategy_config = {
            "grid_size": 0.01,
            "grid_levels": 10,
            "order_size": 0.01,
            "take_profit": 0.02,
            "stop_loss": 0.05
        }
        
        # 创建策略实例
        self.strategy = GridStrategy(self.strategy_config)
        
        # 创建回测引擎
        self.backtester = Backtester(
            initial_balance=10000,
            commission=0.001,
            slippage=0.0005
        )
        
        # 创建绩效计算器
        self.metrics_calculator = MetricsCalculator()
        
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_backtester_initialization(self):
        """测试回测引擎初始化"""
        # 验证参数设置
        self.assertEqual(self.backtester.initial_balance, 10000)
        self.assertEqual(self.backtester.commission, 0.001)
        self.assertEqual(self.backtester.slippage, 0.0005)
        
        # 验证初始状态
        self.assertEqual(self.backtester.current_balance, 10000)
        self.assertEqual(len(self.backtester.trades), 0)
        self.assertEqual(len(self.backtester.positions), 0)
    
    def test_backtester_run(self):
        """测试回测引擎运行"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        
        # 验证结果
        self.assertIn("trades", results)
        self.assertIn("portfolio_value", results)
        self.assertIn("returns", results)
        self.assertIn("benchmark_returns", results)
        
        # 验证交易记录
        self.assertGreater(len(results["trades"]), 0)
        
        # 验证投资组合价值
        self.assertEqual(len(results["portfolio_value"]), len(self.test_data))
        
        # 验证收益率
        self.assertEqual(len(results["returns"]), len(self.test_data))
    
    def test_metrics_calculator_total_return(self):
        """测试总收益率计算"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        
        # 计算绩效指标
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 验证总收益率
        self.assertIn("total_return", metrics)
        self.assertIsInstance(metrics["total_return"], float)
    
    def test_metrics_calculator_sharpe_ratio(self):
        """测试夏普比率计算"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        
        # 计算绩效指标
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 验证夏普比率
        self.assertIn("sharpe_ratio", metrics)
        self.assertIsInstance(metrics["sharpe_ratio"], float)
    
    def test_metrics_calculator_max_drawdown(self):
        """测试最大回撤计算"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        
        # 计算绩效指标
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 验证最大回撤
        self.assertIn("max_drawdown", metrics)
        self.assertIsInstance(metrics["max_drawdown"], float)
        self.assertGreaterEqual(metrics["max_drawdown"], 0)
    
    def test_metrics_calculator_win_rate(self):
        """测试胜率计算"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        
        # 计算绩效指标
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 验证胜率
        self.assertIn("win_rate", metrics)
        self.assertIsInstance(metrics["win_rate"], float)
        self.assertGreaterEqual(metrics["win_rate"], 0)
        self.assertLessEqual(metrics["win_rate"], 1)
    
    def test_report_generator_html_report(self):
        """测试HTML报告生成"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 生成HTML报告
        report_generator = ReportGenerator()
        report_path = report_generator.generate_html_report(results, metrics, self.temp_dir)
        
        # 验证报告文件是否存在
        self.assertTrue(os.path.exists(report_path))
        
        # 验证报告内容
        with open(report_path, 'r') as f:
            content = f.read()
            self.assertIn("<html>", content)
            self.assertIn("回测报告", content)
    
    def test_report_generator_markdown_report(self):
        """测试Markdown报告生成"""
        # 运行回测
        results = self.backtester.run(self.strategy, self.test_data)
        metrics = self.metrics_calculator.calculate_all(results)
        
        # 生成Markdown报告
        report_generator = ReportGenerator()
        report_path = report_generator.generate_markdown_report(results, metrics, self.temp_dir)
        
        # 验证报告文件是否存在
        self.assertTrue(os.path.exists(report_path))
        
        # 验证报告内容
        with open(report_path, 'r') as f:
            content = f.read()
            self.assertIn("# 回测报告", content)
            self.assertIn("## 绩效指标", content)


if __name__ == "__main__":
    unittest.main()