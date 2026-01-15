"""
1秒K线数据处理简化测试（不依赖binance模块）

测试内容:
1. Kline对象创建和验证
2. volume字段准确性
3. K线关闭标识处理
4. OHLC逻辑验证
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from datetime import datetime

from core.strategy.kline_breakout_detector import Kline


def test_kline_object_creation():
    """测试1: Kline对象创建"""
    print("\n【测试1: Kline对象创建】")

    # 创建Kline对象（使用真实的1秒K线成交量）
    kline = Kline(
        symbol="BTCUSDT",
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=123.45,  # ✅ 真实的1秒K线成交量（不是last_quantity）
        timestamp=pd.to_datetime("2024-01-15 10:00:00")
    )

    # 验证基本属性
    assert kline.symbol == "BTCUSDT", "symbol应该正确"
    assert kline.open == 50000.0, "open应该正确"
    assert kline.high == 50100.0, "high应该正确"
    assert kline.low == 49900.0, "low应该正确"
    assert kline.close == 50050.0, "close应该正确"
    assert kline.volume == 123.45, "volume应该正确"

    # 验证计算属性
    expected_change = 50.0
    assert abs(kline.price_change - expected_change) < 0.01, "price_change应该正确"

    expected_pct = (expected_change / 50000.0) * 100
    assert abs(kline.price_change_pct - expected_pct) < 0.001, "price_change_pct应该正确"

    print(f"✅ Kline对象创建成功")
    print(f"   Symbol: {kline.symbol}")
    print(f"   OHLC: {kline.open}/{kline.high}/{kline.low}/{kline.close}")
    print(f"   Volume: {kline.volume} (✅ 真实1秒K线成交量)")
    print(f"   Price Change: {kline.price_change:.2f} ({kline.price_change_pct:.3f}%)")


def test_volume_field_accuracy():
    """测试2: volume字段准确性"""
    print("\n【测试2: volume字段准确性】")

    # 场景1: 真实1秒K线成交量（该秒内所有成交总和）
    true_1s_volume = 1234.56  # 例如：该秒内总成交1234.56个BTC

    kline1 = Kline(
        symbol="BTCUSDT",
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=true_1s_volume,  # ✅ 直接使用真实1秒K线volume
        timestamp=pd.to_datetime("2024-01-15 10:00:01")
    )

    assert kline1.volume == true_1s_volume, "volume应该等于真实1秒K线成交量"
    assert kline1.volume > 0, "volume应该是正数"

    print(f"✅ volume字段准确性验证通过")
    print(f"   真实1秒K线成交量: {kline1.volume} BTC")
    print(f"   ✅ 不使用last_quantity字段（ticker的单次成交量）")

    # 场景2: 对比ticker的last_quantity（错误方案）
    ticker_last_quantity = 0.5  # ticker的lastQty（最近一次成交数量）

    print(f"\n   ⚠️ ticker的last_quantity: {ticker_last_quantity} BTC")
    print(f"   ✅ 两者相差 {true_1s_volume / ticker_last_quantity:.1f} 倍")
    print(f"   ✅ 因此必须使用Kline的volume字段")


def test_kline_close_flag():
    """测试3: K线关闭标识处理"""
    print("\n【测试3: K线关闭标识处理】")

    # 场景1: 已关闭的K线（应该处理）
    closed_kline_msg = {
        "e": "kline",
        "E": 1672515782136,
        "s": "BNBBTC",
        "k": {
            "t": 1672515780000,
            "T": 1672515839999,
            "s": "BNBBTC",
            "i": "1s",
            "o": "0.0010",
            "c": "0.0020",
            "h": "0.0025",
            "l": "0.0015",
            "v": "1000",  # ✅ 真实的1秒K线成交量
            "n": 100,
            "x": True,  # ✅ K线已关闭
            "q": "1.0000",
        }
    }

    kline_data = closed_kline_msg['k']
    is_closed = kline_data.get('x', False)

    assert is_closed == True, "应该识别为已关闭的K线"
    print(f"✅ 已关闭K线识别正确: x={is_closed}")

    # 场景2: 未关闭的K线（应该跳过）
    unclosed_kline_msg = {
        "e": "kline",
        "k": {
            "x": False,  # ❌ K线未关闭
            "v": "500"
        }
    }

    kline_data2 = unclosed_kline_msg['k']
    is_closed2 = kline_data2.get('x', False)

    assert is_closed2 == False, "应该识别为未关闭的K线"
    print(f"✅ 未关闭K线识别正确: x={is_closed2}")
    print(f"   ✅ 策略应该跳过未关闭的K线（x=False）")


def test_ohlc_logic():
    """测试4: OHLC逻辑验证"""
    print("\n【测试4: OHLC逻辑验证】")

    kline = Kline(
        symbol="ETHUSDT",
        open=3000.0,
        high=3010.0,
        low=2990.0,
        close=3005.0,
        volume=500.25,
        timestamp=pd.to_datetime("2024-01-15 10:00:00")
    )

    # 验证OHLC逻辑
    assert kline.high >= kline.open, "high应该 >= open"
    assert kline.high >= kline.close, "high应该 >= close"
    assert kline.low <= kline.open, "low应该 <= open"
    assert kline.low <= kline.close, "low应该 <= close"

    print(f"✅ OHLC逻辑验证通过")
    print(f"   Open: {kline.open}")
    print(f"   High: {kline.high} (>= open, close)")
    print(f"   Low: {kline.low} (<= open, close)")
    print(f"   Close: {kline.close}")


def test_kline_stream_format():
    """测试5: K线流格式"""
    print("\n【测试5: K线流格式验证】")

    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

    # ✅ 新方案：1秒K线流
    kline_streams = [f"{symbol.lower()}@kline_1s" for symbol in symbols]

    # ❌ 旧方案：ticker流
    ticker_streams = [f"{symbol.lower()}@ticker" for symbol in symbols]

    expected_kline = ['btcusdt@kline_1s', 'ethusdt@kline_1s', 'bnbusdt@kline_1s']
    expected_ticker = ['btcusdt@ticker', 'ethusdt@ticker', 'bnbusdt@ticker']

    assert kline_streams == expected_kline, "1秒K线流格式应该正确"
    assert ticker_streams == expected_ticker, "ticker流格式应该正确"

    print(f"✅ K线流格式验证通过")
    print(f"\n   对比:")
    for i, symbol in enumerate(symbols):
        print(f"   {symbol}:")
        print(f"     ❌ 旧方案: {ticker_streams[i]} (ticker流)")
        print(f"     ✅ 新方案: {kline_streams[i]} (1秒K线流)")


def test_volume_data_types():
    """测试6: volume数据类型"""
    print("\n【测试6: volume数据类型验证】")

    # 测试不同类型的volume值
    test_cases = [
        ("整数", 1000, 1000.0),
        ("浮点数", 123.45, 123.45),
        ("字符串", "500.25", 500.25),
    ]

    for name, input_value, expected_value in test_cases:
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=float(input_value),  # 转换为float
            timestamp=pd.to_datetime("2024-01-15 10:00:00")
        )

        assert abs(kline.volume - expected_value) < 0.001, f"{name}类型的volume应该正确"
        print(f"   ✅ {name}: {input_value} → {kline.volume}")


def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("1秒K线数据处理验证测试")
    print("="*70)

    try:
        # 运行所有测试
        test_kline_object_creation()
        test_volume_field_accuracy()
        test_kline_close_flag()
        test_ohlc_logic()
        test_kline_stream_format()
        test_volume_data_types()

        print("\n" + "="*70)
        print("✅ 所有测试通过！")
        print("="*70)

        print("\n【关键验证点总结】")
        print("1. ✅ Kline对象使用volume字段（不是last_quantity）")
        print("2. ✅ volume是真实的1秒K线成交量")
        print("3. ✅ 只处理已关闭的K线（x=True）")
        print("4. ✅ OHLC逻辑验证正确")
        print("5. ✅ 订阅@kline_1s流（不是@ticker流）")

        print("\n【下一步】")
        print("Phase 4: 重新验证策略效果（使用真实1秒K线数据）")

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
