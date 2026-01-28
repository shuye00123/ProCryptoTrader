"""
统一数据提供者抽象层

该模块定义了数据提供者的统一接口，实现策略逻辑与数据获取的完全隔离。
支持回测模式（本地文件）和实时模式（WebSocket订阅）的无缝切换。

核心特性:
1. 数据源抽象: 策略不关心数据来源（文件/API/WebSocket）
2. 预热数据支持: 回测前自动获取历史数据用于指标计算
3. 统一接口: 回测和实时模式使用相同的方法签名
4. 最小侵入: 策略逻辑无需修改即可切换数据源

作者: Claude Code
创建时间: 2026-01-12
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Callable, Any
from pathlib import Path
import pandas as pd
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DataProviderInterface(ABC):
    """
    数据提供者统一接口抽象基类

    该接口定义了数据提供者的核心方法，所有具体实现（回测/实时）
    都必须实现这些方法，确保策略可以在不同数据源间无缝切换。
    """

    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        获取历史K线数据

        Args:
            symbol: 交易对符号 (如 'BTC/USDT' 或 'BTCUSDT')
            timeframe: 时间框架 (如 '1s', '1m', '15m', '1h', '1d')
            start_date: 开始日期 (可选, 格式: 'YYYY-MM-DD')
            end_date: 结束日期 (可选, 格式: 'YYYY-MM-DD')
            limit: 数据条数限制 (默认500条)

        Returns:
            包含OHLCV数据的DataFrame，索引为timestamp

        Raises:
            DataNotFoundError: 请求数据不存在
            DataValidationError: 数据格式错误
        """
        pass

    @abstractmethod
    async def subscribe_realtime(
        self,
        symbols: List[str],
        timeframes: List[str],
        callback_1s: Callable,
        callback_higher_tf: Callable
    ):
        """
        订阅实时K线数据

        Args:
            symbols: 交易对列表 (如 ['BTCUSDT', 'ETHUSDT'])
            timeframes: 时间框架列表 (如 ['1s', '15m', '1h'])
            callback_1s: 1秒K线数据回调函数
            callback_higher_tf: 更高时间框架K线数据回调函数 (15m, 1h等)

        Note:
            回测模式不支持此方法，会抛出NotImplementedError
        """
        pass

    @abstractmethod
    async def get_warmup_data(
        self,
        symbol: str,
        timeframe: str,
        warmup_periods: int = 200
    ) -> pd.DataFrame:
        """
        获取预热数据（回测开始前的历史数据）

        该方法用于在回测开始前获取一段历史数据，用于初始化技术指标。
        例如，如果要计算200周期的SMA，需要先获取200条历史数据。

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            warmup_periods: 预热周期数 (默认200条)

        Returns:
            包含预热数据的DataFrame

        Example:
            >>> warmup_data = await provider.get_warmup_data('BTC/USDT', '1h', 200)
            >>> # 使用warmup_data初始化技术指标
            >>> sma_200 = warmup_data['close'].rolling(200).mean().iloc[-1]
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查数据提供者是否可用

        Returns:
            bool: 数据提供者是否可用
        """
        pass


class BacktestDataProvider(DataProviderInterface):
    """
    回测模式数据提供者 - 从本地文件加载历史数据

    该实现使用FixedDataLoader从本地parquet文件加载OHLCV数据，
    支持时间范围过滤和数据验证。

    Attributes:
        data_dir: 数据文件目录路径
        data_loader: FixedDataLoader实例
        cache_enabled: 是否启用数据缓存
    """

    def __init__(
        self,
        data_dir: str = "data",
        cache_enabled: bool = True,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化回测数据提供者

        Args:
            data_dir: 数据文件目录路径 (默认'data')
            cache_enabled: 是否启用数据缓存 (默认True)
            config: 额外配置参数
        """
        self.data_dir = Path(data_dir)
        self.cache_enabled = cache_enabled
        self.config = config or {}
        self._data_cache: Dict[str, pd.DataFrame] = {}

        # 导入FixedDataLoader
        try:
            from scripts.fixed_data_loader import FixedDataLoader
            self.data_loader = FixedDataLoader(str(self.data_dir))
            logger.info(f"[BacktestDataProvider] 初始化成功，数据目录: {self.data_dir}")
        except ImportError as e:
            logger.error(f"[BacktestDataProvider] 导入FixedDataLoader失败: {e}")
            raise

    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        从本地parquet文件加载历史数据

        Args:
            symbol: 交易对符号 (如 'BTC/USDT')
            timeframe: 时间框架 (如 '1h', '1d')
            start_date: 开始日期 (格式: 'YYYY-MM-DD')
            end_date: 结束日期 (格式: 'YYYY-MM-DD')
            limit: 数据条数限制

        Returns:
            包含OHLCV数据的DataFrame

        Raises:
            DataNotFoundError: 数据文件不存在
            DataValidationError: 数据格式错误
        """
        try:
            # 检查缓存
            cache_key = f"{symbol}_{timeframe}_{start_date}_{end_date}_{limit}"
            if self.cache_enabled and cache_key in self._data_cache:
                logger.debug(f"[BacktestDataProvider] 缓存命中: {cache_key}")
                return self._data_cache[cache_key].copy()

            # 转换时间框架格式 (1h -> 1h, 1d -> 1d等)
            # FixedDataLoader可能使用特定格式，这里保持原样
            logger.debug(f"[BacktestDataProvider] 加载数据: {symbol} {timeframe} "
                        f"({start_date} - {end_date}), 限制{limit}条")

            # 调用FixedDataLoader加载数据
            df = self.data_loader.load_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )

            # 数据验证
            if df is None or df.empty:
                raise ValueError(f"数据为空: {symbol} {timeframe}")

            # 应用限制
            if limit and len(df) > limit:
                df = df.tail(limit).copy()

            # 确保索引是timestamp
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df.set_index('timestamp', inplace=True)
                else:
                    raise ValueError(f"数据缺少timestamp列或索引: {symbol} {timeframe}")

            # 数据完整性检查
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"缺少必需列: {missing_columns}")

            # 更新缓存
            if self.cache_enabled:
                self._data_cache[cache_key] = df.copy()

            logger.info(f"[BacktestDataProvider] 成功加载{len(df)}条数据: "
                       f"{symbol} {timeframe}")
            return df

        except Exception as e:
            logger.error(f"[BacktestDataProvider] 加载数据失败: {symbol} {timeframe}, "
                        f"错误: {e}")
            raise

    async def subscribe_realtime(
        self,
        symbols: List[str],
        timeframes: List[str],
        callback_1s: Callable,
        callback_higher_tf: Callable
    ):
        """
        回测模式不支持实时订阅

        Args:
            symbols: 交易对列表
            timeframes: 时间框架列表
            callback_1s: 1秒K线回调
            callback_higher_tf: 更高时间框架回调

        Raises:
            NotImplementedError: 回测模式不支持实时订阅
        """
        raise NotImplementedError(
            "回测模式不支持实时订阅。"
            "请使用实时模式（mode='live'或mode='paper'）进行WebSocket订阅。"
        )

    async def get_warmup_data(
        self,
        symbol: str,
        timeframe: str,
        warmup_periods: int = 200
    ) -> pd.DataFrame:
        """
        获取预热数据（回测开始前的历史数据）

        该方法从本地文件加载warmup_periods条历史数据，用于初始化技术指标。

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            warmup_periods: 预热周期数 (默认200条)

        Returns:
            包含预热数据的DataFrame

        Example:
            >>> warmup = await provider.get_warmup_data('BTC/USDT', '1h', 200)
            >>> initial_sma = warmup['close'].rolling(200).mean().iloc[-1]
        """
        try:
            logger.info(f"[BacktestDataProvider] 获取预热数据: {symbol} {timeframe}, "
                       f"{warmup_periods}条")

            # 计算结束日期（当前时间）
            end_date = datetime.now()

            # 估算开始日期（根据时间框架）
            timeframe_seconds = self._parse_timeframe_to_seconds(timeframe)
            start_date = end_date - timedelta(seconds=timeframe_seconds * warmup_periods)

            # 加载数据
            df = await self.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                limit=warmup_periods
            )

            logger.info(f"[BacktestDataProvider] 预热数据加载完成: {len(df)}条")
            return df

        except Exception as e:
            logger.error(f"[BacktestDataProvider] 获取预热数据失败: {e}")
            # 如果预热数据加载失败，返回空DataFrame（策略会处理）
            return pd.DataFrame()

    def is_available(self) -> bool:
        """
        检查数据提供者是否可用

        Returns:
            bool: 数据目录是否存在且可访问
        """
        return self.data_dir.exists() and self.data_dir.is_dir()

    def _parse_timeframe_to_seconds(self, timeframe: str) -> int:
        """
        解析时间框架字符串为秒数

        Args:
            timeframe: 时间框架字符串 (如 '1s', '15m', '1h', '1d')

        Returns:
            int: 对应的秒数

        Examples:
            >>> self._parse_timeframe_to_seconds('1s')
            1
            >>> self._parse_timeframe_to_seconds('15m')
            900
            >>> self._parse_timeframe_to_seconds('1h')
            3600
        """
        timeframe = timeframe.lower()
        if timeframe.endswith('s'):
            return int(timeframe[:-1])
        elif timeframe.endswith('m'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 3600
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 86400
        else:
            logger.warning(f"[BacktestDataProvider] 未知时间框架格式: {timeframe}")
            return 60  # 默认1分钟

    def clear_cache(self):
        """清空数据缓存"""
        self._data_cache.clear()
        logger.info("[BacktestDataProvider] 缓存已清空")

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            包含缓存统计的字典
        """
        total_items = len(self._data_cache)
        total_rows = sum(len(df) for df in self._data_cache.values())

        return {
            'cache_enabled': self.cache_enabled,
            'cached_items': total_items,
            'total_rows': total_rows,
            'cache_keys': list(self._data_cache.keys())
        }


class RealtimeDataProvider(DataProviderInterface):
    """
    实时模式数据提供者 - WebSocket订阅

    该实现使用MultiTimeframeKlineSubscriber管理多时间框架WebSocket订阅，
    支持实时K线数据接收和缓存。

    Attributes:
        symbols: 订阅的交易对列表
        timeframes: 订阅的时间框架列表
        subscriber: 多时间框架订阅管理器
        kline_cache: K线数据缓存 {symbol: {timeframe: deque}}
    """

    def __init__(
        self,
        symbols: List[str],
        timeframes: List[str],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化实时数据提供者

        Args:
            symbols: 交易对列表 (如 ['BTCUSDT', 'ETHUSDT'])
            timeframes: 时间框架列表 (如 ['1s', '15m', '1h'])
            config: 额外配置参数
        """
        from collections import deque

        self.symbols = symbols
        self.timeframes = timeframes
        self.config = config or {}

        # K线数据缓存（用于实时模式的技术指标计算）
        self.kline_cache: Dict[str, Dict[str, deque]] = {}
        self._max_cache_size = config.get('max_cache_size', 500) if config else 500

        # 初始化缓存
        for symbol in symbols:
            self.kline_cache[symbol] = {}
            for tf in timeframes:
                self.kline_cache[symbol][tf] = deque(maxlen=self._max_cache_size)

        # 导入MultiTimeframeKlineSubscriber (Phase 1已实现)
        from core.strategy.multi_timeframe_subscriber import MultiTimeframeKlineSubscriber

        # 创建多时间框架订阅管理器
        self.subscriber = MultiTimeframeKlineSubscriber(
            symbols=symbols,
            timeframes=timeframes,
            config=config
        )
        self._running = False

        logger.info(f"[RealtimeDataProvider] 初始化成功，交易对: {symbols}, "
                   f"时间框架: {timeframes}")

    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        从交易所API获取历史数据（用于初始化缓存）

        该方法从Binance REST API获取历史K线数据，用于实时模式启动时
        初始化技术指标缓存。

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            start_date: 开始日期 (可选)
            end_date: 结束日期 (可选)
            limit: 数据条数限制 (默认500)

        Returns:
            包含OHLCV数据的DataFrame

        Note:
            该方法将在Phase 4集成时实现Binance REST API调用
        """
        # Phase 4实现: 从Binance REST API获取历史数据
        # 当前返回空DataFrame，待Phase 4完成
        logger.warning(f"[RealtimeDataProvider] get_historical_data将在Phase 4实现")
        return pd.DataFrame()

    async def subscribe_realtime(
        self,
        symbols: List[str],
        timeframes: List[str],
        callback_1s: Callable,
        callback_higher_tf: Callable
    ):
        """
        启动WebSocket实时订阅

        该方法使用MultiTimeframeKlineSubscriber启动多时间框架WebSocket订阅。

        Args:
            symbols: 交易对列表
            timeframes: 时间框架列表
            callback_1s: 1秒K线数据回调函数
            callback_higher_tf: 更高时间框架K线数据回调函数

        Note:
            需要传入api_key和api_secret参数（如果订阅私有数据流）
        """
        if self.subscriber is None:
            logger.error("[RealtimeDataProvider] MultiTimeframeKlineSubscriber未初始化")
            raise RuntimeError("MultiTimeframeKlineSubscriber未正确初始化")

        # 注册处理器
        self.subscriber.register_handler('1s', callback_1s)
        for tf in timeframes[1:]:  # 15m, 1h等
            self.subscriber.register_handler(tf, callback_higher_tf)

        # 启动订阅
        await self.subscriber.start_all_subscriptions()
        self._running = True

        logger.info(f"[RealtimeDataProvider] WebSocket订阅启动成功: {timeframes}")

    async def get_warmup_data(
        self,
        symbol: str,
        timeframe: str,
        warmup_periods: int = 200
    ) -> pd.DataFrame:
        """
        实时模式从REST API获取预热数据

        该方法在实时模式启动时调用，从交易所API获取一段历史数据
        用于初始化技术指标缓存。

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            warmup_periods: 预热周期数 (默认200条)

        Returns:
            包含预热数据的DataFrame

        Note:
            该方法依赖get_historical_data实现（Phase 4完成）
        """
        logger.info(f"[RealtimeDataProvider] 获取预热数据: {symbol} {timeframe}, "
                   f"{warmup_periods}条")

        # 从REST API获取历史数据
        historical_data = await self.get_historical_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=warmup_periods
        )

        return historical_data

    def is_available(self) -> bool:
        """
        检查数据提供者是否可用

        Returns:
            bool: WebSocket连接是否运行中
        """
        return self._running and self.subscriber is not None

    def update_kline_cache(self, symbol: str, timeframe: str, kline_data: Dict):
        """
        更新K线缓存（由MultiTimeframeKlineSubscriber调用）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            kline_data: K线数据字典
        """
        if symbol in self.kline_cache and timeframe in self.kline_cache[symbol]:
            self.kline_cache[symbol][timeframe].append(kline_data)
            logger.debug(f"[RealtimeDataProvider] 更新K线缓存: {symbol} {timeframe}")

    def get_cached_klines(self, symbol: str, timeframe: str) -> List[Dict]:
        """
        获取缓存的K线数据

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            K线数据列表
        """
        if symbol not in self.kline_cache or timeframe not in self.kline_cache[symbol]:
            return []

        return list(self.kline_cache[symbol][timeframe])

    async def stop_subscription(self):
        """停止WebSocket订阅"""
        if self.subscriber and self._running:
            await self.subscriber.stop_all_subscriptions()
            self._running = False
            logger.info("[RealtimeDataProvider] WebSocket订阅已停止")


def create_data_provider(
    mode: str,
    symbols: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    data_dir: str = "data",
    config: Optional[Dict[str, Any]] = None
) -> DataProviderInterface:
    """
    工厂函数：根据模式创建数据提供者

    Args:
        mode: 运行模式 ('backtest', 'live', 'paper')
        symbols: 交易对列表 (实时模式需要)
        timeframes: 时间框架列表 (实时模式需要)
        data_dir: 数据目录 (回测模式)
        config: 额外配置参数

    Returns:
        DataProviderInterface实例

    Raises:
        ValueError: 不支持的模式

    Examples:
        >>> # 回测模式
        >>> provider = create_data_provider('backtest', data_dir='data')
        >>> data = await provider.get_historical_data('BTC/USDT', '1h')

        >>> # 实时模式
        >>> provider = create_data_provider(
        ...     'live',
        ...     symbols=['BTCUSDT', 'ETHUSDT'],
        ...     timeframes=['1s', '15m', '1h']
        ... )
        >>> await provider.subscribe_realtime(...)
    """
    mode = mode.lower()

    if mode == 'backtest':
        logger.info("[create_data_provider] 创建回测数据提供者")
        return BacktestDataProvider(data_dir=data_dir, config=config)

    elif mode in ['live', 'paper']:
        if not symbols or not timeframes:
            raise ValueError("实时模式需要提供symbols和timeframes参数")

        logger.info(f"[create_data_provider] 创建实时数据提供者: {mode}")
        return RealtimeDataProvider(
            symbols=symbols,
            timeframes=timeframes,
            config=config
        )

    else:
        raise ValueError(f"不支持的模式: {mode}. 支持的模式: 'backtest', 'live', 'paper'")
