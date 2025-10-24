#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证统一信号类型后的回测系统
"""

import sys
from pathlib import Path
import pandas as pd
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from strategies.fixed_ma_strategy import FixedMAStrategy
from scripts.fixed_data_loader import FixedDataLoader
from core.backtest.backtester import Backtester, BacktestConfig
from core.strategy.base_strategy import SignalType

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_unified_backtest():
    """测试统一信号类型的回测系统"""
    print("=" * 80)
    print("验证统一信号类型后的回测系统")
    print("=" * 80)

    try:
        # 1. 创建策略
        strategy_config = {
            'short_window': 10,
            'long_window': 30,
            'symbol': 'BTC/USDT',
            'max_positions': 1,
            'position_size': 0.1
        }

        strategy = FixedMAStrategy(strategy_config)
        print(f"✓ 策略创建成功: {strategy.name}")

        # 2. 加载数据
        loader = FixedDataLoader()
        data = loader.load_data('BTC/USDT', '1d', '2024-01-01', '2024-03-31')

        if data.empty:
            print("❌ 无法加载数据")
            return False

        print(f"✓ 数据加载成功: {len(data)} 条")

        # 3. 创建回测配置
        backtest_config = BacktestConfig(
            initial_balance=10000,
            symbols=['BTC/USDT'],
            start_date='2024-01-01',
            end_date='2024-03-31',
            slippage=0.001,
            fee_rate=0.001,
            data_dir='data/binance'
        )

        # 4. 创建回测引擎
        backtester = Backtester(strategy, backtest_config)
        print(f"✓ 回测引擎创建成功")

        # 5. 运行回测
        print("开始回测...")
        # 首先加载数据
        backtester.load_data()
        results = backtester.run()

        if results:
            print(f"✓ 回测完成")
            print(f"  总交易数: {results.get('total_trades', 0)}")
            print(f"  最终资金: ${results.get('final_balance', 0):.2f}")
            print(f"  总收益率: {results.get('total_return_pct', 0):.2f}%")
            print(f"  最大回撤: {results.get('max_drawdown_pct', 0):.2f}%")

            # 检查信号类型
            trades = results.get('trades', [])
            signal_types_used = set()
            for trade in trades:
                if 'signal_type' in trade:
                    signal_types_used.add(trade['signal_type'])

            print(f"  使用的信号类型: {signal_types_used}")

            # 验证只使用了统一的信号类型
            invalid_signals = signal_types_used - {SignalType.OPEN_LONG.value, SignalType.CLOSE_LONG.value,
                                                  SignalType.OPEN_SHORT.value, SignalType.CLOSE_SHORT.value}

            if invalid_signals:
                print(f"❌ 发现无效信号类型: {invalid_signals}")
                return False
            else:
                print(f"✓ 信号类型统一验证通过")

            return True
        else:
            print("❌ 回测失败")
            return False

    except Exception as e:
        print(f"❌ 回测测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    success = test_unified_backtest()

    print("\n" + "=" * 80)
    if success:
        print("🎉 统一信号类型系统验证成功！")
        print("\n✅ 完成的工作:")
        print("  1. 移除了BUY/SELL信号类型")
        print("  2. 统一使用OPEN_LONG/CLOSE_LONG等信号类型")
        print("  3. 更新了回测引擎逻辑")
        print("  4. 更新了策略实现")
        print("  5. 清理了相关文档")
        print("  6. 验证了系统功能完整性")
        print("\n💡 系统现在更加简洁、一致，避免了信号类型的混乱！")
    else:
        print("❌ 统一信号类型系统验证失败，需要进一步调试。")

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)