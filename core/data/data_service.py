"""
简化的数据服务层

提供统一的数据访问接口，基于DataManager实现。
移除复杂的Repository架构，简化为直接的数据管理。
"""

from typing import Dict, List, Optional, Any, Union
import pandas as pd
from datetime import datetime, timedelta
import logging
from pathlib import Path

from .data_manager import DataManager
from .data_fetcher import DataFetcher
from .data_validator import DataValidator
from ..exceptions import DataError, ValidationError

logger = logging.getLogger(__name__)


class DataService:
    """
    简化的数据服务

    提供统一的数据访问和管理接口，基于传统DataManager实现。
    移除了Repository架构，保持简洁高效的数据访问模式。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据服务

        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

        # 初始化数据管理器
        self.data_manager = DataManager(self.config)
        self.data_fetcher = DataFetcher()
        self.data_validator = DataValidator()

        # 统计信息
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'local_hits': 0,
            'remote_hits': 0,
            'errors': 0,
            'avg_response_time': 0.0
        }

    def get_ohlcv_data(
        self,
        symbol: str,
        timeframe: str = '1h',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            start_date: 开始日期
            end_date: 结束日期
            limit: 数据条数限制

        Returns:
            pd.DataFrame: OHLCV数据
        """
        try:
            import time
            start_time = time.time()

            # 1. 尝试从本地获取
            data = self.data_manager.load_data(symbol, timeframe, start_date, end_date)

            if not data.empty:
                self.stats['local_hits'] += 1
                self.logger.info(f"从本地获取数据: {symbol}/{timeframe}, {len(data)} 条记录")
            else:
                # 2. 从远程获取并保存
                self.logger.info(f"从远程获取数据: {symbol}/{timeframe}")
                data = self.data_fetcher.fetch_ohlcv(symbol, timeframe, limit)

                if not data.empty:
                    self.data_manager.save_data(data, symbol, timeframe)
                    self.stats['remote_hits'] += 1

            # 3. 验证数据质量
            if not data.empty:
                validation_result = self.data_validator.validate_ohlc_data(data)
                if not validation_result['is_valid']:
                    self.logger.warning(f"数据质量验证警告: {validation_result['warnings']}")
                else:
                    self.logger.debug(f"数据质量评分: {validation_result['quality_score']:.3f}")

            # 更新统计
            response_time = (time.time() - start_time) * 1000
            self.stats['total_requests'] += 1
            self.stats['avg_response_time'] = (
                (self.stats['avg_response_time'] * (self.stats['total_requests'] - 1) + response_time) /
                self.stats['total_requests']
            )

            return data

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"获取数据失败 {symbol}/{timeframe}: {e}")
            raise DataError(f"无法获取数据: {symbol}/{timeframe}") from e

    def save_data(
        self,
        data: pd.DataFrame,
        symbol: str,
        timeframe: str = '1h',
        overwrite: bool = False
    ) -> bool:
        """
        保存数据

        Args:
            data: 数据DataFrame
            symbol: 交易对符号
            timeframe: 时间框架
            overwrite: 是否覆盖现有数据

        Returns:
            bool: 是否保存成功
        """
        try:
            # 验证数据
            validation_result = self.data_validator.validate_ohlc_data(data)
            if not validation_result['is_valid']:
                error_msg = f"数据验证失败: {validation_result['errors']}"
                self.logger.error(error_msg)
                raise ValidationError(error_msg)

            # 保存数据
            success = self.data_manager.save_data(data, symbol, timeframe, overwrite)

            if success:
                self.logger.info(f"数据已保存: {symbol}/{timeframe}, {len(data)} 条记录")

            return success

        except Exception as e:
            self.logger.error(f"保存数据失败 {symbol}/{timeframe}: {e}")
            raise DataError(f"无法保存数据: {symbol}/{timeframe}") from e

    def update_data(
        self,
        symbol: str,
        timeframe: str = '1h',
        limit: int = 500
    ) -> bool:
        """
        更新数据（增量获取最新数据）

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            limit: 获取条数

        Returns:
            bool: 是否更新成功
        """
        try:
            success = self.data_manager.update_data(symbol, timeframe, limit)

            if success:
                self.logger.info(f"数据已更新: {symbol}/{timeframe}")

            return success

        except Exception as e:
            self.logger.error(f"更新数据失败 {symbol}/{timeframe}: {e}")
            raise DataError(f"无法更新数据: {symbol}/{timeframe}") from e

    def list_symbols(self) -> List[str]:
        """
        获取可用的交易对列表

        Returns:
            List[str]: 交易对列表
        """
        try:
            return self.data_fetcher.get_symbols()
        except Exception as e:
            self.logger.error(f"获取交易对列表失败: {e}")
            return []

    def list_timeframes(self) -> List[str]:
        """
        获取支持的时间框架列表

        Returns:
            List[str]: 时间框架列表
        """
        try:
            return self.data_fetcher.get_timeframes()
        except Exception as e:
            self.logger.error(f"获取时间框架列表失败: {e}")
            return []

    def validate_data(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        验证数据质量

        Args:
            data: 要验证的数据

        Returns:
            Dict[str, Any]: 验证结果
        """
        try:
            return self.data_validator.validate_ohlc_data(data)
        except Exception as e:
            self.logger.error(f"数据验证失败: {e}")
            return {
                'is_valid': False,
                'errors': [str(e)],
                'warnings': [],
                'quality_score': 0.0
            }

    def get_service_stats(self) -> Dict[str, Any]:
        """
        获取服务统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        return self.stats.copy()

    def cleanup_old_data(self, days: int = 30) -> int:
        """
        清理过期数据

        Args:
            days: 保留天数

        Returns:
            int: 清理的文件数量
        """
        try:
            count = 0
            cutoff_date = datetime.now() - timedelta(days=days)
            data_dir = Path(self.data_manager.data_dir)

            for file_path in data_dir.rglob("*.parquet"):
                try:
                    # 检查文件修改时间
                    if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_date:
                        file_path.unlink()
                        count += 1
                except Exception as e:
                    self.logger.warning(f"删除文件失败 {file_path}: {e}")

            if count > 0:
                self.logger.info(f"清理了 {count} 个过期数据文件")

            return count

        except Exception as e:
            self.logger.error(f"清理过期数据失败: {e}")
            return 0

    def get_data_info(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        获取数据信息

        Args:
            symbol: 交易对符号
            timeframe: 时间框架

        Returns:
            Dict[str, Any]: 数据信息
        """
        try:
            data = self.data_manager.load_data(symbol, timeframe)

            if data.empty:
                return {'exists': False}

            return {
                'exists': True,
                'row_count': len(data),
                'date_range': {
                    'start': data.index[0].strftime('%Y-%m-%d %H:%M:%S'),
                    'end': data.index[-1].strftime('%Y-%m-%d %H:%M:%S')
                },
                'columns': list(data.columns),
                'size_mb': data.memory_usage(deep=True).sum() / (1024 * 1024)
            }

        except Exception as e:
            self.logger.error(f"获取数据信息失败 {symbol}/{timeframe}: {e}")
            return {'exists': False, 'error': str(e)}


# 兼容性别名，支持旧代码
SimpleDataService = DataService