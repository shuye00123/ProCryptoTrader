#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试配置文件解析器
"""

import unittest
import tempfile
import os
import json
import yaml
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from core.utils.config import ConfigParser


class TestConfigParser(unittest.TestCase):
    """配置解析器测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.parser = ConfigParser()
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建测试配置数据
        self.test_config = {
            "basic": {
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_balance": 10000
            },
            "strategy": {
                "name": "GridStrategy",
                "params": {
                    "grid_size": 0.01,
                    "grid_levels": 10
                }
            }
        }
    
    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_read_json_config(self):
        """测试读取JSON配置文件"""
        # 创建JSON配置文件
        json_file = os.path.join(self.temp_dir, "test.json")
        with open(json_file, 'w') as f:
            json.dump(self.test_config, f)
        
        # 读取配置
        config = self.parser.read_config(json_file)
        
        # 验证结果
        self.assertEqual(config.get("basic.start_date"), "2023-01-01")
        self.assertEqual(config.get("basic.end_date"), "2023-12-31")
        self.assertEqual(config.get("basic.initial_balance"), 10000)
        self.assertEqual(config.get("strategy.name"), "GridStrategy")
        self.assertEqual(config.get("strategy.params.grid_size"), 0.01)
        self.assertEqual(config.get("strategy.params.grid_levels"), 10)
    
    def test_read_yaml_config(self):
        """测试读取YAML配置文件"""
        # 创建YAML配置文件
        yaml_file = os.path.join(self.temp_dir, "test.yaml")
        with open(yaml_file, 'w') as f:
            yaml.dump(self.test_config, f)
        
        # 读取配置
        config = self.parser.read_config(yaml_file)
        
        # 验证结果
        self.assertEqual(config.get("basic.start_date"), "2023-01-01")
        self.assertEqual(config.get("basic.end_date"), "2023-12-31")
        self.assertEqual(config.get("basic.initial_balance"), 10000)
        self.assertEqual(config.get("strategy.name"), "GridStrategy")
        self.assertEqual(config.get("strategy.params.grid_size"), 0.01)
        self.assertEqual(config.get("strategy.params.grid_levels"), 10)
    
    def test_save_json_config(self):
        """测试保存JSON配置文件"""
        # 保存配置
        json_file = os.path.join(self.temp_dir, "test_save.json")
        self.parser.save_config(self.test_config, json_file)
        
        # 验证文件是否存在
        self.assertTrue(os.path.exists(json_file))
        
        # 读取并验证内容
        with open(json_file, 'r') as f:
            saved_config = json.load(f)
        
        self.assertEqual(saved_config, self.test_config)
    
    def test_save_yaml_config(self):
        """测试保存YAML配置文件"""
        # 保存配置
        yaml_file = os.path.join(self.temp_dir, "test_save.yaml")
        self.parser.save_config(self.test_config, yaml_file)
        
        # 验证文件是否存在
        self.assertTrue(os.path.exists(yaml_file))
        
        # 读取并验证内容
        with open(yaml_file, 'r') as f:
            saved_config = yaml.safe_load(f)
        
        self.assertEqual(saved_config, self.test_config)
    
    def test_merge_configs(self):
        """测试合并配置"""
        # 创建第二个配置
        config2 = {
            "basic": {
                "end_date": "2024-01-01",  # 覆盖第一个配置的值
                "benchmark": "BTC/USDT"    # 新增字段
            },
            "trading": {  # 新增部分
                "commission": 0.001,
                "slippage": 0.0005
            }
        }
        
        # 合并配置
        merged = self.parser.merge_configs(self.test_config, config2)
        
        # 验证结果
        self.assertEqual(merged.get("basic.start_date"), "2023-01-01")  # 保留原值
        self.assertEqual(merged.get("basic.end_date"), "2024-01-01")    # 使用新值
        self.assertEqual(merged.get("basic.benchmark"), "BTC/USDT")     # 新增字段
        self.assertEqual(merged.get("strategy.name"), "GridStrategy")   # 保留原部分
        self.assertEqual(merged.get("trading.commission"), 0.001)       # 新增部分
        self.assertEqual(merged.get("trading.slippage"), 0.0005)        # 新增部分
    
    def test_validate_config_success(self):
        """测试配置验证成功"""
        # 定义验证规则
        schema = {
            "basic": {
                "start_date": {"type": str, "required": True},
                "end_date": {"type": str, "required": True},
                "initial_balance": {"type": (int, float), "required": True, "min_value": 0}
            },
            "strategy": {
                "name": {"type": str, "required": True},
                "params": {"type": dict, "required": True}
            }
        }
        
        # 验证配置
        is_valid, errors = self.parser.validate_config(self.test_config, schema)
        
        # 验证结果
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_validate_config_failure(self):
        """测试配置验证失败"""
        # 创建无效配置
        invalid_config = {
            "basic": {
                "start_date": "2023-01-01",
                # 缺少 end_date
                "initial_balance": -1000  # 负值，不符合 min_value: 0
            },
            "strategy": {
                # 缺少 name
                "params": "not a dict"  # 不是字典类型
            }
        }
        
        # 定义验证规则
        schema = {
            "basic": {
                "start_date": {"type": str, "required": True},
                "end_date": {"type": str, "required": True},
                "initial_balance": {"type": (int, float), "required": True, "min_value": 0}
            },
            "strategy": {
                "name": {"type": str, "required": True},
                "params": {"type": dict, "required": True}
            }
        }
        
        # 验证配置
        is_valid, errors = self.parser.validate_config(invalid_config, schema)
        
        # 验证结果
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
        # 检查错误信息
        error_messages = " ".join(errors)
        self.assertIn("end_date", error_messages)  # 缺少必需字段
        self.assertIn("initial_balance", error_messages)  # 值小于最小值
        self.assertIn("name", error_messages)  # 缺少必需字段
        self.assertIn("params", error_messages)  # 类型错误


if __name__ == "__main__":
    unittest.main()