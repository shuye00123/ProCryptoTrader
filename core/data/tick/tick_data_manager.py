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
from .streaming_disk_queue import StreamingDiskQueue

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

        # V3.0: 流式磁盘队列 - 入队时写入临时Parquet文件，出队时移动文件
        self._save_queue: Optional[StreamingDiskQueue] = None
        self._save_worker_task = None

        # 管理统计
        self._manager_stats = {
            'start_time': 0,
            'ticks_collected': 0,
            'ticks_saved': 0,
            'save_cycles': 0,
            'last_save_time': 0,
            'total_runtime': 0,
            'queue_max_size': 0,  # 队列最大长度统计
            'queue_dropped': 0     # 队列丢弃计数
        }

        # 控制锁
        self._manager_lock = threading.RLock()

        logger.info(f"TickDataManager初始化完成 (V3.0流式磁盘队列模式) - "
                   f"转存间隔: {config.save_interval_seconds}秒, "
                   f"存储路径: {config.storage.base_path}")

    async def start(self):
        """启动tick数据管理器"""
        if self._running:
            logger.warning("TickDataManager已经在运行中")
            return

        self._running = True
        self._manager_stats['start_time'] = time.time()

        # V3.0: 创建流式磁盘队列 - 使用配置参数
        if self.config.streaming_queue.enabled:
            temp_dir = Path(self.config.streaming_queue.temp_dir)
            self._save_queue = StreamingDiskQueue(
                temp_dir=temp_dir,
                queue_name="tick_save",
                max_workers=self.config.streaming_queue.max_workers
            )
            logger.info(f"流式磁盘队列已启用 - 临时目录: {temp_dir}, "
                       f"并行线程: {self.config.streaming_queue.max_workers}")
        else:
            self._save_queue = None
            logger.warning("流式磁盘队列未启用，将使用传统保存模式")

        # 创建存储目录
        storage_path = Path(self.config.storage.base_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # V3.0: 启动保存工作协程（处理文件移动）
        self._save_worker_task = asyncio.create_task(self._save_worker())

        # 启动定期转存任务（只负责入队）
        self._save_task = asyncio.create_task(self._periodic_save_task())

        # 启动监控任务（如果启用）
        if self.config.monitoring.enable_metrics:
            self._monitor_task = asyncio.create_task(self._monitor_task_func())

        logger.info("TickDataManager已启动 (V3.0流式磁盘队列模式)")

    async def stop(self):
        """停止tick数据管理器"""
        if not self._running:
            return

        logger.info("正在停止TickDataManager...")

        self._running = False

        # V3.0: 等待流式磁盘队列处理完成
        if self._save_queue and not self._save_queue.empty():
            queue_size = self._save_queue.qsize()
            logger.info(f"等待处理剩余 {queue_size} 个文件...")
            try:
                await asyncio.wait_for(self._save_queue.join(), timeout=120)
                logger.info("文件处理完成")
            except asyncio.TimeoutError:
                logger.warning("文件处理超时，临时文件将在下次启动时处理")

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

        # V3.0: 取消保存工作协程
        if self._save_worker_task and not self._save_worker_task.done():
            self._save_worker_task.cancel()
            try:
                await self._save_worker_task
            except asyncio.CancelledError:
                pass

        # 执行最后一次保存（确保所有数据落盘）
        await self._do_save_all()

        # V3.0: 清理流式磁盘队列资源
        if self._save_queue:
            await self._save_queue.cleanup()

        # 清理其他资源
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

                # V2.0: 智能内存检查后入队（而非直接创建任务）
                buffer_stats = self.buffer.get_stats()
                cleanup_status = buffer_stats.get('cleanup_status', {})

                if cleanup_status.get('should_save', False):
                    process_memory_percent = buffer_stats.get('process_memory_percent', 0)
                    reason = cleanup_status.get('reason', '内存压力')

                    logger.info(f"智能内存告警 - 进程内存: {process_memory_percent:.1f}%, "
                               f"原因: {reason}, 触发保存入队")

                    # V2.0: 入队而非直接创建任务
                    await self._enqueue_save_request()

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
        """定期保存任务 - V2.0: 只负责入队，不直接执行保存

        工作流程：
        1. 等待指定间隔
        2. 将保存请求放入队列
        3. 工作协程负责实际保存操作
        """
        logger.info("启动定期保存任务 (V2.0队列模式)")

        while self._running:
            try:
                await asyncio.sleep(self.config.save_interval_seconds)

                if not self._running:
                    break

                # V2.0: 只入队，不阻塞
                await self._enqueue_save_request()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定期保存任务错误: {e}")

        logger.info("定期保存任务已停止")

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
        """强制保存所有数据 - V2.0: 入队而非直接执行"""
        await self._enqueue_save_request()

    async def _enqueue_save_request(self):
        """将保存请求放入流式磁盘队列 - V3.0新方法

        流式写入流程:
        1. 调用buffer.get_all_ticks()获取所有tick数据
        2. 并行写入每个交易对的临时Parquet文件
        3. 写完一个交易对立即清空该交易对内存
        4. 将文件路径列表入队

        关键优化: 内存峰值大幅降低，因为写完一个交易对立即释放内存
        """
        if self._save_queue is None:
            logger.warning("保存队列未初始化，直接执行保存")
            await self._do_save_all()
            return

        try:
            # 构建元数据
            metadata = {
                'trigger_time': time.time(),
                'reason': 'periodic_or_memory_pressure',
            }

            # V3.0: 流式入队 - 内部会并行写入临时文件并立即释放内存
            success = await self._save_queue.enqueue_from_buffer(
                get_ticks_func=self.buffer.get_all_ticks,
                clear_symbol_func=self.buffer.clear_symbol,
                metadata=metadata
            )

            if success:
                queue_size = self._save_queue.qsize()
                if queue_size > self._manager_stats['queue_max_size']:
                    self._manager_stats['queue_max_size'] = queue_size

                logger.debug(f"保存请求已入队到流式磁盘队列，当前队列长度: {queue_size}")
            else:
                self._manager_stats['queue_dropped'] += 1
                logger.error(f"保存请求入队失败 (已丢弃: {self._manager_stats['queue_dropped']})")

        except Exception as e:
            logger.error(f"入队操作失败: {e}")
            self._manager_stats['queue_dropped'] += 1

    async def _save_worker(self):
        """保存工作协程 - V3.0新方法: 直接移动临时文件到最终目录

        V3.0架构变更:
        - 不再调用save_all()进行数据读取+写入
        - 直接从队列获取已写入的临时文件路径列表
        - 将临时文件移动到最终目录(原子操作，极快)
        - 移动完成后标记任务完成

        性能优势:
        - 移动文件(~50ms) vs 读取+写入(~800ms) = 16x速度提升
        - 无需读取数据，零内存开销

        降级模式:
        - 如果流式队列未启用，使用传统save_all()方法
        """
        if self._save_queue is None:
            logger.info("保存工作协程已启动 (传统模式 - 流式队列未启用)")
            while self._running:
                try:
                    await asyncio.sleep(1)  # 传统模式下休眠等待
                    # 在传统模式下，保存由_enqueue_save_request直接调用_do_save_all完成
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"保存工作协程异常: {e}")
            logger.info("保存工作协程已停止")
            return

        logger.info("保存工作协程已启动 (V3.0文件移动模式)")

        while self._running:
            try:
                # 从队列获取文件路径列表
                queue_item = await self._save_queue.dequeue()

                if queue_item is None:
                    continue

                # V3.0: 直接移动文件到最终目录 (无需读取+重新写入!)
                results = await self._save_queue.move_files_to_final_destination(
                    queue_item,
                    get_final_path_func=self._get_final_storage_path
                )

                # 更新统计
                self._manager_stats['ticks_saved'] += results['total_ticks']
                self._manager_stats['save_cycles'] += 1
                self._manager_stats['last_save_time'] = time.time()

                logger.info(f"文件移动完成 - 移动: {len(results['moved'])}, "
                           f"失败: {len(results['failed'])}, "
                           f"tick数: {results['total_ticks']}")

                # 标记任务完成
                self._save_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"保存工作协程异常: {e}")

        logger.info("保存工作协程已停止")

    def _get_final_storage_path(self, symbol: str, timestamp_ms: int) -> Path:
        """获取最终存储路径 - 供StreamingDiskQueue使用

        Args:
            symbol: 交易对符号
            timestamp_ms: 毫秒时间戳

        Returns:
            最终存储文件路径
        """
        return self.config.get_storage_path(symbol, timestamp_ms)

    async def _do_save_all(self):
        """实际执行保存操作 - V2.0新方法"""
        try:
            logger.debug("执行保存操作")
            await self.save_all()
        except Exception as e:
            logger.error(f"保存操作失败: {e}")

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