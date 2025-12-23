"""
Tick数据管理器

统一管理tick数据的收集、缓冲、转存和完整性检查。
提供tick数据的完整生命周期管理。
"""

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from pathlib import Path
import logging

from ..websocket_client import TickerData
from .config_models import TickDataConfig
from .memory_buffer import MemoryBuffer
from .async_tick_saver import AsyncTickSaver
from .data_integrity_manager import DataIntegrityManager

logger = logging.getLogger(__name__)


class TickDataManager:
    """Tick数据管理器

    提供tick数据的完整管理功能，包括收集、缓冲、转存和监控。
    """

    def __init__(self, config: TickDataConfig):
        self.config = config
        self._running = False
        self._save_task = None
        self._monitor_task = None

        # 核心组件
        self.buffer = MemoryBuffer(config.buffer)
        self.saver = AsyncTickSaver(config)
        self.integrity_manager = DataIntegrityManager(config)

        # 管理统计
        self._manager_stats = {
            'start_time': 0,
            'ticks_collected': 0,
            'ticks_saved': 0,
            'save_cycles': 0,
            'last_save_time': 0,
            'total_runtime': 0
        }

        # 控制锁
        self._manager_lock = threading.RLock()

        logger.info(f"TickDataManager初始化完成 - "
                   f"转存间隔: {config.save_interval_seconds}秒, "
                   f"存储路径: {config.storage.base_path}")

    async def start(self):
        """启动tick数据管理器"""
        if self._running:
            logger.warning("TickDataManager已经在运行中")
            return

        self._running = True
        self._manager_stats['start_time'] = time.time()

        # 创建存储目录
        storage_path = Path(self.config.storage.base_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # 启动定期转存任务
        self._save_task = asyncio.create_task(self._periodic_save_task())

        # 启动监控任务（如果启用）
        if self.config.monitoring.enable_metrics:
            self._monitor_task = asyncio.create_task(self._monitor_task_func())

        logger.info("TickDataManager已启动")

    async def stop(self):
        """停止tick数据管理器"""
        if not self._running:
            return

        logger.info("正在停止TickDataManager...")

        self._running = False

        # 取消任务
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # 执行最后一次保存
        await self._force_save_all()

        # 清理资源
        await self.saver.cleanup()

        # 更新统计信息
        if self._manager_stats['start_time'] > 0:
            self._manager_stats['total_runtime'] = time.time() - self._manager_stats['start_time']

        logger.info("TickDataManager已停止")

    async def collect_tick(self, tick_data: TickerData) -> bool:
        """收集tick数据

        Args:
            tick_data: tick数据

        Returns:
            是否成功收集
        """
        if not self._running:
            logger.debug("TickDataManager未运行，忽略tick数据")
            return False

        try:
            # 添加到缓冲区
            success = self.buffer.add_tick(tick_data)

            if success:
                self._manager_stats['ticks_collected'] += 1

                # 使用新的智能内存检查（防抖 + 更准确的监控）
                buffer_stats = self.buffer.get_stats()
                cleanup_status = buffer_stats.get('cleanup_status', {})

                if cleanup_status.get('should_save', False):
                    process_memory_percent = buffer_stats.get('process_memory_percent', 0)
                    reason = cleanup_status.get('reason', '内存压力')

                    logger.info(f"智能内存告警 - 进程内存: {process_memory_percent:.1f}%, "
                               f"原因: {reason}, 触发保存")

                    # 异步触发保存，避免阻塞tick收集
                    asyncio.create_task(self._force_save_all())

            return success

        except Exception as e:
            logger.error(f"收集tick数据失败: {e}")
            return False

    async def save_symbol(self, symbol: str) -> bool:
        """保存指定交易对的tick数据

        Args:
            symbol: 交易对符号

        Returns:
            是否保存成功
        """
        try:
            # 获取缓冲区数据
            tick_data_list = self.buffer.get_ticks(symbol)
            if not tick_data_list:
                logger.debug(f"交易对 {symbol} 无数据需要保存")
                return True

            # 保存数据
            success = await self.saver.save_ticks(symbol, tick_data_list)

            if success:
                # 清空已保存的数据
                self.buffer.clear_symbol(symbol)
                self._manager_stats['ticks_saved'] += len(tick_data_list)
                logger.debug(f"保存交易对 {symbol} 的 {len(tick_data_list)} 条tick数据")

            return success

        except Exception as e:
            logger.error(f"保存交易对 {symbol} 失败: {e}")
            return False

    async def save_all(self) -> Dict[str, bool]:
        """保存所有缓冲区的tick数据

        Returns:
            各交易对保存结果
        """
        try:
            # 获取所有缓冲区数据
            all_ticks = self.buffer.get_all_ticks()

            if not all_ticks:
                logger.debug("无数据需要保存")
                return {}

            # 批量保存
            save_results = await self.saver.save_batch(all_ticks)

            # 清空已保存的数据
            total_saved = 0
            for symbol, success in save_results.items():
                if success:
                    saved_count = self.buffer.clear_symbol(symbol)
                    total_saved += saved_count
                    logger.debug(f"保存交易对 {symbol} 的 {saved_count} 条tick数据")

            self._manager_stats['ticks_saved'] += total_saved
            self._manager_stats['save_cycles'] += 1
            self._manager_stats['last_save_time'] = time.time()

            successful_saves = sum(save_results.values())
            logger.info(f"批量保存完成 - 成功: {successful_saves}/{len(save_results)} "
                       f"交易对, 总tick数: {total_saved}")

            return save_results

        except Exception as e:
            logger.error(f"批量保存失败: {e}")
            return {}

    async def _periodic_save_task(self):
        """自适应保存任务 - 根据内存压力和数据量动态调整保存频率

        优化策略:
        - 内存使用率 > 80%: 立即触发保存，间隔缩短至30秒
        - 数据增长快 (>5000 tick): 提前触发保存，间隔60秒
        - 正常情况: 使用配置的默认间隔
        """
        logger.info("启动自适应保存任务")

        last_total_ticks = 0
        # 动态保存间隔，初始值为配置的默认值
        save_interval = self.config.save_interval_seconds

        while self._running:
            try:
                await asyncio.sleep(save_interval)

                if not self._running:
                    break

                # 获取当前缓冲区状态
                current_stats = self.buffer.get_stats()
                total_ticks = current_stats.get('total_ticks', 0)
                memory_percent = current_stats.get('process_memory_percent', 0)
                tick_growth = total_ticks - last_total_ticks

                # 动态调整保存策略
                if memory_percent > 80:
                    # 内存告警 - 立即保存，缩短间隔
                    logger.warning(f"内存压力 {memory_percent:.1f}%，触发紧急保存")
                    await self.save_all()
                    save_interval = 30  # 加快保存频率
                    last_total_ticks = total_ticks

                elif tick_growth > 5000:
                    # 数据量增长快 - 提前保存
                    logger.info(f"数据增长快 (+{tick_growth} ticks)，触发提前保存")
                    await self.save_all()
                    save_interval = 60  # 使用较短间隔
                    last_total_ticks = total_ticks

                else:
                    # 正常情况 - 定期保存
                    logger.debug(f"执行定期保存 (总tick: {total_ticks})")
                    await self.save_all()
                    save_interval = self.config.save_interval_seconds  # 恢复默认间隔
                    last_total_ticks = total_ticks

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自适应保存任务错误: {e}")
                # 继续运行，不要因为单次错误而停止
                # 发生错误时恢复默认间隔
                save_interval = self.config.save_interval_seconds

        logger.info("自适应保存任务已停止")

    async def _monitor_task_func(self):
        """监控任务"""
        logger.info("启动监控任务")

        while self._running:
            try:
                # 每5分钟监控一次
                await asyncio.sleep(300)

                if not self._running:
                    break

                # 执行健康检查
                health_status = await self._health_check()

                # 记录监控信息
                if health_status['status'] != 'healthy':
                    logger.warning(f"系统状态异常: {health_status}")

                # 输出统计信息
                if self._manager_stats['save_cycles'] > 0 and \
                   self._manager_stats['save_cycles'] % 12 == 0:  # 每小时输出一次
                    await self._log_statistics()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控任务错误: {e}")

        logger.info("监控任务已停止")

    async def _force_save_all(self):
        """强制保存所有数据"""
        try:
            logger.debug("执行强制保存")
            await self.save_all()
        except Exception as e:
            logger.error(f"强制保存失败: {e}")

    async def _health_check(self) -> Dict[str, any]:
        """执行增强的健康检查

        Returns:
            健康状态信息
        """
        try:
            # 检查缓冲区健康状态
            buffer_health = self.buffer.health_check()

            # 检查写入统计
            write_stats = await self.saver.get_write_stats()

            # 检查验证统计
            validation_stats = self.integrity_manager.get_validation_stats()

            # 综合判断系统健康状态
            overall_status = "healthy"
            issues = []

            if buffer_health['status'] == 'critical':
                overall_status = "critical"
                issues.append(buffer_health['message'])
            elif buffer_health['status'] == 'warning':
                overall_status = "warning"
                issues.append(buffer_health['message'])

            if write_stats.get('success_rate', 100) < 90:
                overall_status = "critical" if overall_status == "healthy" else overall_status
                issues.append(f"写入成功率低: {write_stats['success_rate']:.1f}%")

            # 添加防抖状态信息
            debounce_remaining = buffer_health.get('debounce_remaining', 0)
            if debounce_remaining > 0:
                issues.append(f"内存清理冷却中: {debounce_remaining:.0f}秒")

            return {
                'status': overall_status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'issues': issues,
                'buffer_health': buffer_health,
                'write_stats': write_stats,
                'validation_stats': validation_stats,
                'memory_summary': {
                    'process_memory_percent': buffer_health.get('process_memory_percent', 0),
                    'buffer_memory_percent': buffer_health.get('buffer_memory_percent', 0),
                    'system_memory_gb': buffer_health.get('system_memory_gb', 0)
                }
            }

        except Exception as e:
            return {
                'status': 'error',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }

    async def _log_statistics(self):
        """输出统计信息"""
        try:
            manager_stats = self.get_manager_stats()
            buffer_stats = self.buffer.get_stats()
            write_stats = await self.saver.get_write_stats()

            logger.info("=== Tick数据管理器统计信息 ===")
            logger.info(f"运行时间: {manager_stats['runtime_hours']:.1f} 小时")
            logger.info(f"收集tick数: {manager_stats['ticks_collected']:,}")
            logger.info(f"保存tick数: {manager_stats['ticks_saved']:,}")
            logger.info(f"保存周期数: {manager_stats['save_cycles']}")
            logger.info(f"内存使用: {buffer_stats['memory_usage_percent']:.1f}%")
            logger.info(f"缓冲交易对: {buffer_stats['symbol_count']}")
            logger.info(f"写入成功率: {write_stats.get('success_rate', 0):.1f}%")
            logger.info("================================")

        except Exception as e:
            logger.error(f"输出统计信息失败: {e}")

    async def validate_saved_data(self, symbol: Optional[str] = None) -> Dict[str, any]:
        """验证已保存的数据完整性

        Args:
            symbol: 交易对符号，None表示验证所有

        Returns:
            验证结果
        """
        try:
            storage_path = Path(self.config.storage.base_path) / self.config.storage.exchange

            if symbol:
                # 验证指定交易对
                symbol_path = storage_path / symbol.replace('/', '-')
                return await self.integrity_manager.validate_directory(symbol_path)
            else:
                # 验证所有数据
                return await self.integrity_manager.validate_directory(storage_path)

        except Exception as e:
            logger.error(f"验证保存数据失败: {e}")
            return {
                'valid': False,
                'error': str(e)
            }

    def get_manager_stats(self) -> Dict[str, any]:
        """获取管理器统计信息

        Returns:
            统计信息字典
        """
        stats = self._manager_stats.copy()

        # 计算运行时间
        if stats['start_time'] > 0:
            current_time = time.time()
            if self._running:
                stats['runtime_hours'] = (current_time - stats['start_time']) / 3600
            else:
                stats['runtime_hours'] = stats['total_runtime'] / 3600
        else:
            stats['runtime_hours'] = 0

        # 计算保存效率
        if stats['ticks_collected'] > 0:
            stats['save_efficiency'] = (stats['ticks_saved'] / stats['ticks_collected']) * 100
        else:
            stats['save_efficiency'] = 0

        # 计算平均保存周期
        if stats['total_runtime'] > 0 and stats['save_cycles'] > 0:
            stats['avg_save_cycle_minutes'] = (stats['total_runtime'] / stats['save_cycles']) / 60
        else:
            stats['avg_save_cycle_minutes'] = 0

        stats['is_running'] = self._running

        return stats

    async def get_detailed_status(self) -> Dict[str, any]:
        """获取详细状态信息

        Returns:
            详细状态字典
        """
        try:
            manager_stats = self.get_manager_stats()
            buffer_stats = self.buffer.get_stats()
            write_stats = await self.saver.get_write_stats()
            validation_stats = self.integrity_manager.get_validation_stats()
            health_status = await self._health_check()

            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'manager_stats': manager_stats,
                'buffer_stats': buffer_stats,
                'write_stats': write_stats,
                'validation_stats': validation_stats,
                'health_status': health_status,
                'config': {
                    'save_interval_seconds': self.config.save_interval_seconds,
                    'storage_path': self.config.storage.base_path,
                    'compression': self.config.storage.compression,
                    'max_buffer_size_mb': self.config.buffer.max_size_mb
                }
            }

        except Exception as e:
            logger.error(f"获取详细状态失败: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }

    def get_buffer_status(self, symbol: Optional[str] = None) -> Dict[str, any]:
        """获取缓冲区状态

        Args:
            symbol: 交易对符号，None表示返回所有

        Returns:
            缓冲区状态信息
        """
        if symbol:
            return self.buffer.get_buffer_status(symbol)
        else:
            buffer_stats = self.buffer.get_stats()
            symbol_statuses = {}
            for sym in buffer_stats.get('symbol_ticks', {}).keys():
                symbol_statuses[sym] = self.buffer.get_buffer_status(sym)

            return {
                'overall_stats': buffer_stats,
                'symbol_statuses': symbol_statuses
            }