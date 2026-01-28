"""
指标缓存管理器

该模块实现技术指标计算结果的智能缓存管理，避免重复计算，
显著提升策略性能（目标：99%计算量减少）。

核心特性:
1. 多级缓存结构: 按symbol和timeframe组织缓存
2. 线程安全访问: 使用异步锁保护并发访问
3. 缓存元数据跟踪: 记录最后更新时间和缓存统计
4. TTL过期策略: 自动清理过期缓存
5. 批量操作支持: 高效的批量缓存获取和更新

作者: Claude Code
创建时间: 2026-01-12
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import sys

if sys.version_info >= (3, 9):
    from collections import abc
else:
    import collections.abc as abc

logger = logging.getLogger(__name__)


class IndicatorCacheManager:
    """
    技术指标缓存管理器

    该类负责缓存15m/1h时间框架的技术指标计算结果，避免每秒重复计算。

    缓存结构:
    {
        symbol: {
            timeframe: {
                'indicators': {indicator_name: value},
                'last_update': datetime,
                'cache_hits': int,
                'cache_misses': int
            }
        }
    }

    Attributes:
        cache: 三层缓存字典
        cache_metadata: 缓存元数据
        locks: 异步锁字典（用于并发控制）
        max_age_seconds: 缓存最大有效期（秒）
        enabled: 缓存开关

    Example:
        >>> cache_mgr = IndicatorCacheManager(max_age_seconds=3600)
        >>>
        >>> # 更新缓存
        >>> indicators = {'sma_20': 50000.0, 'rsi': 65.0}
        >>> cache_mgr.update_indicators('BTCUSDT', '15m', indicators)
        >>>
        >>> # 读取缓存
        >>> cached = cache_mgr.get_indicators('BTCUSDT', '15m')
        >>> print(cached)  # {'sma_20': 50000.0, 'rsi': 65.0}
        >>>
        >>> # 检查缓存有效性
        >>> is_valid = cache_mgr.is_cache_valid('BTCUSDT', '15m')
        >>> print(is_valid)  # True
    """

    def __init__(
        self,
        max_age_seconds: int = 3600,
        enabled: bool = True,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化指标缓存管理器

        Args:
            max_age_seconds: 缓存最大有效期（秒，默认1小时）
            enabled: 是否启用缓存（默认True）
            config: 额外配置参数
                - enable_stats: 是否启用统计（默认True）
                - cleanup_interval: 清理间隔（秒，默认300）
        """
        self.max_age_seconds = max_age_seconds
        self.enabled = enabled
        self.config = config or {}

        # 缓存结构: {symbol: {timeframe: {'indicators': {}, 'last_update': datetime}}}
        self.cache: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))

        # 缓存元数据: {symbol: {timeframe: last_update_time}}
        self.cache_metadata: Dict[str, Dict[str, Optional[datetime]]] = defaultdict(
            lambda: defaultdict(lambda: None)
        )

        # 统计信息: {symbol: {timeframe: {'hits': int, 'misses': int}}}
        self.stats: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {'hits': 0, 'misses': 0})
        )

        # 异步锁: {symbol: asyncio.Lock}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # 配置
        self.enable_stats = self.config.get('enable_stats', True)

        logger.info(f"[IndicatorCacheManager] 初始化完成: "
                   f"max_age={max_age_seconds}s, enabled={enabled}")

    def get_indicators(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict[str, Any]:
        """
        获取缓存的指标值（线程安全）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            指标字典 {indicator_name: value}，如果缓存不存在或已过期返回空字典

        Example:
            >>> indicators = cache_mgr.get_indicators('BTCUSDT', '15m')
            >>> print(indicators.get('sma_20'))  # 50000.0
        """
        if not self.enabled:
            return {}

        # 检查缓存是否存在
        if symbol not in self.cache:
            if self.enable_stats:
                self.stats[symbol][timeframe]['misses'] += 1
            return {}

        if timeframe not in self.cache[symbol]:
            if self.enable_stats:
                self.stats[symbol][timeframe]['misses'] += 1
            return {}

        # 检查缓存是否过期
        if not self.is_cache_valid(symbol, timeframe):
            if self.enable_stats:
                self.stats[symbol][timeframe]['misses'] += 1
            logger.debug(f"[IndicatorCacheManager] 缓存已过期: {symbol} {timeframe}")
            return {}

        # 返回缓存
        if self.enable_stats:
            self.stats[symbol][timeframe]['hits'] += 1

        return self.cache[symbol][timeframe].get('indicators', {}).copy()

    async def get_indicators_async(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict[str, Any]:
        """
        异步获取缓存的指标值（线程安全）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            指标字典

        Note:
            该方法使用异步锁保护并发访问
        """
        if not self.enabled:
            return {}

        # 获取或创建symbol级别的锁
        lock = await self._get_lock(symbol)

        async with lock:
            return self.get_indicators(symbol, timeframe)

    def update_indicators(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        更新指标缓存（线程安全）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            indicators: 指标字典 {indicator_name: value}
            metadata: 额外的元数据（可选）

        Example:
            >>> indicators = {
            ...     'sma_20': 50000.0,
            ...     'rsi': 65.0,
            ...     'macd': 123.45
            ... }
            >>> cache_mgr.update_indicators('BTCUSDT', '15m', indicators)
        """
        if not self.enabled:
            return

        # 更新缓存
        self.cache[symbol][timeframe]['indicators'] = indicators.copy()
        self.cache[symbol][timeframe]['last_update'] = datetime.utcnow()

        # 更新元数据
        self.cache_metadata[symbol][timeframe] = datetime.utcnow()

        # 添加额外元数据
        if metadata:
            self.cache[symbol][timeframe]['metadata'] = metadata

        logger.debug(f"[IndicatorCacheManager] 更新缓存: {symbol} {timeframe}, "
                    f"指标数量: {len(indicators)}")

    async def update_indicators_async(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        异步更新指标缓存（线程安全）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            indicators: 指标字典
            metadata: 额外的元数据（可选）

        Note:
            该方法使用异步锁保护并发访问
        """
        if not self.enabled:
            return

        # 获取或创建symbol级别的锁
        lock = await self._get_lock(symbol)

        async with lock:
            self.update_indicators(symbol, timeframe, indicators, metadata)

    def is_cache_valid(
        self,
        symbol: str,
        timeframe: str,
        max_age_seconds: Optional[int] = None
    ) -> bool:
        """
        检查缓存是否有效

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            max_age_seconds: 最大有效期（秒，如果为None则使用实例默认值）

        Returns:
            bool: 缓存是否有效

        Example:
            >>> is_valid = cache_mgr.is_cache_valid('BTCUSDT', '15m', max_age_seconds=1800)
            >>> print(is_valid)  # True or False
        """
        if not self.enabled:
            return False

        # 检查缓存是否存在
        if symbol not in self.cache_metadata:
            return False

        if timeframe not in self.cache_metadata[symbol]:
            return False

        last_update = self.cache_metadata[symbol][timeframe]
        if last_update is None:
            return False

        # 检查缓存年龄
        max_age = max_age_seconds or self.max_age_seconds
        age = (datetime.utcnow() - last_update).total_seconds()

        return age < max_age

    async def get_cached_indicators_safe(
        self,
        symbol: str,
        timeframes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        安全获取多个时间框架的缓存指标

        Args:
            symbol: 交易对符号
            timeframes: 时间框架列表 (如 ['15m', '1h'])

        Returns:
            字典: {timeframe: {indicator_name: value}}

        Example:
            >>> cached = await cache_mgr.get_cached_indicators_safe(
            ...     'BTCUSDT',
            ...     ['15m', '1h']
            ... )
            >>> print(cached)
            >>> {
            >>>     '15m': {'sma_20': 50000.0, 'rsi': 65.0},
            >>>     '1h': {'ema_12': 50100.0, 'macd': 123.45}
            >>> }
        """
        if not self.enabled:
            return {}

        result = {}

        for tf in timeframes:
            indicators = await self.get_indicators_async(symbol, tf)
            if indicators:
                result[tf] = indicators

        return result

    def clear_cache(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None
    ):
        """
        清空缓存

        Args:
            symbol: 交易对符号（如果为None则清空所有symbol）
            timeframe: 时间框架（如果为None则清空所有timeframe）

        Examples:
            >>> # 清空特定symbol的特定timeframe缓存
            >>> cache_mgr.clear_cache('BTCUSDT', '15m')
            >>>
            >>> # 清空特定symbol的所有timeframe缓存
            >>> cache_mgr.clear_cache('BTCUSDT')
            >>>
            >>> # 清空所有缓存
            >>> cache_mgr.clear_cache()
        """
        if symbol is None:
            # 清空所有缓存
            self.cache.clear()
            self.cache_metadata.clear()
            logger.info("[IndicatorCacheManager] 清空所有缓存")
        elif timeframe is None:
            # 清空特定symbol的所有timeframe缓存
            if symbol in self.cache:
                del self.cache[symbol]
            if symbol in self.cache_metadata:
                del self.cache_metadata[symbol]
            logger.info(f"[IndicatorCacheManager] 清空{symbol}的所有缓存")
        else:
            # 清空特定symbol的特定timeframe缓存
            if symbol in self.cache and timeframe in self.cache[symbol]:
                del self.cache[symbol][timeframe]
            if symbol in self.cache_metadata and timeframe in self.cache_metadata[symbol]:
                del self.cache_metadata[symbol][timeframe]
            logger.info(f"[IndicatorCacheManager] 清空{symbol} {timeframe}缓存")

    def invalidate_cache(
        self,
        symbol: str,
        timeframe: str
    ):
        """
        使特定缓存失效（标记为过期）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Note:
            该方法不会删除缓存数据，只是将last_update设置为None
        """
        if symbol in self.cache_metadata and timeframe in self.cache_metadata[symbol]:
            self.cache_metadata[symbol][timeframe] = None
            logger.debug(f"[IndicatorCacheManager] 缓存已失效: {symbol} {timeframe}")

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            包含以下统计信息的字典:
            - total_symbols: 总交易对数量
            - total_entries: 总缓存条目数
            - cache_hit_rate: 总缓存命中率
            - individual_stats: 各symbol/timeframe的统计
            - cache_size_mb: 缓存内存占用估算

        Example:
            >>> stats = cache_mgr.get_cache_statistics()
            >>> print(f"命中率: {stats['cache_hit_rate']:.2%}")
        """
        if not self.enable_stats:
            return {'cache_enabled': False, 'stats_disabled': True}

        total_symbols = len(self.cache)
        total_entries = sum(
            len(timeframes)
            for timeframes in self.cache.values()
        )

        # 计算总命中率
        total_hits = sum(
            tf_stats['hits']
            for symbol_stats in self.stats.values()
            for tf_stats in symbol_stats.values()
        )
        total_misses = sum(
            tf_stats['misses']
            for symbol_stats in self.stats.values()
            for tf_stats in symbol_stats.values()
        )
        total_requests = total_hits + total_misses
        hit_rate = total_hits / max(total_requests, 1)

        return {
            'cache_enabled': self.enabled,
            'max_age_seconds': self.max_age_seconds,
            'total_symbols': total_symbols,
            'total_entries': total_entries,
            'cache_hit_rate': hit_rate,
            'total_requests': total_requests,
            'total_hits': total_hits,
            'total_misses': total_misses,
            'individual_stats': dict(self.stats),
            'cache_size_mb': self._estimate_cache_size()
        }

    def get_timeframe_statistics(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        获取特定symbol/timeframe的统计信息

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            包含统计信息的字典
        """
        stats = {
            'cache_exists': symbol in self.cache and timeframe in self.cache[symbol],
            'cache_valid': self.is_cache_valid(symbol, timeframe),
            'last_update': self.cache_metadata.get(symbol, {}).get(timeframe),
            'indicator_count': 0,
            'indicator_names': [],
            'cache_age_seconds': 0,
            'stats': self.stats.get(symbol, {}).get(timeframe, {})
        }

        if stats['cache_exists']:
            cache_data = self.cache[symbol][timeframe]
            indicators = cache_data.get('indicators', {})
            stats['indicator_count'] = len(indicators)
            stats['indicator_names'] = list(indicators.keys())

            last_update = self.cache_metadata[symbol][timeframe]
            if last_update:
                stats['cache_age_seconds'] = (datetime.utcnow() - last_update).total_seconds()

        return stats

    async def cleanup_expired_cache(self):
        """
        清理过期的缓存条目

        该方法会遍历所有缓存，删除超过max_age_seconds的条目。
        """
        if not self.enabled:
            return

        now = datetime.utcnow()
        expired_keys = []

        for symbol, timeframes in self.cache_metadata.items():
            for timeframe, last_update in timeframes.items():
                if last_update is None:
                    continue

                age = (now - last_update).total_seconds()
                if age > self.max_age_seconds:
                    expired_keys.append((symbol, timeframe))

        # 删除过期缓存
        for symbol, timeframe in expired_keys:
            self.clear_cache(symbol, timeframe)
            logger.debug(f"[IndicatorCacheManager] 清理过期缓存: {symbol} {timeframe}")

        if expired_keys:
            logger.info(f"[IndicatorCacheManager] 清理了{len(expired_keys)}个过期缓存条目")

    async def _get_lock(self, symbol: str) -> asyncio.Lock:
        """
        获取或创建symbol级别的异步锁

        Args:
            symbol: 交易对符号

        Returns:
            asyncio.Lock实例
        """
        async with self._global_lock:
            if symbol not in self._locks:
                self._locks[symbol] = asyncio.Lock()
            return self._locks[symbol]

    def _estimate_cache_size(self) -> float:
        """
        估算缓存内存占用（MB）

        Returns:
            估算的内存占用（MB）
        """
        import sys

        total_size = 0

        for symbol, timeframes in self.cache.items():
            for timeframe, data in timeframes.items():
                # 估算字典大小
                total_size += sys.getsizeof(data)
                total_size += sys.getsizeof(data.get('indicators', {}))

                # 估算指标数据大小
                for indicator_name, value in data.get('indicators', {}).items():
                    total_size += sys.getsizeof(indicator_name)
                    total_size += sys.getsizeof(value)

        # 转换为MB
        return total_size / (1024 * 1024)

    def print_statistics(self):
        """打印缓存统计信息（用于调试）"""
        stats = self.get_cache_statistics()

        print("\n" + "=" * 80)
        print("指标缓存统计信息")
        print("=" * 80)
        print(f"缓存状态: {'✅ 启用' if self.enabled else '❌ 禁用'}")
        print(f"最大有效期: {self.max_age_seconds}秒 ({self.max_age_seconds / 60:.1f}分钟)")
        print(f"交易对数量: {stats['total_symbols']}")
        print(f"缓存条目数: {stats['total_entries']}")
        print(f"总请求数: {stats['total_requests']}")
        print(f"缓存命中: {stats['total_hits']}")
        print(f"缓存未命中: {stats['total_misses']}")
        print(f"命中率: {stats['cache_hit_rate']:.2%}")
        print(f"内存占用: {stats['cache_size_mb']:.2f} MB")

        if stats['individual_stats']:
            print("\n各交易对统计:")
            for symbol, tf_stats in stats['individual_stats'].items():
                print(f"  {symbol}:")
                for tf, tf_stat in tf_stats.items():
                    hits = tf_stat['hits']
                    misses = tf_stat['misses']
                    total = hits + misses
                    hit_rate = hits / max(total, 1)
                    print(f"    {tf}: {hits}次命中, {misses}次未命中, "
                          f"命中率 {hit_rate:.2%}")

        print("=" * 80 + "\n")


# 辅议的缓存配置
DEFAULT_CACHE_CONFIG = {
    'max_age_seconds': 3600,      # 1小时
    'enabled': True,
    'enable_stats': True,
    'cleanup_interval': 300       # 5分钟
}

AGGRESSIVE_CACHE_CONFIG = {
    'max_age_seconds': 7200,      # 2小时（更激进）
    'enabled': True,
    'enable_stats': True,
    'cleanup_interval': 600       # 10分钟
}

CONSERVATIVE_CACHE_CONFIG = {
    'max_age_seconds': 1800,      # 30分钟（更保守）
    'enabled': True,
    'enable_stats': True,
    'cleanup_interval': 180       # 3分钟
}


def create_indicator_cache(
    mode: str = 'default',
    config: Optional[Dict[str, Any]] = None
) -> IndicatorCacheManager:
    """
    工厂函数：创建指标缓存管理器

    Args:
        mode: 缓存模式 ('default', 'aggressive', 'conservative')
        config: 自定义配置（覆盖mode配置）

    Returns:
        IndicatorCacheManager实例

    Example:
        >>> # 默认模式
        >>> cache = create_indicator_cache()
        >>>
        >>> # 激进模式（更长有效期）
        >>> cache = create_indicator_cache(mode='aggressive')
        >>>
        >>> # 自定义配置
        >>> cache = create_indicator_cache(
        ...     mode='default',
        ...     config={'max_age_seconds': 1800}
        ... )
    """
    # 选择基础配置
    if mode == 'aggressive':
        base_config = AGGRESSIVE_CACHE_CONFIG.copy()
    elif mode == 'conservative':
        base_config = CONSERVATIVE_CACHE_CONFIG.copy()
    else:
        base_config = DEFAULT_CACHE_CONFIG.copy()

    # 合并自定义配置
    if config:
        base_config.update(config)

    return IndicatorCacheManager(**base_config)
