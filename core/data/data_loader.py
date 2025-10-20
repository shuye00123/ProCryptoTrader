import os
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple
from .data_manager import DataManager

# 设置日志记录器
logger = logging.getLogger(__name__)


class DataLoader:
    """
    数据加载类，用于从本地加载K线数据，支持回测阶段使用
    """
    
    def __init__(self, data_dir: str = "data", exchange: str = "binance"):
        """
        初始化数据加载器
        
        Args:
            data_dir: 数据存储目录
            exchange: 交易所名称
        """
        self.data_dir = data_dir
        self.exchange = exchange
        self.data_manager = DataManager(data_dir, exchange)
    
    def load_data(self, symbol: str, timeframe: str, 
                  start_date: Optional[str] = None, 
                  end_date: Optional[str] = None) -> pd.DataFrame:
        """
        从本地加载指定交易对和时间框架的数据
        
        Args:
            symbol: 交易对，如 'BTC/USDT'
            timeframe: 时间框架，如 '1m', '5m', '1h', '1d'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            包含OHLCV数据的DataFrame
        """
        return self.data_manager.load_data(symbol, timeframe, start_date, end_date)
    
    def load_multiple_symbols(self, symbols: List[str], timeframe: str, 
                             start_date: Optional[str] = None, 
                             end_date: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        从本地加载多个交易对的数据
        
        Args:
            symbols: 交易对列表
            timeframe: 时间框架
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            包含多个交易对数据的字典
        """
        result = {}
        
        for symbol in symbols:
            df = self.load_data(symbol, timeframe, start_date, end_date)
            if not df.empty:
                result[symbol] = df
                
        return result
    
    def load_multiple_timeframes(self, symbol: str, timeframes: List[str], 
                                start_date: Optional[str] = None, 
                                end_date: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        从本地加载单个交易对的多个时间框架数据
        
        Args:
            symbol: 交易对
            timeframes: 时间框架列表
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            包含多个时间框架数据的字典
        """
        result = {}
        
        for timeframe in timeframes:
            df = self.load_data(symbol, timeframe, start_date, end_date)
            if not df.empty:
                result[timeframe] = df
                
        return result
    
    def resample_data(self, df: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """
        将数据重新采样到目标时间框架
        
        Args:
            df: 原始数据DataFrame
            target_timeframe: 目标时间框架，如 '5m', '1h', '1d'
            
        Returns:
            重新采样后的DataFrame
        """
        if df.empty:
            return df
            
        # 确定重采样规则
        if target_timeframe.endswith('m'):
            rule = f"{target_timeframe[:-1]}T"  # 分钟
        elif target_timeframe.endswith('h'):
            rule = f"{target_timeframe[:-1]}H"  # 小时
        elif target_timeframe.endswith('d'):
            rule = f"{target_timeframe[:-1]}D"  # 天
        elif target_timeframe.endswith('w'):
            rule = f"{target_timeframe[:-1]}W"  # 周
        else:
            raise ValueError(f"不支持的时间框架: {target_timeframe}")
        
        # 重采样OHLCV数据
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return resampled
    
    def load_csv(self, file_path: str) -> pd.DataFrame:
        """
        从CSV文件加载数据
        
        Args:
            file_path: CSV文件路径
            
        Returns:
            加载的数据DataFrame
        """
        try:
            df = pd.read_csv(file_path)
            # 确保时间戳列是datetime类型
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"加载CSV文件失败: {file_path}, 错误: {str(e)}")
            raise
    
    def load_json(self, file_path: str) -> pd.DataFrame:
        """
        从JSON文件加载数据
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            加载的数据DataFrame
        """
        try:
            df = pd.read_json(file_path, orient='records')
            # 确保时间戳列是datetime类型
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"加载JSON文件失败: {file_path}, 错误: {str(e)}")
            raise
    
    def get_available_symbols(self, timeframe: Optional[str] = None) -> List[str]:
        """
        获取可用的交易对列表
        
        Args:
            timeframe: 可选的时间框架过滤
            
        Returns:
            交易对列表
        """
        return self.data_manager.get_available_symbols(timeframe)
    
    def get_available_timeframes(self, symbol: Optional[str] = None) -> List[str]:
        """
        获取可用的时间框架列表
        
        Args:
            symbol: 可选的交易对过滤
            
        Returns:
            时间框架列表
        """
        return self.data_manager.get_available_timeframes(symbol)
    
    def get_data_info(self, symbol: str, timeframe: str) -> Dict:
        """
        获取数据信息
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            
        Returns:
            包含数据信息的字典
        """
        df = self.load_data(symbol, timeframe)
        
        if df.empty:
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'count': 0,
                'start_date': None,
                'end_date': None,
                'file_size': 0
            }
        
        file_path = self.data_manager._get_file_path(symbol, timeframe)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'count': len(df),
            'start_date': df.index.min().strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': df.index.max().strftime('%Y-%m-%d %H:%M:%S'),
            'file_size': file_size
        }
    
    def validate_data(self, df: pd.DataFrame) -> Dict:
        """
        验证数据质量
        
        Args:
            df: 要验证的DataFrame
            
        Returns:
            包含验证结果的字典
        """
        if df.empty:
            return {
                'valid': False,
                'issues': ['数据为空']
            }
        
        issues = []
        
        # 检查缺失值
        if df.isnull().any().any():
            missing_cols = df.columns[df.isnull().any()].tolist()
            issues.append(f"存在缺失值的列: {', '.join(missing_cols)}")
        
        # 检查异常值
        for col in ['open', 'high', 'low', 'close']:
            if (df[col] <= 0).any():
                issues.append(f"{col}列存在非正值")
        
        # 检查OHLC逻辑
        invalid_ohlc = (df['high'] < df['low']) | (df['high'] < df['open']) | (df['high'] < df['close']) | \
                      (df['low'] > df['open']) | (df['low'] > df['close'])
        if invalid_ohlc.any():
            issues.append(f"存在{invalid_ohlc.sum()}条OHLC逻辑错误的记录")
        
        # 检查时间序列连续性
        time_diff = df.index.to_series().diff().dropna()
        expected_diff = pd.Timedelta(minutes=1)  # 假设最小时间间隔为1分钟
        if not (time_diff == expected_diff).all():
            issues.append("时间序列不连续")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'total_records': len(df),
            'date_range': f"{df.index.min()} 到 {df.index.max()}"
        }
    
    def list_available_data(self) -> Dict[str, List[str]]:
        """
        列出所有可用的数据
        
        Returns:
            交易对和时间框架的字典
        """
        return self.data_manager.list_available_data()
    
    def prepare_backtest_data(self, symbols: List[str], timeframe: str, 
                             start_date: str, end_date: str, 
                             fill_missing: bool = True) -> Dict[str, pd.DataFrame]:
        """
        准备回测数据，确保数据完整性和一致性
        
        Args:
            symbols: 交易对列表
            timeframe: 时间框架
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            fill_missing: 是否填充缺失数据
            
        Returns:
            包含回测数据的字典
        """
        result = {}
        
        for symbol in symbols:
            df = self.load_data(symbol, timeframe, start_date, end_date)
            
            if df.empty:
                logger.warning(f"警告: {symbol} 没有可用数据")
                continue
                
            # 验证数据质量
            validation = self.validate_data(df)
            if not validation['valid']:
                logger.warning(f"警告: {symbol} 数据质量存在问题: {', '.join(validation['issues'])}")
            
            # 填充缺失数据
            if fill_missing:
                df = self._fill_missing_data(df, timeframe)
            
            result[symbol] = df
        
        return result
    
    def _fill_missing_data(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        填充缺失数据
        
        Args:
            df: 原始数据DataFrame
            timeframe: 时间框架
            
        Returns:
            填充后的DataFrame
        """
        if df.empty:
            return df
        
        # 创建完整的时间索引
        start_date = df.index.min()
        end_date = df.index.max()
        
        # 确定时间频率
        if timeframe.endswith('m'):
            freq = f"{timeframe[:-1]}T"  # 分钟
        elif timeframe.endswith('h'):
            freq = f"{timeframe[:-1]}H"  # 小时
        elif timeframe.endswith('d'):
            freq = f"{timeframe[:-1]}D"  # 天
        else:
            freq = "1T"  # 默认1分钟
        
        full_index = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # 重新索引并填充数据
        df_full = df.reindex(full_index)
        
        # 使用前向填充OHLC数据
        df_full[['open', 'high', 'low', 'close']] = df_full[['open', 'high', 'low', 'close']].ffill()
        
        # 成交量填充为0
        df_full['volume'] = df_full['volume'].fillna(0)
        
        return df_full