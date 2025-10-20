#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据模块
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

from core.data.data_loader import DataLoader
from core.data.data_processor import DataProcessor
from core.data.data_storage import DataStorage


class TestData(unittest.TestCase):
    """数据模块测试类"""
    
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
        
        # 创建数据加载器
        self.data_loader = DataLoader()
        
        # 创建数据处理器
        self.data_processor = DataProcessor()
        
        # 创建数据存储器
        self.data_storage = DataStorage(self.temp_dir)
    
    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_data_loader_load_csv(self):
        """测试CSV数据加载"""
        # 保存测试数据为CSV
        csv_path = os.path.join(self.temp_dir, "test_data.csv")
        self.test_data.to_csv(csv_path, index=False)
        
        # 加载CSV数据
        loaded_data = self.data_loader.load_csv(csv_path)
        
        # 验证数据
        self.assertEqual(len(loaded_data), len(self.test_data))
        self.assertIn("timestamp", loaded_data.columns)
        self.assertIn("open", loaded_data.columns)
        self.assertIn("high", loaded_data.columns)
        self.assertIn("low", loaded_data.columns)
        self.assertIn("close", loaded_data.columns)
        self.assertIn("volume", loaded_data.columns)
    
    def test_data_loader_load_json(self):
        """测试JSON数据加载"""
        # 保存测试数据为JSON
        json_path = os.path.join(self.temp_dir, "test_data.json")
        self.test_data.to_json(json_path, orient="records")
        
        # 加载JSON数据
        loaded_data = self.data_loader.load_json(json_path)
        
        # 验证数据
        self.assertEqual(len(loaded_data), len(self.test_data))
        self.assertIn("timestamp", loaded_data.columns)
        self.assertIn("open", loaded_data.columns)
        self.assertIn("high", loaded_data.columns)
        self.assertIn("low", loaded_data.columns)
        self.assertIn("close", loaded_data.columns)
        self.assertIn("volume", loaded_data.columns)
    
    def test_data_processor_clean_data(self):
        """测试数据清洗"""
        # 添加缺失值
        dirty_data = self.test_data.copy()
        dirty_data.loc[10:15, "close"] = np.nan
        
        # 清洗数据
        clean_data = self.data_processor.clean_data(dirty_data)
        
        # 验证数据
        self.assertEqual(len(clean_data), len(self.test_data) - 6)  # 减少了6行
        self.assertFalse(clean_data.isnull().any().any())
    
    def test_data_processor_add_technical_indicators(self):
        """测试技术指标添加"""
        # 添加技术指标
        data_with_indicators = self.data_processor.add_technical_indicators(self.test_data)
        
        # 验证指标
        self.assertIn("sma_20", data_with_indicators.columns)
        self.assertIn("sma_50", data_with_indicators.columns)
        self.assertIn("rsi", data_with_indicators.columns)
        self.assertIn("macd", data_with_indicators.columns)
        self.assertIn("macd_signal", data_with_indicators.columns)
        self.assertIn("bb_upper", data_with_indicators.columns)
        self.assertIn("bb_middle", data_with_indicators.columns)
        self.assertIn("bb_lower", data_with_indicators.columns)
    
    def test_data_processor_resample_data(self):
        """测试数据重采样"""
        # 重采样为4小时
        resampled_data = self.data_processor.resample_data(self.test_data, "4h")
        
        # 验证数据
        self.assertLess(len(resampled_data), len(self.test_data))
        self.assertIn("timestamp", resampled_data.columns)
        self.assertIn("open", resampled_data.columns)
        self.assertIn("high", resampled_data.columns)
        self.assertIn("low", resampled_data.columns)
        self.assertIn("close", resampled_data.columns)
        self.assertIn("volume", resampled_data.columns)
    
    def test_data_storage_save_data(self):
        """测试数据保存"""
        # 保存数据
        symbol = "BTC/USDT"
        timeframe = "1h"
        self.data_storage.save_data(self.test_data, symbol, timeframe)
        
        # 验证文件是否存在（使用处理后的文件名）
        safe_symbol = symbol.replace('/', '_')
        file_path = os.path.join(self.temp_dir, f"{safe_symbol}_{timeframe}.csv")
        self.assertTrue(os.path.exists(file_path))
        
        # 验证数据
        loaded_data = pd.read_csv(file_path)
        self.assertEqual(len(loaded_data), len(self.test_data))
    
    def test_data_storage_load_data(self):
        """测试数据加载"""
        # 保存数据
        symbol = "BTC/USDT"
        timeframe = "1h"
        self.data_storage.save_data(self.test_data, symbol, timeframe)
        
        # 加载数据
        loaded_data = self.data_storage.load_data(symbol, timeframe)
        
        # 验证数据
        self.assertEqual(len(loaded_data), len(self.test_data))
        self.assertIn("timestamp", loaded_data.columns)
        self.assertIn("open", loaded_data.columns)
        self.assertIn("high", loaded_data.columns)
        self.assertIn("low", loaded_data.columns)
        self.assertIn("close", loaded_data.columns)
        self.assertIn("volume", loaded_data.columns)
    
    def test_data_storage_list_symbols(self):
        """测试交易对列表"""
        # 保存多个交易对的数据
        symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        timeframe = "1h"
        
        for symbol in symbols:
            self.data_storage.save_data(self.test_data, symbol, timeframe)
        
        # 列出交易对
        listed_symbols = self.data_storage.list_symbols(timeframe)
        
        # 验证交易对（使用原始符号）
        for symbol in symbols:
            self.assertIn(symbol, listed_symbols)
    
    def test_data_storage_delete_data(self):
        """测试数据删除"""
        # 保存数据
        symbol = "BTC/USDT"
        timeframe = "1h"
        self.data_storage.save_data(self.test_data, symbol, timeframe)
        
        # 验证文件是否存在（使用处理后的文件名）
        safe_symbol = symbol.replace('/', '_')
        file_path = os.path.join(self.temp_dir, f"{safe_symbol}_{timeframe}.csv")
        self.assertTrue(os.path.exists(file_path))
        
        # 删除数据
        self.data_storage.delete_data(symbol, timeframe)
        
        # 验证文件是否已删除
        self.assertFalse(os.path.exists(file_path))


if __name__ == "__main__":
    unittest.main()