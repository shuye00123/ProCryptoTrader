"""
数据完整性管理器

负责验证转存数据的完整性，检测和处理数据损坏，提供数据修复机制。
"""

import json
import hashlib
import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timezone
import logging
import pandas as pd
import pyarrow.parquet as pq

from .config_models import TickDataConfig, IntegrityConfig

logger = logging.getLogger(__name__)


class DataIntegrityManager:
    """数据完整性管理器

    提供数据验证、完整性检查、损坏检测和修复功能。
    """

    def __init__(self, config: TickDataConfig):
        self.config = config
        self.integrity_config = config.integrity

        # 验证统计
        self._validation_stats = {
            'files_validated': 0,
            'files_passed': 0,
            'files_failed': 0,
            'files_repaired': 0,
            'total_errors': 0,
            'last_validation_time': 0
        }

        # 已知的损坏文件
        self._corrupted_files: Set[Path] = set()

        logger.info(f"DataIntegrityManager初始化完成 - "
                   f"验证启用: {self.integrity_config.enable_validation}, "
                   f"校验和启用: {self.integrity_config.checksum_enabled}, "
                   f"自动修复: {self.integrity_config.auto_repair}")

    async def validate_file(self, file_path: Path) -> Dict[str, any]:
        """验证单个Parquet文件的完整性

        Args:
            file_path: 文件路径

        Returns:
            验证结果字典
        """
        if not file_path.exists():
            return {
                'valid': False,
                'error': '文件不存在',
                'file_path': str(file_path)
            }

        start_time = datetime.now()
        validation_result = {
            'file_path': str(file_path),
            'valid': False,
            'error': None,
            'checksum_valid': True,
            'row_count': 0,
            'file_size': 0,
            'validation_time': 0,
            'recommendations': []
        }

        try:
            # 基础文件检查
            validation_result.update(self._basic_file_check(file_path))

            # Parquet格式验证
            parquet_result = await self._validate_parquet_format(file_path)
            validation_result.update(parquet_result)

            # 校验和验证
            if self.integrity_config.checksum_enabled:
                checksum_result = await self._validate_checksum(file_path)
                validation_result.update(checksum_result)

            # 数据质量检查
            if validation_result.get('row_count', 0) > 0:
                quality_result = await self._validate_data_quality(file_path)
                validation_result.update(quality_result)

            # 综合判断
            validation_result['valid'] = self._is_file_valid(validation_result)

            # 生成修复建议
            if not validation_result['valid'] and self.integrity_config.auto_repair:
                validation_result['recommendations'] = self._generate_repair_recommendations(validation_result)

        except Exception as e:
            validation_result['valid'] = False
            validation_result['error'] = str(e)
            logger.error(f"验证文件失败 {file_path}: {e}")

        finally:
            # 计算验证时间
            validation_time = (datetime.now() - start_time).total_seconds()
            validation_result['validation_time'] = validation_time

            # 更新统计信息
            self._update_validation_stats(validation_result)

        return validation_result

    async def validate_directory(self, directory_path: Path,
                               recursive: bool = True) -> Dict[str, any]:
        """验证目录中的所有Parquet文件

        Args:
            directory_path: 目录路径
            recursive: 是否递归验证子目录

        Returns:
            目录验证结果
        """
        if not directory_path.exists() or not directory_path.is_dir():
            return {
                'valid': False,
                'error': '目录不存在或不是有效目录',
                'directory_path': str(directory_path)
            }

        start_time = datetime.now()
        logger.info(f"开始验证目录: {directory_path}")

        # 查找所有Parquet文件
        parquet_files = []
        if recursive:
            parquet_files = list(directory_path.rglob("*.parquet"))
        else:
            parquet_files = list(directory_path.glob("*.parquet"))

        logger.info(f"找到 {len(parquet_files)} 个Parquet文件")

        # 并发验证文件
        validation_tasks = []
        for file_path in parquet_files:
            task = asyncio.create_task(self.validate_file(file_path))
            validation_tasks.append(task)

        # 等待所有验证完成
        validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

        # 统计结果
        total_files = len(parquet_files)
        valid_files = sum(1 for result in validation_results
                         if isinstance(result, dict) and result.get('valid', False))
        failed_files = total_files - valid_files

        directory_result = {
            'directory_path': str(directory_path),
            'total_files': total_files,
            'valid_files': valid_files,
            'failed_files': failed_files,
            'success_rate': (valid_files / total_files * 100) if total_files > 0 else 0,
            'validation_time': (datetime.now() - start_time).total_seconds(),
            'file_results': []
        }

        # 添加详细结果
        for i, result in enumerate(validation_results):
            if isinstance(result, dict):
                directory_result['file_results'].append(result)
            elif isinstance(result, Exception):
                directory_result['file_results'].append({
                    'file_path': str(parquet_files[i]),
                    'valid': False,
                    'error': f"验证异常: {result}"
                })

        logger.info(f"目录验证完成 - "
                   f"总计: {total_files}, "
                   f"有效: {valid_files}, "
                   f"失败: {failed_files}, "
                   f"成功率: {directory_result['success_rate']:.1f}%")

        return directory_result

    async def repair_file(self, file_path: Path) -> Dict[str, any]:
        """修复损坏的Parquet文件

        Args:
            file_path: 损坏文件路径

        Returns:
            修复结果
        """
        if not self.integrity_config.auto_repair:
            return {
                'success': False,
                'error': '自动修复功能未启用',
                'file_path': str(file_path)
            }

        logger.info(f"尝试修复文件: {file_path}")

        repair_result = {
            'file_path': str(file_path),
            'success': False,
            'original_size': 0,
            'repaired_size': 0,
            'rows_recovered': 0,
            'repair_method': None,
            'error': None
        }

        try:
            # 获取原始文件大小
            if file_path.exists():
                repair_result['original_size'] = file_path.stat().st_size

            # 尝试不同的修复方法
            for method in ['pyarrow_repair', 'pandas_repair', 'partial_repair']:
                try:
                    method_result = await self._attempt_repair(file_path, method)
                    if method_result['success']:
                        repair_result.update(method_result)
                        repair_result['repair_method'] = method
                        self._validation_stats['files_repaired'] += 1
                        break
                except Exception as e:
                    logger.debug(f"修复方法 {method} 失败: {e}")
                    continue

            if not repair_result['success']:
                repair_result['error'] = '所有修复方法都失败了'

        except Exception as e:
            repair_result['error'] = str(e)
            logger.error(f"修复文件失败: {e}")

        return repair_result

    def _basic_file_check(self, file_path: Path) -> Dict[str, any]:
        """基础文件检查

        Args:
            file_path: 文件路径

        Returns:
            检查结果
        """
        try:
            stat = file_path.stat()
            return {
                'file_size': stat.st_size,
                'modified_time': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                'readable': file_path.is_file(),
                'writable': os.access(file_path, os.W_OK) if 'os' in globals() else True
            }
        except Exception as e:
            return {
                'file_size': 0,
                'error': f"基础文件检查失败: {e}"
            }

    async def _validate_parquet_format(self, file_path: Path) -> Dict[str, any]:
        """验证Parquet格式

        Args:
            file_path: 文件路径

        Returns:
            格式验证结果
        """
        try:
            # 读取Parquet文件元数据
            parquet_file = pq.ParquetFile(file_path)

            # 获取基本元数据
            metadata = parquet_file.metadata
            schema = parquet_file.schema_arrow

            # 检查行数
            row_count = metadata.num_rows

            # 检查列数和列名
            column_count = metadata.num_columns
            column_names = schema.names

            # 读取前几行数据进行基本验证
            table = parquet_file.read_row_group(0)
            sample_rows = len(table)

            return {
                'row_count': row_count,
                'column_count': column_count,
                'column_names': column_names,
                'sample_rows': sample_rows,
                'parquet_version': metadata.format_version,
                'compression': metadata.compression
            }

        except Exception as e:
            return {
                'row_count': 0,
                'format_error': f"Parquet格式验证失败: {e}"
            }

    async def _validate_checksum(self, file_path: Path) -> Dict[str, any]:
        """验证文件校验和

        Args:
            file_path: 文件路径

        Returns:
            校验和验证结果
        """
        checksum_path = file_path.with_suffix('.json')

        if not checksum_path.exists():
            return {
                'checksum_valid': True,
                'checksum_info': '校验和文件不存在'
            }

        try:
            # 读取校验和文件
            with open(checksum_path, 'r', encoding='utf-8') as f:
                checksum_data = json.load(f)

            # 计算当前文件的校验和
            current_checksum = self._calculate_file_checksum(file_path)
            stored_checksum = checksum_data.get('checksum', '')

            checksum_valid = current_checksum == stored_checksum

            return {
                'checksum_valid': checksum_valid,
                'stored_checksum': stored_checksum,
                'current_checksum': current_checksum,
                'checksum_algorithm': checksum_data.get('algorithm', 'md5')
            }

        except Exception as e:
            return {
                'checksum_valid': False,
                'checksum_error': f"校验和验证失败: {e}"
            }

    async def _validate_data_quality(self, file_path: Path) -> Dict[str, any]:
        """验证数据质量

        Args:
            file_path: 文件路径

        Returns:
            数据质量验证结果
        """
        try:
            # 读取文件进行数据质量检查
            df = pd.read_parquet(file_path)

            quality_checks = {
                'null_values': df.isnull().sum().to_dict(),
                'duplicate_rows': df.duplicated().sum(),
                'price_anomalies': self._check_price_anomalies(df),
                'timestamp_gaps': self._check_timestamp_gaps(df),
                'data_range': self._check_data_range(df)
            }

            # 计算质量分数
            quality_score = self._calculate_quality_score(quality_checks)

            return {
                'data_quality_score': quality_score,
                'quality_checks': quality_checks,
                'data_validation_passed': quality_score >= 80
            }

        except Exception as e:
            return {
                'data_quality_score': 0,
                'quality_error': f"数据质量检查失败: {e}"
            }

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """计算文件MD5校验和

        Args:
            file_path: 文件路径

        Returns:
            MD5校验和
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _check_price_anomalies(self, df: pd.DataFrame) -> Dict[str, any]:
        """检查价格异常

        Args:
            df: 数据DataFrame

        Returns:
            价格异常检查结果
        """
        try:
            if 'price' not in df.columns:
                return {'error': '价格列不存在'}

            price_series = df['price']

            # 基本统计
            price_stats = {
                'mean': float(price_series.mean()),
                'std': float(price_series.std()),
                'min': float(price_series.min()),
                'max': float(price_series.max())
            }

            # 检测异常值 (使用3σ规则)
            mean = price_stats['mean']
            std = price_stats['std']
            outliers = ((price_series < (mean - 3 * std)) |
                       (price_series > (mean + 3 * std))).sum()

            return {
                'price_stats': price_stats,
                'outlier_count': int(outliers),
                'outlier_percentage': float((outliers / len(price_series)) * 100)
            }

        except Exception as e:
            return {'error': f"价格异常检查失败: {e}"}

    def _check_timestamp_gaps(self, df: pd.DataFrame) -> Dict[str, any]:
        """检查时间戳间隔

        Args:
            df: 数据DataFrame

        Returns:
            时间戳间隔检查结果
        """
        try:
            timestamp_col = None
            for col in ['event_time', 'timestamp', 'created_at']:
                if col in df.columns:
                    timestamp_col = col
                    break

            if timestamp_col is None:
                return {'error': '时间戳列不存在'}

            timestamps = pd.to_datetime(df[timestamp_col])
            timestamps = timestamps.sort_values()

            # 计算时间间隔
            time_diffs = timestamps.diff().dropna()

            return {
                'total_records': len(df),
                'time_span_hours': (timestamps.max() - timestamps.min()).total_seconds() / 3600,
                'average_interval_seconds': float(time_diffs.mean().total_seconds()),
                'max_interval_seconds': float(time_diffs.max().total_seconds()),
                'gaps_count': (time_diffs > pd.Timedelta(minutes=10)).sum()
            }

        except Exception as e:
            return {'error': f"时间戳间隔检查失败: {e}"}

    def _check_data_range(self, df: pd.DataFrame) -> Dict[str, any]:
        """检查数据范围

        Args:
            df: 数据DataFrame

        Returns:
            数据范围检查结果
        """
        try:
            range_info = {}
            for col in ['price', 'volume', 'quote_volume']:
                if col in df.columns:
                    series = df[col]
                    range_info[col] = {
                        'min': float(series.min()),
                        'max': float(series.max()),
                        'mean': float(series.mean()),
                        'negative_count': int((series < 0).sum())
                    }

            return range_info

        except Exception as e:
            return {'error': f"数据范围检查失败: {e}"}

    def _calculate_quality_score(self, quality_checks: Dict[str, any]) -> float:
        """计算数据质量分数

        Args:
            quality_checks: 质量检查结果

        Returns:
            质量分数 (0-100)
        """
        score = 100.0

        # 空值检查 (-20分)
        null_counts = quality_checks.get('null_values', {})
        total_nulls = sum(null_counts.values())
        if total_nulls > 0:
            score -= min(20, total_nulls * 0.1)

        # 重复行检查 (-15分)
        duplicate_rows = quality_checks.get('duplicate_rows', 0)
        if duplicate_rows > 0:
            score -= min(15, duplicate_rows * 0.5)

        # 价格异常检查 (-25分)
        price_anomalies = quality_checks.get('price_anomalies', {})
        if 'outlier_percentage' in price_anomalies:
            score -= min(25, price_anomalies['outlier_percentage'] * 2)

        # 时间戳间隔检查 (-20分)
        timestamp_gaps = quality_checks.get('timestamp_gaps', {})
        if 'gaps_count' in timestamp_gaps:
            score -= min(20, timestamp_gaps['gaps_count'] * 0.1)

        # 数据范围检查 (-20分)
        data_range = quality_checks.get('data_range', {})
        for col_info in data_range.values():
            if isinstance(col_info, dict) and 'negative_count' in col_info:
                negative_count = col_info['negative_count']
                if negative_count > 0:
                    score -= min(20, negative_count * 0.1)

        return max(0, score)

    def _is_file_valid(self, validation_result: Dict[str, any]) -> bool:
        """判断文件是否有效

        Args:
            validation_result: 验证结果

        Returns:
            是否有效
        """
        # 检查基础错误
        if validation_result.get('error'):
            return False

        # 检查格式错误
        if validation_result.get('format_error'):
            return False

        # 检查校验和
        if not validation_result.get('checksum_valid', True):
            return False

        # 检查数据质量
        data_validation = validation_result.get('data_validation_passed', True)
        if not data_validation:
            return False

        # 检查基本数据
        if validation_result.get('row_count', 0) == 0:
            return False

        return True

    def _generate_repair_recommendations(self, validation_result: Dict[str, any]) -> List[str]:
        """生成修复建议

        Args:
            validation_result: 验证结果

        Returns:
            修复建议列表
        """
        recommendations = []

        error = validation_result.get('error')
        if error:
            if "Parquet" in error:
                recommendations.append("尝试使用pyarrow或pandas重新读取并保存文件")
            elif "权限" in error or "permission" in error.lower():
                recommendations.append("检查文件权限设置")
            elif "不存在" in error:
                recommendations.append("检查文件路径是否正确")

        if not validation_result.get('checksum_valid', True):
            recommendations.append("重新生成校验和文件")

        data_quality = validation_result.get('data_quality_score', 100)
        if data_quality < 80:
            recommendations.append("进行数据清洗和质量修复")

        return recommendations

    async def _attempt_repair(self, file_path: Path, method: str) -> Dict[str, any]:
        """尝试修复文件

        Args:
            file_path: 文件路径
            method: 修复方法

        Returns:
            修复结果
        """
        backup_path = file_path.with_suffix('.backup')

        try:
            # 创建备份
            if file_path.exists():
                shutil.copy2(file_path, backup_path)

            if method == 'pyarrow_repair':
                return await self._pyarrow_repair(file_path)
            elif method == 'pandas_repair':
                return await self._pandas_repair(file_path)
            elif method == 'partial_repair':
                return await self._partial_repair(file_path)
            else:
                return {'success': False, 'error': f'未知修复方法: {method}'}

        except Exception as e:
            # 恢复备份
            if backup_path.exists() and not file_path.exists():
                shutil.copy2(backup_path, file_path)
            raise e

        finally:
            # 清理备份文件
            if backup_path.exists():
                backup_path.unlink()

    async def _pyarrow_repair(self, file_path: Path) -> Dict[str, any]:
        """使用pyarrow修复文件

        Args:
            file_path: 文件路径

        Returns:
            修复结果
        """
        try:
            # 尝试读取并重新保存
            table = pq.read_table(file_path)

            # 获取原始行数
            original_rows = len(table)

            # 重新保存文件
            pq.write_table(table, file_path, compression=self.config.storage.compression)

            return {
                'success': True,
                'rows_recovered': original_rows,
                'repaired_size': file_path.stat().st_size
            }

        except Exception as e:
            return {'success': False, 'error': f"pyarrow修复失败: {e}"}

    async def _pandas_repair(self, file_path: Path) -> Dict[str, any]:
        """使用pandas修复文件

        Args:
            file_path: 文件路径

        Returns:
            修复结果
        """
        try:
            # 尝试读取并重新保存
            df = pd.read_parquet(file_path)

            # 清理数据
            df = df.dropna()
            df = df.drop_duplicates()

            # 获取修复后的行数
            repaired_rows = len(df)

            # 重新保存文件
            df.to_parquet(file_path, compression=self.config.storage.compression)

            return {
                'success': True,
                'rows_recovered': repaired_rows,
                'repaired_size': file_path.stat().st_size
            }

        except Exception as e:
            return {'success': False, 'error': f"pandas修复失败: {e}"}

    async def _partial_repair(self, file_path: Path) -> Dict[str, any]:
        """部分修复文件

        Args:
            file_path: 文件路径

        Returns:
            修复结果
        """
        try:
            # 尝试读取行组进行修复
            parquet_file = pq.ParquetFile(file_path)

            all_data = []
            for i in range(parquet_file.num_row_groups):
                try:
                    table = parquet_file.read_row_group(i)
                    all_data.append(table)
                except Exception:
                    continue  # 跳过损坏的行组

            if all_data:
                # 合并有效的行组
                combined_table = pa.concat_tables(all_data)
                repaired_rows = len(combined_table)

                # 重新保存
                pq.write_table(combined_table, file_path,
                              compression=self.config.storage.compression)

                return {
                    'success': True,
                    'rows_recovered': repaired_rows,
                    'repaired_size': file_path.stat().st_size
                }
            else:
                return {'success': False, 'error': '无法读取任何有效数据'}

        except Exception as e:
            return {'success': False, 'error': f"部分修复失败: {e}"}

    def _update_validation_stats(self, validation_result: Dict[str, any]):
        """更新验证统计信息

        Args:
            validation_result: 验证结果
        """
        self._validation_stats['files_validated'] += 1
        self._validation_stats['last_validation_time'] = datetime.now().timestamp()

        if validation_result.get('valid', False):
            self._validation_stats['files_passed'] += 1
        else:
            self._validation_stats['files_failed'] += 1
            # 计算错误数量
            errors = 0
            if validation_result.get('error'):
                errors += 1
            if not validation_result.get('checksum_valid', True):
                errors += 1
            if not validation_result.get('data_validation_passed', True):
                errors += 1

            self._validation_stats['total_errors'] += errors

    def get_validation_stats(self) -> Dict[str, any]:
        """获取验证统计信息

        Returns:
            统计信息字典
        """
        stats = self._validation_stats.copy()

        # 计算成功率
        if stats['files_validated'] > 0:
            stats['success_rate'] = (stats['files_passed'] / stats['files_validated']) * 100
        else:
            stats['success_rate'] = 0.0

        stats['corrupted_files_count'] = len(self._corrupted_files)

        return stats