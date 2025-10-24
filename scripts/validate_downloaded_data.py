#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证下载的数据并提供使用示例
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data.data_manager import DataManager
from core.utils.logger import get_logger

logger = get_logger("ValidateDownloadedData")

def analyze_symbol_data(manager: DataManager, symbol: str, timeframe: str = '1d'):
    """分析单个交易对的数据"""
    print(f"\n📊 分析 {symbol} 数据:")

    # 加载数据
    data = manager.load_data(symbol, timeframe)

    if data.empty:
        print(f"   ❌ 数据为空")
        return

    # 基本统计
    print(f"   📅 数据时间范围: {data.index.min().strftime('%Y-%m-%d')} 至 {data.index.max().strftime('%Y-%m-%d')}")
    print(f"   📈 数据点数: {len(data)}")
    print(f"   💰 价格范围: {data['low'].min():.6f} - {data['high'].max():.6f}")
    print(f"   📍 最新价格: {data['close'].iloc[-1]:.6f}")
    print(f"   📊 平均成交量: {data['volume'].mean():.0f}")

    # 计算收益率
    data['returns'] = data['close'].pct_change()

    # 收益率统计
    annual_return = data['returns'].mean() * 365
    annual_volatility = data['returns'].std() * np.sqrt(365)
    sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0

    print(f"   📈 年化收益率: {annual_return:.2%}")
    print(f"   📉 年化波动率: {annual_volatility:.2%}")
    print(f"   📊 夏普比率: {sharpe_ratio:.2f}")

    # 最大回撤
    cumulative_returns = (1 + data['returns']).cumprod()
    running_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - running_max) / running_max
    max_drawdown = drawdown.min()

    print(f"   📉 最大回撤: {max_drawdown:.2%}")

    # 胜率统计
    winning_days = (data['returns'] > 0).sum()
    total_days = len(data['returns'].dropna())
    win_rate = winning_days / total_days if total_days > 0 else 0

    print(f"   🏆 胜率: {win_rate:.2%} ({winning_days}/{total_days} 天)")

    # 最近表现
    recent_30_days = data.tail(30)
    recent_return = (recent_30_days['close'].iloc[-1] / recent_30_days['close'].iloc[0] - 1) * 100

    print(f"   📈 最近30天: {recent_return:+.2f}%")

    return data

def compare_symbols(manager: DataManager, symbols: list):
    """比较多个交易对的表现"""
    print(f"\n🔍 交易对表现对比:")

    results = []

    for symbol in symbols:
        data = manager.load_data(symbol, '1d')
        if not data.empty:
            data['returns'] = data['close'].pct_change()
            annual_return = data['returns'].mean() * 365
            annual_volatility = data['returns'].std() * np.sqrt(365)
            # 计算最大回撤
            cumulative_returns = (1 + data['returns']).cumprod()
            running_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - running_max) / running_max
            max_drawdown = drawdown.min()

            results.append({
                'Symbol': symbol,
                'Annual Return': f"{annual_return:.2%}",
                'Annual Volatility': f"{annual_volatility:.2%}",
                'Max Drawdown': f"{max_drawdown:.2%}",
                'Latest Price': f"{data['close'].iloc[-1]:.6f}"
            })

    if results:
        df = pd.DataFrame(results)
        print(df.to_string(index=False))

def create_portfolio_analysis(manager: DataManager, symbols: list, weights: list = None):
    """创建投资组合分析"""
    print(f"\n💼 投资组合分析:")

    if weights is None:
        weights = [1.0 / len(symbols)] * len(symbols)  # 等权重

    if len(symbols) != len(weights):
        print("❌ 交易对数量与权重数量不匹配")
        return

    # 加载所有数据
    portfolio_data = {}
    for symbol in symbols:
        data = manager.load_data(symbol, '1d')
        if not data.empty:
            portfolio_data[symbol] = data

    if not portfolio_data:
        print("❌ 没有可用的数据")
        return

    # 使用最短的数据范围
    min_length = min(len(data) for data in portfolio_data.values())
    start_date = max(data.index[0] for data in portfolio_data.values())
    end_date = min(data.index[-1] for data in portfolio_data.values())

    print(f"   📅 组合时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")

    # 计算组合收益率
    portfolio_returns = pd.Series(0, index=portfolio_data[symbols[0]].index[:min_length])

    for i, symbol in enumerate(symbols):
        if symbol in portfolio_data:
            data = portfolio_data[symbol]
            # 计算收益率
            data['returns'] = data['close'].pct_change()
            returns = data['returns'].iloc[:min_length]
            portfolio_returns += returns * weights[i]

    # 组合统计
    portfolio_value = (1 + portfolio_returns).cumprod()
    annual_return = portfolio_returns.mean() * 365
    annual_volatility = portfolio_returns.std() * np.sqrt(365)
    sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0

    max_drawdown = ((portfolio_value.expanding().max() - portfolio_value) / portfolio_value.expanding().max()).max()

    print(f"   📈 年化收益率: {annual_return:.2%}")
    print(f"   📉 年化波动率: {annual_volatility:.2%}")
    print(f"   📊 夏普比率: {sharpe_ratio:.2f}")
    print(f"   📉 最大回撤: {max_drawdown:.2%}")

    # 显示权重分配
    print(f"\n   ⚖️  权重分配:")
    for symbol, weight in zip(symbols, weights):
        print(f"      {symbol}: {weight:.1%}")

def main():
    """主函数"""
    print("=" * 80)
    print("🔍 下载的数据验证和使用示例")
    print("=" * 80)

    # 数据目录
    data_dir = project_root / "data" / "binance_demo"

    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        print("💡 请先运行下载脚本: python3 scripts/download_demo_binance_data.py")
        return 1

    # 初始化数据管理器
    try:
        manager = DataManager(str(data_dir), 'binance')
        print("✓ DataManager 初始化成功")

        # 获取可用数据
        available_data = manager.list_available_data()
        print(f"✓ 发现 {len(available_data)} 个交易对的数据")

        if not available_data:
            print("❌ 没有找到可用数据")
            return 1

        # 分析主要交易对
        major_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT']
        available_major = [s for s in major_symbols if s in available_data]

        print(f"\n🏆 主要交易对分析:")
        for symbol in available_major:
            analyze_symbol_data(manager, symbol)

        # 表现对比
        top_symbols = list(available_data.keys())[:10]
        compare_symbols(manager, top_symbols)

        # 投资组合分析
        portfolio_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        available_portfolio = [s for s in portfolio_symbols if s in available_data]

        if len(available_portfolio) >= 2:
            # 等权重组合
            create_portfolio_analysis(manager, available_portfolio)

            # 不同权重组合（比特币60%，其他等分）
            if len(available_portfolio) == 3:
                alt_weights = [0.6, 0.2, 0.2][:len(available_portfolio)]
                print(f"\n💼 偏重投资组合分析 (BTC 60%):")
                create_portfolio_analysis(manager, available_portfolio, alt_weights)

        # 数据质量检查
        print(f"\n🔍 数据质量检查:")

        quality_issues = 0
        total_symbols = len(available_data)

        for symbol in list(available_data.keys())[:5]:  # 检查前5个
            data = manager.load_data(symbol, '1d')
            if not data.empty:
                # 检查数据连续性
                expected_days = (data.index.max() - data.index.min()).days + 1
                actual_days = len(data)
                completeness = actual_days / expected_days

                if completeness < 0.95:
                    print(f"   ⚠️  {symbol}: 数据完整性 {completeness:.1%} (预期{expected_days}天，实际{actual_days}天)")
                    quality_issues += 1

                # 检查异常值
                returns = data['close'].pct_change()
                extreme_changes = (abs(returns) > 0.3).sum()  # 超过30%的变化
                if extreme_changes > 0:
                    print(f"   ⚠️  {symbol}: 有 {extreme_changes} 个极端价格变化日")
                    quality_issues += 1

        if quality_issues == 0:
            print("   ✅ 所有检查的数据质量良好")
        else:
            print(f"   ⚠️  发现 {quality_issues} 个数据质量问题")

        # 使用建议
        print(f"\n💡 数据使用建议:")
        print(f"   1. 策略回测: 使用这些数据进行策略开发和回测")
        print(f"   2. 风险分析: 基于历史数据进行风险分析")
        print(f"   3. 投资组合: 构建多资产投资组合")
        print(f"   4. 机器学习: 作为ML模型的训练数据")

        print(f"\n📁 数据文件位置: {data_dir}")
        print(f"   格式: Apache Parquet (高效列式存储)")
        print(f"   结构: data/binance_demo/binance/SYMBOL/1d.parquet")

        return 0

    except Exception as e:
        logger.error(f"验证过程中发生错误: {e}")
        print(f"❌ 验证失败: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)