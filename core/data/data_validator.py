"""
数据验证器实现

提供全面的数据质量验证和清理功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging

from ..exceptions import ValidationError, DataError

logger = logging.getLogger(__name__)


class OHLCVDataValidator:
    """
    OHLCV数据验证器

    提供OHLCV数据的全面验证和清理功能。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化验证器

        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

        # 验证规则配置
        self.required_columns = ['open', 'high', 'low', 'close', 'volume']
        self.numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        self.min_price = self.config.get('min_price', 0.0)
        self.max_price_change_pct = self.config.get('max_price_change_pct', 0.5)  # 50%
        self.allow_duplicates = self.config.get('allow_duplicates', False)
        self.allow_gaps = self.config.get('allow_gaps', True)

    def validate_ohlcv_data(self, data: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        验证OHLCV数据

        Args:
            data: OHLCV数据

        Returns:
            Tuple[bool, List[str]]: (是否有效, 错误信息列表)
        """
        errors = []

        if data.empty:
            errors.append("数据为空")
            return False, errors

        # 检查必需列
        missing_columns = [col for col in self.required_columns if col not in data.columns]
        if missing_columns:
            errors.append(f"缺少必需列: {', '.join(missing_columns)}")

        # 检查数据类型
        for col in self.numeric_columns:
            if col in data.columns:
                if not pd.api.types.is_numeric_dtype(data[col]):
                    try:
                        data[col] = pd.to_numeric(data[col], errors='coerce')
                        if data[col].isna().any():
                            errors.append(f"列 {col} 包含非数值数据")
                    except:
                        errors.append(f"列 {col} 无法转换为数值类型")

        # 检查空值
        null_counts = data.isnull().sum()
        for col, count in null_counts.items():
            if col in self.required_columns and count > 0:
                errors.append(f"列 {col} 包含 {count} 个空值")

        # 检查数值有效性
        if all(col in data.columns for col in ['open', 'high', 'low', 'close']):
            # 检查负值
            price_columns = ['open', 'high', 'low', 'close']
            for col in price_columns:
                if (data[col] < self.min_price).any():
                    invalid_count = (data[col] < self.min_price).sum()
                    errors.append(f"列 {col} 包含 {invalid_count} 个小于最小值的数值")

            # 检查成交量
            if 'volume' in data.columns and (data['volume'] < 0).any():
                invalid_count = (data['volume'] < 0).sum()
                errors.append(f"成交量列包含 {invalid_count} 个负值")

            # 检查OHLC逻辑
            self._validate_ohlc_logic(data, errors)

        # 检查时间索引
        if not isinstance(data.index, pd.DatetimeIndex):
            errors.append("数据索引不是时间类型")
        else:
            self._validate_time_index(data, errors)

        # 检查重复数据
        if not self.allow_duplicates and data.index.duplicated().any():
            duplicate_count = data.index.duplicated().sum()
            errors.append(f"包含 {duplicate_count} 个重复的时间索引")

        return len(errors) == 0, errors

    def validate_symbol(self, symbol: str) -> bool:
        """
        验证交易对

        Args:
            symbol: 交易对

        Returns:
            bool: 是否有效
        """
        if not symbol or not isinstance(symbol, str):
            return False

        # 基本格式验证
        if '/' not in symbol:
            return False

        # 检查交易对格式
        parts = symbol.split('/')
        if len(parts) != 2:
            return False

        base, quote = parts
        if not base.strip() or not quote.strip():
            return False

        # 检查字符有效性
        for part in parts:
            if not part.replace('-', '').replace('_', '').isalnum():
                return False

        return True

    def validate_timeframe(self, timeframe: str) -> bool:
        """
        验证时间框架

        Args:
            timeframe: 时间框架

        Returns:
            bool: 是否有效
        """
        if not timeframe or not isinstance(timeframe, str):
            return False

        if len(timeframe) < 2:
            return False

        # 解析数值和单位
        unit = timeframe[-1].lower()
        value_part = timeframe[:-1]

        # 检查单位
        valid_units = ['m', 'h', 'd', 'w', 'M']
        if unit not in valid_units:
            return False

        # 检查数值
        try:
            value = int(value_part)
            return value > 0
        except ValueError:
            return False

    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        清理数据

        Args:
            data: 原始数据

        Returns:
            pd.DataFrame: 清理后的数据
        """
        if data.empty:
            return data.copy()

        cleaned = data.copy()

        # 移除完全重复的行
        if not self.allow_duplicates:
            cleaned = cleaned[~cleaned.index.duplicated(keep='last')]

        # 处理异常值
        if all(col in cleaned.columns for col in ['open', 'high', 'low', 'close']):
            # 修复OHLC逻辑错误
            cleaned = self._fix_ohlc_logic(cleaned)

            # 移除极端价格变化
            cleaned = self._remove_extreme_price_changes(cleaned)

        # 处理空值
        cleaned = self._handle_missing_values(cleaned)

        # 确保时间索引排序
        if isinstance(cleaned.index, pd.DatetimeIndex):
            cleaned = cleaned.sort_index()

        return cleaned

    def get_data_quality_score(self, data: pd.DataFrame) -> float:
        """
        计算数据质量分数

        Args:
            data: 数据

        Returns:
            float: 质量分数 (0-1)
        """
        if data.empty:
            return 0.0

        score = 1.0

        # 完整性评分 (30%)
        completeness = 1.0 - (data.isnull().sum().sum() / (len(data) * len(data.columns)))
        score -= (1.0 - completeness) * 0.3

        # 唯一性评分 (20%)
        if not self.allow_duplicates:
            uniqueness = 1.0 - (data.index.duplicated().sum() / len(data))
            score -= (1.0 - uniqueness) * 0.2

        # 逻辑一致性评分 (30%)
        if all(col in data.columns for col in ['open', 'high', 'low', 'close']):
            consistency_score = self._calculate_consistency_score(data)
            score -= (1.0 - consistency_score) * 0.3

        # 时间连续性评分 (20%)
        if isinstance(data.index, pd.DatetimeIndex):
            continuity_score = self._calculate_time_continuity_score(data)
            score -= (1.0 - continuity_score) * 0.2

        return max(0.0, min(1.0, score))

    def get_validation_report(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        获取详细的验证报告

        Args:
            data: 数据

        Returns:
            Dict[str, Any]: 验证报告
        """
        is_valid, errors = self.validate_ohlcv_data(data)
        quality_score = self.get_data_quality_score(data)

        report = {
            'is_valid': is_valid,
            'quality_score': quality_score,
            'error_count': len(errors),
            'errors': errors,
            'statistics': {
                'row_count': len(data),
                'column_count': len(data.columns),
                'null_count': data.isnull().sum().sum(),
                'duplicate_count': data.index.duplicated().sum() if hasattr(data.index, 'duplicated') else 0
            }
        }

        # 添加时间统计
        if isinstance(data.index, pd.DatetimeIndex):
            report['time_statistics'] = {
                'start_time': data.index.min(),
                'end_time': data.index.max(),
                'duration_days': (data.index.max() - data.index.min()).days,
                'has_gaps': not self._has_continuous_time_index(data)
            }

        # 添加价格统计
        if all(col in data.columns for col in ['open', 'high', 'low', 'close']):
            price_data = data[['open', 'high', 'low', 'close']]
            report['price_statistics'] = {
                'mean_price': price_data.mean().mean(),
                'price_volatility': price_data.std().mean(),
                'extreme_changes': self._count_extreme_changes(data)
            }

        return report

    # 私有方法

    def _validate_ohlc_logic(self, data: pd.DataFrame, errors: List[str]):
        """验证OHLC逻辑"""
        try:
            # 检查 high >= low
            invalid_high_low = data['high'] < data['low']
            if invalid_high_low.any():
                count = invalid_high_low.sum()
                errors.append(f"包含 {count} 条 high < low 的记录")

            # 检查 high >= open, close
            invalid_high_open = data['high'] < data['open']
            if invalid_high_open.any():
                count = invalid_high_open.sum()
                errors.append(f"包含 {count} 条 high < open 的记录")

            invalid_high_close = data['high'] < data['close']
            if invalid_high_close.any():
                count = invalid_high_close.sum()
                errors.append(f"包含 {count} 条 high < close 的记录")

            # 检查 low <= open, close
            invalid_low_open = data['low'] > data['open']
            if invalid_low_open.any():
                count = invalid_low_open.sum()
                errors.append(f"包含 {count} 条 low > open 的记录")

            invalid_low_close = data['low'] > data['close']
            if invalid_low_close.any():
                count = invalid_low_close.sum()
                errors.append(f"包含 {count} 条 low > close 的记录")

        except Exception as e:
            errors.append(f"OHLC逻辑验证失败: {e}")

    def _validate_time_index(self, data: pd.DataFrame, errors: List[str]):
        """验证时间索引"""
        try:
            # 检查时间范围
            min_time = data.index.min()
            max_time = data.index.max()

            if min_time > max_time:
                errors.append("时间索引范围无效")

            # 检查时间连续性（如果不允许间隔）
            if not self.allow_gaps and len(data) > 1:
                if not self._has_continuous_time_index(data):
                    errors.append("时间索引不连续")

        except Exception as e:
            errors.append(f"时间索引验证失败: {e}")

    def _has_continuous_time_index(self, data: pd.DataFrame) -> bool:
        """检查时间索引是否连续"""
        if len(data) <= 1:
            return True

        # 计算预期的时间间隔（取最小间隔作为基准）
        time_diffs = data.index.to_series().diff().dropna()
        min_diff = time_diffs.min()

        # 检查所有间隔是否为基准间隔的整数倍
        expected_diffs = time_diffs.apply(lambda x: x.total_seconds() / min_diff.total_seconds())
        return expected_diffs.apply(lambda x: abs(x - round(x)) < 1e-6).all()

    def _fix_ohlc_logic(self, data: pd.DataFrame) -> pd.DataFrame:
        """修复OHLC逻辑错误"""
        if not all(col in data.columns for col in ['open', 'high', 'low', 'close']):
            return data

        fixed = data.copy()

        # 确保 high 是最大值
        max_prices = fixed[['open', 'high', 'low', 'close']].max(axis=1)
        fixed['high'] = fixed[['high', max_prices]].max(axis=1)

        # 确保 low 是最小值
        min_prices = fixed[['open', 'high', 'low', 'close']].min(axis=1)
        fixed['low'] = fixed[['low', min_prices]].min(axis=1)

        return fixed

    def _remove_extreme_price_changes(self, data: pd.DataFrame) -> pd.DataFrame:
        """移除极端价格变化"""
        if not all(col in data.columns for col in ['open', 'close']):
            return data

        # 计算价格变化率
        price_changes = data['close'].pct_change().abs()
        threshold = self.max_price_change_pct

        # 标记极端变化
        extreme_changes = price_changes > threshold

        if extreme_changes.any():
            self.logger.warning(f"移除 {extreme_changes.sum()} 条极端价格变化记录")
            return data[~extreme_changes]

        return data

    def _handle_missing_values(self, data: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值"""
        if data.empty:
            return data

        # 对于价格数据，使用前向填充
        price_columns = ['open', 'high', 'low', 'close']
        for col in price_columns:
            if col in data.columns:
                data[col] = data[col].fillna(method='ffill')

        # 对于成交量，填充为0
        if 'volume' in data.columns:
            data['volume'] = data['volume'].fillna(0)

        return data

    def _calculate_consistency_score(self, data: pd.DataFrame) -> float:
        """计算一致性分数"""
        try:
            # OHLC逻辑一致性
            ohlc_errors = 0
            total_records = len(data)

            # 检查各种逻辑错误
            ohlc_errors += (data['high'] < data['low']).sum()
            ohlc_errors += (data['high'] < data['open']).sum()
            ohlc_errors += (data['high'] < data['close']).sum()
            ohlc_errors += (data['low'] > data['open']).sum()
            ohlc_errors += (data['low'] > data['close']).sum()

            consistency_score = 1.0 - (ohlc_errors / (total_records * 5))  # 5种检查
            return max(0.0, consistency_score)

        except:
            return 0.0

    def _calculate_time_continuity_score(self, data: pd.DataFrame) -> float:
        """计算时间连续性分数"""
        try:
            if len(data) <= 1:
                return 1.0

            if self._has_continuous_time_index(data):
                return 1.0

            # 计算连续性比例
            time_diffs = data.index.to_series().diff().dropna()
            min_diff = time_diffs.min()
            expected_diffs = time_diffs.apply(lambda x: x.total_seconds() / min_diff.total_seconds())

            continuous_count = expected_diffs.apply(lambda x: abs(x - round(x)) < 1e-6).sum()
            return continuous_count / len(expected_diffs)

        except:
            return 0.0

    def _count_extreme_changes(self, data: pd.DataFrame) -> int:
        """统计极端变化数量"""
        try:
            if 'close' not in data.columns:
                return 0

            price_changes = data['close'].pct_change().abs()
            threshold = self.max_price_change_pct
            return (price_changes > threshold).sum()

        except:
            return 0


# 为了向后兼容，提供DataValidator别名
DataValidator = OHLCVDataValidator