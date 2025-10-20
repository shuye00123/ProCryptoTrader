#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件读取示例
演示如何使用config_parser模块读取和解析配置文件
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.utils.config import ConfigParser


def read_backtest_config():
    """读取回测配置文件"""
    print("=" * 50)
    print("读取回测配置文件")
    print("=" * 50)
    
    # 配置文件路径
    config_path = project_root / "configs" / "backtest_config.yaml"
    
    # 创建配置解析器
    parser = ConfigParser()
    
    # 读取配置文件
    config = parser.read_config(config_path)
    
    # 打印基本信息
    print(f"回测开始日期: {config.get('basic.start_date')}")
    print(f"回测结束日期: {config.get('basic.end_date')}")
    print(f"初始资金: {config.get('basic.initial_balance')}")
    print(f"策略名称: {config.get('strategy.name')}")
    
    # 打印策略参数
    print("\n策略参数:")
    for key, value in config.get('strategy.params', {}).items():
        print(f"  {key}: {value}")
    
    # 打印交易对
    print("\n交易对:")
    for symbol in config.get('data.symbols', []):
        print(f"  - {symbol}")
    
    return config


def read_live_config():
    """读取实盘配置文件"""
    print("\n" + "=" * 50)
    print("读取实盘配置文件")
    print("=" * 50)
    
    # 配置文件路径
    config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建配置解析器
    parser = ConfigParser()
    
    # 读取配置文件
    config = parser.read_config(config_path)
    
    # 打印基本信息
    print(f"交易模式: {config.get('basic.mode')}")
    print(f"时区: {config.get('misc.timezone')}")
    
    # 打印策略信息
    print("\n策略列表:")
    for i, strategy in enumerate(config.get('strategies', [])):
        print(f"  策略 {i+1}:")
        print(f"    名称: {strategy.get('name')}")
        print(f"    交易对: {strategy.get('symbols')}")
        print(f"    时间框架: {strategy.get('timeframe')}")
        print(f"    启用状态: {strategy.get('enabled')}")
    
    # 打印交易所信息
    print("\n交易所设置:")
    for name, settings in config.get('exchanges', {}).items():
        print(f"  {name}:")
        print(f"    启用: {settings.get('enabled')}")
        print(f"    测试环境: {settings.get('sandbox')}")
        print(f"    杠杆倍数: {settings.get('leverage')}")
    
    return config


def merge_configs():
    """合并配置文件"""
    print("\n" + "=" * 50)
    print("合并配置文件")
    print("=" * 50)
    
    # 配置文件路径
    backtest_config_path = project_root / "configs" / "backtest_config.yaml"
    live_config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建配置解析器
    parser = ConfigParser()
    
    # 读取配置文件
    backtest_config = parser.read_config(backtest_config_path)
    live_config = parser.read_config(live_config_path)
    
    # 合并配置
    merged_config = parser.merge_configs(backtest_config, live_config)
    
    # 打印合并后的配置信息
    print(f"合并后的策略数量: {len(merged_config.get('strategies', []))}")
    print(f"合并后的交易对数量: {len(merged_config.get('data.symbols', []))}")
    
    return merged_config


def validate_config():
    """验证配置文件"""
    print("\n" + "=" * 50)
    print("验证配置文件")
    print("=" * 50)
    
    # 配置文件路径
    config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建配置解析器
    parser = ConfigParser()
    
    # 读取配置文件
    config = parser.read_config(config_path)
    
    # 定义验证规则
    schema = {
        "basic": {
            "mode": {"type": str, "required": True, "choices": ["paper", "live"]},
            "symbols": {"type": list, "required": True, "min_items": 1},
            "timeframes": {"type": list, "required": True, "min_items": 1}
        },
        "risk": {
            "max_drawdown": {"type": (int, float), "required": True, "min_value": 0, "max_value": 1},
            "max_loss_per_trade": {"type": (int, float), "required": True, "min_value": 0, "max_value": 1},
            "max_open_positions": {"type": int, "required": True, "min_value": 1}
        }
    }
    
    # 验证配置
    is_valid, errors = parser.validate_config(config, schema)
    
    if is_valid:
        print("配置文件验证通过!")
    else:
        print("配置文件验证失败:")
        for error in errors:
            print(f"  - {error}")
    
    return is_valid


def save_config():
    """保存配置文件"""
    print("\n" + "=" * 50)
    print("保存配置文件")
    print("=" * 50)
    
    # 创建配置解析器
    parser = ConfigParser()
    
    # 创建示例配置
    config = {
        "basic": {
            "mode": "paper",
            "symbols": ["BTC/USDT", "ETH/USDT"],
            "timeframes": ["1h", "4h"]
        },
        "strategy": {
            "name": "TestStrategy",
            "params": {
                "param1": "value1",
                "param2": 100
            }
        },
        "risk": {
            "max_drawdown": 0.2,
            "max_loss_per_trade": 0.05
        }
    }
    
    # 保存配置文件
    output_path = project_root / "configs" / "test_config.yaml"
    parser.save_config(config, output_path)
    
    print(f"配置文件已保存到: {output_path}")
    
    # 读取并验证保存的配置
    saved_config = parser.read_config(output_path)
    print(f"保存的配置中的策略名称: {saved_config.get('strategy.name')}")
    
    return output_path


def main():
    """主函数"""
    print("配置文件读取示例")
    print("=" * 50)
    
    # 读取回测配置
    backtest_config = read_backtest_config()
    
    # 读取实盘配置
    live_config = read_live_config()
    
    # 合并配置
    merged_config = merge_configs()
    
    # 验证配置
    is_valid = validate_config()
    
    # 保存配置
    save_config()
    
    print("\n" + "=" * 50)
    print("示例执行完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()