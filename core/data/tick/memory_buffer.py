"""
内存缓冲管理器

管理tick数据的内存缓冲，实现多级缓存策略和自动清理功能。
"""

import asyncio
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Deque, Optional, Set
import logging
import psutil
import gc

from ..websocket_client import TickerData
from .config_models import BufferConfig

logger = logging.getLogger(__name__)


class MemoryBuffer:
    """tick数据内存缓冲管理器

    提供高效的内存缓冲管理，支持多交易对并发缓冲和自动清理。
    """

    def __init__(self, config: BufferConfig):
        self.config = config
        self._lock = threading.RLock()

        # 按交易对分组的缓冲区
        self._buffers: Dict[str, Deque[TickerData]] = defaultdict(
            lambda: deque(maxlen=config.max_ticks_per_symbol)
        )

        # 内存使用监控
        self._memory_stats = {
            'total_ticks': 0,
            'total_memory_mb': 0.0,
            'last_cleanup_time': 0,
            'cleanup_count': 0
        }

        # LRU缓存管理
        self._access_times: Dict[str, float] = defaultdict(time.time)
        self._last_access_cleanup = time.time()

        logger.info(f"MemoryBuffer初始化完成 - "
                   f"最大缓冲: {config.max_size_mb}MB, "
                   f"最大tick数/交易对: {config.max_ticks_per_symbol}")

    def add_tick(self, tick_data: TickerData) -> bool:
        """添加tick数据到缓冲区

        Args:
            tick_data: tick数据

        Returns:
            是否成功添加
        """
        try:
            with self._lock:
                # 检查内存限制
                if self._should_trigger_cleanup():
                    self._cleanup_buffers()

                # 添加数据到对应交易对缓冲区
                symbol = tick_data.symbol
                self._buffers[symbol].append(tick_data)

                # 更新访问时间
                self._access_times[symbol] = time.time()

                # 更新统计信息
                self._memory_stats['total_ticks'] += 1

                # 定期更新内存使用统计
                if time.time() - self._memory_stats['last_cleanup_time'] > 10:
                    self._update_memory_stats()

            return True

        except Exception as e:
            logger.error(f"添加tick数据失败: {e}")
            return False

    def get_ticks(self, symbol: str, limit: Optional[int] = None) -> List[TickerData]:
        """获取指定交易对的tick数据

        Args:
            symbol: 交易对符号
            limit: 最大返回数量，None表示返回全部

        Returns:
            tick数据列表
        """
        try:
            with self._lock:
                buffer = self._buffers.get(symbol, deque())
                if limit is None:
                    result = list(buffer)
                else:
                    result = list(buffer)[-limit:]

                # 更新访问时间
                if result:
                    self._access_times[symbol] = time.time()

                return result

        except Exception as e:
            logger.error(f"获取tick数据失败: {e}")
            return []

    def get_all_ticks(self) -> Dict[str, List[TickerData]]:
        """获取所有缓冲区的tick数据

        Returns:
            按交易对分组的tick数据字典
        """
        try:
            with self._lock:
                result = {}
                for symbol, buffer in self._buffers.items():
                    if buffer:  # 只返回非空缓冲区
                        result[symbol] = list(buffer)
                        self._access_times[symbol] = time.time()
                return result

        except Exception as e:
            logger.error(f"获取所有tick数据失败: {e}")
            return {}

    def clear_symbol(self, symbol: str) -> int:
        """清空指定交易对的缓冲区

        Args:
            symbol: 交易对符号

        Returns:
            清除的tick数量
        """
        try:
            with self._lock:
                buffer = self._buffers.get(symbol, deque())
                count = len(buffer)
                buffer.clear()

                if symbol in self._access_times:
                    del self._access_times[symbol]

                self._memory_stats['total_ticks'] -= count
                logger.debug(f"清空交易对 {symbol} 的缓冲区，清除 {count} 条tick数据")
                return count

        except Exception as e:
            logger.error(f"清空交易对 {symbol} 缓冲区失败: {e}")
            return 0

    def clear_all(self) -> int:
        """清空所有缓冲区

        Returns:
            清除的tick总数
        """
        try:
            with self._lock:
                total_count = 0
                for symbol in list(self._buffers.keys()):
                    total_count += self.clear_symbol(symbol)

                # 强制垃圾回收
                gc.collect()

                logger.info(f"清空所有缓冲区，共清除 {total_count} 条tick数据")
                return total_count

        except Exception as e:
            logger.error(f"清空所有缓冲区失败: {e}")
            return 0

    def _should_trigger_cleanup(self) -> bool:
        """判断是否应该触发清理

        Returns:
            是否需要清理
        """
        # 检查内存使用率
        current_memory_mb = self._get_memory_usage_mb()
        if current_memory_mb > self.config.max_size_mb * self.config.cleanup_ratio:
            return True

        # 检查时间间隔
        if time.time() - self._memory_stats['last_cleanup_time'] > 300:  # 5分钟
            return True

        return False

    def _cleanup_buffers(self):
        """清理缓冲区，释放内存"""
        try:
            start_time = time.time()
            cleared_count = 0

            # 获取当前内存使用情况
            current_memory_mb = self._get_memory_usage_mb()

            if current_memory_mb > self.config.max_size_mb:
                # 基于LRU清理最少使用的交易对数据
                sorted_symbols = sorted(
                    self._access_times.items(),
                    key=lambda x: x[1]
                )

                # 清理最旧的交易对数据，直到内存使用降到目标值
                target_memory_mb = self.config.max_size_mb * 0.7
                for symbol, _ in sorted_symbols:
                    cleared_count += self.clear_symbol(symbol)
                    current_memory_mb = self._get_memory_usage_mb()
                    if current_memory_mb <= target_memory_mb:
                        break

            # 清理过期的访问时间记录
            self._cleanup_access_times()

            # 更新统计信息
            self._memory_stats['last_cleanup_time'] = time.time()
            self._memory_stats['cleanup_count'] += 1
            self._update_memory_stats()

            cleanup_time = time.time() - start_time
            logger.info(f"缓冲区清理完成 - 耗时: {cleanup_time:.3f}s, "
                       f"清除: {cleared_count}条数据, "
                       f"当前内存: {current_memory_mb:.1f}MB")

        except Exception as e:
            logger.error(f"缓冲区清理失败: {e}")

    def _cleanup_access_times(self):
        """清理过期的访问时间记录"""
        try:
            current_time = time.time()
            if current_time - self._last_access_cleanup > 600:  # 10分钟
                # 清理超过1小时未访问的记录
                cutoff_time = current_time - 3600
                expired_symbols = [
                    symbol for symbol, access_time in self._access_times.items()
                    if access_time < cutoff_time
                ]

                for symbol in expired_symbols:
                    del self._access_times[symbol]

                self._last_access_cleanup = current_time
                logger.debug(f"清理过期访问时间记录: {len(expired_symbols)}个")

        except Exception as e:
            logger.error(f"清理访问时间记录失败: {e}")

    def _get_memory_usage_mb(self) -> float:
        """获取当前内存使用量（MB）

        Returns:
            内存使用量（MB）
        """
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024

        except Exception:
            return 0.0

    def _update_memory_stats(self):
        """更新内存使用统计"""
        try:
            self._memory_stats['total_memory_mb'] = self._get_memory_usage_mb()
            self._memory_stats['total_ticks'] = sum(
                len(buffer) for buffer in self._buffers.values()
            )

        except Exception as e:
            logger.error(f"更新内存统计失败: {e}")

    def get_stats(self) -> Dict[str, any]:
        """获取缓冲区统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            self._update_memory_stats()

            symbol_counts = {
                symbol: len(buffer) for symbol, buffer in self._buffers.items() if buffer
            }

            # 计算实际的内存使用率（基于进程内存，不是缓冲大小）
            process_memory_mb = self._get_memory_usage_mb()
            memory_usage_percent = (process_memory_mb / self.config.max_size_mb) * 100 if self.config.max_size_mb > 0 else 0

            return {
                **self._memory_stats,
                'symbol_count': len(symbol_counts),
                'symbol_ticks': symbol_counts,
                'memory_usage_percent': memory_usage_percent,
                'process_memory_mb': process_memory_mb
            }

    def get_buffer_status(self, symbol: str) -> Dict[str, any]:
        """获取指定交易对的缓冲区状态

        Args:
            symbol: 交易对符号

        Returns:
            缓冲区状态信息
        """
        with self._lock:
            buffer = self._buffers.get(symbol, deque())
            last_access = self._access_times.get(symbol, 0)

            # 计算时间范围
            timestamps = [tick.event_time for tick in buffer] if buffer else []
            time_range = {}
            if timestamps:
                time_range = {
                    'start_time': min(timestamps),
                    'end_time': max(timestamps),
                    'duration_seconds': max(timestamps) - min(timestamps)
                }

            return {
                'symbol': symbol,
                'tick_count': len(buffer),
                'max_capacity': self.config.max_ticks_per_symbol,
                'utilization_percent': (len(buffer) / self.config.max_ticks_per_symbol) * 100,
                'last_access_time': last_access,
                'last_access_datetime': (
                    datetime.fromtimestamp(last_access, tz=timezone.utc).isoformat()
                    if last_access > 0 else None
                ),
                'time_range': time_range
            }

    def health_check(self) -> Dict[str, any]:
        """健康检查

        Returns:
            健康状态信息
        """
        try:
            stats = self.get_stats()
            memory_usage_percent = stats.get('memory_usage_percent', 0)

            # 判断健康状态
            if memory_usage_percent > 90:
                status = "critical"
                message = "内存使用率过高，需要立即清理"
            elif memory_usage_percent > 80:
                status = "warning"
                message = "内存使用率较高，建议清理"
            else:
                status = "healthy"
                message = "运行正常"

            return {
                'status': status,
                'message': message,
                'memory_usage_percent': memory_usage_percent,
                'total_ticks': stats.get('total_ticks', 0),
                'symbol_count': stats.get('symbol_count', 0),
                'cleanup_count': stats.get('cleanup_count', 0),
                'last_cleanup_time': stats.get('last_cleanup_time', 0)
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'健康检查失败: {e}',
                'memory_usage_percent': 0,
                'total_ticks': 0,
                'symbol_count': 0,
                'cleanup_count': 0,
                'last_cleanup_time': 0
            }