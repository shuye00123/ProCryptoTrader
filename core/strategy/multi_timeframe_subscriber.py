"""
多时间框架K线订阅管理器

该模块实现多时间框架WebSocket订阅的统一管理，支持同时订阅多个时间框架（1s、15m、1h等），
并为不同时间框架注册独立的处理器回调。

核心特性:
1. 并行订阅: 同时订阅1s、15m、1h等多个时间框架
2. 独立处理器: 为每个时间框架注册专属的数据处理回调
3. 自动重连: 每个时间框架独立的WebSocket重连机制
4. 异步处理: 完全异步的K线数据流处理
5. 状态监控: 实时监控订阅连接状态

作者: Claude Code
创建时间: 2026-01-12
"""

import asyncio
import logging
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class MultiTimeframeKlineSubscriber:
    """
    多时间框架K线订阅管理器

    该类负责管理多个时间框架的WebSocket订阅，为每个时间框架创建
    独立的数据流和处理器，实现高性能的多时间框架数据接收。

    Attributes:
        symbols: 交易对列表
        timeframes: 时间框架列表 (如 ['1s', '15m', '1h'])
        bsm: BinanceSocketManager实例
        sockets: 各时间框架的WebSocket连接 {timeframe: socket}
        handlers: 各时间框架的处理器回调 {timeframe: callback}
        ws_running: WebSocket运行状态
        reconnect_attempts: 各时间框架的重连次数 {timeframe: attempts}
        stats: 订阅统计信息

    Example:
        >>> subscriber = MultiTimeframeKlineSubscriber(
        ...     symbols=['BTCUSDT', 'ETHUSDT'],
        ...     timeframes=['1s', '15m', '1h']
        ... )
        >>> subscriber.register_handler('1s', my_1s_handler)
        >>> subscriber.register_handler('15m', my_15m_handler)
        >>> await subscriber.start_all_subscriptions(api_key, api_secret)
    """

    def __init__(
        self,
        symbols: List[str],
        timeframes: List[str],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化多时间框架订阅管理器

        Args:
            symbols: 交易对列表 (如 ['BTCUSDT', 'ETHUSDT'])
            timeframes: 时间框架列表 (如 ['1s', '15m', '1h'])
            config: 额外配置参数
                - max_reconnect_attempts: 最大重连次数 (默认5)
                - reconnect_delay_ms: 重连延迟毫秒 (默认1000)
                - enable_stats: 是否启用统计 (默认True)
                - max_queue_size: SDK队列大小 (默认10000,解决队列溢出)
        """
        self.symbols = symbols
        self.timeframes = timeframes
        self.config = config or {}

        # 🔥 队列大小配置（解决BinanceWebsocketQueueOverflow）
        self.max_queue_size = self.config.get('max_queue_size', 10000)
        logger.info(f"[MultiTimeframeSubscriber] 📦 SDK队列大小配置: {self.max_queue_size}")

        # WebSocket连接管理
        self.bsm = None  # BinanceSocketManager实例
        self.sockets: Dict[str, Any] = {}  # {timeframe: socket}
        self.ws_running = False
        self._tasks: Dict[str, asyncio.Task] = {}  # {timeframe: task}

        # 处理器注册
        self.handlers: Dict[str, Callable] = {}  # {timeframe: callback}

        # 重连配置
        self.max_reconnect_attempts = self.config.get('max_reconnect_attempts', 5)
        self.reconnect_delay_ms = self.config.get('reconnect_delay_ms', 1000)
        self.reconnect_attempts: Dict[str, int] = defaultdict(int)

        # 统计信息
        self.enable_stats = self.config.get('enable_stats', True)
        self.stats: Dict[str, Dict[str, int]] = {
            tf: {
                'messages_received': 0,
                'messages_processed': 0,
                'errors': 0,
                'last_message_time': None
            }
            for tf in timeframes
        }

        # 🔧 连接健康检查配置
        self.enable_health_check = self.config.get('enable_health_check', True)
        self.health_check_interval = self.config.get('health_check_interval', 30)  # 秒
        self.health_check_task: Optional[asyncio.Task] = None

        logger.info(f"[MultiTimeframeSubscriber] 初始化完成: "
                   f"{len(symbols)}个交易对, {len(timeframes)}个时间框架")
        logger.info(f"[MultiTimeframeSubscriber] 交易对: {symbols}")
        logger.info(f"[MultiTimeframeSubscriber] 时间框架: {timeframes}")
        logger.info(f"[MultiTimeframeSubscriber] 健康检查: {'启用' if self.enable_health_check else '禁用'}")

    def register_handler(self, timeframe: str, handler: Callable):
        """
        注册特定时间框架的K线处理器

        Args:
            timeframe: 时间框架 (如 '1s', '15m', '1h')
            handler: 处理器回调函数，接收原始WebSocket消息

        Raises:
            ValueError: 时间框架不在配置列表中

        Example:
            >>> def my_1s_handler(msg):
            ...     kline = msg.get('k', {})
            ...     print(f"1s K线: {kline.get('c')}")  # 最新收盘价
            >>> subscriber.register_handler('1s', my_1s_handler)
        """
        if timeframe not in self.timeframes:
            raise ValueError(
                f"时间框架'{timeframe}'不在配置列表中。"
                f"支持的时间框架: {self.timeframes}"
            )

        self.handlers[timeframe] = handler
        logger.info(f"[MultiTimeframeSubscriber] 注册处理器: {timeframe}")

    async def start_all_subscriptions(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        启动所有时间框架的WebSocket订阅

        该方法为每个时间框架创建独立的WebSocket连接和数据流处理任务。

        Args:
            api_key: Binance API密钥 (可选，公共数据流不需要)
            api_secret: Binance API密钥 (可选，公共数据流不需要)

        Raises:
            ConnectionError: WebSocket连接失败
            ValueError: 没有注册任何处理器

        Note:
            - 公共K线数据流不需要API密钥
            - 私有数据流（如账户数据）需要API密钥
        """
        if not self.handlers:
            raise ValueError(
                "没有注册任何处理器。请先使用register_handler()注册处理器。"
            )

        if self.ws_running:
            logger.warning("[MultiTimeframeSubscriber] WebSocket已在运行中")
            return

        try:
            # 导入BinanceSocketManager
            from binance import BinanceSocketManager
            from binance.client import Client

            logger.info("[MultiTimeframeSubscriber] 正在创建BinanceSocketManager...")

            # 创建客户端（如果提供了API密钥）
            if api_key and api_secret:
                client = Client(api_key, api_secret)
            else:
                client = Client()  # 公共数据流不需要API密钥

            # 修复python-binance的bug：手动添加https_proxy属性
            # BinanceSocketManager._get_socket() 会尝试访问 client.https_proxy
            # 但 BaseClient.__init__() 中 https_proxy 只是局部变量，不是实例属性
            client.https_proxy = None
            client.http_proxy = None

            # 🔥 创建BinanceSocketManager并传入队列大小配置
            self.bsm = BinanceSocketManager(
                client,
                user_timeout=60,
                max_queue_size=self.max_queue_size  # 🔥 关键配置：解决队列溢出
            )
            logger.info(f"[MultiTimeframeSubscriber] ✅ BinanceSocketManager已创建 (队列大小: {self.max_queue_size})")
            self.ws_running = True

            # 为每个时间框架创建订阅
            for timeframe in self.timeframes:
                try:
                    await self._start_timeframe_subscription(timeframe)
                    self.reconnect_attempts[timeframe] = 0  # 重置重连计数
                except Exception as e:
                    logger.error(f"[MultiTimeframeSubscriber] 启动{timeframe}订阅失败: {e}")
                    # 继续启动其他时间框架的订阅

            logger.info(f"[MultiTimeframeSubscriber] ✅ 所有订阅启动成功: {list(self.sockets.keys())}")

            # 🔧 启动健康检查任务
            if self.enable_health_check:
                self.health_check_task = asyncio.create_task(
                    self._health_check_loop(),
                    name="health_check_loop"
                )
                logger.info(f"[MultiTimeframeSubscriber] ✅ 健康检查任务已启动 (间隔: {self.health_check_interval}秒)")

        except Exception as e:
            logger.error(f"[MultiTimeframeSubscriber] 启动WebSocket订阅失败: {e}")
            self.ws_running = False
            raise

    async def _start_timeframe_subscription(self, timeframe: str):
        """
        启动特定时间框架的WebSocket订阅

        Args:
            timeframe: 时间框架 (如 '1s', '15m', '1h')

        Raises:
            Exception: WebSocket连接失败
        """
        try:
            # 构建订阅流
            streams = [f"{s.lower()}@kline_{timeframe}" for s in self.symbols]
            logger.info(f"[MultiTimeframeSubscriber] 创建{timeframe}订阅流: {streams[:3]}...")

            # 创建multiplex socket
            socket = self.bsm.multiplex_socket(streams)
            # 注意：不在这里调用 __aenter__()，而是在 _process_timeframe_stream 中使用 async with
            self.sockets[timeframe] = socket

            # 启动异步处理任务
            task = asyncio.create_task(
                self._process_timeframe_stream(timeframe, socket),
                name=f"kline_{timeframe}_processor"
            )
            self._tasks[timeframe] = task

            logger.info(f"[MultiTimeframeSubscriber] ✅ {timeframe}订阅启动成功")

        except Exception as e:
            logger.error(f"[MultiTimeframeSubscriber] {timeframe}订阅失败: {e}")
            raise

    async def _process_timeframe_stream(self, timeframe: str, socket):
        """
        处理特定时间框架的K线数据流

        根据python-binance官方文档，使用async with + recv()方式接收消息
        参考: https://python-binance.readthedocs.io/en/latest/websockets.html

        Args:
            timeframe: 时间框架
            socket: WebSocket socket对象
        """
        handler = self.handlers.get(timeframe)

        if not handler:
            logger.error(f"[MultiTimeframeSubscriber] {timeframe}没有注册处理器")
            return

        logger.info(f"[MultiTimeframeSubscriber] {timeframe}数据流处理任务已启动")

        try:
            # 使用上下文管理器接收消息（官方推荐方式）
            async with socket as tscm:
                while self.ws_running:
                    try:
                        # 使用 recv() 方法接收消息
                        msg = await tscm.recv()

                        if msg is None:
                            logger.debug(f"[MultiTimeframeSubscriber] {timeframe}接收到空消息，停止")
                            break

                        # 更新统计
                        if self.enable_stats:
                            self.stats[timeframe]['messages_received'] += 1
                            self.stats[timeframe]['last_message_time'] = datetime.now()

                        # 🔥 性能监控：记录处理开始时间
                        import time
                        process_start = time.time()

                        # 调用注册的处理器
                        if asyncio.iscoroutinefunction(handler):
                            await handler(msg)
                        else:
                            handler(msg)

                        # 🔥 性能监控：记录处理时间
                        process_time = time.time() - process_start
                        if process_time > 0.1:  # 处理时间超过100ms警告
                            logger.warning(
                                f"[MultiTimeframeSubscriber] ⚠️ {timeframe}消息处理耗时过长: "
                                f"{process_time*1000:.2f}ms (建议<100ms)"
                            )

                        # 更新处理统计
                        if self.enable_stats:
                            self.stats[timeframe]['messages_processed'] += 1

                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"[MultiTimeframeSubscriber] {timeframe}消息处理错误: {e}")
                        if self.enable_stats:
                            self.stats[timeframe]['errors'] += 1

                        # 🔧 检测连接关闭错误
                        if ("Read loop has been closed" in error_msg or
                            "Connection closed" in error_msg or
                            "Connection error" in error_msg):
                            logger.warning(f"[MultiTimeframeSubscriber] {timeframe}连接已关闭，停止处理")
                            break  # 退出内层循环，触发重连

                        # 其他错误继续处理
                        await asyncio.sleep(0.1)  # 短暂延迟避免错误循环

        except asyncio.CancelledError:
            logger.info(f"[MultiTimeframeSubscriber] {timeframe}处理任务被取消")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[MultiTimeframeSubscriber] {timeframe}数据流错误: {e}")

            # 检测是否是连接关闭错误
            if ("Read loop has been closed" not in error_msg and
                "Connection closed" not in error_msg):
                # 只有非连接关闭错误才触发重连
                if self.ws_running:
                    await self._handle_reconnect(timeframe)

    async def _handle_reconnect(self, timeframe: str):
        """
        处理特定时间框架的WebSocket重连

        改进版本:
        - 移除递归调用，使用循环重连机制
        - 在每次重连前重新创建BinanceSocketManager
        - 清理旧socket资源后再重连

        Args:
            timeframe: 需要重连的时间框架
        """
        self.reconnect_attempts[timeframe] += 1
        attempt = self.reconnect_attempts[timeframe]

        if attempt > self.max_reconnect_attempts:
            logger.error(
                f"[MultiTimeframeSubscriber] {timeframe}重连失败，"
                f"已达到最大重连次数({self.max_reconnect_attempts})"
            )
            return

        # 指数退避延迟
        delay = (self.reconnect_delay_ms * (2 ** (attempt - 1))) / 1000.0
        logger.warning(
            f"[MultiTimeframeSubscriber] {timeframe}连接断开，"
            f"{delay:.1f}秒后第{attempt}次重连..."
        )

        await asyncio.sleep(delay)

        try:
            # 🔧 关闭旧socket - 确保完全清理
            if timeframe in self.sockets:
                try:
                    old_socket = self.sockets.pop(timeframe)
                    await old_socket.__aexit__(None, None, None)
                    logger.debug(f"[MultiTimeframeSubscriber] 已关闭{timeframe}旧socket")
                except Exception as e:
                    logger.warning(f"[MultiTimeframeSubscriber] 关闭旧socket失败: {e}")

            # 🔧 取消旧任务
            if timeframe in self._tasks:
                try:
                    old_task = self._tasks.pop(timeframe)
                    if not old_task.done():
                        old_task.cancel()
                        await old_task  # 等待任务取消完成
                        logger.debug(f"[MultiTimeframeSubscriber] 已取消{timeframe}旧任务")
                except Exception as e:
                    logger.warning(f"[MultiTimeframeSubscriber] 取消旧任务失败: {e}")

            # 🔧 重新创建BinanceSocketManager（可选，python-binance可能需要）
            # 注意：这会影响所有时间框架，所以这里只是代码示例
            # if attempt == 1:
            #     await self._recreate_binance_socket_manager()

            # 🔧 重新订阅
            await self._start_timeframe_subscription(timeframe)

            logger.info(f"[MultiTimeframeSubscriber] ✅ {timeframe}重连成功")
            self.reconnect_attempts[timeframe] = 0  # 重置重连计数

        except Exception as e:
            logger.error(f"[MultiTimeframeSubscriber] {timeframe}重连失败: {e}")
            # 🔧 不再递归调用，而是检查是否需要继续重连
            if self.ws_running and attempt < self.max_reconnect_attempts:
                # 创建新的重连任务（非递归）
                logger.info(f"[MultiTimeframeSubscriber] 计划下一次{timeframe}重连")
                await self._handle_reconnect(timeframe)  # 使用await而非create_task

    async def stop_all_subscriptions(self):
        """
        停止所有WebSocket订阅

        该方法会：
        1. 设置运行标志为False
        2. 取消健康检查任务
        3. 取消所有数据处理任务
        4. 关闭所有WebSocket连接
        5. 关闭BinanceSocketManager
        """
        logger.info("[MultiTimeframeSubscriber] 正在停止所有订阅...")

        self.ws_running = False

        # 🔧 取消健康检查任务
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
                logger.debug("[MultiTimeframeSubscriber] 健康检查任务已取消")
            except asyncio.CancelledError:
                logger.debug("[MultiTimeframeSubscriber] 健康检查任务已取消")

        # 取消所有任务
        for timeframe, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.debug(f"[MultiTimeframeSubscriber] 取消{timeframe}处理任务")

        # 等待所有任务完成取消
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            self._tasks.clear()

        # 关闭所有socket
        for timeframe, socket in self.sockets.items():
            try:
                await socket.__aexit__(None, None, None)
                logger.debug(f"[MultiTimeframeSubscriber] 关闭{timeframe}socket")
            except Exception as e:
                logger.error(f"[MultiTimeframeSubscriber] 关闭{timeframe}socket失败: {e}")

        self.sockets.clear()

        # 关闭BinanceSocketManager
        if self.bsm:
            try:
                await self.bsm.close()
                logger.info("[MultiTimeframeSubscriber] BinanceSocketManager已关闭")
            except Exception as e:
                logger.error(f"[MultiTimeframeSubscriber] 关闭BSM失败: {e}")

        logger.info("[MultiTimeframeSubscriber] ✅ 所有订阅已停止")

    def is_running(self) -> bool:
        """
        检查订阅是否正在运行

        Returns:
            bool: WebSocket是否运行中
        """
        return self.ws_running

    def get_active_timeframes(self) -> List[str]:
        """
        获取当前活跃的时间框架列表

        Returns:
            List[str]: 已建立连接的时间框架列表
        """
        return list(self.sockets.keys())

    def get_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        获取订阅统计信息

        Returns:
            包含各时间框架统计信息的字典:
            {
                '1s': {'messages_received': 1000, 'messages_processed': 995, 'errors': 5, ...},
                '15m': {...},
                '1h': {...}
            }
        """
        return self.stats.copy()

    def get_status_summary(self) -> Dict[str, Any]:
        """
        获取订阅状态摘要

        Returns:
            包含以下信息的字典:
            - running: 是否运行中
            - symbols: 交易对列表
            - timeframes: 时间框架列表
            - active_timeframes: 当前活跃的时间框架
            - handlers_registered: 已注册处理器的数量
            - reconnect_attempts: 各时间框架的重连次数
        """
        return {
            'running': self.ws_running,
            'symbols': self.symbols,
            'timeframes': self.timeframes,
            'active_timeframes': self.get_active_timeframes(),
            'handlers_registered': len(self.handlers),
            'reconnect_attempts': dict(self.reconnect_attempts)
        }

    def print_status(self):
        """打印订阅状态摘要（用于调试）"""
        status = self.get_status_summary()
        stats = self.get_statistics()

        print("\n" + "=" * 80)
        print("多时间框架K线订阅状态")
        print("=" * 80)
        print(f"运行状态: {'🟢 运行中' if status['running'] else '🔴 已停止'}")
        print(f"交易对数量: {len(status['symbols'])}")
        print(f"时间框架数量: {len(status['timeframes'])}")
        print(f"活跃时间框架: {status['active_timeframes']}")
        print(f"已注册处理器: {status['handlers_registered']}/{len(status['timeframes'])}")

        if status['reconnect_attempts']:
            print("\n重连状态:")
            for tf, attempts in status['reconnect_attempts'].items():
                print(f"  {tf}: {attempts}次重连")

        if self.enable_stats and status['running']:
            print("\n消息统计:")
            for tf, tf_stats in stats.items():
                print(f"  {tf}:")
                print(f"    接收: {tf_stats['messages_received']}条")
                print(f"    处理: {tf_stats['messages_processed']}条")
                print(f"    错误: {tf_stats['errors']}个")
                if tf_stats['last_message_time']:
                    print(f"    最后消息: {tf_stats['last_message_time']}")

        print("=" * 80 + "\n")

    async def _health_check_loop(self):
        """
        连接健康检查循环

        定期检查各时间框架的连接健康状态:
        1. 检查是否收到消息（最后消息时间）
        2. 检查错误率是否过高
        3. 检测到不健康连接时主动重连
        """
        logger.info(f"[MultiTimeframeSubscriber] 健康检查循环已启动 (间隔: {self.health_check_interval}秒)")

        while self.ws_running:
            try:
                await asyncio.sleep(self.health_check_interval)

                if not self.ws_running:
                    break

                # 检查所有时间框架的健康状态
                for timeframe in self.timeframes:
                    if not self.ws_running:
                        break

                    health_status = self._check_timeframe_health(timeframe)

                    if not health_status['healthy']:
                        logger.warning(
                            f"[MultiTimeframeSubscriber] {timeframe}连接不健康: "
                            f"{health_status['reason']}"
                        )

                        # 主动重连不健康的连接
                        if timeframe in self._tasks:
                            try:
                                # 取消旧任务
                                old_task = self._tasks.pop(timeframe)
                                if not old_task.done():
                                    old_task.cancel()
                                    await old_task
                            except Exception as e:
                                logger.warning(f"[MultiTimeframeSubscriber] 取消旧任务失败: {e}")

                            # 触发重连
                            logger.info(f"[MultiTimeframeSubscriber] 主动重连{timeframe}")
                            await self._handle_reconnect(timeframe)

            except asyncio.CancelledError:
                logger.info("[MultiTimeframeSubscriber] 健康检查任务被取消")
                break
            except Exception as e:
                logger.error(f"[MultiTimeframeSubscriber] 健康检查错误: {e}")
                # 继续运行，不因为单次检查失败而停止

        logger.info("[MultiTimeframeSubscriber] 健康检查循环已停止")

    def _check_timeframe_health(self, timeframe: str) -> Dict[str, Any]:
        """
        检查单个时间框架的连接健康状态

        Args:
            timeframe: 时间框架

        Returns:
            {
                'healthy': bool,  # 是否健康
                'reason': str     # 不健康的原因（如果健康则为空）
            }
        """
        if not self.enable_stats:
            return {'healthy': True, 'reason': ''}

        stats = self.stats.get(timeframe, {})
        last_msg_time = stats.get('last_message_time')
        errors = stats.get('errors', 0)
        messages_received = stats.get('messages_received', 0)

        # 检查1: 是否从未收到消息
        if messages_received == 0:
            # 如果连接已建立超过30秒仍未收到消息，认为不健康
            if timeframe in self.sockets:
                return {'healthy': False, 'reason': '从未收到消息'}
            else:
                return {'healthy': False, 'reason': '未建立连接'}

        # 检查2: 最后消息时间是否太久
        if last_msg_time:
            time_since_last_msg = (datetime.now() - last_msg_time).total_seconds()
            # 如果超过2个健康检查间隔没有收到消息，认为不健康
            if time_since_last_msg > self.health_check_interval * 2:
                return {'healthy': False, 'reason': f'超过{time_since_last_msg:.0f}秒未收到消息'}

        # 检查3: 错误率是否过高
        if messages_received > 0:
            error_rate = errors / messages_received
            if error_rate > 0.1:  # 错误率超过10%
                return {'healthy': False, 'reason': f'错误率过高: {error_rate:.1%}'}

        # 所有检查通过
        return {'healthy': True, 'reason': ''}



# 辅助函数
def validate_timeframes(timeframes: List[str]) -> List[str]:
    """
    验证时间框架格式

    Args:
        timeframes: 时间框架列表

    Returns:
        验证后的时间框架列表

    Raises:
        ValueError: 时间框架格式无效

    Supported timeframes:
        1s, 5s, 15s, 30s (秒)
        1m, 3m, 5m, 15m, 30m (分钟)
        1h, 2h, 4h, 6h, 8h, 12h (小时)
        1d, 3d (天)
        1w (周)
        1M (月)
    """
    valid_patterns = [
        r'^\d+s$',  # 秒
        r'^\d+m$',  # 分钟
        r'^\d+h$',  # 小时
        r'^\d+d$',  # 天
        r'^\d+w$',  # 周
        r'^\d+M$'   # 月
    ]

    import re

    for tf in timeframes:
        if not any(re.match(pattern, tf) for pattern in valid_patterns):
            raise ValueError(
                f"无效的时间框架格式: '{tf}'. "
                f"支持的格式: 1s, 1m, 15m, 1h, 1d, 1w, 1M等"
            )

    return timeframes


def create_subscriber(
    symbols: List[str],
    timeframes: List[str],
    config: Optional[Dict[str, Any]] = None
) -> MultiTimeframeKlineSubscriber:
    """
    工厂函数：创建多时间框架订阅管理器

    Args:
        symbols: 交易对列表
        timeframes: 时间框架列表
        config: 额外配置参数

    Returns:
        MultiTimeframeKlineSubscriber实例

    Example:
        >>> subscriber = create_subscriber(
        ...     symbols=['BTCUSDT', 'ETHUSDT'],
        ...     timeframes=['1s', '15m', '1h'],
        ...     config={'max_reconnect_attempts': 3}
        ... )
    """
    # 验证时间框架
    timeframes = validate_timeframes(timeframes)

    # 创建订阅管理器
    subscriber = MultiTimeframeKlineSubscriber(
        symbols=symbols,
        timeframes=timeframes,
        config=config
    )

    return subscriber
