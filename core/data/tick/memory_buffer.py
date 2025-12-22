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
import sys

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

        # 改进的内存使用监控
        self._memory_stats = {
            'total_ticks': 0,
            'total_memory_mb': 0.0,
            'last_cleanup_time': 0,
            'cleanup_count': 0,
            'last_save_trigger': 0,  # 最后一次触发保存的时间
            'save_debounce_cooldown': 30,  # 防抖冷却时间（秒）
        }

        # LRU缓存管理
        self._access_times: Dict[str, float] = defaultdict(time.time)
        self._last_access_cleanup = time.time()

        # 获取系统总内存（用于智能阈值调整）
        try:
            self.system_memory_gb = psutil.virtual_memory().total / (1024**3)
            # 针对4GB服务器优化阈值
            if self.system_memory_gb < 6:
                self.process_memory_warning_threshold = 70  # 进程内存告警阈值
                self.process_memory_critical_threshold = 80  # 进程内存危险阈值
            else:
                self.process_memory_warning_threshold = 80
                self.process_memory_critical_threshold = 90
        except Exception:
            self.system_memory_gb = 4.0  # 默认值
            self.process_memory_warning_threshold = 70
            self.process_memory_critical_threshold = 80

        logger.info(f"MemoryBuffer初始化完成 - "
                   f"最大缓冲: {config.max_size_mb}MB, "
                   f"最大tick数/交易对: {config.max_ticks_per_symbol}, "
                   f"系统内存: {self.system_memory_gb:.1f}GB, "
                   f"进程内存阈值: {self.process_memory_warning_threshold}%/{self.process_memory_critical_threshold}%")

    def add_tick(self, tick_data: TickerData) -> bool:
        """添加tick数据到缓冲区

        Args:
            tick_data: tick数据

        Returns:
            是否成功添加
        """
        try:
            with self._lock:
                # 智能内存检查和清理触发
                cleanup_result = self._check_and_trigger_cleanup()
                if cleanup_result['should_save']:
                    # 返回需要外部保存的信号，而不是在add_tick内部触发
                    self._memory_stats['last_save_trigger'] = time.time()
                    logger.info(f"内存告警触发 - 进程内存: {cleanup_result['process_memory_percent']:.1f}%, "
                               f"建议触发保存清理")

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

    def _check_and_trigger_cleanup(self) -> Dict[str, any]:
        """智能内存检查和清理触发判断

        Returns:
            判断结果字典，包含是否需要保存、清理等信息
        """
        current_time = time.time()
        result = {
            'should_save': False,
            'should_cleanup': False,
            'process_memory_percent': 0,
            'buffer_memory_percent': 0,
            'reason': ''
        }

        try:
            # 获取进程内存使用率（更准确的监控）
            process_memory_mb = self._get_process_memory_mb()
            system_memory_mb = psutil.virtual_memory().total / (1024 * 1024)
            process_memory_percent = (process_memory_mb / system_memory_mb) * 100
            result['process_memory_percent'] = process_memory_percent

            # 获取缓冲区内存使用率
            buffer_memory_mb = self._get_memory_usage_mb()
            buffer_memory_percent = (buffer_memory_mb / self.config.max_size_mb) * 100
            result['buffer_memory_percent'] = buffer_memory_percent

            # 防抖机制检查
            time_since_last_save = current_time - self._memory_stats['last_save_trigger']
            if time_since_last_save < self._memory_stats['save_debounce_cooldown']:
                result['reason'] = f"防抖冷却中 (剩余{self._memory_stats['save_debounce_cooldown'] - time_since_last_save:.0f}秒)"
                return result

            # 分级判断逻辑
            # 1. 优先检查进程内存（更准确）
            if process_memory_percent > self.process_memory_critical_threshold:
                result['should_save'] = True
                result['should_cleanup'] = True
                result['reason'] = f"进程内存危险 ({process_memory_percent:.1f}% > {self.process_memory_critical_threshold}%)"
                return result

            if process_memory_percent > self.process_memory_warning_threshold:
                result['should_save'] = True
                result['reason'] = f"进程内存告警 ({process_memory_percent:.1f}% > {self.process_memory_warning_threshold}%)"
                return result

            # 2. 检查缓冲区内存（备用指标）
            if buffer_memory_percent > 85:  # 提高阈值，避免过于敏感
                result['should_save'] = True
                result['reason'] = f"缓冲区内存过高 ({buffer_memory_percent:.1f}% > 85%)"
                return result

            # 3. 时间触发清理（定期维护）
            if current_time - self._memory_stats['last_cleanup_time'] > 600:  # 10分钟
                result['should_cleanup'] = True
                result['reason'] = "定期清理时间到达"

            return result

        except Exception as e:
            logger.error(f"内存检查失败: {e}")
            result['reason'] = f"检查失败: {e}"
            return result

    def _cleanup_buffers(self):
        """智能清理缓冲区，释放内存"""
        try:
            start_time = time.time()
            cleared_count = 0
            current_time = time.time()

            # 获取当前内存使用情况
            current_memory_mb = self._get_memory_usage_mb()
            process_memory_mb = self._get_process_memory_mb()

            logger.debug(f"开始清理 - 缓冲内存: {current_memory_mb:.1f}MB, 进程内存: {process_memory_mb:.1f}MB")

            # 多层清理策略
            # 1. 清理过期的tick数据（基于时间）
            cleared_time_data = self._cleanup_expired_ticks()
            cleared_count += cleared_time_data

            # 2. 如果还需要更多清理，基于LRU清理
            if current_memory_mb > self.config.max_size_mb * 0.8:
                cleared_lru_data = self._cleanup_by_lru()
                cleared_count += cleared_lru_data

            # 3. 清理过期的访问时间记录
            self._cleanup_access_times()

            # 4. 强制垃圾回收
            if cleared_count > 0:
                gc.collect()

            # 更新统计信息
            self._memory_stats['last_cleanup_time'] = current_time
            self._memory_stats['cleanup_count'] += 1
            self._update_memory_stats()

            cleanup_time = time.time() - start_time
            final_buffer_memory = self._get_memory_usage_mb()
            final_process_memory = self._get_process_memory_mb()

            logger.info(f"智能缓冲区清理完成 - 耗时: {cleanup_time:.3f}s, "
                       f"清除: {cleared_count}条数据, "
                       f"缓冲内存: {current_memory_mb:.1f}MB → {final_buffer_memory:.1f}MB, "
                       f"进程内存: {process_memory_mb:.1f}MB → {final_process_memory:.1f}MB")

        except Exception as e:
            logger.error(f"缓冲区清理失败: {e}")

    def _cleanup_expired_ticks(self) -> int:
        """清理过期的tick数据（基于时间）"""
        try:
            cleared_count = 0
            current_time = time.time()
            expiry_threshold = 300  # 5分钟前的数据认为是过期的

            for symbol, buffer in list(self._buffers.items()):
                if not buffer:
                    continue

                # 获取最早的数据时间
                oldest_tick_time = None
                for tick in buffer:
                    if hasattr(tick, 'event_time') and tick.event_time:
                        oldest_tick_time = tick.event_time / 1000  # 转换为秒
                        break

                # 如果数据过期，清理前50%
                if oldest_tick_time and (current_time - oldest_tick_time) > expiry_threshold:
                    original_count = len(buffer)
                    # 只清理前50%的数据，保留较新的数据
                    remove_count = min(len(buffer), max(1, len(buffer) // 2))

                    for _ in range(remove_count):
                        if buffer:
                            buffer.popleft()
                            cleared_count += 1

                    self._memory_stats['total_ticks'] -= cleared_count
                    logger.debug(f"清理过期数据 {symbol}: {remove_count} 条")

            return cleared_count

        except Exception as e:
            logger.error(f"清理过期tick失败: {e}")
            return 0

    def _cleanup_by_lru(self) -> int:
        """基于LRU清理最少使用的交易对数据"""
        try:
            cleared_count = 0

            # 按访问时间排序，清理最久未访问的交易对
            sorted_symbols = sorted(
                self._access_times.items(),
                key=lambda x: x[1]
            )

            current_memory_mb = self._get_memory_usage_mb()
            target_memory_mb = self.config.max_size_mb * 0.6  # 目标降到60%

            for symbol, last_access in sorted_symbols:
                if current_memory_mb <= target_memory_mb:
                    break

                # 保留最近访问的交易对，跳过30秒内有活动的
                if time.time() - last_access < 30:
                    continue

                # 清理该交易对的一部分数据而不是全部
                buffer = self._buffers.get(symbol, deque())
                if buffer:
                    original_count = len(buffer)
                    # 清理75%的数据，保留25%
                    remove_count = max(1, int(original_count * 0.75))

                    for _ in range(remove_count):
                        if buffer:
                            buffer.popleft()
                            cleared_count += 1

                    self._memory_stats['total_ticks'] -= cleared_count
                    current_memory_mb = self._get_memory_usage_mb()
                    logger.debug(f"LRU清理 {symbol}: {remove_count} 条，剩余 {len(buffer)} 条")

            return cleared_count

        except Exception as e:
            logger.error(f"LRU清理失败: {e}")
            return 0

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
        """获取当前Tick数据缓冲的实际内存使用量（MB）

        Returns:
            Tick数据缓冲的内存使用量（MB），而不是整个进程的内存
        """
        try:
            if not self._buffers:
                return 0.0

            # 估算Tick数据缓冲的实际内存使用量
            total_memory_bytes = 0

            for symbol, buffer in self._buffers.items():
                if buffer:
                    # 每个TickerData对象大约占用的内存（字节）
                    # 包括对象开销 + 数据字段
                    estimated_size_per_tick = 200  # 估算每个tick对象约200字节
                    total_memory_bytes += len(buffer) * estimated_size_per_tick

            # 转换为MB
            return total_memory_bytes / 1024 / 1024

        except Exception:
            return 0.0

    def _get_process_memory_mb(self) -> float:
        """获取整个进程的内存使用量（MB）

        Returns:
            整个进程的内存使用量（MB）
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
        """获取增强的缓冲区统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            self._update_memory_stats()

            symbol_counts = {
                symbol: len(buffer) for symbol, buffer in self._buffers.items() if buffer
            }

            # 计算Tick数据缓冲的实际内存使用率
            buffer_memory_mb = self._get_memory_usage_mb()
            buffer_memory_percent = (buffer_memory_mb / self.config.max_size_mb) * 100 if self.config.max_size_mb > 0 else 0

            # 获取进程内存和系统内存（主要监控指标）
            process_memory_mb = self._get_process_memory_mb()
            system_memory_mb = psutil.virtual_memory().total / (1024 * 1024)
            process_memory_percent = (process_memory_mb / system_memory_mb) * 100

            # 获取内存检查结果
            cleanup_result = self._check_and_trigger_cleanup()

            return {
                **self._memory_stats,
                'symbol_count': len(symbol_counts),
                'symbol_ticks': symbol_counts,

                # 内存使用信息
                'buffer_memory_mb': buffer_memory_mb,
                'buffer_memory_percent': buffer_memory_percent,
                'process_memory_mb': process_memory_mb,
                'process_memory_percent': process_memory_percent,
                'system_memory_gb': self.system_memory_gb,

                # 阈值信息
                'process_memory_warning_threshold': self.process_memory_warning_threshold,
                'process_memory_critical_threshold': self.process_memory_critical_threshold,

                # 清理状态
                'cleanup_status': {
                    'should_save': cleanup_result['should_save'],
                    'should_cleanup': cleanup_result['should_cleanup'],
                    'reason': cleanup_result['reason'],
                    'debounce_remaining': max(0, self._memory_stats['save_debounce_cooldown'] -
                                             (time.time() - self._memory_stats['last_save_trigger']))
                }
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
        """增强的健康检查

        Returns:
            健康状态信息
        """
        try:
            stats = self.get_stats()
            process_memory_percent = stats.get('process_memory_percent', 0)
            buffer_memory_percent = stats.get('buffer_memory_percent', 0)

            # 基于进程内存判断健康状态（更准确）
            if process_memory_percent > stats.get('process_memory_critical_threshold', 80):
                status = "critical"
                message = f"进程内存危险 ({process_memory_percent:.1f}%)，需要立即清理"
            elif process_memory_percent > stats.get('process_memory_warning_threshold', 70):
                status = "warning"
                message = f"进程内存告警 ({process_memory_percent:.1f}%)，建议清理"
            elif buffer_memory_percent > 85:
                status = "warning"
                message = f"缓冲区内存较高 ({buffer_memory_percent:.1f}%)"
            else:
                status = "healthy"
                message = "运行正常"

            return {
                'status': status,
                'message': message,

                # 内存信息
                'process_memory_percent': process_memory_percent,
                'buffer_memory_percent': buffer_memory_percent,
                'process_memory_mb': stats.get('process_memory_mb', 0),
                'buffer_memory_mb': stats.get('buffer_memory_mb', 0),

                # 基本信息
                'total_ticks': stats.get('total_ticks', 0),
                'symbol_count': stats.get('symbol_count', 0),
                'cleanup_count': stats.get('cleanup_count', 0),
                'last_cleanup_time': stats.get('last_cleanup_time', 0),

                # 系统信息
                'system_memory_gb': stats.get('system_memory_gb', 0),
                'debounce_remaining': stats.get('cleanup_status', {}).get('debounce_remaining', 0)
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'健康检查失败: {e}',
                'process_memory_percent': 0,
                'buffer_memory_percent': 0,
                'total_ticks': 0,
                'symbol_count': 0,
                'cleanup_count': 0,
                'last_cleanup_time': 0
            }