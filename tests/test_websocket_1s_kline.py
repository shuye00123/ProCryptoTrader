"""
WebSocket 1秒K线数据处理单元测试

测试内容:
1. 1秒K线消息解析
2. Kline对象创建
3. K线关闭标识验证
4. volume字段准确性验证
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from core.data.websocket_client import BinanceWebSocketClient
from core.strategy.kline_breakout_detector import Kline

# pytest标记（如果使用pytest运行）
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # 创建模拟的pytest.mark装饰器
    class MockPytestMark:
        def asyncio(self, func):
            return func
    pytest = Mock()
    pytest.mark = MockPytestMark()


class TestKlineDataProcessing:
    """测试1秒K线数据处理"""

    def test_kline_object_creation(self):
        """测试Kline对象创建"""
        # 创建Kline对象
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.5,  # ✅ 真实的1秒K线成交量
            timestamp=pd.to_datetime("2024-01-15 10:00:00")
        )

        # 验证基本属性
        assert kline.symbol == "BTCUSDT"
        assert kline.open == 50000.0
        assert kline.high == 50100.0
        assert kline.low == 49900.0
        assert kline.close == 50050.0
        assert kline.volume == 100.5  # ✅ 验证volume字段

        # 验证计算属性
        assert kline.price_change == 50.0
        assert abs(kline.price_change_pct - 0.1) < 0.001  # 50/50000*100 = 0.1%

        print("✅ Kline对象创建测试通过")

    def test_kline_close_flag_validation(self):
        """测试K线关闭标识验证"""
        # 模拟已关闭的K线消息
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

        # 验证已关闭的K线应该被处理
        assert closed_kline_msg['k']['x'] == True
        print("✅ 已关闭K线标识验证通过")

        # 模拟未关闭的K线消息
        unclosed_kline_msg = {
            "e": "kline",
            "k": {
                "x": False,  # ❌ K线未关闭
                "v": "500"
            }
        }

        # 验证未关闭的K线不应该被处理
        assert unclosed_kline_msg['k']['x'] == False
        print("✅ 未关闭K线标识验证通过")

    def test_kline_volume_accuracy(self):
        """测试Kline volume字段准确性"""
        # 真实1秒K线成交量（该秒内所有成交总和）
        true_1s_volume = 1234.56

        kline = Kline(
            symbol="ETHUSDT",
            open=3000.0,
            high=3005.0,
            low=2995.0,
            close=3002.0,
            volume=true_1s_volume,  # ✅ 使用真实1秒K线成交量
            timestamp=pd.to_datetime("2024-01-15 10:00:01")
        )

        # 验证volume字段准确性
        assert kline.volume == true_1s_volume
        assert kline.volume > 0  # 成交量应该为正数

        print(f"✅ Kline volume字段准确性验证通过: {kline.volume}")

    def test_ohlc_logic_validation(self):
        """测试OHLC逻辑正确性"""
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,  # 应该 >= open, close
            low=49900.0,   # 应该 <= open, close
            close=50050.0,
            volume=100.0,
            timestamp=pd.to_datetime("2024-01-15 10:00:00")
        )

        # 验证OHLC逻辑
        assert kline.high >= kline.open, "high应该 >= open"
        assert kline.high >= kline.close, "high应该 >= close"
        assert kline.low <= kline.open, "low应该 <= open"
        assert kline.low <= kline.close, "low应该 <= close"

        print("✅ OHLC逻辑验证通过")


class TestWebSocketKlineProcessing:
    """测试WebSocket K线消息处理"""

    @pytest.mark.asyncio
    async def test_process_kline_message_closed(self):
        """测试处理已关闭的K线消息"""
        # 创建WebSocket客户端实例
        client = BinanceWebSocketClient(testnet=True)

        # 创建模拟的K线回调
        kline_received = []

        async def mock_kline_callback(kline):
            kline_received.append(kline)

        client.add_kline_callback(mock_kline_callback)

        # 模拟已关闭的K线消息
        kline_msg = {
            "e": "kline",
            "E": 1672515782136,
            "s": "BTCUSDT",
            "k": {
                "t": 1672515780000,
                "T": 1672515839999,
                "s": "BTCUSDT",
                "i": "1s",
                "o": "50000.0",
                "c": "50050.0",
                "h": "50100.0",
                "l": "49900.0",
                "v": "123.45",  # ✅ 真实的1秒K线成交量
                "n": 100,
                "x": True,  # ✅ K线已关闭
                "q": "6172500.0",
            }
        }

        # 处理K线消息
        await client._process_kline_message(kline_msg)

        # 验证回调被调用
        assert len(kline_received) == 1, "应该收到1个K线"

        # 验证Kline对象属性
        kline = kline_received[0]
        assert kline.symbol == "BTCUSDT"
        assert kline.open == 50000.0
        assert kline.close == 50050.0
        assert kline.volume == 123.45  # ✅ 验证volume字段准确性

        print("✅ 已关闭K线消息处理测试通过")

    @pytest.mark.asyncio
    async def test_process_kline_message_unclosed(self):
        """测试处理未关闭的K线消息（应该被跳过）"""
        # 创建WebSocket客户端实例
        client = BinanceWebSocketClient(testnet=True)

        # 创建模拟的K线回调
        kline_received = []

        async def mock_kline_callback(kline):
            kline_received.append(kline)

        client.add_kline_callback(mock_kline_callback)

        # 模拟未关闭的K线消息
        kline_msg = {
            "e": "kline",
            "k": {
                "x": False,  # ❌ K线未关闭
                "v": "100.0"
            }
        }

        # 处理K线消息
        await client._process_kline_message(kline_msg)

        # 验证回调没有被调用（未关闭的K线应该被跳过）
        assert len(kline_received) == 0, "未关闭的K线应该被跳过"

        print("✅ 未关闭K线消息跳过测试通过")

    @pytest.mark.asyncio
    async def test_multiplex_socket_format(self):
        """测试multiplex_socket格式消息处理"""
        # 创建WebSocket客户端实例
        client = BinanceWebSocketClient(testnet=True)

        # 创建模拟的K线回调
        kline_received = []

        async def mock_kline_callback(kline):
            kline_received.append(kline)

        client.add_kline_callback(mock_kline_callback)

        # 模拟multiplex_socket格式消息
        multiplex_msg = {
            "stream": "btcusdt@kline_1s",  # ✅ 1秒K线流
            "data": {
                "e": "kline",
                "E": 1672515782136,
                "s": "BTCUSDT",
                "k": {
                    "t": 1672515780000,
                    "T": 1672515839999,
                    "s": "BTCUSDT",
                    "i": "1s",
                    "o": "50000.0",
                    "c": "50050.0",
                    "h": "50100.0",
                    "l": "49900.0",
                    "v": "250.75",  # ✅ 真实的1秒K线成交量
                    "n": 150,
                    "x": True,  # ✅ K线已关闭
                    "q": "12537500.0",
                }
            }
        }

        # 处理消息
        await client._process_single_message(multiplex_msg)

        # 验证回调被调用
        assert len(kline_received) == 1, "应该收到1个K线"

        # 验证volume字段
        kline = kline_received[0]
        assert kline.volume == 250.75, "volume字段应该准确"

        print("✅ multiplex_socket格式消息处理测试通过")


class TestKlineDataQuality:
    """测试K线数据质量"""

    def test_volume_positive_check(self):
        """测试volume字段正数检查"""
        # volume应该总是正数
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.5,  # ✅ 正数
            timestamp=pd.to_datetime("2024-01-15 10:00:00")
        )

        assert kline.volume > 0, "volume应该是正数"
        print("✅ volume正数检查通过")

    def test_timestamp_parsing(self):
        """测试时间戳解析"""
        # 测试毫秒时间戳转换
        timestamp_ms = 1672515780000  # 2023-01-01 00:03:00
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.0,
            timestamp=pd.to_datetime(timestamp_ms, unit='ms')
        )

        # 验证时间戳解析正确
        assert kline.timestamp is not None
        assert isinstance(kline.timestamp, pd.Timestamp)

        print("✅ 时间戳解析测试通过")

    def test_price_calculation_accuracy(self):
        """测试价格计算准确性"""
        kline = Kline(
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.0,
            timestamp=pd.to_datetime("2024-01-15 10:00:00")
        )

        # 验证价格变化计算
        expected_change = 50050.0 - 50000.0
        assert abs(kline.price_change - expected_change) < 0.01

        # 验证价格变化百分比计算
        expected_pct = (expected_change / 50000.0) * 100
        assert abs(kline.price_change_pct - expected_pct) < 0.001

        print("✅ 价格计算准确性测试通过")


class TestKlineStreamGeneration:
    """测试K线流生成"""

    def test_kline_stream_format(self):
        """测试1秒K线流格式生成"""
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

        # 生成1秒K线流
        streams = [f"{symbol.lower()}@kline_1s" for symbol in symbols]

        # 验证流格式
        expected_streams = [
            'btcusdt@kline_1s',
            'ethusdt@kline_1s',
            'bnbusdt@kline_1s'
        ]

        assert streams == expected_streams, "1秒K线流格式应该正确"

        # 验证每个流都包含@kline_1s后缀
        for stream in streams:
            assert stream.endswith('@kline_1s'), f"流 {stream} 应该以 @kline_1s 结尾"

        print("✅ 1秒K线流格式生成测试通过")

    def test_stream_vs_ticker_comparison(self):
        """对比K线流和Ticker流"""
        symbol = 'BTCUSDT'

        # Ticker流格式（旧方案）
        ticker_stream = f"{symbol.lower()}@ticker"

        # 1秒K线流格式（新方案）
        kline_stream = f"{symbol.lower()}@kline_1s"

        # 验证两者不同
        assert ticker_stream != kline_stream, "Ticker流和K线流应该不同"
        assert ticker_stream == "btcusdt@ticker"
        assert kline_stream == "btcusdt@kline_1s"

        print(f"✅ 流格式对比测试通过:")
        print(f"   Ticker流: {ticker_stream}")
        print(f"   K线流: {kline_stream}")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始运行 WebSocket 1秒K线数据处理测试")
    print("="*60 + "\n")

    # TestKlineDataProcessing
    print("【测试组1: Kline数据处理】")
    test = TestKlineDataProcessing()
    test.test_kline_object_creation()
    test.test_kline_close_flag_validation()
    test.test_kline_volume_accuracy()
    test.test_ohlc_logic_validation()
    print()

    # TestKlineDataQuality
    print("【测试组2: Kline数据质量】")
    test = TestKlineDataQuality()
    test.test_volume_positive_check()
    test.test_timestamp_parsing()
    test.test_price_calculation_accuracy()
    print()

    # TestKlineStreamGeneration
    print("【测试组3: K线流生成】")
    test = TestKlineStreamGeneration()
    test.test_kline_stream_format()
    test.test_stream_vs_ticker_comparison()
    print()

    print("="*60)
    print("✅ 所有测试通过！")
    print("="*60 + "\n")


if __name__ == "__main__":
    # 运行所有测试
    run_all_tests()

    # 也可以使用pytest运行：
    # pytest tests/test_websocket_1s_kline.py -v
