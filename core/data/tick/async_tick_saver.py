"""
异步Tick数据转存器

负责将内存中的tick数据异步转存为Parquet格式。
支持批量处理、并发写入、错误恢复和性能优化。
"""

import asyncio
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
import logging
import hashlib
import tempfile
import shutil
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..websocket_client import TickerData
from .config_models import TickDataConfig, PerformanceConfig

logger = logging.getLogger(__name__)


class AsyncTickSaver:
    """异步Tick数据转存器

    提供高性能的异步Parquet文件写入功能。
    """

    def __init__(self, config: TickDataConfig):
        self.config = config
        self.performance_config = config.performance

        # 并发控制
        self._write_semaphore = asyncio.Semaphore(
            self.performance_config.max_concurrent_writes
        )

        # 线程池用于CPU密集型操作
        self._executor = ThreadPoolExecutor(
            max_workers=min(4, self.performance_config.max_concurrent_writes)
        )

        # 写入统计
        self._write_stats = {
            'total_writes': 0,
            'successful_writes': 0,
            'failed_writes': 0,
            'total_ticks_saved': 0,
            'total_bytes_written': 0,
            'write_time_total': 0.0,
            'last_write_time': 0
        }

        # 错误重试配置
        self._max_retries = 3
        self._retry_delays = [1, 2, 5]  # 重试延迟（秒）

        # 活跃写入任务跟踪
        self._active_writes: Set[str] = set()
        self._write_locks: Dict[str, asyncio.Lock] = {}

        logger.info(f"AsyncTickSaver初始化完成 - "
                   f"最大并发写入: {self.performance_config.max_concurrent_writes}, "
                   f"批量大小: {self.performance_config.batch_size}, "
                   f"压缩: {config.storage.compression}")

    async def save_ticks(self, symbol: str, tick_data_list: List[TickerData]) -> bool:
        """保存tick数据到Parquet文件

        Args:
            symbol: 交易对符号
            tick_data_list: tick数据列表

        Returns:
            是否保存成功
        """
        if not tick_data_list:
            return True

        start_time = time.time()
        file_key = self._get_file_key(symbol, tick_data_list[-1].event_time)

        try:
            # 获取文件写入锁
            if file_key not in self._write_locks:
                self._write_locks[file_key] = asyncio.Lock()

            async with self._write_locks[file_key]:
                # 检查是否已有写入任务
                if file_key in self._active_writes:
                    logger.debug(f"文件 {file_key} 正在写入中，跳过本次保存")
                    return True

                self._active_writes.add(file_key)

                try:
                    # 使用信号量控制并发写入
                    async with self._write_semaphore:
                        success = await self._write_with_retry(
                            symbol, tick_data_list, file_key
                        )

                        # 更新统计信息
                        write_time = time.time() - start_time
                        self._update_write_stats(success, len(tick_data_list), write_time)

                        return success

                finally:
                    self._active_writes.discard(file_key)

        except Exception as e:
            logger.error(f"保存tick数据失败: {e}")
            self._write_stats['failed_writes'] += 1
            return False

    async def save_batch(self, tick_data_dict: Dict[str, List[TickerData]]) -> Dict[str, bool]:
        """批量保存多个交易对的tick数据

        Args:
            tick_data_dict: 按交易对分组的tick数据

        Returns:
            各交易对保存结果
        """
        if not tick_data_dict:
            return {}

        # 创建并发写入任务
        tasks = []
        for symbol, tick_list in tick_data_dict.items():
            if tick_list:  # 跳过空列表
                task = asyncio.create_task(self.save_ticks(symbol, tick_list))
                tasks.append((symbol, task))

        # 等待所有任务完成
        results = {}
        for symbol, task in tasks:
            try:
                result = await asyncio.wait_for(
                    task, timeout=self.performance_config.write_timeout_seconds
                )
                results[symbol] = result
            except asyncio.TimeoutError:
                logger.error(f"保存交易对 {symbol} 超时")
                results[symbol] = False
                task.cancel()
            except Exception as e:
                logger.error(f"保存交易对 {symbol} 失败: {e}")
                results[symbol] = False

        return results

    async def _write_with_retry(self, symbol: str, tick_data_list: List[TickerData],
                               file_key: str) -> bool:
        """带重试机制的写入操作

        Args:
            symbol: 交易对符号
            tick_data_list: tick数据列表
            file_key: 文件键

        Returns:
            是否写入成功
        """
        for attempt in range(self._max_retries):
            try:
                return await self._write_to_file(symbol, tick_data_list, file_key)

            except Exception as e:
                logger.warning(f"写入失败 (尝试 {attempt + 1}/{self._max_retries}): {e}")

                if attempt < self._max_retries - 1:
                    # 指数退避重试
                    delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
                    await asyncio.sleep(delay)
                else:
                    # 最后一次尝试失败
                    logger.error(f"写入最终失败: {symbol}")
                    return False

        return False

    async def _write_to_file(self, symbol: str, tick_data_list: List[TickerData],
                           file_key: str) -> bool:
        """写入Parquet文件

        Args:
            symbol: 交易对符号
            tick_data_list: tick数据列表
            file_key: 文件键

        Returns:
            是否写入成功
        """
        # 获取文件路径
        file_path = self._get_file_path(symbol, tick_data_list[0].event_time)
        logger.info(f"写入路径: {file_path} ，时间{tick_data_list[0].event_time}")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 转换为DataFrame
        df = await self._convert_to_dataframe(tick_data_list)
        if df.empty:
            return True

        # 使用线程池执行实际的文件写入
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._write_parquet_file,
            file_path,
            df,
            file_key
        )

    def _write_parquet_file(self, file_path: Path, df: pd.DataFrame, file_key: str) -> bool:
        """在线程池中执行Parquet文件写入

        Args:
            file_path: 文件路径
            df: 数据DataFrame
            file_key: 文件键

        Returns:
            是否写入成功
        """
        try:
            # 创建临时文件
            temp_path = file_path.with_suffix('.tmp')
            checksum_path = file_path.with_suffix('.json')

            # 写入临时文件
            compression = None if self.config.storage.compression == 'none' else self.config.storage.compression
            df.to_parquet(
                temp_path,
                engine='pyarrow',
                compression=compression,
                index=False
            )

            # 生成校验和
            checksum = self._calculate_checksum(temp_path)

            # 原子性重命名
            temp_path.rename(file_path)

            # 写入校验和文件
            if self.config.integrity.checksum_enabled:
                checksum_data = {
                    'file': file_path.name,
                    'checksum': checksum,
                    'algorithm': 'md5',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'row_count': len(df)
                }

                with open(checksum_path, 'w', encoding='utf-8') as f:
                    json.dump(checksum_data, f, indent=2)

            logger.debug(f"成功写入Parquet文件: {file_path} ({len(df)}行)")
            return True

        except Exception as e:
            logger.error(f"写入Parquet文件失败: {e}")
            # 清理临时文件
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            return False

    async def _convert_to_dataframe(self, tick_data_list: List[TickerData]) -> pd.DataFrame:
        """转换tick数据列表为DataFrame

        Args:
            tick_data_list: tick数据列表

        Returns:
            转换后的DataFrame
        """
        if not tick_data_list:
            return pd.DataFrame()

        def safe_timestamp_to_datetime(timestamp: int, field_name: str = "", symbol: str = ""):
            """安全的时间戳转换，处理各种异常时间戳"""
            logger.info(f"[SAFE_CONVERT] {symbol} {field_name}原始时间戳: {timestamp}")

            if timestamp == 0:
                logger.info(f"[SAFE_CONVERT] {symbol} {field_name}时间戳为0，返回NaT")
                return pd.NaT  # 返回Not a Time

            # 检查时间戳是否在合理范围内
            current_year = datetime.now().year
            # 允许的时间范围：2000年到2030年
            min_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            max_timestamp = datetime(2030, 12, 31, tzinfo=timezone.utc).timestamp() * 1000

            # 如果时间戳明显不在合理范围内，先进行修复尝试
            if timestamp < min_timestamp or timestamp > max_timestamp:
                logger.warning(f"[SAFE_CONVERT] {symbol} {field_name}时间戳超出合理范围: {timestamp}")

                # 修复尝试1：如果时间戳过大，尝试除以不同的因子
                if timestamp > 1e18:  # 可能是纳秒级时间戳
                    fixed_timestamp = timestamp // 1_000_000
                    logger.info(f"[SAFE_CONVERT] {symbol} {field_name}尝试纳秒转毫秒: {timestamp} → {fixed_timestamp}")
                    try:
                        dt = pd.to_datetime(fixed_timestamp, unit='ms', utc=True)
                        if min_timestamp <= fixed_timestamp <= max_timestamp:
                            logger.info(f"[SAFE_CONVERT] {symbol} {field_name}纳秒转毫秒成功: {dt}")
                            return dt
                    except:
                        pass

                if timestamp > 1e15:  # 可能是微秒级或错误放大的毫秒时间戳
                    for divisor in [1000, 1_000_000, 1_000_000_000]:
                        fixed_timestamp = timestamp // divisor
                        if min_timestamp <= fixed_timestamp <= max_timestamp:
                            try:
                                dt = pd.to_datetime(fixed_timestamp, unit='ms', utc=True)
                                logger.info(f"[SAFE_CONVERT] {symbol} {field_name}修复成功(除{divisor}): {timestamp} → {fixed_timestamp} → {dt}")
                                return dt
                            except:
                                pass
                    logger.warning(f"[SAFE_CONVERT] {symbol} {field_name}所有除法修复都失败")

                # 修复尝试2：如果时间戳过小，可能是秒级
                elif timestamp < 1e12:  # 可能是秒级时间戳
                    fixed_timestamp = timestamp * 1000
                    try:
                        dt = pd.to_datetime(fixed_timestamp, unit='ms', utc=True)
                        if min_timestamp <= fixed_timestamp <= max_timestamp:
                            logger.info(f"[SAFE_CONVERT] {symbol} {field_name}秒级转换成功: {timestamp} → {fixed_timestamp} → {dt}")
                            return dt
                    except:
                        pass

                # 所有修复尝试都失败，使用当前时间
                import time
                current_ms = int(time.time() * 1000)
                dt_current = pd.to_datetime(current_ms, unit='ms', utc=True)
                logger.error(f"[SAFE_CONVERT] {symbol} {field_name}修复失败，使用当前时间: 原始{timestamp} → 当前{dt_current}")
                return dt_current

            # 时间戳在合理范围内，直接转换
            try:
                dt = pd.to_datetime(timestamp, unit='ms', utc=True)
                logger.info(f"[SAFE_CONVERT] {symbol} {field_name}直接转换成功: {timestamp} → {dt}")
                return dt
            except Exception as e:
                logger.error(f"[SAFE_CONVERT] {symbol} {field_name}转换失败(时间戳{timestamp}): {e}")
                # 使用当前时间作为最后备选
                import time
                current_ms = int(time.time() * 1000)
                dt_current = pd.to_datetime(current_ms, unit='ms', utc=True)
                return dt_current

        # 批量转换为字典列表
        data_dicts = []
        for tick in tick_data_list:
            data_dicts.append({
                'symbol': tick.symbol,
                'price': float(tick.price),
                'price_change': float(tick.price_change),
                'price_change_percent': float(tick.price_change_percent),
                'weighted_avg_price': float(tick.weighted_avg_price),
                'open_price': float(tick.open_price),
                'high_price': float(tick.high_price),
                'low_price': float(tick.low_price),
                'volume': float(tick.volume),
                'quote_volume': float(tick.quote_volume),
                'open_time': safe_timestamp_to_datetime(tick.open_time, "open_time", tick.symbol),
                'close_time': safe_timestamp_to_datetime(tick.close_time, "close_time", tick.symbol),
                'event_time': safe_timestamp_to_datetime(tick.event_time, "event_time", tick.symbol),
                'first_id': int(tick.first_id),
                'last_id': int(tick.last_id),
                'count': int(tick.count),
                'last_quantity': float(tick.last_quantity),
                'created_at': datetime.now(timezone.utc)
            })

        return pd.DataFrame(data_dicts)

    def _get_file_key(self, symbol: str, timestamp: int) -> str:
        """生成文件键

        Args:
            symbol: 交易对符号
            timestamp: 时间戳

        Returns:
            文件键
        """
        def safe_timestamp_for_file_key(timestamp: int) -> int:
            """为文件键生成安全的时间戳"""
            logger.info(f"[FILE_KEY] 原始时间戳: {timestamp}")

            # 检查时间戳合理性范围
            current_year = datetime.now().year
            min_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            max_timestamp = datetime(2030, 12, 31, tzinfo=timezone.utc).timestamp() * 1000

            # 如果时间戳在合理范围内，直接返回
            if min_timestamp <= timestamp <= max_timestamp:
                logger.info(f"[FILE_KEY] 时间戳正常，直接使用: {timestamp}")
                return timestamp

            logger.warning(f"[FILE_KEY] 时间戳异常，尝试修复: {timestamp}")

            # 修复异常时间戳
            if timestamp > 1e18:  # 可能是纳秒级时间戳
                fixed_timestamp = timestamp // 1_000_000
                if min_timestamp <= fixed_timestamp <= max_timestamp:
                    logger.info(f"[FILE_KEY] 纳秒转毫秒修复成功: {timestamp} → {fixed_timestamp}")
                    return fixed_timestamp

            if timestamp > 1e15:  # 可能是微秒级或错误放大的毫秒时间戳
                for divisor in [1000, 1_000_000, 1_000_000_000]:
                    fixed_timestamp = timestamp // divisor
                    if min_timestamp <= fixed_timestamp <= max_timestamp:
                        logger.info(f"[FILE_KEY] 除法修复成功(除{divisor}): {timestamp} → {fixed_timestamp}")
                        return fixed_timestamp

            elif timestamp < 1e12:  # 可能是秒级时间戳
                fixed_timestamp = timestamp * 1000
                if min_timestamp <= fixed_timestamp <= max_timestamp:
                    logger.info(f"[FILE_KEY] 秒级修复成功: {timestamp} → {fixed_timestamp}")
                    return fixed_timestamp

            # 所有修复都失败，使用当前时间
            import time
            current_ms = int(time.time() * 1000)
            logger.error(f"[FILE_KEY] 修复失败，使用当前时间: {timestamp} → {current_ms}")
            return current_ms

        normalized_symbol = symbol.replace('/', '-')
        safe_timestamp = safe_timestamp_for_file_key(timestamp)

        try:
            dt = datetime.fromtimestamp(safe_timestamp / 1000, tz=timezone.utc)
            logger.info(f"[FILE_KEY] 时间戳转换成功: {safe_timestamp} → {dt}")
        except Exception as e:
            logger.error(f"[FILE_KEY] 时间戳转换失败: {safe_timestamp}, 错误: {e}")
            # 使用当前时间作为备选
            import time
            current_ms = int(time.time() * 1000)
            dt = datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc)
            logger.info(f"[FILE_KEY] 使用当前时间: {dt}")

        return f"{normalized_symbol}_{dt.year:04d}{dt.month:02d}{dt.day:02d}{dt.hour:02d}"

    def _get_file_path(self, symbol: str, timestamp: int) -> Path:
        """获取完整文件路径

        Args:
            symbol: 交易对符号
            timestamp: 时间戳

        Returns:
            完整文件路径
        """
        return self.config.get_storage_path(symbol, timestamp)

    def _calculate_checksum(self, file_path: Path) -> str:
        """计算文件MD5校验和

        Args:
            file_path: 文件路径

        Returns:
            MD5校验和
        """
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.warning(f"计算校验和失败: {e}")
            return ""

    def _update_write_stats(self, success: bool, tick_count: int, write_time: float):
        """更新写入统计信息

        Args:
            success: 是否成功
            tick_count: tick数量
            write_time: 写入时间
        """
        self._write_stats['total_writes'] += 1
        self._write_stats['write_time_total'] += write_time
        self._write_stats['last_write_time'] = time.time()

        if success:
            self._write_stats['successful_writes'] += 1
            self._write_stats['total_ticks_saved'] += tick_count
        else:
            self._write_stats['failed_writes'] += 1

    async def get_write_stats(self) -> Dict[str, any]:
        """获取写入统计信息

        Returns:
            统计信息字典
        """
        stats = self._write_stats.copy()

        # 计算平均写入时间
        if stats['total_writes'] > 0:
            stats['average_write_time'] = stats['write_time_total'] / stats['total_writes']
            stats['success_rate'] = (stats['successful_writes'] / stats['total_writes']) * 100
        else:
            stats['average_write_time'] = 0.0
            stats['success_rate'] = 0.0

        # 计算平均每秒写入的tick数
        if stats['write_time_total'] > 0:
            stats['ticks_per_second'] = stats['total_ticks_saved'] / stats['write_time_total']
        else:
            stats['ticks_per_second'] = 0.0

        stats['active_writes'] = len(self._active_writes)

        return stats

    async def cleanup(self):
        """清理资源"""
        try:
            # 等待所有活跃写入任务完成
            if self._active_writes:
                logger.info(f"等待 {len(self._active_writes)} 个写入任务完成...")
                # 这里可以添加等待逻辑，但要注意避免无限等待

            # 关闭线程池
            self._executor.shutdown(wait=True)

            logger.info("AsyncTickSaver清理完成")

        except Exception as e:
            logger.error(f"AsyncTickSaver清理失败: {e}")

    def __del__(self):
        """析构函数"""
        try:
            if hasattr(self, '_executor'):
                self._executor.shutdown(wait=False)
        except Exception:
            pass