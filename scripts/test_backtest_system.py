#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整回测系统测试脚本
测试使用下载的Binance数据进行回测
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
from strategies.simple_ma_strategy import SimpleMAStrategy, BacktestCompatibleStrategy
from scripts.fixed_data_loader import FixedDataLoader

class TestBacktestRunner:
    """测试回测运行器"""

    def __init__(self):
        self.data_loader = FixedDataLoader()

    def create_test_config(self) -> BacktestConfig:
        """创建测试回测配置"""
        return BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_balance=10000.0,
            fee_rate=0.001,  # 0.1% 手续费
            slippage=0.0005,  # 0.05% 滑点
            leverage=1.0,
            symbols=["BTC/USDT"],
            timeframes=["1d"],
            data_dir=str(project_root / "data" / "binance"),
            output_dir=str(project_root / "results" / "test_backtest"),
            random_seed=42
        )

    def create_strategy(self) -> BacktestCompatibleStrategy:
        """创建测试策略"""
        config = {
            'name': 'SimpleMA_Test',
            'symbol': 'BTC/USDT',
            'short_window': 10,
            'long_window': 30,
            'max_positions': 1,
            'position_size': 0.1,
            'stop_loss_pct': 0.05,
            'take_profit_pct': 0.1
        }
        return BacktestCompatibleStrategy(config)

    def test_data_loading(self):
        """测试数据加载"""
        print("=" * 60)
        print("测试数据加载")
        print("=" * 60)

        config = self.create_test_config()

        try:
            # 加载测试数据
            data = self.data_loader.load_data(
                symbol=config.symbols[0],
                timeframe=config.timeframes[0],
                start_date=config.start_date,
                end_date=config.end_date
            )

            if not data.empty:
                print(f"✓ 数据加载成功")
                print(f"  数据量: {len(data)} 条")
                print(f"  时间范围: {data.index.min()} 至 {data.index.max()}")
                print(f"  价格范围: ${data['close'].min():,.2f} - ${data['close'].max():,.2f}")
                print(f"  平均价格: ${data['close'].mean():,.2f}")

                # 显示前几行数据
                print(f"\n📊 数据示例:")
                print(data.head(3))

                return True
            else:
                print(f"❌ 数据加载失败")
                return False

        except Exception as e:
            print(f"❌ 数据加载出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_strategy_signals(self):
        """测试策略信号生成"""
        print(f"\n" + "=" * 60)
        print("测试策略信号生成")
        print("=" * 60)

        try:
            # 创建策略
            strategy = self.create_strategy()

            # 加载数据
            data = self.data_loader.load_data(
                symbol="BTC/USDT",
                timeframe="1d",
                start_date="2024-01-01",
                end_date="2024-12-31"  # 只用一个月测试
            )

            if data.empty:
                print(f"❌ 无法加载数据")
                return False

            # 初始化策略
            config = {
                'initial_balance': 10000,
                'symbols': ['BTC/USDT'],
                'timeframes': ['1d'],
                'start_date': '2024-01-01',
                'end_date': '2024-12-31'
            }
            strategy.initialize(config)

            # 测试信号生成
            signals = []
            for i in range(30, len(data)):  # 从第30天开始，确保有足够数据计算指标
                current_data = {'BTC/USDT': data.iloc[:i+1]}
                strategy_signals = strategy.generate_signals(current_data)
                if strategy_signals:
                    signals.extend(strategy_signals)
                    for signal in strategy_signals:
                        print(f"  {data.index[i]}: {signal.signal_type.value} - "
                              f"价格: ${signal.price:.2f}, 数量: {signal.amount}")

            print(f"✓ 策略信号生成测试完成")
            print(f"  生成了 {len(signals)} 个信号")
            return True

        except Exception as e:
            print(f"❌ 策略测试出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_backtest(self):
        """运行完整回测"""
        print(f"\n" + "=" * 60)
        print("运行完整回测")
        print("=" * 60)

        try:
            # 创建配置和策略
            config = self.create_test_config()
            strategy = self.create_strategy()

            # 创建回测引擎
            backtester = Backtester(strategy, config)

            print(f"回测配置:")
            print(f"  时间范围: {config.start_date} 至 {config.end_date}")
            print(f"  初始资金: ${config.initial_balance:,.2f}")
            print(f"  手续费率: {config.fee_rate*100:.2f}%")
            print(f"  滑点: {config.slippage*100:.2f}%")
            print(f"  交易对: {config.symbols}")
            print(f"  策略: {strategy.__class__.__name__}")

            # 运行回测
            print(f"\n开始回测...")
            results = backtester.run()

            # 显示结果
            self.display_backtest_results(results)

            return True

        except Exception as e:
            print(f"❌ 回测出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def display_backtest_results(self, results):
        """显示回测结果"""
        print(f"\n" + "=" * 60)
        print("回测结果")
        print("=" * 60)

        # 基本统计
        print(f"初始资金: ${results['initial_balance']:,.2f}")
        print(f"最终权益: ${results['final_balance']:,.2f}")
        print(f"总收益率: {results['total_return']:+.2f}%")
        print(f"年化收益率: {results['annual_return']:+.2f}%")
        print(f"最大回撤: {results['max_drawdown']:.2f}%")
        print(f"夏普比率: {results['sharpe_ratio']:.2f}")
        print(f"总交易次数: {results['total_trades']}")
        print(f"胜率: {results['win_rate']:.2f}%")
        print(f"盈亏比: {results['profit_loss_ratio']:.2f}")

        # 权益曲线信息
        equity_curve = results['equity_curve']
        if not equity_curve.empty:
            print(f"\n权益曲线统计:")
            print(f"  数据点数: {len(equity_curve)}")
            print(f"  最高权益: ${equity_curve['equity'].max():,.2f}")
            print(f"  最低权益: ${equity_curve['equity'].min():,.2f}")

            # 计算波动率
            daily_returns = equity_curve['equity'].pct_change().dropna()
            volatility = daily_returns.std() * (365 ** 0.5) * 100
            print(f"  年化波动率: {volatility:.2f}%")

        # 交易记录
        trades_df = results['trade_records']
        if not trades_df.empty:
            print(f"\n交易记录统计:")
            print(f"  交易次数: {len(trades_df)}")

            # 计算每笔交易的平均值
            avg_trade_value = trades_df['value'].mean()
            avg_fee = trades_df['fee'].mean()
            print(f"  平均交易价值: ${avg_trade_value:,.2f}")
            print(f"  平均手续费: ${avg_fee:.2f}")

            # 显示最近几笔交易
            print(f"\n最近5笔交易:")
            print(trades_df.tail(5)[['timestamp', 'symbol', 'side', 'price', 'quantity', 'value', 'fee']].to_string())

        print(f"\n结果文件已保存到: {results['config'].output_dir}")

    def run_all_tests(self):
        """运行所有测试"""
        print("ProCryptoTrader 回测系统测试")
        print("=" * 80)

        success_count = 0
        total_tests = 3

        # 测试数据加载
        if self.test_data_loading():
            success_count += 1

        # 测试策略信号
        if self.test_strategy_signals():
            success_count += 1

        # 运行回测
        if self.run_backtest():
            success_count += 1

        # 显示总结
        print(f"\n" + "=" * 80)
        print(f"测试总结: {success_count}/{total_tests} 通过")
        print("=" * 80)

        if success_count == total_tests:
            print("🎉 所有测试通过！回测系统运行正常。")
        else:
            print("⚠️  部分测试失败，请检查相关模块。")

        return success_count == total_tests

def main():
    """主函数"""
    try:
        runner = TestBacktestRunner()
        success = runner.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)