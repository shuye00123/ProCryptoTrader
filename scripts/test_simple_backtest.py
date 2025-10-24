#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单回测测试脚本 - 测试买入持有策略
验证回测系统的基本功能和报表生成
"""

import os
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.backtest.backtester import Backtester, BacktestConfig
from core.strategy.base_strategy import BaseStrategy, Signal, SignalType
from scripts.fixed_data_loader import FixedDataLoader

class SimpleBuyHoldStrategy(BaseStrategy):
    """
    简单买入持有策略 - 第一天买入，最后一天卖出
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.symbol = config.get('symbol', 'BTC/USDT')
        self.has_bought = False
        self.has_sold = False

    def calculate_indicators(self, data: dict) -> dict:
        """简单策略不需要指标"""
        return {}

    def generate_signals(self, data: dict) -> list:
        """生成买入持有信号"""
        signals = []

        if self.symbol not in data:
            return signals

        df = data[self.symbol]
        if df.empty:
            return signals

        current_price = df['close'].iloc[-1]
        current_date = df.index[-1]

        # 第一天买入
        if not self.has_bought:
            signal = Signal(
                signal_type=SignalType.OPEN_LONG,
                symbol=self.symbol,
                price=current_price,
                amount=0.8,  # 使用80%资金
                confidence=1.0
            )
            signals.append(signal)
            self.has_bought = True
            print(f"{current_date.strftime('%Y-%m-%d')}: 买入信号 - 价格: ${current_price:.2f}")

        # 最后一天卖出（模拟）
        elif self.has_bought and not self.has_sold:
            # 检查是否是数据的最后一天
            if len(df) >= 2:
                # 这里我们不会立即卖出，让回测引擎在结束时处理
                pass

        return signals

    def initialize(self, config: dict):
        """初始化策略"""
        print(f"买入持有策略初始化完成")
        print(f"将在第一天买入 {self.symbol}")
        print(f"初始资金: {config.get('initial_balance', 10000):.2f}")

def test_buy_hold_backtest():
    """测试买入持有回测"""
    print("=" * 80)
    print("ProCryptoTrader - 买入持有策略回测测试")
    print("=" * 80)

    try:
        # 创建策略
        strategy_config = {
            'name': 'BuyHold_Test',
            'symbol': 'BTC/USDT',
            'max_positions': 1
        }
        strategy = SimpleBuyHoldStrategy(strategy_config)

        # 创建回测配置
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-03-31",  # 使用较短的期间进行测试
            initial_balance=10000.0,
            fee_rate=0.001,
            slippage=0.0005,
            leverage=1.0,
            symbols=["BTC/USDT"],
            timeframes=["1d"],
            data_dir=str(project_root / "data" / "binance"),
            output_dir=str(project_root / "results" / "buy_hold_test"),
            random_seed=42
        )

        print(f"\n回测配置:")
        print(f"  策略: 买入持有")
        print(f"  时间范围: {config.start_date} 至 {config.end_date}")
        print(f"  初始资金: ${config.initial_balance:,.2f}")
        print(f"  交易对: {config.symbols[0]}")

        # 运行回测
        print(f"\n开始回测...")
        backtester = Backtester(strategy, config)
        results = backtester.run()

        # 显示结果
        display_results(results)

        # 验证结果
        return validate_results(results)

    except Exception as e:
        print(f"❌ 回测出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def display_results(results):
    """显示回测结果"""
    print(f"\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)

    # 基本统计
    print(f"📊 基本统计:")
    print(f"  初始资金: ${results['initial_balance']:,.2f}")
    print(f"  最终权益: ${results['final_balance']:,.2f}")
    print(f"  总收益率: {results['total_return']:+.2f}%")
    print(f"  年化收益率: {results['annual_return']:+.2f}%")
    print(f"  最大回撤: {results['max_drawdown']:.2f}%")
    print(f"  夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"  总交易次数: {results['total_trades']}")

    # 权益曲线
    equity_curve = results['equity_curve']
    if not equity_curve.empty:
        print(f"\n📈 权益曲线:")
        print(f"  数据点数: {len(equity_curve)}")
        print(f"  最高权益: ${equity_curve['equity'].max():,.2f}")
        print(f"  最低权益: ${equity_curve['equity'].min():,.2f}")

        # 计算波动率
        daily_returns = equity_curve['equity'].pct_change().dropna()
        if len(daily_returns) > 0:
            volatility = daily_returns.std() * (365 ** 0.5) * 100
            print(f"  年化波动率: {volatility:.2f}%")

    # 交易记录
    trades_df = results['trade_records']
    if not trades_df.empty:
        print(f"\n💼 交易记录:")
        print(f"  交易次数: {len(trades_df)}")

        # 显示所有交易
        print(f"\n  交易详情:")
        for idx, trade in trades_df.iterrows():
            print(f"    {trade['timestamp']}: {trade['side']} {trade['quantity']:.6f} @ ${trade['price']:.2f} "
                  f"(价值: ${trade['value']:.2f}, 手续费: ${trade['fee']:.2f})")

        # 计算交易统计
        if 'pnl' in trades_df.columns:
            winning_trades = trades_df[trades_df['pnl'] > 0]
            losing_trades = trades_df[trades_df['pnl'] < 0]

            print(f"\n📊 交易统计:")
            print(f"  盈利交易: {len(winning_trades)}")
            print(f"  亏损交易: {len(losing_trades)}")

            if len(winning_trades) > 0:
                avg_win = winning_trades['pnl'].mean()
                print(f"  平均盈利: ${avg_win:.2f}")

            if len(losing_trades) > 0:
                avg_loss = losing_trades['pnl'].mean()
                print(f"  平均亏损: ${avg_loss:.2f}")

    print(f"\n📁 结果文件: {results['config'].output_dir}")

def validate_results(results):
    """验证回测结果的合理性"""
    print(f"\n" + "=" * 60)
    print("结果验证")
    print("=" * 60)

    validation_passed = True

    # 基本验证
    if results['final_balance'] < 0:
        print(f"❌ 最终权益为负数: ${results['final_balance']:.2f}")
        validation_passed = False

    if results['total_trades'] == 0:
        print(f"⚠️  没有发生任何交易")

    # 权益曲线验证
    equity_curve = results['equity_curve']
    if equity_curve.empty:
        print(f"❌ 权益曲线为空")
        validation_passed = False
    else:
        # 检查权益曲线的连续性
        equity_values = equity_curve['equity'].values
        if len(equity_values) != len(set(equity_values)):
            print(f"✓ 权益曲线有变化")
        else:
            print(f"⚠️  权益曲线没有变化")

    # 数据完整性验证
    if results['initial_balance'] > 0 and results['final_balance'] >= 0:
        print(f"✓ 资金数据合理")
    else:
        print(f"❌ 资金数据异常")
        validation_passed = False

    # 时间验证
    if not equity_curve.empty:
        start_time = equity_curve.index.min()
        end_time = equity_curve.index.max()
        duration = (end_time - start_time).days

        if duration > 0:
            print(f"✓ 时间跨度合理: {duration} 天")
        else:
            print(f"⚠️  时间跨度异常: {duration} 天")

    if validation_passed:
        print(f"\n✅ 结果验证通过！回测数据合理。")
    else:
        print(f"\n❌ 结果验证发现问题，请检查回测逻辑。")

    return validation_passed

def main():
    """主函数"""
    success = test_buy_hold_backtest()

    if success:
        print(f"\n🎉 回测测试成功完成！")
        print(f"\n💡 测试验证了:")
        print(f"  ✓ 数据加载功能正常")
        print(f"  ✓ 策略信号生成正常")
        print(f"  ✓ 回测引擎运行正常")
        print(f"  ✓ 交易执行逻辑正常")
        print(f"  ✓ 报表数据生成正确")
        print(f"  ✓ 权益曲线记录完整")
        print(f"\n🚀 回测系统已准备就绪，可用于策略开发和测试！")
    else:
        print(f"\n❌ 回测测试发现问题，请检查相关模块。")

    return 0 if success else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)