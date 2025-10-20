import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


class DataProcessor:
    """数据处理器类，用于清洗、处理和增强数据"""
    
    def __init__(self):
        """初始化数据处理器"""
        pass
    
    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        清洗数据，处理缺失值和异常值
        
        Args:
            data: 原始数据DataFrame
            
        Returns:
            清洗后的数据DataFrame
        """
        # 复制数据
        cleaned_data = data.copy()
        
        # 删除包含缺失值的行
        cleaned_data = cleaned_data.dropna()
        
        # 确保时间戳是datetime类型
        if 'timestamp' in cleaned_data.columns:
            cleaned_data['timestamp'] = pd.to_datetime(cleaned_data['timestamp'])
        
        # 确保价格列是数值类型
        price_columns = ['open', 'high', 'low', 'close']
        for col in price_columns:
            if col in cleaned_data.columns:
                cleaned_data[col] = pd.to_numeric(cleaned_data[col], errors='coerce')
        
        # 确保成交量是数值类型
        if 'volume' in cleaned_data.columns:
            cleaned_data['volume'] = pd.to_numeric(cleaned_data['volume'], errors='coerce')
        
        # 再次删除可能因类型转换产生的缺失值
        cleaned_data = cleaned_data.dropna()
        
        # 确保价格数据合理（高>=低，收盘价在高低之间等）
        if all(col in cleaned_data.columns for col in ['high', 'low', 'close', 'open']):
            # 过滤掉不合理的K线数据
            cleaned_data = cleaned_data[
                (cleaned_data['high'] >= cleaned_data['low']) &
                (cleaned_data['high'] >= cleaned_data['close']) &
                (cleaned_data['high'] >= cleaned_data['open']) &
                (cleaned_data['low'] <= cleaned_data['close']) &
                (cleaned_data['low'] <= cleaned_data['open']) &
                (cleaned_data['close'] > 0) &
                (cleaned_data['open'] > 0)
            ]
        
        # 按时间戳排序
        if 'timestamp' in cleaned_data.columns:
            cleaned_data = cleaned_data.sort_values('timestamp').reset_index(drop=True)
        
        return cleaned_data
    
    def add_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        添加技术指标
        
        Args:
            data: 原始数据DataFrame
            
        Returns:
            添加技术指标后的数据DataFrame
        """
        # 复制数据
        enhanced_data = data.copy()
        
        # 确保数据按时间排序
        if 'timestamp' in enhanced_data.columns:
            enhanced_data = enhanced_data.sort_values('timestamp')
        
        # 确保有收盘价列
        if 'close' not in enhanced_data.columns:
            raise ValueError("数据中缺少'close'列")
        
        # 计算简单移动平均线
        enhanced_data['sma_20'] = enhanced_data['close'].rolling(window=20).mean()
        enhanced_data['sma_50'] = enhanced_data['close'].rolling(window=50).mean()
        
        # 计算相对强弱指数(RSI)
        delta = enhanced_data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        enhanced_data['rsi'] = 100 - (100 / (1 + rs))
        
        # 计算MACD
        exp1 = enhanced_data['close'].ewm(span=12, adjust=False).mean()
        exp2 = enhanced_data['close'].ewm(span=26, adjust=False).mean()
        enhanced_data['macd'] = exp1 - exp2
        enhanced_data['macd_signal'] = enhanced_data['macd'].ewm(span=9, adjust=False).mean()
        enhanced_data['macd_histogram'] = enhanced_data['macd'] - enhanced_data['macd_signal']
        
        # 计算布林带
        bb_period = 20
        bb_std = 2
        enhanced_data['bb_middle'] = enhanced_data['close'].rolling(window=bb_period).mean()
        bb_std_dev = enhanced_data['close'].rolling(window=bb_period).std()
        enhanced_data['bb_upper'] = enhanced_data['bb_middle'] + (bb_std_dev * bb_std)
        enhanced_data['bb_lower'] = enhanced_data['bb_middle'] - (bb_std_dev * bb_std)
        
        # 计算ATR (Average True Range)
        if all(col in enhanced_data.columns for col in ['high', 'low', 'close']):
            high_low = enhanced_data['high'] - enhanced_data['low']
            high_close = np.abs(enhanced_data['high'] - enhanced_data['close'].shift())
            low_close = np.abs(enhanced_data['low'] - enhanced_data['close'].shift())
            
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            enhanced_data['atr'] = true_range.rolling(window=14).mean()
        
        # 计算价格变化百分比
        enhanced_data['pct_change'] = enhanced_data['close'].pct_change()
        
        return enhanced_data
    
    def resample_data(self, data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        重采样数据到不同时间周期
        
        Args:
            data: 原始数据DataFrame
            timeframe: 目标时间周期 ('1h', '4h', '1d'等)
            
        Returns:
            重采样后的数据DataFrame
        """
        # 复制数据
        resampled_data = data.copy()
        
        # 确保时间戳是datetime类型并设为索引
        if 'timestamp' in resampled_data.columns:
            resampled_data['timestamp'] = pd.to_datetime(resampled_data['timestamp'])
            resampled_data = resampled_data.set_index('timestamp')
        
        # 定义重采样规则
        resample_rule = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # 只保留存在的列
        resample_rule = {k: v for k, v in resample_rule.items() if k in resampled_data.columns}
        
        # 执行重采样
        resampled_data = resampled_data.resample(timeframe).agg(resample_rule)
        
        # 删除可能产生的空行
        resampled_data = resampled_data.dropna()
        
        # 重置索引，将时间戳转回列
        resampled_data = resampled_data.reset_index()
        
        return resampled_data
    
    def normalize_data(self, data: pd.DataFrame, method: str = 'minmax') -> pd.DataFrame:
        """
        标准化数据
        
        Args:
            data: 原始数据DataFrame
            method: 标准化方法 ('minmax', 'zscore')
            
        Returns:
            标准化后的数据DataFrame
        """
        # 复制数据
        normalized_data = data.copy()
        
        # 只对数值列进行标准化
        numeric_columns = normalized_data.select_dtypes(include=[np.number]).columns
        
        # 排除时间戳列
        if 'timestamp' in numeric_columns:
            numeric_columns = numeric_columns.drop('timestamp')
        
        if method == 'minmax':
            # Min-Max标准化
            for col in numeric_columns:
                min_val = normalized_data[col].min()
                max_val = normalized_data[col].max()
                if max_val != min_val:  # 避免除零
                    normalized_data[col] = (normalized_data[col] - min_val) / (max_val - min_val)
        elif method == 'zscore':
            # Z-Score标准化
            for col in numeric_columns:
                mean_val = normalized_data[col].mean()
                std_val = normalized_data[col].std()
                if std_val != 0:  # 避免除零
                    normalized_data[col] = (normalized_data[col] - mean_val) / std_val
        else:
            raise ValueError(f"不支持的标准化方法: {method}")
        
        return normalized_data
    
    def filter_data(self, data: pd.DataFrame, start_date: Optional[str] = None, 
                   end_date: Optional[str] = None, symbols: Optional[list] = None) -> pd.DataFrame:
        """
        根据日期和交易对过滤数据
        
        Args:
            data: 原始数据DataFrame
            start_date: 开始日期 (YYYY-MM-DD格式)
            end_date: 结束日期 (YYYY-MM-DD格式)
            symbols: 要保留的交易对列表
            
        Returns:
            过滤后的数据DataFrame
        """
        # 复制数据
        filtered_data = data.copy()
        
        # 确保时间戳是datetime类型
        if 'timestamp' in filtered_data.columns:
            filtered_data['timestamp'] = pd.to_datetime(filtered_data['timestamp'])
            
            # 按日期范围过滤
            if start_date:
                start_date = pd.to_datetime(start_date)
                filtered_data = filtered_data[filtered_data['timestamp'] >= start_date]
            
            if end_date:
                end_date = pd.to_datetime(end_date)
                filtered_data = filtered_data[filtered_data['timestamp'] <= end_date]
        
        # 按交易对过滤
        if 'symbol' in filtered_data.columns and symbols:
            filtered_data = filtered_data[filtered_data['symbol'].isin(symbols)]
        
        return filtered_data.reset_index(drop=True)