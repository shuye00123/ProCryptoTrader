"""
多时间框架K线突破策略测试脚本

测试内容：
1. KlineBreakoutDetector初始化和基本功能
2. MultiTimeframeConfirmator初始化和指标计算
3. MultiTimeframeKlineBreakoutStrategy初始化
4. 简单信号生成测试
"""

import sys
import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.strategy.kline_breakout_detector import KlineBreakoutDetector, Kline
from core.strategy.multi_timeframe_confirmator import MultiTimeframeConfirmator
from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy
from core.strategy.base_strategy import Signal, SignalType

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_klines(symbol: str, count: int = 300, trend: str = 'uptrend', include_breakout: bool = False) -> pd.DataFrame:
    """
    创建测试用K线数据

    Args:
        symbol: 交易对符号
        count: K线数量
        trend: 趋势方向 ('uptrend', 'downtrend', 'sideways')
        include_breakout: 是否包含量价突破（用于测试）

    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(42)

    # 生成时间序列（1秒间隔）
    timestamps = pd.date_range(
        start=datetime.now() - timedelta(seconds=count),
        periods=count,
        freq='1s'
    )

    # 生成价格数据
    base_price = 50000.0

    if trend == 'uptrend':
        # 上升趋势：随机游走 + 上升趋势
        price_changes = np.random.randn(count) * 10 + 2  # 平均每秒+2美元
    elif trend == 'downtrend':
        # 下降趋势
        price_changes = np.random.randn(count) * 10 - 2
    else:  # sideways
        # 横盘震荡
        price_changes = np.random.randn(count) * 10

    prices = base_price + np.cumsum(price_changes)

    # 创建K线数据
    data = pd.DataFrame({
        'timestamp': timestamps,
        'open': prices,
        'high': prices + np.random.rand(count) * 20,
        'low': prices - np.random.rand(count) * 20,
        'close': prices + np.random.randn(count) * 5,
        'volume': np.random.randint(100, 1000, count)
    })

    # 如果需要包含突破
    if include_breakout and count >= 100:
        # 在最后10根K线制造突破
        breakout_start = count - 10

        # 1. 价格突破布林带上轨
        # 计算前90根K线的布林带
        prices_before = prices[:breakout_start]
        bb_middle = np.mean(prices_before[-20:])
        bb_std = np.std(prices_before[-20:])
        bb_upper = bb_middle + 2 * bb_std

        # 让最后10根K线突破布林带上轨
        for i in range(breakout_start, count):
            breakout_price = bb_upper * 1.005  # 突破到布林带上轨外0.5%
            data.loc[i, 'open'] = breakout_price
            data.loc[i, 'close'] = breakout_price + np.random.randn() * 2
            data.loc[i, 'high'] = breakout_price + np.random.rand() * 10
            data.loc[i, 'low'] = breakout_price - np.random.rand() * 10

        # 2. 成交量激增（3倍平均）
        avg_volume = data.loc[:breakout_start, 'volume'].mean()
        data.loc[breakout_start:, 'volume'] = int(avg_volume * 3.5)  # 3.5倍成交量

    # 确保high >= close >= low
    data['high'] = data[['open', 'close', 'high']].max(axis=1)
    data['low'] = data[['open', 'close', 'low']].min(axis=1)

    data.set_index('timestamp', inplace=True)

    return data


def create_higher_timeframe_test_data(symbol: str, count: int = 200) -> Dict[str, pd.DataFrame]:
    """
    创建更高时间框架的测试数据（15m/1h）

    Args:
        symbol: 交易对符号
        count: K线数量

    Returns:
        {'15m': DataFrame, '1h': DataFrame}
    """
    np.random.seed(42)

    result = {}

    # 15分钟数据（模拟200条）
    timestamps_15m = pd.date_range(
        start=datetime.now() - timedelta(minutes=count),
        periods=count,
        freq='15T'
    )

    base_price = 50000.0
    price_changes = np.random.randn(count) * 50 + 10  # 更大的波动
    prices_15m = base_price + np.cumsum(price_changes)

    data_15m = pd.DataFrame({
        'timestamp': timestamps_15m,
        'open': prices_15m,
        'high': prices_15m + np.random.rand(count) * 100,
        'low': prices_15m - np.random.rand(count) * 100,
        'close': prices_15m + np.random.randn(count) * 20,
        'volume': np.random.randint(10000, 100000, count)
    })

    data_15m['high'] = data_15m[['open', 'close', 'high']].max(axis=1)
    data_15m['low'] = data_15m[['open', 'close', 'low']].min(axis=1)
    data_15m.set_index('timestamp', inplace=True)

    result['15m'] = data_15m

    # 1小时数据（模拟200条）
    timestamps_1h = pd.date_range(
        start=datetime.now() - timedelta(hours=count),
        periods=count,
        freq='1H'
    )

    price_changes_1h = np.random.randn(count) * 100 + 20  # 更大的波动
    prices_1h = base_price + np.cumsum(price_changes_1h)

    data_1h = pd.DataFrame({
        'timestamp': timestamps_1h,
        'open': prices_1h,
        'high': prices_1h + np.random.rand(count) * 200,
        'low': prices_1h - np.random.rand(count) * 200,
        'close': prices_1h + np.random.randn(count) * 50,
        'volume': np.random.randint(50000, 500000, count)
    })

    data_1h['high'] = data_1h[['open', 'close', 'high']].max(axis=1)
    data_1h['low'] = data_1h[['open', 'close', 'low']].min(axis=1)
    data_1h.set_index('timestamp', inplace=True)

    result['1h'] = data_1h

    return result


def test_kline_breakout_detector():
    """测试1秒K线量价突破检测器"""
    logger.info("=" * 80)
    logger.info("测试1: KlineBreakoutDetector（量价突破版本）")
    logger.info("=" * 80)

    # 配置
    config = {
        'volume_surge_threshold': 3.0,  # 3倍成交量
        'volume_window': 50,
        'bb_breakout_threshold': 0.002,
        'bb_period': 20,
        'min_signal_strength': 0.7
    }

    # 创建检测器
    detector = KlineBreakoutDetector(config)
    logger.info(f"✅ 量价突破检测器初始化成功")

    # 创建测试数据（包含量价突破）
    symbol = "BTCUSDT"
    klines_1s = create_test_klines(symbol, count=100, trend='uptrend', include_breakout=True)

    # 创建更高时间框架数据
    higher_tf_data = create_higher_timeframe_test_data(symbol, count=100)

    logger.info(f"生成了{len(klines_1s)}条1秒K线数据（包含量价突破）")
    logger.info(f"生成了更高时间框架数据: {list(higher_tf_data.keys())}")

    # 逐个K线测试检测
    signals_detected = 0

    for idx, row in klines_1s.iterrows():
        kline = Kline(
            symbol=symbol,
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume']),
            timestamp=idx
        )

        # 检测量价突破（传递更高时间框架数据）
        signal = detector.detect_breakout(
            kline,
            symbol,
            higher_tf_data  # 传递15m/1h数据用于布林带和支撑阻力检测
        )

        if signal:
            signals_detected += 1
            logger.info(f"  📊 检测到量价突破 #{signals_detected}: "
                       f"类型={signal.signal_type.value}, "
                       f"价格={kline.close:.2f}, "
                       f"置信度={signal.confidence:.2f}, "
                       f"原因={signal.metadata.get('reason', 'N/A')}")

            # 显示详细元数据
            if 'volume_analysis' in signal.metadata:
                vol_analysis = signal.metadata['volume_analysis']
                logger.info(f"     成交量分析: 比率={vol_analysis['volume_ratio']:.2f}x, "
                           f"当前={vol_analysis['current_volume']:.0f}, "
                           f"平均={vol_analysis['avg_volume']:.0f}")

            if 'price_breakout' in signal.metadata:
                price_breakout = signal.metadata['price_breakout']
                logger.info(f"     价格突破: BB={price_breakout['bb_breakout']}, "
                           f"SR={price_breakout['sr_breakout']}")

    logger.info(f"✅ 测试完成，共检测到{signals_detected}个量价突破信号")
    logger.info(f"检测器状态: {detector.get_detector_status(symbol)}")

    return signals_detected > 0


def test_multi_timeframe_confirmator():
    """测试多时间框架确认器"""
    logger.info("=" * 80)
    logger.info("测试2: MultiTimeframeConfirmator")
    logger.info("=" * 80)

    # 配置
    config = {
        'min_timeframes': 2,
        'min_indicators': 2
    }

    # 创建确认器
    confirmator = MultiTimeframeConfirmator(config=config)
    logger.info(f"✅ 确认器初始化成功")
    logger.info(f"确认规则: {confirmator.get_confirmator_status()}")

    # 创建多时间框架测试数据
    symbol = "BTCUSDT"

    multi_timeframe_data = {
        '15m': create_test_klines(symbol, count=200, trend='uptrend'),
        '1h': create_test_klines(symbol, count=200, trend='uptrend'),
        '1d': create_test_klines(symbol, count=200, trend='uptrend')
    }

    logger.info(f"生成了{len(multi_timeframe_data)}个时间框架的测试数据")

    # 创建初步信号
    preliminary = Signal(
        signal_type=SignalType.OPEN_LONG,
        symbol=symbol,
        price=50000.0,
        amount=0.1,
        confidence=0.7
    )

    # 运行确认（异步）
    async def run_confirmation():
        confirmed = await confirmator.confirm_breakout(
            preliminary, symbol, multi_timeframe_data
        )

        if confirmed:
            logger.info(f"✅ 信号确认通过")
            logger.info(f"  最终置信度: {confirmed.confidence:.2f}")
            logger.info(f"  确认详情: {confirmed.metadata}")
        else:
            logger.info(f"❌ 信号未通过确认")

        return confirmed

    # 运行异步测试
    confirmed = asyncio.run(run_confirmation())

    return confirmed is not None


def test_strategy_initialization():
    """测试策略初始化"""
    logger.info("=" * 80)
    logger.info("测试3: MultiTimeframeKlineBreakoutStrategy初始化")
    logger.info("=" * 80)

    # 加载配置
    import yaml
    config_path = Path(__file__).parent.parent / 'configs' / 'mt_kline_breakout_config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    logger.info(f"✅ 配置文件加载成功: {config_path}")

    # 创建策略
    strategy = MultiTimeframeKlineBreakoutStrategy(config)
    logger.info(f"✅ 策略初始化成功: {strategy.name}")

    # 获取策略状态
    status = strategy.get_strategy_status()
    logger.info(f"策略状态:")
    logger.info(f"  交易对: {status['symbols']}")
    logger.info(f"  模式: {'回测' if status['is_backtest'] else '实盘'}")
    logger.info(f"  WebSocket: {'运行中' if status['websocket_running'] else '未运行'}")

    return True


def test_strategy_signal_generation():
    """测试策略信号生成（量价突破版本）"""
    logger.info("=" * 80)
    logger.info("测试4: 策略信号生成（量价突破版本）")
    logger.info("=" * 80)

    # 配置
    config = {
        'mode': 'backtest',
        'name': 'MultiTimeframeKlineBreakout',
        'symbols': ['BTC-USDT'],
        'strategy': {
            'name': 'MultiTimeframeKlineBreakout',
            'kline_breakout': {
                'volume_surge_threshold': 3.0,
                'volume_window': 50,
                'bb_breakout_threshold': 0.002,
                'min_signal_strength': 0.7
            },
            'multi_timeframe': {
                'enabled': True,
                'min_timeframes': 1,
                'min_indicators': 1
            }
        }
    }

    # 创建策略
    strategy = MultiTimeframeKlineBreakoutStrategy(config)
    logger.info(f"✅ 策略创建成功")

    # 创建测试数据（包含量价突破）
    symbol = 'BTC-USDT'
    data_1s = {
        symbol: create_test_klines('BTCUSDT', count=100, trend='uptrend', include_breakout=True)
    }

    # 创建更高时间框架数据
    higher_tf_data = {
        symbol: create_higher_timeframe_test_data('BTCUSDT', count=100)
    }

    logger.info(f"生成了{len(data_1s[symbol])}条1秒K线数据（包含量价突破）")
    logger.info(f"生成了更高时间框架数据: {list(higher_tf_data[symbol].keys())}")

    # 计算技术指标
    indicators = strategy.calculate_indicators(data_1s)
    logger.info(f"✅ 计算技术指标完成，覆盖{len(indicators)}个交易对")

    for symbol, symbol_indicators in indicators.items():
        logger.info(f"  {symbol}: {list(symbol_indicators.keys())}")

    # 生成信号（传递更高时间框架数据）
    signals = strategy.generate_signals(data_1s, higher_tf_data)
    logger.info(f"✅ 信号生成完成，共{len(signals)}个信号")

    for i, signal in enumerate(signals, 1):
        logger.info(f"  信号#{i}: {signal.signal_type.value}, "
                   f"价格={signal.price:.2f}, "
                   f"置信度={signal.confidence:.2f}, "
                   f"原因={signal.metadata.get('reason', 'N/A')}")

    # 获取信号统计
    stats = strategy.get_signal_statistics()
    logger.info(f"信号统计:")
    logger.info(f"  初步信号: {stats['preliminary_signals']}")
    logger.info(f"  确认信号: {stats['confirmed_signals']}")
    logger.info(f"  确认率: {stats['confirmation_rate']:.2%}")

    return len(signals) > 0


def test_websocket_integration():
    """测试WebSocket集成（简单测试，不实际连接）"""
    logger.info("=" * 80)
    logger.info("测试5: WebSocket集成（配置测试）")
    logger.info("=" * 80)

    config = {
        'mode': 'paper',
        'name': 'MultiTimeframeKlineBreakout',
        'symbols': ['BTC-USDT', 'ETH-USDT'],
        'strategy': {
            'kline_breakout': {'window_size': 200}
        }
    }

    strategy = MultiTimeframeKlineBreakoutStrategy(config)
    logger.info(f"✅ 策略创建成功")

    # 检查WebSocket相关属性
    logger.info(f"  Binance符号格式: {strategy.binance_symbols}")
    logger.info(f"  K线检测器: {strategy.kline_detector is not None}")
    logger.info(f"  WebSocket状态: {strategy.ws_running}")

    # 注意：不实际启动WebSocket连接（需要API密钥）
    logger.info(f"ℹ️  WebSocket连接需要实际API环境，跳过连接测试")

    return True


def run_all_tests():
    """运行所有测试"""
    logger.info("")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 20 + "多时间框架K线突破策略测试" + " " * 30 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("")

    tests = [
        ("KlineBreakoutDetector", test_kline_breakout_detector),
        ("MultiTimeframeConfirmator", test_multi_timeframe_confirmator),
        ("策略初始化", test_strategy_initialization),
        ("策略信号生成", test_strategy_signal_generation),
        ("WebSocket集成", test_websocket_integration)
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            logger.info(f"\n🔍 开始测试: {test_name}")
            result = test_func()
            results[test_name] = "✅ 通过" if result else "❌ 失败"
            logger.info(f"测试结果: {results[test_name]}")
        except Exception as e:
            results[test_name] = f"❌ 错误: {e}"
            logger.error(f"测试出错: {e}", exc_info=True)

    # 测试结果汇总
    logger.info("")
    logger.info("=" * 80)
    logger.info("测试结果汇总")
    logger.info("=" * 80)

    for test_name, result in results.items():
        logger.info(f"{test_name:30s}: {result}")

    passed = sum(1 for r in results.values() if "✅" in r)
    total = len(results)

    logger.info("")
    logger.info(f"总计: {passed}/{total} 测试通过")

    if passed == total:
        logger.info("🎉 所有测试通过！")
    else:
        logger.warning(f"⚠️  {total - passed}个测试失败")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
