"""
币安WebSocket客户端 - 基于python-binance SDK实现

## 核心功能
- 使用python-binance的AsyncClient和BinanceSocketManager
- 订阅全市场ticker数据（!ticker@arr）
- 自动重连和错误处理
- 保持原有接口兼容性

## 迁移说明
从websockets库迁移到python-binance SDK，提供更稳定的连接和官方支持。
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

# python-binance SDK
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

# 设置日志
logger = logging.getLogger(__name__)

# Tick数据管理器导入（延迟导入避免循环依赖）
TICK_MANAGER = None


def set_tick_data_manager(manager):
    """设置全局Tick数据管理器"""
    global TICK_MANAGER
    TICK_MANAGER = manager


def get_tick_data_manager():
    """获取当前设置的Tick数据管理器"""
    return TICK_MANAGER


@dataclass
class TickerData:
    """Ticker数据结构"""
    symbol: str
    price: float
    price_change: float
    price_change_percent: float
    weighted_avg_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    open_time: int
    close_time: int
    event_time: int
    first_id: int
    last_id: int
    count: int
    last_quantity: float

    __slots__ = [
        'symbol', 'price', 'price_change', 'price_change_percent',
        'weighted_avg_price', 'open_price', 'high_price', 'low_price',
        'volume', 'quote_volume', 'open_time', 'close_time', 'event_time',
        'first_id', 'last_id', 'count', 'last_quantity'
    ]

    @classmethod
    def from_dict(cls, data: Dict) -> 'TickerData':
        """从字典创建TickerData实例（兼容Binance API格式）"""
        try:
            return cls(
                symbol=data['s'],
                price=float(data['c']),
                price_change=float(data['p']) if data.get('p') else 0.0,
                price_change_percent=float(data['P']) if data.get('P') else 0.0,
                weighted_avg_price=float(data['w']) if data.get('w') else 0.0,
                open_price=float(data['o']) if data.get('o') else 0.0,
                high_price=float(data['h']) if data.get('h') else 0.0,
                low_price=float(data['l']) if data.get('l') else 0.0,
                volume=float(data['v']) if data.get('v') else 0.0,
                quote_volume=float(data['q']) if data.get('q') else 0.0,
                open_time=int(data['O']) if data.get('O') else 0,
                close_time=int(data['C']) if data.get('C') else 0,
                event_time=int(data['E']) if data.get('E') else 0,
                first_id=int(data['F']) if data.get('F') else 0,
                last_id=int(data['L']) if data.get('L') else 0,
                count=int(data['n']) if data.get('n') else 0,
                last_quantity=float(data['Q']) if data.get('Q') else 0.0
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"解析Ticker数据失败: {e}")
            return None


class BinanceWebSocketClient:
    """币安WebSocket客户端 - 基于python-binance SDK

    使用AsyncClient和BinanceSocketManager实现：
    - 全市场ticker订阅
    - 自动重连机制
    - 保持原有接口兼容性
    """

    def __init__(self, testnet: bool = True, max_reconnects: int = 10, reconnect_interval: int = 5):
        # 连接配置
        self.testnet = testnet
        self.max_reconnects = max_reconnects
        self.reconnect_interval = reconnect_interval
        self.reconnect_count = 0
        self.is_connected = False
        self.is_running = False
        self._should_reconnect = False

        # python-binance 组件
        self._client: Optional[AsyncClient] = None      # AsyncClient实例
        self._bm: Optional[BinanceSocketManager] = None # BinanceSocketManager实例
        self._ts = None                                 # Ticker socket
        self._ts_context = None                         # Socket上下文

        # 兼容性：保留原有属性名
        self.ws_connection = None
        self.ws_url = "wss://stream.binancefuture.com/ws" if testnet else "wss://fstream.binance.com/ws"

        # 连接状态
        self.connection_start_time = None
        self.ticker_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        self.ticker_cache: Dict[str, TickerData] = {}

        # 统计信息
        self.messages_received = 0
        self.errors_count = 0
        self._last_recv_time = None

    def add_ticker_callback(self, callback: Callable):
        """添加Ticker数据回调函数"""
        self.ticker_callbacks.append(callback)

    def add_error_callback(self, callback: Callable):
        """添加错误回调函数"""
        self.error_callbacks.append(callback)

    async def _call_ticker_callbacks(self, ticker: TickerData):
        """调用Ticker回调函数"""
        for callback in self.ticker_callbacks:
            try:
                callback(ticker)
            except Exception as e:
                logger.error(f"回调失败: {e}")

        # Tick数据管理器异步处理
        if TICK_MANAGER:
            asyncio.create_task(TICK_MANAGER.collect_tick(ticker))

    def _call_error_callbacks(self, error: Exception):
        """调用错误回调函数"""
        for callback in self.error_callbacks:
            try:
                callback(error)
            except Exception:
                pass

    async def connect_all_ticker(self):
        """连接WebSocket并订阅所有Ticker（使用python-binance）"""
        try:
            logger.info(f"连接WebSocket: python-binance SDK (testnet={self.testnet})")

            # 关闭旧连接
            await self.disconnect()

            # 初始化 AsyncClient（公共数据流不需要API密钥）
            self._client = await AsyncClient.create(
                api_key=None,
                api_secret=None,
                testnet=self.testnet
            )

            # 创建 BinanceSocketManager
            self._bm = BinanceSocketManager(
                client=self._client,
                user_timeout=60  # 连接超时设置
            )

            # 获取 ticker socket（等效于 !ticker@arr 全市场订阅）
            self._ts = self._bm.ticker_socket()

            self.is_connected = True
            self.connection_start_time = datetime.now()
            # 连接成功后重置重连计数
            if self.reconnect_count == 0:
                logger.info("WebSocket连接成功 (python-binance)")
            else:
                logger.info(f"WebSocket重连成功 (第{self.reconnect_count}次)")
            self.reconnect_count = 0  # 重置重连计数

            # 启动消息循环
            await self._message_loop()

        except BinanceAPIException as e:
            logger.error(f"Binance API错误: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)

    async def _message_loop(self):
        """消息处理循环（使用python-binance socket）"""
        self.is_running = True
        self._should_reconnect = False
        self._last_recv_time = datetime.now()
        logger.info("开始消息处理循环")

        try:
            # 使用 async with 管理 socket 生命周期
            async with self._ts as tscm:
                self._ts_context = tscm

                while self.is_running and self.is_connected:
                    # 10分钟静默检测
                    if (datetime.now() - self._last_recv_time).total_seconds() > 600:
                        logger.warning("10分钟未收到数据，可能连接已断开")
                        self._should_reconnect = True
                        break

                    # 接收消息（python-binance自动处理JSON解析）
                    message = await tscm.recv()
                    self._last_recv_time = datetime.now()
                    self.messages_received += 1

                    # 定期输出连接状态（每1000条消息）
                    if self.messages_received % 1000 == 0:
                        if self.connection_start_time:
                            duration = (datetime.now() - self.connection_start_time).total_seconds()
                            logger.info(f"📊 已接收消息: {self.messages_received}条, "
                                       f"连接时长: {duration:.0f}秒")

                    # 异步处理消息，避免阻塞接收
                    asyncio.create_task(self._handle_message(message))

        except Exception as e:
            logger.info(f"连接关闭: {e}")
            self.is_connected = False
            await self._handle_connection_error(e)
        finally:
            self.is_running = False
            self._ts_context = None
            # 如果需要重连，启动重连循环
            if not self.is_connected and self.reconnect_count < self.max_reconnects:
                await self._reconnect_loop()

    async def _handle_message(self, message):
        """处理WebSocket消息（后台任务，不阻塞主循环）

        python-binance返回的消息格式与Binance API一致，
        TickerData.from_dict()可以直接使用。
        """
        try:
            # python-binance已经解析为字典
            data = message if isinstance(message, dict) else {}

            # 处理不同类型的消息
            if isinstance(data, list):
                # !ticker@arr 返回的ticker数组
                await self._process_ticker_array(data)
            elif isinstance(data, dict):
                await self._process_single_message(data)

        except Exception as e:
            logger.error(f"消息处理失败: {e}")
            self.errors_count += 1

    async def _process_ticker_array(self, ticker_array: List[Dict]):
        """处理Ticker数组（!ticker@arr）"""
        for ticker_data in ticker_array:
            ticker = TickerData.from_dict(ticker_data)
            if ticker:
                self.ticker_cache[ticker.symbol] = ticker
                await self._call_ticker_callbacks(ticker)

    async def _process_single_message(self, data: Dict):
        """处理单个消息"""
        if 'e' in data and data['e'] == '24hrTicker':
            # 单个ticker数据（24小时ticker）
            ticker = TickerData.from_dict(data)
            if ticker:
                self.ticker_cache[ticker.symbol] = ticker
                await self._call_ticker_callbacks(ticker)
        elif 'e' in data and data['e'] == 'error':
            # 错误消息
            logger.error(f"收到错误消息: {data}")
            self.errors_count += 1
        # 忽略其他类型的消息

    async def _handle_connection_error(self, error: Exception):
        """处理连接错误"""
        self.errors_count += 1
        logger.warning(f"连接错误: {error}")

        # 调用错误回调
        self._call_error_callbacks(error)

    async def _reconnect_loop(self):
        """重连循环（非递归）"""
        while self.reconnect_count < self.max_reconnects:
            self.reconnect_count += 1

            # 指数退避
            backoff_interval = min(
                self.reconnect_interval * (1.5 ** (self.reconnect_count - 1)),
                60  # 最大60秒
            )

            logger.info(f"尝试重连 ({self.reconnect_count}/{self.max_reconnects}), "
                       f"等待 {backoff_interval:.1f} 秒后开始...")
            await asyncio.sleep(backoff_interval)

            try:
                # 关闭旧连接
                await self.disconnect()

                # 尝试重新连接
                await self.connect_all_ticker()
                return  # 连接成功，退出重连循环

            except Exception as e:
                logger.error(f"重连失败: {e}")
                self._call_error_callbacks(e)

        logger.error(f"达到最大重连次数 ({self.max_reconnects})，停止重连")

    async def disconnect(self):
        """断开WebSocket连接"""
        logger.info("正在断开WebSocket连接")

        self.is_running = False
        self.is_connected = False

        try:
            # 退出socket上下文
            if self._ts_context:
                try:
                    await self._ts_context.__aexit__(None, None, None)
                except Exception:
                    pass
                self._ts_context = None

            # 关闭AsyncClient连接
            if self._client:
                await self._client.close_connection()
                self._client = None

            logger.info("WebSocket连接已关闭")
        except Exception as e:
            logger.error(f"关闭连接时出错: {e}")

    def get_ticker(self, symbol: str) -> Optional[TickerData]:
        """获取指定交易对的最新Ticker数据"""
        return self.ticker_cache.get(symbol)

    def get_all_tickers(self) -> Dict[str, TickerData]:
        """获取所有缓存的Ticker数据"""
        return self.ticker_cache.copy()

    def get_stats(self) -> Dict:
        """获取连接统计信息"""
        stats = {
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'messages_received': self.messages_received,
            'errors_count': self.errors_count,
            'reconnect_count': self.reconnect_count,
            'cached_symbols_count': len(self.ticker_cache),
        }

        if self.connection_start_time:
            stats['connection_duration'] = (datetime.now() - self.connection_start_time).total_seconds()

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
    """创建并配置币安WebSocket客户端"""
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
        if ticker.symbol in ['BTCUSDT', 'ETHUSDT']:
            logger.info(f"{ticker.symbol}: ${ticker.price} ({ticker.price_change_percent:+.2f}%)")

    def error_handler(error: Exception):
        logger.error(f"WebSocket错误: {error}")

    client = await create_binance_ws_client(
        testnet=True,
        ticker_callback=ticker_handler,
        error_callback=error_handler
    )

    try:
        await asyncio.sleep(60)
    finally:
        await client.disconnect()

    stats = client.get_stats()
    logger.info(f"统计信息: {stats}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(example_usage())
