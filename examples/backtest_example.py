#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测脚本示例
演示如何使用回测模块进行策略回测
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.backtest.backtester import Backtester
from core.backtest.metrics import MetricsCalculator
from core.backtest.report_generator import ReportGenerator
from core.data.data_loader import DataLoader
from core.strategy.grid_strategy import GridStrategy
from core.strategy.martingale_strategy import MartingaleStrategy
from examples.strategy_example import DualMovingAverageStrategy
from core.utils.logger import get_logger
from core.utils.config import ConfigParser

logger = get_logger("BacktestExample")


def load_data_from_config(config_path: str) -> pd.DataFrame:
    """
    从配置文件加载数据
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        K线数据
    """
    # 读取配置
    parser = ConfigParser()
    config = parser.read_config(config_path)
    
    # 获取数据设置
    data_config = config.get("data", {})
    symbols = data_config.get("symbols", ["BTC/USDT"])
    timeframes = data_config.get("timeframes", ["1h"])
    data_dir = data_config.get("data_dir", "./data")
    
    # 加载数据
    data_loader = DataLoader(data_dir)
    
    # 这里我们使用模拟数据，实际应用中应该从文件加载
    logger.info("生成模拟数据用于回测示例")
    
    # 生成模拟数据
    start_date = datetime.strptime(config.get("basic.start_date", "2023-01-01"), "%Y-%m-%d")
    end_date = datetime.strptime(config.get("basic.end_date", "2023-12-31"), "%Y-%m-%d")
    dates = pd.date_range(start=start_date, end=end_date, freq="1h")
    
    # 生成价格数据
    np.random.seed(42)  # 设置随机种子，确保结果可复现
    price = 50000  # 初始价格
    prices = [price]
    
    for _ in range(len(dates) - 1):
        # 随机游走
        change = np.random.normal(0, 0.01)  # 平均0，标准差1%
        price = price * (1 + change)
        prices.append(price)
    
    # 创建DataFrame
    data = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
        "low": [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
        "close": prices,
        "volume": np.random.randint(100, 1000, len(dates))
    })
    
    return data


def run_grid_strategy_backtest(config_path: str):
    """
    运行网格策略回测
    
    Args:
        config_path: 配置文件路径
    """
    logger.info("=" * 50)
    logger.info("运行网格策略回测")
    logger.info("=" * 50)
    
    # 读取配置
    parser = ConfigParser()
    config = parser.read_config(config_path)
    
    # 获取策略配置
    strategy_config = config.get("strategy", {})
    strategy_params = strategy_config.get("params", {})
    
    # 创建策略实例
    strategy = GridStrategy(strategy_params)
    
    # 加载数据
    data = load_data_from_config(config_path)
    
    # 创建回测引擎
    backtester = Backtester(
        initial_balance=config.get("basic.initial_balance", 10000),
        commission=config.get("trading.commission", 0.001),
        slippage=config.get("trading.slippage", 0.0005)
    )
    
    # 运行回测
    results = backtester.run(strategy, data)
    
    # 计算绩效指标
    metrics_calculator = MetricsCalculator()
    metrics = metrics_calculator.calculate_all(results)
    
    # 打印绩效指标
    logger.info("回测结果:")
    logger.info(f"总收益率: {metrics['total_return']:.2%}")
    logger.info(f"年化收益率: {metrics['annualized_return']:.2%}")
    logger.info(f"最大回撤: {metrics['max_drawdown']:.2%}")
    logger.info(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    logger.info(f"胜率: {metrics['win_rate']:.2%}")
    logger.info(f"交易次数: {metrics['total_trades']}")
    
    # 生成报告
    output_dir = config.get("output.output_dir", "./results")
    os.makedirs(output_dir, exist_ok=True)
    
    report_generator = ReportGenerator()
    report_path = report_generator.generate_html_report(results, metrics, output_dir)
    
    logger.info(f"回测报告已保存到: {report_path}")
    
    return results, metrics


def run_martingale_strategy_backtest(config_path: str):
    """
    运行马丁格尔策略回测
    
    Args:
        config_path: 配置文件路径
    """
    logger.info("=" * 50)
    logger.info("运行马丁格尔策略回测")
    logger.info("=" * 50)
    
    # 读取配置
    parser = ConfigParser()
    config = parser.read_config(config_path)
    
    # 获取策略配置
    strategy_config = config.get("strategy", {})
    strategy_params = strategy_config.get("params", {})
    
    # 创建策略实例
    strategy = MartingaleStrategy(strategy_params)
    
    # 加载数据
    data = load_data_from_config(config_path)
    
    # 创建回测引擎
    backtester = Backtester(
        initial_balance=config.get("basic.initial_balance", 10000),
        commission=config.get("trading.commission", 0.001),
        slippage=config.get("trading.slippage", 0.0005)
    )
    
    # 运行回测
    results = backtester.run(strategy, data)
    
    # 计算绩效指标
    metrics_calculator = MetricsCalculator()
    metrics = metrics_calculator.calculate_all(results)
    
    # 打印绩效指标
    logger.info("回测结果:")
    logger.info(f"总收益率: {metrics['total_return']:.2%}")
    logger.info(f"年化收益率: {metrics['annualized_return']:.2%}")
    logger.info(f"最大回撤: {metrics['max_drawdown']:.2%}")
    logger.info(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    logger.info(f"胜率: {metrics['win_rate']:.2%}")
    logger.info(f"交易次数: {metrics['total_trades']}")
    
    # 生成报告
    output_dir = config.get("output.output_dir", "./results")
    os.makedirs(output_dir, exist_ok=True)
    
    report_generator = ReportGenerator()
    report_path = report_generator.generate_html_report(results, metrics, output_dir)
    
    logger.info(f"回测报告已保存到: {report_path}")
    
    return results, metrics


def run_dual_ma_strategy_backtest(config_path: str):
    """
    运行双均线策略回测
    
    Args:
        config_path: 配置文件路径
    """
    logger.info("=" * 50)
    logger.info("运行双均线策略回测")
    logger.info("=" * 50)
    
    # 读取配置
    parser = ConfigParser()
    config = parser.read_config(config_path)
    
    # 创建策略配置
    strategy_config = {
        "short_window": 10,
        "long_window": 30,
        "stop_loss": 0.05,
        "take_profit": 0.1,
        "position_size": 0.5
    }
    
    # 创建策略实例
    strategy = DualMovingAverageStrategy(strategy_config)
    
    # 加载数据
    data = load_data_from_config(config_path)
    
    # 创建回测引擎
    backtester = Backtester(
        initial_balance=config.get("basic.initial_balance", 10000),
        commission=config.get("trading.commission", 0.001),
        slippage=config.get("trading.slippage", 0.0005)
    )
    
    # 运行回测
    results = backtester.run(strategy, data)
    
    # 计算绩效指标
    metrics_calculator = MetricsCalculator()
    metrics = metrics_calculator.calculate_all(results)
    
    # 打印绩效指标
    logger.info("回测结果:")
    logger.info(f"总收益率: {metrics['total_return']:.2%}")
    logger.info(f"年化收益率: {metrics['annualized_return']:.2%}")
    logger.info(f"最大回撤: {metrics['max_drawdown']:.2%}")
    logger.info(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    logger.info(f"胜率: {metrics['win_rate']:.2%}")
    logger.info(f"交易次数: {metrics['total_trades']}")
    
    # 生成报告
    output_dir = config.get("output.output_dir", "./results")
    os.makedirs(output_dir, exist_ok=True)
    
    report_generator = ReportGenerator()
    report_path = report_generator.generate_html_report(results, metrics, output_dir)
    
    logger.info(f"回测报告已保存到: {report_path}")
    
    return results, metrics


def compare_strategies(config_path: str):
    """
    比较多个策略的回测结果
    
    Args:
        config_path: 配置文件路径
    """
    logger.info("=" * 50)
    logger.info("比较策略回测结果")
    logger.info("=" * 50)
    
    # 运行各策略回测
    grid_results, grid_metrics = run_grid_strategy_backtest(config_path)
    martingale_results, martingale_metrics = run_martingale_strategy_backtest(config_path)
    dual_ma_results, dual_ma_metrics = run_dual_ma_strategy_backtest(config_path)
    
    # 创建比较表
    comparison = pd.DataFrame({
        "指标": ["总收益率", "年化收益率", "最大回撤", "夏普比率", "胜率", "交易次数"],
        "网格策略": [
            f"{grid_metrics['total_return']:.2%}",
            f"{grid_metrics['annualized_return']:.2%}",
            f"{grid_metrics['max_drawdown']:.2%}",
            f"{grid_metrics['sharpe_ratio']:.2f}",
            f"{grid_metrics['win_rate']:.2%}",
            grid_metrics['total_trades']
        ],
        "马丁格尔策略": [
            f"{martingale_metrics['total_return']:.2%}",
            f"{martingale_metrics['annualized_return']:.2%}",
            f"{martingale_metrics['max_drawdown']:.2%}",
            f"{martingale_metrics['sharpe_ratio']:.2f}",
            f"{martingale_metrics['win_rate']:.2%}",
            martingale_metrics['total_trades']
        ],
        "双均线策略": [
            f"{dual_ma_metrics['total_return']:.2%}",
            f"{dual_ma_metrics['annualized_return']:.2%}",
            f"{dual_ma_metrics['max_drawdown']:.2%}",
            f"{dual_ma_metrics['sharpe_ratio']:.2f}",
            f"{dual_ma_metrics['win_rate']:.2%}",
            dual_ma_metrics['total_trades']
        ]
    })
    
    # 打印比较表
    logger.info("策略比较结果:")
    logger.info(comparison.to_string(index=False))
    
    # 保存比较结果
    output_dir = "./results"
    os.makedirs(output_dir, exist_ok=True)
    
    comparison.to_csv(f"{output_dir}/strategy_comparison.csv", index=False)
    logger.info(f"策略比较结果已保存到: {output_dir}/strategy_comparison.csv")


def main():
    """主函数"""
    # 配置文件路径
    config_path = project_root / "configs" / "backtest_config.yaml"
    
    # 运行单个策略回测
    run_grid_strategy_backtest(config_path)
    
    # 比较多个策略
    compare_strategies(config_path)
    
    logger.info("回测示例执行完成!")


if __name__ == "__main__":
    main()