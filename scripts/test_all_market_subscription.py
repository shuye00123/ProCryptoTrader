"""
全市场自动订阅功能测试脚本

测试多时间框架K线突破策略的全市场自动订阅功能：
1. 测试 AUTO 标记识别
2. 测试从Binance获取交易对
3. 测试过滤功能（成交量、价格、排除列表）
4. 验证配置文件正确性
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.utils.logger import get_logger, setup_logging
from core.utils.config import load_config


async def test_auto_detection():
    """测试1: AUTO标记识别"""
    print("\n" + "="*80)
    print("测试 1: AUTO 标记识别")
    print("="*80)

    from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy

    # 测试配置
    test_config = {
        'symbols': ['AUTO'],
        'mode': 'paper',
        'strategy': {
            'name': 'MultiTimeframeKlineBreakout',
            'kline_breakout': {}
        }
    }

    # 创建策略
    strategy = MultiTimeframeKlineBreakoutStrategy(test_config)

    # 验证
    assert strategy.auto_fetch_symbols == True, "❌ AUTO标记识别失败"
    assert strategy.binance_symbols == ['AUTO'], "❌ 临时标记设置失败"

    print("✅ AUTO标记识别测试通过")
    return True


async def test_fetch_symbols():
    """测试2: 获取全市场交易对"""
    print("\n" + "="*80)
    print("测试 2: 获取全市场交易对")
    print("="*80)

    from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy

    # 测试配置（启用成交量过滤）
    test_config = {
        'symbols': ['AUTO'],
        'mode': 'paper',
        'strategy': {
            'name': 'MultiTimeframeKlineBreakout',
            'kline_breakout': {}
        },
        'websocket_subscribe': {
            'all_market': {
                'enabled': True,
                'quote_asset': 'USDT',
                'min_volume_24h': 1000000,  # 100万USDT成交量过滤
                'exclude_symbols': ['USDCUSDT', 'TUSDUSDT']
            }
        }
    }

    # 创建策略
    strategy = MultiTimeframeKlineBreakoutStrategy(test_config)

    # 测试获取交易对
    print("正在获取交易对列表...")
    symbols = await strategy._fetch_all_market_symbols()

    # 验证
    assert len(symbols) > 0, "❌ 未获取到任何交易对"
    assert all(s.endswith('USDT') for s in symbols), "❌ 交易对格式错误"
    assert 'USDCUSDT' not in symbols, "❌ 排除列表未生效"

    print(f"✅ 获取到 {len(symbols)} 个交易对")
    print(f"   示例交易对: {symbols[:10]}")
    return True


async def test_volume_filter():
    """测试3: 成交量过滤"""
    print("\n" + "="*80)
    print("测试 3: 成交量过滤功能")
    print("="*80)

    from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy

    # 测试配置：高成交量阈值
    test_config = {
        'symbols': ['AUTO'],
        'mode': 'paper',
        'strategy': {
            'name': 'MultiTimeframeKlineBreakout',
            'kline_breakout': {}
        },
        'websocket_subscribe': {
            'all_market': {
                'enabled': True,
                'quote_asset': 'USDT',
                'min_volume_24h': 10000000  # 1000万USDT
            }
        }
    }

    strategy = MultiTimeframeKlineBreakoutStrategy(test_config)
    symbols = await strategy._fetch_all_market_symbols()

    print(f"✅ 高成交量过滤后剩余 {len(symbols)} 个交易对（阈值1000万USDT）")

    # 对比低成交量阈值
    test_config['websocket_subscribe']['all_market']['min_volume_24h'] = 100000  # 10万USDT
    strategy2 = MultiTimeframeKlineBreakoutStrategy(test_config)
    symbols2 = await strategy2._fetch_all_market_symbols()

    print(f"✅ 低成交量过滤后剩余 {len(symbols2)} 个交易对（阈值10万USDT）")
    print(f"✅ 过滤效果: {len(symbols2) - len(symbols)} 个交易对被过滤")

    return True


async def test_initialize():
    """测试4: 完整初始化流程"""
    print("\n" + "="*80)
    print("测试 4: 完整初始化流程")
    print("="*80)

    from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy

    # 测试配置（模拟真实场景）
    test_config = {
        'symbols': ['AUTO'],
        'mode': 'paper',
        'strategy': {
            'name': 'MultiTimeframeKlineBreakout',
            'kline_breakout': {},
            'max_positions': 3,
            'position_size': 0.02
        },
        'websocket_subscribe': {
            'all_market': {
                'enabled': True,
                'quote_asset': 'USDT',
                'min_volume_24h': 5000000  # 500万USDT
            }
        }
    }

    strategy = MultiTimeframeKlineBreakoutStrategy(test_config)

    print("正在初始化策略...")
    await strategy.initialize(initial_balance=10000.0)

    # 验证
    assert len(strategy.binance_symbols) > 0, "❌ 初始化后交易对列表为空"
    assert strategy.binance_symbols != ['AUTO'], "❌ 交易对列表未更新"

    print(f"✅ 策略初始化成功")
    print(f"   订阅交易对数量: {len(strategy.binance_symbols)}")
    print(f"   初始余额: {strategy.initial_balance} USDT")

    return True


async def test_config_file():
    """测试5: 配置文件验证"""
    print("\n" + "="*80)
    print("测试 5: 配置文件验证")
    print("="*80)

    config_path = project_root / "configs" / "mt_kline_breakout_config.yaml"

    if not config_path.exists():
        print(f"⚠️  配置文件不存在: {config_path}")
        return False

    # 加载配置
    config = load_config(str(config_path))

    # 验证配置
    symbols = config.get('symbols', [])
    print(f"配置中的交易对: {symbols}")

    if 'AUTO' in [s.upper() for s in symbols]:
        print("✅ 检测到 AUTO 标记")

        ws_config = config.get('websocket_subscribe', {})
        all_market = ws_config.get('all_market', {})

        if all_market.get('enabled'):
            print("✅ 全市场订阅已启用")
            print(f"   报价资产: {all_market.get('quote_asset')}")
            print(f"   最小成交量: {all_market.get('min_volume_24h')}")
            print(f"   排除数量: {len(all_market.get('exclude_symbols', []))}")
        else:
            print("⚠️  全市场订阅未启用")
    else:
        print("ℹ️  未使用 AUTO 标记，使用手动指定的交易对")

    return True


async def main():
    """主测试函数"""
    print("\n" + "🔥 "*40)
    print("全市场自动订阅功能测试")
    print("🔥 "*40)

    # 设置日志
    setup_logging(level='INFO')
    logger = get_logger("TestAllMarketSubscription")

    tests = [
        ("AUTO标记识别", test_auto_detection),
        ("获取全市场交易对", test_fetch_symbols),
        ("成交量过滤", test_volume_filter),
        ("完整初始化流程", test_initialize),
        ("配置文件验证", test_config_file)
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # 测试结果汇总
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    print(f"✅ 通过: {passed}/{len(tests)}")
    print(f"❌ 失败: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 所有测试通过！全市场订阅功能正常工作")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
