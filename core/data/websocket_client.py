"""
币安WebSocket客户端 - 高频突破策略数据层

基于币安官方API文档实现的全市场Ticker流WebSocket客户端
文档地址: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams

实现特性:
- 自动重连机制
- 错误处理和容错
- 数据缓存和处理
- 多种连接模式支持
"""

import asyncio
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class TickerData:
    """Ticker数据结构"""
    symbol: str                # 交易对符号
    price: float              # 最新价格
    price_change: float       # 24小时价格变化
    price_change_percent: float  # 24小时价格变化百分比
    weighted_avg_price: float # 加权平均价格
    open_price: float         # 24小时开盘价
    high_price: float         # 24小时最高价
    low_price: float          # 24小时最低价
    volume: float             # 24小时成交量
    quote_volume: float       # 24小时成交额
    open_time: int            # 24小时开始时间
    close_time: int           # 统计截止时间
    event_time: int           # 🔥 WebSocket事件时间（实时）
    first_id: int             # 首笔成交id
    last_id: int              # 末笔成交id
    count: int                # 24小时内成交数量
    last_quantity: float      # 🔥 Q字段：最新价格上的成交量

    @classmethod
    def from_dict(cls, data: Dict) -> 'TickerData':
        """从字典创建TickerData实例"""
        try:

            # 提取所有时间字段
            event_time = int(data['E']) if data.get('E') else 0

            final_timestamp = event_time

            return cls(
                symbol=data['s'],
                price=float(data['c']),                              # 最新价格
                price_change=float(data['p']) if data.get('p') else 0.0,     # 24小时价格变化 (p字段)
                price_change_percent=float(data['P']) if data.get('P') else 0.0,  # 24小时价格变化百分比 (P字段)
                weighted_avg_price=float(data['w']) if data.get('w') else 0.0,  # 24小时加权平均价格 (w字段)
                open_price=float(data['o']) if data.get('o') else 0.0,           # 24小时开盘价 (o字段)
                high_price=float(data['h']) if data.get('h') else 0.0,           # 24小时最高价 (h字段)
                low_price=float(data['l']) if data.get('l') else 0.0,            # 24小时最低价 (l字段)
                volume=float(data['v']) if data.get('v') else 0.0,               # 24小时成交量 (v字段)
                quote_volume=float(data['q']) if data.get('q') else 0.0,         # 24小时成交额 (q字段)
                open_time=int(data['O']) if data.get('O') else 0,               # 统计开始时间 (O字段)
                close_time=int(data['C']) if data.get('C') else 0,              # 统计截止时间 (C字段)
                event_time=final_timestamp,                                    # WebSocket事件时间 (E字段)
                first_id=int(data['F']) if data.get('F') else 0,               # 24小时内第一笔成交交易ID (F字段)
                last_id=int(data['L']) if data.get('L') else 0,                # 24小时内最后一笔成交交易ID (L字段)
                count=int(data['n']) if data.get('n') else 0,                  # 24小时内成交数量 (n字段)
                last_quantity=float(data['Q']) if data.get('Q') else 0.0        # 🔥 Q字段：最新一笔交易的成交量
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"解析Ticker数据失败: {e}, 数据: {data}")
            return None


class BinanceWebSocketClient:
    """币安WebSocket客户端

    专门用于高频突破策略的实时数据获取，支持全市场Ticker流订阅
    """

    def __init__(self, testnet: bool = True, max_reconnects: int = 10, reconnect_interval: int = 5):
        """
        初始化WebSocket客户端

        Args:
            testnet: 是否使用测试网
            max_reconnects: 最大重连次数
            reconnect_interval: 重连间隔（秒）
        """
        self.testnet = testnet
        self.max_reconnects = max_reconnects
        self.reconnect_interval = reconnect_interval
        self.reconnect_count = 0
        self.is_connected = False
        self.is_running = False

        # WebSocket连接
        self.ws_connection = None
        self.ws_url = self._get_ws_url()

        # 回调函数
        self.ticker_callbacks: List[Callable[[TickerData], None]] = []
        self.error_callbacks: List[Callable[[Exception], None]] = []

        # 数据缓存
        self.ticker_cache: Dict[str, TickerData] = {}
        self.last_update_time: Dict[str, datetime] = {}

        # 统计信息
        self.stats = {
            'messages_received': 0,
            'errors_count': 0,
            'reconnects_count': 0,
            'last_message_time': None,
            'connection_start_time': None
        }

    def _get_ws_url(self) -> str:
        """获取WebSocket URL

        根据币安API文档：
        - 测试网: wss://stream.binancefuture.com/ws
        - 正式网: wss://fstream.binance.com/ws

        Returns:
            WebSocket URL
        """
        if self.testnet:
            url = "wss://stream.binancefuture.com/ws"
            logger.info(f"使用币安测试网WebSocket URL: {url}")
        else:
            url = "wss://fstream.binance.com/ws"
            logger.info(f"使用币安正式网WebSocket URL: {url}")
        return url

    def add_ticker_callback(self, callback: Callable[[TickerData], None]):
        """添加Ticker数据回调函数

        Args:
            callback: 回调函数，接收TickerData参数
        """
        self.ticker_callbacks.append(callback)
        logger.info(f"添加Ticker回调函数，当前总数: {len(self.ticker_callbacks)}")

    def add_error_callback(self, callback: Callable[[Exception], None]):
        """添加错误回调函数

        Args:
            callback: 回调函数，接收Exception参数
        """
        self.error_callbacks.append(callback)
        logger.info(f"添加错误回调函数，当前总数: {len(self.error_callbacks)}")

    def _call_ticker_callbacks(self, ticker: TickerData):
        """调用所有Ticker回调函数"""
        for callback in self.ticker_callbacks:
            try:
                callback(ticker)
            except Exception as e:
                logger.error(f"Ticker回调函数执行失败: {e}")

    def _call_error_callbacks(self, error: Exception):
        """调用所有错误回调函数"""
        for callback in self.error_callbacks:
            try:
                callback(error)
            except Exception as e:
                logger.error(f"错误回调函数执行失败: {e}")

    async def connect_all_ticker(self):
        """连接全市场Ticker流

        订阅!ticker@arr流，获取所有USDT-M合约的24小时价格变动统计
        """
        try:
            logger.info(f"正在连接币安WebSocket: {self.ws_url}")

            # 建立WebSocket连接 (兼容新版本websockets库)
            self.ws_connection = await websockets.connect(
                self.ws_url,
                ping_interval=30,  # 30秒心跳
                close_timeout=1    # 1秒关闭超时
            )

            self.is_connected = True
            self.reconnect_count = 0
            self.stats['connection_start_time'] = datetime.now()

            logger.info("WebSocket连接成功")

            # 发送订阅消息
            await self._subscribe_all_ticker()

            # 开始消息处理循环
            await self._message_loop()

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)

    async def _subscribe_all_ticker(self):
        """订阅全市场Ticker流"""
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": ["!ticker@arr"],
            "id": 1
        }

        try:
            await self.ws_connection.send(json.dumps(subscribe_msg))
            logger.info("已发送全市场Ticker订阅请求")

            # 等待订阅确认
            response = await asyncio.wait_for(self.ws_connection.recv(), timeout=10)
            response_data = json.loads(response)

            if response_data.get('id') == 1 and response_data.get('result') is None:
                logger.info("全市场Ticker订阅成功")
            else:
                logger.warning(f"订阅响应异常: {response_data}")

        except asyncio.TimeoutError:
            logger.error("订阅超时")
        except Exception as e:
            logger.error(f"订阅失败: {e}")

    async def _message_loop(self):
        """消息处理循环"""
        self.is_running = True
        logger.info("开始消息处理循环")

        try:
            while self.is_running and self.is_connected:
                try:
                    # 接收消息
                    message = await asyncio.wait_for(
                        self.ws_connection.recv(),
                        timeout=60  # 60秒超时
                    )

                    # 处理消息
                    await self._handle_message(message)

                except asyncio.TimeoutError:
                    logger.warning("接收消息超时，发送ping保活")
                    await self.ws_connection.ping()

        except ConnectionClosed as e:
            logger.warning(f"WebSocket连接关闭: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)

        except Exception as e:
            logger.error(f"消息处理循环异常: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)

        finally:
            self.is_running = False
            logger.info("消息处理循环结束")

    async def _handle_message(self, message: str):
        """处理WebSocket消息

        Args:
            message: 接收到的JSON消息
        """
        try:
            data = json.loads(message)
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now()

            # 处理不同类型的消息
            if isinstance(data, list):
                # 全市场Ticker数据 (array)
                await self._process_ticker_array(data)
            elif isinstance(data, dict):
                # 单个消息处理
                await self._process_single_message(data)
            else:
                logger.debug(f"未知消息类型: {type(data)}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            self.stats['errors_count'] += 1
        except Exception as e:
            logger.error(f"消息处理失败: {e}")
            self.stats['errors_count'] += 1

    async def _process_ticker_array(self, ticker_array: List[Dict]):
        """处理Ticker数组数据

        Args:
            ticker_array: Ticker数据数组
        """
        for ticker_data in ticker_array:
            ticker = TickerData.from_dict(ticker_data)
            if ticker:
                # 更新缓存
                self.ticker_cache[ticker.symbol] = ticker
                self.last_update_time[ticker.symbol] = datetime.now()

                # 调用回调函数
                self._call_ticker_callbacks(ticker)

    async def _process_single_message(self, data: Dict):
        """处理单个消息

        Args:
            data: 消息数据
        """
        # 处理订阅确认等消息
        if 'id' in data:
            logger.debug(f"收到响应消息: {data}")
        elif 'error' in data:
            logger.error(f"收到错误消息: {data['error']}")
            self.stats['errors_count'] += 1
        elif 'e' in data and data['e'] == '24hrTicker':
            # 处理单个交易对的Ticker数据 (币安期货格式)
            ticker = TickerData.from_dict(data)
            if ticker:
                # 更新缓存
                self.ticker_cache[ticker.symbol] = ticker
                self.last_update_time[ticker.symbol] = datetime.now()

                # 调用回调函数
                self._call_ticker_callbacks(ticker)
                logger.debug(f"处理单个Ticker数据: {ticker.symbol}")
        elif 'stream' in data and 'data' in data:
            # 处理包装格式的Ticker数据 (币安现货格式)
            ticker_data = data['data']
            ticker = TickerData.from_dict(ticker_data)
            if ticker:
                # 更新缓存
                self.ticker_cache[ticker.symbol] = ticker
                self.last_update_time[ticker.symbol] = datetime.now()

                # 调用回调函数
                self._call_ticker_callbacks(ticker)
                logger.debug(f"处理单个Ticker数据: {ticker.symbol}")
        else:
            logger.info(f"未处理的消息: {data}")

    async def _handle_connection_error(self, error: Exception):
        """处理连接错误

        Args:
            error: 错误信息
        """
        self.stats['errors_count'] += 1
        logger.error(f"连接错误: {error}")

        # 调用错误回调
        self._call_error_callbacks(error)

        # 尝试重连
        if self.reconnect_count < self.max_reconnects:
            self.reconnect_count += 1
            self.stats['reconnects_count'] = self.reconnect_count

            logger.info(f"尝试重连 ({self.reconnect_count}/{self.max_reconnects})")
            await asyncio.sleep(self.reconnect_interval)

            try:
                await self.connect_all_ticker()
            except Exception as e:
                logger.error(f"重连失败: {e}")
                await self._handle_connection_error(e)
        else:
            logger.error(f"达到最大重连次数 ({self.max_reconnects})，停止重连")
            self.is_running = False

    async def disconnect(self):
        """断开WebSocket连接"""
        logger.info("正在断开WebSocket连接")

        self.is_running = False
        self.is_connected = False

        if self.ws_connection:
            try:
                await self.ws_connection.close()
                logger.info("WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"关闭连接时出错: {e}")

    def get_ticker(self, symbol: str) -> Optional[TickerData]:
        """获取指定交易对的最新Ticker数据

        Args:
            symbol: 交易对符号

        Returns:
            TickerData实例，如果不存在返回None
        """
        return self.ticker_cache.get(symbol)

    def get_all_tickers(self) -> Dict[str, TickerData]:
        """获取所有缓存的Ticker数据

        Returns:
            所有Ticker数据的字典
        """
        return self.ticker_cache.copy()

    def get_stats(self) -> Dict:
        """获取连接统计信息

        Returns:
            统计信息字典
        """
        stats = self.stats.copy()

        # 添加连接时长
        if stats['connection_start_time']:
            stats['connection_duration'] = (
                datetime.now() - stats['connection_start_time']
            ).total_seconds()

        # 添加当前状态
        stats['is_connected'] = self.is_connected
        stats['is_running'] = self.is_running
        stats['reconnect_count'] = self.reconnect_count
        stats['cached_symbols_count'] = len(self.ticker_cache)

        return stats

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect_all_ticker()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()


# 便利函数
async def create_binance_ws_client(testnet: bool = True,
                                 ticker_callback: Optional[Callable[[TickerData], None]] = None,
                                 error_callback: Optional[Callable[[Exception], None]] = None) -> BinanceWebSocketClient:
    """创建并配置币安WebSocket客户端

    Args:
        testnet: 是否使用测试网
        ticker_callback: Ticker数据回调函数
        error_callback: 错误回调函数

    Returns:
        配置好的WebSocket客户端
    """
    client = BinanceWebSocketClient(testnet=testnet)

    if ticker_callback:
        client.add_ticker_callback(ticker_callback)
    if error_callback:
        client.add_error_callback(error_callback)

    return client


# 示例使用
async def example_usage():
    """示例用法"""

    def ticker_handler(ticker: TickerData):
        """Ticker数据处理函数"""
        if ticker.symbol in ['BTCUSDT', 'ETHUSDT']:
            logger.info(f"{ticker.symbol}: ${ticker.price} ({ticker.price_change_percent:+.2f}%)")

    def error_handler(error: Exception):
        """错误处理函数"""
        logger.error(f"WebSocket错误: {error}")

    # 创建客户端
    client = await create_binance_ws_client(
        testnet=True,
        ticker_callback=ticker_handler,
        error_callback=error_handler
    )

    try:
        # 运行60秒
        await asyncio.sleep(60)
    finally:
        # 断开连接
        await client.disconnect()

    # 打印统计信息
    stats = client.get_stats()
    logger.info(f"统计信息: {stats}")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    asyncio.run(example_usage())