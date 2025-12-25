"""
流式磁盘队列 - 高性能临时文件存储

核心优化:
1. 流式转换: 直接从TickerData对象流式写入Parquet
2. 分片存储: 每个交易对独立文件
3. 并行写入: 使用线程池并行处理多个交易对
4. 立即释放: 写完一个交易对立即清空内存

与传统DiskQueue的区别:
- 传统: get_all_ticks() → pickle序列化 → 单文件写入
- 流式: 按交易对迭代 → 流式Parquet写入 → 并行多文件

性能优势:
- PyArrow C++实现比pickle快3-5倍
- 分片并行写入，充分利用多核
- 出队时直接移动文件，无需重新写入
"""

import asyncio
import time
import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Callable
from concurrent.futures import ThreadPoolExecutor
import logging
import shutil

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..websocket_client import TickerData

logger = logging.getLogger(__name__)


class StreamingDiskQueue:
    """流式磁盘队列 - 高性能临时文件存储

    设计理念:
    1. 入队时: 并行写入每个交易对的临时Parquet文件，写完立即清空内存
    2. 队列: 只存储文件路径列表（轻量级，可无限长）
    3. 出队时: 直接移动文件到最终目录（极快，无需读取+重新写入）
    """

    def __init__(
        self,
        temp_dir: Optional[Path] = None,
        queue_name: str = "tick_save",
        max_workers: int = 2
    ):
        """初始化流式磁盘队列

        Args:
            temp_dir: 临时文件目录，None则使用项目目录下的data/temp
            queue_name: 队列名称（用于创建子目录）
            max_workers: 并行写入的线程数（默认2，匹配2核CPU）
        """
        # 创建临时文件目录
        if temp_dir is None:
            self.temp_dir = Path("data/temp") / queue_name
        else:
            self.temp_dir = temp_dir / queue_name

        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 队列存储文件路径列表（不是数据本身）
        self._queue: asyncio.Queue = asyncio.Queue()

        # 线程池用于并行写入
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 统计信息
        self._stats = {
            'enqueued': 0,
            'dequeued': 0,
            'files_created': 0,
            'files_deleted': 0,
            'files_moved': 0,
            'ticks_written': 0,
            'write_time_total': 0.0,
            'current_queue_size': 0,
        }

        # 启动时清理残留的临时文件
        self._cleanup_orphaned_files()

        logger.info(f"StreamingDiskQueue初始化完成 - 临时目录: {self.temp_dir}, "
                   f"并发写入: {max_workers}")

    def _cleanup_orphaned_files(self):
        """启动时清理残留的临时文件"""
        try:
            existing_files = list(self.temp_dir.glob("*.parquet"))
            if existing_files:
                logger.warning(f"发现 {len(existing_files)} 个残留临时文件，开始清理...")
                for f in existing_files:
                    try:
                        f.unlink()
                    except Exception as e:
                        logger.error(f"清理文件失败 {f}: {e}")
                logger.info(f"清理完成，共清理 {len(existing_files)} 个文件")
        except Exception as e:
            logger.error(f"清理残留文件失败: {e}")

    async def enqueue_from_buffer(
        self,
        get_ticks_func: Callable[[], Dict[str, List[TickerData]]],
        clear_symbol_func: Callable[[str], int],
        metadata: Optional[dict] = None
    ) -> bool:
        """从内存缓冲区入队 - 流式并行写入

        这是整个系统的关键优化点:
        1. 获取所有交易对的tick数据快照（避免数据竞争）
        2. 并行写入每个交易对的临时Parquet文件（线程池）
        3. 写完一个交易对立即清空该交易对内存
        4. 将文件路径列表入队

        数据竞争修复:
        - 在获取tick数据后立即创建深拷贝快照
        - 防止在写入过程中buffer被修改导致数据丢失

        Args:
            get_ticks_func: 获取所有tick的函数 (返回 Dict[str, List[TickerData]])
            clear_symbol_func: 清空指定交易对缓冲区的函数
            metadata: 元数据

        Returns:
            是否成功入队
        """
        start_time = time.time()

        try:
            # 1. 获取所有交易对的tick数据并创建快照
            # 使用深拷贝避免在写入过程中buffer被修改
            all_ticks_source = get_ticks_func()

            if not all_ticks_source:
                return True

            # 创建深拷贝快照，防止并发修改
            # 每个tick对象是不可变的dataclass，但列表本身可能被修改
            all_ticks = {symbol: list(ticks) for symbol, ticks in all_ticks_source.items()}

            # 2. 统计信息
            total_ticks = sum(len(ticks) for ticks in all_ticks.values())
            symbol_count = len(all_ticks)

            logger.info(f"开始流式写入 - 交易对数: {symbol_count}, 总tick数: {total_ticks}")

            # 3. 并行写入每个交易对的临时文件
            file_paths = await self._write_symbols_parallel(all_ticks, clear_symbol_func)

            # 4. 将文件路径列表和元数据打包入队
            queue_item = {
                'file_paths': file_paths,
                'metadata': {
                    **(metadata or {}),
                    'symbol_count': symbol_count,
                    'total_ticks': total_ticks,
                    'enqueue_time': time.time()
                }
            }

            await self._queue.put(queue_item)

            # 更新统计
            self._stats['enqueued'] += 1
            self._stats['files_created'] += len(file_paths)
            self._stats['ticks_written'] += total_ticks
            self._stats['current_queue_size'] = self._queue.qsize()

            write_time = time.time() - start_time
            self._stats['write_time_total'] += write_time

            logger.info(f"流式写入完成 - 文件数: {len(file_paths)}, "
                       f"tick数: {total_ticks}, 耗时: {write_time:.3f}s, "
                       f"速度: {total_ticks/write_time:.0f} ticks/s, "
                       f"队列长度: {self._queue.qsize()}")

            return True

        except Exception as e:
            logger.error(f"入队失败: {e}", exc_info=True)
            return False

    async def _write_symbols_parallel(
        self,
        all_ticks: Dict[str, List[TickerData]],
        clear_symbol_func: Callable[[str], int]
    ) -> List[str]:
        """并行写入多个交易对的临时文件

        关键优化:
        - 每个交易对独立文件（避免大文件写入）
        - 并行写入（线程池，充分利用多核）
        - 写完后立即清空该交易对内存（降低内存峰值）

        Args:
            all_ticks: 按交易对分组的tick数据
            clear_symbol_func: 清空指定交易对缓冲区的函数

        Returns:
            写入的文件路径列表
        """
        file_paths = []
        loop = asyncio.get_event_loop()

        # 创建写入任务集合
        pending = set()
        future_to_symbol = {}

        for symbol, ticks in all_ticks.items():
            if not ticks:
                continue

            # 为每个交易对创建写入任务
            future = loop.run_in_executor(
                self._executor,
                self._write_symbol_to_parquet,
                symbol, ticks
            )
            pending.add(future)
            future_to_symbol[future] = symbol

        # 使用asyncio.wait()循环处理完成的任务
        while pending:
            # 等待任意一个任务完成
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED
            )

            # 处理已完成的任务
            for completed_future in done:
                symbol = future_to_symbol[completed_future]
                try:
                    file_path = completed_future.result()  # 获取结果（已完成的Future）
                    file_paths.append(file_path)

                    # 关键优化: 写完立即清空该交易对的内存
                    cleared_count = clear_symbol_func(symbol)

                    logger.debug(f"交易对 {symbol} 已写入临时文件并清空内存: "
                                f"{file_path.name} ({cleared_count} ticks)")

                except Exception as e:
                    logger.error(f"写入交易对 {symbol} 失败: {e}")

        return file_paths

    def _write_symbol_to_parquet(
        self,
        symbol: str,
        ticks: List[TickerData]
    ) -> str:
        """将单个交易对的tick写入临时Parquet文件

        优化策略:
        1. 流式构建DataFrame（避免先创建大列表）
        2. 使用PyArrow直接写入（C++实现，比pickle快）
        3. 使用snappy压缩（平衡速度和压缩率）

        资源清理:
        - 如果写入失败，自动清理部分写入的文件

        Args:
            symbol: 交易对符号
            ticks: tick数据列表

        Returns:
            写入的文件路径

        Raises:
            Exception: 写入失败时抛出异常（部分文件已清理）
        """
        write_start = time.time()
        timestamp = int(time.time() * 1000000)

        # 生成临时文件名
        safe_symbol = symbol.replace('/', '-')
        file_name = f"{safe_symbol}_{timestamp}.parquet"
        file_path = self.temp_dir / file_name

        # 标记文件是否完成写入
        write_completed = False

        try:
            # 流式构建DataFrame
            # 使用字典列表方式，然后转DataFrame
            data_dicts = []
            created_at = pd.Timestamp.now(tz=datetime.timezone.utc)

            for tick in ticks:
                data_dicts.append({
                    'symbol': tick.symbol,
                    'price': tick.price,
                    'price_change': tick.price_change,
                    'price_change_percent': tick.price_change_percent,
                    'weighted_avg_price': tick.weighted_avg_price,
                    'open_price': tick.open_price,
                    'high_price': tick.high_price,
                    'low_price': tick.low_price,
                    'volume': tick.volume,
                    'quote_volume': tick.quote_volume,
                    'open_time': self._safe_timestamp_to_datetime(tick.open_time),
                    'close_time': self._safe_timestamp_to_datetime(tick.close_time),
                    'event_time': self._safe_timestamp_to_datetime(tick.event_time),
                    'first_id': tick.first_id,
                    'last_id': tick.last_id,
                    'count': tick.count,
                    'last_quantity': tick.last_quantity,
                    'created_at': created_at
                })

            # 创建DataFrame
            df = pd.DataFrame(data_dicts)

            # 使用PyArrow写入（更高效）
            table = pa.Table.from_pandas(df, preserve_index=False)
            pq.write_table(
                table,
                file_path,
                compression='snappy',  # 平衡速度和压缩率
                flavor='spark'         # 兼容Spark
            )

            write_completed = True
            write_time = time.time() - write_start
            logger.debug(f"写入 {symbol}: {len(ticks)} ticks → {file_path.name} "
                        f"({write_time:.3f}s, {len(ticks)/write_time:.0f} ticks/s)")

            return str(file_path)

        except Exception as e:
            logger.error(f"写入临时文件失败 {symbol}: {e}")

            # 清理部分写入的文件
            if not write_completed and file_path.exists():
                try:
                    file_path.unlink()
                    logger.debug(f"已清理部分写入的文件: {file_path.name}")
                except Exception as cleanup_error:
                    logger.warning(f"清理部分文件失败 {file_path.name}: {cleanup_error}")

            raise

    def _safe_timestamp_to_datetime(self, timestamp: int) -> pd.Timestamp:
        """安全的时间戳转换

        Args:
            timestamp: 毫秒时间戳

        Returns:
            pandas Timestamp对象
        """
        if timestamp == 0:
            return pd.NaT

        try:
            return pd.to_datetime(timestamp, unit='ms', utc=True)
        except Exception:
            return pd.NaT

    async def dequeue(self) -> Optional[dict]:
        """出队 - 获取文件路径列表

        Returns:
            包含 file_paths 和 metadata 的字典，或 None
        """
        try:
            queue_item = await self._queue.get()

            file_paths = queue_item.get('file_paths', [])
            metadata = queue_item.get('metadata', {})

            # 更新统计
            self._stats['dequeued'] += 1
            self._stats['current_queue_size'] = self._queue.qsize()

            self._queue.task_done()

            logger.debug(f"从队列取出 {len(file_paths)} 个文件待处理")

            return queue_item

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"出队失败: {e}")
            return None

    async def move_files_to_final_destination(
        self,
        queue_item: dict,
        get_final_path_func: Callable[[str, int], Path]
    ) -> dict:
        """将临时文件移动到最终目录

        优势: 移动文件比读取+写入快得多
        - 移动: 只是修改文件系统目录项（~1-10ms）
        - 读取+写入: 需要读取文件、转换、写入（~500-1000ms）

        Args:
            queue_item: 包含 file_paths 和 metadata 的字典
            get_final_path_func: 获取最终文件路径的函数 (symbol, timestamp_ms) -> Path

        Returns:
            处理结果字典，包含moved和failed列表
        """
        file_paths = queue_item.get('file_paths', [])
        metadata = queue_item.get('metadata', {})

        results = {
            'moved': [],
            'failed': [],
            'total_ticks': metadata.get('total_ticks', 0)
        }

        loop = asyncio.get_event_loop()
        move_start = time.time()

        for temp_path_str in file_paths:
            try:
                temp_path = Path(temp_path_str)

                if not temp_path.exists():
                    logger.warning(f"临时文件不存在: {temp_path}")
                    continue

                # 从文件名解析交易对和时间
                # 格式: BTC-USDT_1234567890.parquet
                filename = temp_path.stem
                parts = filename.split('_')
                if len(parts) >= 2:
                    symbol = parts[0].replace('-', '/')
                    # 修复: 使用整数除法避免精度损失
                    timestamp_ms = int(parts[1]) // 1000000

                    # 获取最终路径
                    final_path = get_final_path_func(symbol, timestamp_ms)

                    # 确保目标目录存在
                    final_path.parent.mkdir(parents=True, exist_ok=True)

                    # 移动文件（原子操作，极快）
                    await loop.run_in_executor(None, temp_path.rename, final_path)

                    results['moved'].append(str(final_path))
                    self._stats['files_moved'] += 1

            except Exception as e:
                logger.error(f"移动文件失败 {temp_path_str}: {e}")
                results['failed'].append(temp_path_str)

        move_time = time.time() - move_start
        if results['moved']:
            logger.debug(f"文件移动完成 - 移动 {len(results['moved'])} 个文件, "
                        f"耗时: {move_time:.3f}s")

        return results

    async def delete_temp_files(self, file_paths: List[str]):
        """删除临时文件（当移动失败时使用）

        Args:
            file_paths: 要删除的临时文件路径列表
        """
        loop = asyncio.get_event_loop()

        for file_path_str in file_paths:
            try:
                file_path = Path(file_path_str)
                if file_path.exists():
                    await loop.run_in_executor(None, file_path.unlink)
                    self._stats['files_deleted'] += 1
            except Exception as e:
                logger.warning(f"删除临时文件失败 {file_path_str}: {e}")

    async def join(self):
        """等待队列中所有任务完成"""
        await self._queue.join()

    def task_done(self):
        """标记任务完成"""
        self._queue.task_done()

    def qsize(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()

    def get_stats(self) -> dict:
        """获取统计信息（同步版本，适用于简单查询）

        Returns:
            统计信息字典，包含队列状态、性能指标等
        """
        # 计算临时文件占用的磁盘空间
        try:
            disk_usage = sum(f.stat().st_size for f in self.temp_dir.glob("*.parquet")) / (1024 * 1024)
        except (OSError, IOError) as e:
            logger.debug(f"计算磁盘使用失败: {e}")
            disk_usage = 0

        stats = self._stats.copy()
        stats['disk_usage_mb'] = round(disk_usage, 2)
        stats['temp_file_count'] = len(list(self.temp_dir.glob("*.parquet")))

        if stats['write_time_total'] > 0 and stats['enqueued'] > 0:
            stats['avg_write_time'] = round(stats['write_time_total'] / stats['enqueued'], 3)
            stats['ticks_per_second'] = round(stats['ticks_written'] / stats['write_time_total'], 1)
        else:
            stats['avg_write_time'] = 0
            stats['ticks_per_second'] = 0

        return stats

    async def get_stats_async(self) -> dict:
        """获取统计信息（异步版本，适用于async上下文）

        将文件I/O操作移到线程池执行，避免阻塞事件循环

        Returns:
            统计信息字典，包含队列状态、性能指标等
        """
        loop = asyncio.get_event_loop()

        # 在线程池中执行文件I/O操作
        try:
            disk_usage = await loop.run_in_executor(
                None,
                lambda: sum(f.stat().st_size for f in self.temp_dir.glob("*.parquet")) / (1024 * 1024)
            )
        except (OSError, IOError) as e:
            logger.debug(f"计算磁盘使用失败: {e}")
            disk_usage = 0

        stats = self._stats.copy()
        stats['disk_usage_mb'] = round(disk_usage, 2)
        stats['temp_file_count'] = len(list(self.temp_dir.glob("*.parquet")))

        if stats['write_time_total'] > 0 and stats['enqueued'] > 0:
            stats['avg_write_time'] = round(stats['write_time_total'] / stats['enqueued'], 3)
            stats['ticks_per_second'] = round(stats['ticks_written'] / stats['write_time_total'], 1)
        else:
            stats['avg_write_time'] = 0
            stats['ticks_per_second'] = 0

        return stats

    async def cleanup(self):
        """清理资源

        1. 等待队列处理完成（带超时和重试）
        2. 关闭线程池
        3. 清理临时文件目录

        清理策略:
        - 首次尝试: 60秒超时
        - 第二次尝试: 120秒超时
        - 最终: 保留临时文件待下次处理，线程池立即关闭
        """
        logger.info("StreamingDiskQueue清理中...")

        # 等待队列处理完成（多次重试）
        queue_completed = False
        for attempt, timeout in enumerate([60, 120], 1):
            try:
                await asyncio.wait_for(self.join(), timeout=timeout)
                logger.info("队列处理完成")
                queue_completed = True
                break
            except asyncio.TimeoutError:
                if attempt == 1:
                    logger.warning(f"队列处理超时({timeout}秒)，尝试延长处理时间...")
                else:
                    logger.error(f"队列处理再次超时({timeout}秒)，保留临时文件待下次处理")

        # 关闭线程池
        # 如果队列未完成，使用wait=False避免无限等待
        shutdown_wait = queue_completed
        try:
            self._executor.shutdown(wait=shutdown_wait)
            logger.info(f"线程池已关闭 (wait={shutdown_wait})")
        except Exception as e:
            logger.error(f"关闭线程池失败: {e}")

        # 清理临时文件目录（如果为空）
        try:
            if self.temp_dir.exists():
                remaining_files = list(self.temp_dir.glob("*.parquet"))
                if not remaining_files:
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"临时目录已删除: {self.temp_dir}")
                else:
                    logger.warning(f"临时目录仍有 {len(remaining_files)} 个文件，保留待下次处理")
        except Exception as e:
            logger.error(f"删除临时目录失败: {e}")

        logger.info("StreamingDiskQueue清理完成")
