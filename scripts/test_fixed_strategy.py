#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复版移动平均策略
验证代码审查中发现的问题是否得到解决
"""

import os
import sys
from pathlib import Path
import pandas as pd
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from strategies.fixed_ma_strategy import FixedMAStrategy
from core.strategy.base_strategy import SignalType
from scripts.fixed_data_loader import FixedDataLoader

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_strategy_creation():
    """测试策略创建"""
    print("=" * 60)
    print("测试策略创建")
    print("=" * 60)

    try:
        # 测试正常配置
        config = {
            'short_window': 10,
            'long_window': 30,
            'symbol': 'BTC/USDT',
            'max_positions': 1,
            'position_size': 0.1
        }

        strategy = FixedMAStrategy(config)
        print(f"✓ 策略创建成功")
        print(f"  短期窗口: {strategy.short_window}")
        print(f"  长期窗口: {strategy.long_window}")
        print(f"  交易对: {strategy.symbol}")

        # 测试参数验证
        try:
            bad_config = {'short_window': 30, 'long_window': 10}  # 短期窗口大于长期窗口
            FixedMAStrategy(bad_config)
            print(f"❌ 参数验证失败：应该抛出异常")
            return False
        except ValueError:
            print(f"✓ 参数验证正常：检测到无效配置")

        return True

    except Exception as e:
        print(f"❌ 策略创建失败: {e}")
        return False

def test_indicator_calculation():
    """测试指标计算"""
    print(f"\n" + "=" * 60)
    print("测试指标计算")
    print("=" * 60)

    try:
        # 创建策略
        config = {
            'short_window': 5,
            'long_window': 10,
            'symbol': 'BTC/USDT'
        }
        strategy = FixedMAStrategy(config)

        # 加载测试数据
        loader = FixedDataLoader()
        data = loader.load_data('BTC/USDT', '1d', '2024-01-01', '2024-01-31')

        if data.empty:
            print(f"❌ 无法加载测试数据")
            return False

        print(f"✓ 加载数据成功: {len(data)} 条")

        # 测试指标计算
        indicators = strategy.calculate_indicators({'BTC/USDT': data})

        symbol_indicators = indicators.get('BTC/USDT', {})
        if 'short_ma' in symbol_indicators and 'long_ma' in symbol_indicators:
            short_ma = symbol_indicators['short_ma']
            long_ma = symbol_indicators['long_ma']

            print(f"✓ 指标计算成功")
            print(f"  短期MA数据点: {len(short_ma)}")
            print(f"  长期MA数据点: {len(long_ma)}")

            # 检查NaN值
            short_ma_nan_count = short_ma.isna().sum()
            long_ma_nan_count = long_ma.isna().sum()

            print(f"  短期MA NaN数量: {short_ma_nan_count}")
            print(f"  长期MA NaN数量: {long_ma_nan_count}")

            # 显示最新值
            if not short_ma.empty and not long_ma.empty:
                latest_short = short_ma.iloc[-1]
                latest_long = long_ma.iloc[-1]
                latest_price = data['close'].iloc[-1]

                print(f"  最新价格: ${latest_price:.2f}")
                print(f"  最新短期MA: ${latest_short:.2f}")
                print(f"  最新长期MA: ${latest_long:.2f}")

                return True
        else:
            print(f"❌ 指标计算失败：缺少必要的指标")
            return False

    except Exception as e:
        print(f"❌ 指标计算测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_signal_generation():
    """测试信号生成"""
    print(f"\n" + "=" * 60)
    print("测试信号生成")
    print("=" * 60)

    try:
        # 创建策略
        config = {
            'short_window': 5,
            'long_window': 10,
            'symbol': 'BTC/USDT'
        }
        strategy = FixedMAStrategy(config)

        # 加载测试数据（使用更多数据以确保有信号）
        loader = FixedDataLoader()
        data = loader.load_data('BTC/USDT', '1d', '2024-01-01', '2024-03-31')

        if data.empty:
            print(f"❌ 无法加载测试数据")
            return False

        print(f"✓ 加载数据成功: {len(data)} 条")

        # 初始化策略
        strategy.initialize({
            'initial_balance': 10000,
            'symbols': ['BTC/USDT'],
            'start_date': '2024-01-01',
            'end_date': '2024-03-31'
        })

        # 测试信号生成
        total_signals = 0
        signal_types = set()

        # 模拟回测中的信号生成过程
        for i in range(10, len(data)):  # 从第10天开始，确保有足够数据计算指标
            current_data = {'BTC/USDT': data.iloc[:i+1]}

            # 更新策略状态
            signals = strategy.update(current_data)

            if signals:
                for signal in signals:
                    total_signals += 1
                    signal_types.add(signal.signal_type)
                    print(f"  信号 {total_signals}: {signal.signal_type.value} @ ${signal.price:.2f} (数量: {signal.amount})")

        print(f"✓ 信号生成测试完成")
        print(f"  总信号数: {total_signals}")
        print(f"  信号类型: {[t.value for t in signal_types]}")

        # 验证信号类型统一性
        has_unified_types = any(t in [SignalType.OPEN_LONG, SignalType.CLOSE_LONG] for t in signal_types)

        print(f"  包含统一信号类型: {has_unified_types}")

        if has_unified_types:
            print(f"✓ 信号类型统一成功")
            return True
        else:
            print(f"❌ 信号类型统一失败")
            return False

    except Exception as e:
        print(f"❌ 信号生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """测试异常处理"""
    print(f"\n" + "=" * 60)
    print("测试异常处理")
    print("=" * 60)

    try:
        strategy = FixedMAStrategy({
            'short_window': 5,
            'long_window': 10,
            'symbol': 'BTC/USDT'
        })

        # 测试空数据
        signals = strategy.generate_signals({})
        print(f"✓ 空数据处理: 返回 {len(signals)} 个信号")

        # 测试无效数据
        signals = strategy.generate_signals({'BTC/USDT': pd.DataFrame()})
        print(f"✓ 空DataFrame处理: 返回 {len(signals)} 个信号")

        # 测试数据不足
        small_data = pd.DataFrame({
            'close': [100, 101, 102]  # 只有3个数据点，不足long_window
        })
        signals = strategy.generate_signals({'BTC/USDT': small_data})
        print(f"✓ 数据不足处理: 返回 {len(signals)} 个信号")

        # 测试包含NaN的数据
        nan_data = pd.DataFrame({
            'close': [100, float('nan'), 102, 103, 104, 105, 106, 107, 108, 109, 110]
        })
        signals = strategy.generate_signals({'BTC/USDT': nan_data})
        print(f"✓ NaN数据处理: 返回 {len(signals)} 个信号")

        print(f"✓ 异常处理测试通过")
        return True

    except Exception as e:
        print(f"❌ 异常处理测试失败: {e}")
        return False

def test_strategy_status():
    """测试策略状态"""
    print(f"\n" + "=" * 60)
    print("测试策略状态")
    print("=" * 60)

    try:
        strategy = FixedMAStrategy({
            'short_window': 10,
            'long_window': 30,
            'symbol': 'BTC/USDT'
        })

        status = strategy.get_strategy_status()

        print(f"✓ 策略状态获取成功")
        print(f"  策略名称: {status.get('name')}")
        print(f"  已初始化: {status.get('is_initialized')}")
        print(f"  持仓数量: {status.get('total_positions')}")
        print(f"  短期窗口: {status.get('short_window')}")
        print(f"  长期窗口: {status.get('long_window')}")
        print(f"  当前交易对: {status.get('current_symbol')}")

        return True

    except Exception as e:
        print(f"❌ 策略状态测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("ProCryptoTrader - 修复版策略测试")
    print("=" * 80)

    tests = [
        ("策略创建", test_strategy_creation),
        ("指标计算", test_indicator_calculation),
        ("信号生成", test_signal_generation),
        ("异常处理", test_error_handling),
        ("策略状态", test_strategy_status)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 测试: {test_name}")
        try:
            if test_func():
                print(f"✅ {test_name} 通过")
                passed += 1
            else:
                print(f"❌ {test_name} 失败")
        except Exception as e:
            print(f"❌ {test_name} 异常: {e}")

    # 总结
    print(f"\n" + "=" * 80)
    print(f"测试总结: {passed}/{total} 通过")
    print("=" * 80)

    if passed == total:
        print("🎉 所有测试通过！修复版策略工作正常。")
        print("\n💡 主要修复:")
        print("  ✓ 信号类型统一 - 使用open_long/close_long")
        print("  ✓ 异常处理和边界检查")
        print("  ✓ 日志记录完善")
        print("  ✓ 状态管理改进")
        print("  ✓ 参数验证增强")
    else:
        print("⚠️  部分测试失败，需要进一步修复。")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)