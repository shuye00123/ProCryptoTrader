import os
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple
import glob
import shutil
from .data_fetcher import DataFetcher

# 设置日志记录器
logger = logging.getLogger(__name__)


class DataManager:
    """
    数据管理类，负责本地数据存储与更新，支持多时间框架
    """
    
    def __init__(self, data_dir: str = "data", exchange: str = "binance", market_type: str = "spot"):
        """
        初始化数据管理器

        Args:
            data_dir: 数据存储目录
            exchange: 交易所名称
            market_type: 市场类型，'spot' 现货 或 'future' 期货
        """
        self.data_dir = data_dir
        self.exchange = exchange
        self.market_type = market_type
        self.data_fetcher = DataFetcher(exchange, market_type=market_type)
        
        # 创建数据目录结构
        self._create_dir_structure()
    
    def _create_dir_structure(self):
        """创建数据目录结构"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        exchange_dir = os.path.join(self.data_dir, self.exchange)
        if not os.path.exists(exchange_dir):
            os.makedirs(exchange_dir)
    
    def _get_symbol_dir(self, symbol: str) -> str:
        """
        获取交易对数据目录
        
        Args:
            symbol: 交易对，如 'BTC/USDT'
            
        Returns:
            交易对数据目录路径
        """
        # 将 '/' 替换为 '-' 以避免目录层级问题
        safe_symbol = symbol.replace('/', '-')
        symbol_dir = os.path.join(self.data_dir, self.exchange, safe_symbol)
        
        if not os.path.exists(symbol_dir):
            os.makedirs(symbol_dir)
            
        return symbol_dir
    
    def _get_file_path(self, symbol: str, timeframe: str) -> str:
        """
        获取数据文件路径
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            
        Returns:
            数据文件路径
        """
        symbol_dir = self._get_symbol_dir(symbol)
        filename = f"{timeframe}.parquet"
        return os.path.join(symbol_dir, filename)
    
    def save_data(self, df: pd.DataFrame, symbol: str, timeframe: str, 
                  overwrite: bool = False) -> bool:
        """
        保存数据到本地
        
        Args:
            df: 要保存的DataFrame
            symbol: 交易对
            timeframe: 时间框架
            overwrite: 是否覆盖现有数据
            
        Returns:
            是否保存成功
        """
        if df.empty:
            logger.warning("数据为空，不保存")
            return False
            
        file_path = self._get_file_path(symbol, timeframe)
        
        try:
            # 如果文件存在且不覆盖，则合并数据
            if os.path.exists(file_path) and not overwrite:
                existing_df = self.load_data(symbol, timeframe)
                if not existing_df.empty:
                    # 合并数据，去重并按时间排序
                    df = pd.concat([existing_df, df])
                    df = df[~df.index.duplicated(keep='last')]
                    df = df.sort_index()
            
            # 保存为parquet格式
            table = pa.Table.from_pandas(df)
            pq.write_table(table, file_path)
            
            logger.info(f"数据已保存到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存数据时出错: {e}")
            return False
    
    def load_data(self, symbol: str, timeframe: str, 
                  start_date: Optional[str] = None, 
                  end_date: Optional[str] = None) -> pd.DataFrame:
        """
        从本地加载数据
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            加载的DataFrame
        """
        file_path = self._get_file_path(symbol, timeframe)
        
        if not os.path.exists(file_path):
            logger.warning(f"数据文件不存在: {file_path}")
            return pd.DataFrame()
        
        try:
            df = pq.read_table(file_path).to_pandas()
            
            # 按日期范围过滤
            if start_date:
                df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]
                
            return df
            
        except Exception as e:
            logger.error(f"加载数据时出错: {e}")
            return pd.DataFrame()
    
    def update_data(self, symbol: str, timeframe: str, limit: int = 500) -> bool:
        """
        更新数据，获取最新的K线数据并保存到本地
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            limit: 获取数量限制
            
        Returns:
            是否更新成功
        """
        try:
            # 获取本地最新数据时间戳
            latest_timestamp = None
            existing_df = self.load_data(symbol, timeframe)
            
            if not existing_df.empty:
                latest_timestamp = int(existing_df.index.max().timestamp() * 1000)
            
            # 获取最新数据
            new_df = self.data_fetcher.fetch_ohlcv(
                symbol, timeframe, limit=limit, since=latest_timestamp
            )
            
            if new_df.empty:
                logger.warning("没有新数据可更新")
                return False
                
            # 保存数据
            return self.save_data(new_df, symbol, timeframe)
            
        except Exception as e:
            logger.error(f"更新数据时出错: {e}")
            return False
    
    def download_historical_data(self, symbol: str, timeframe: str, 
                                 start_date: str, end_date: str = None) -> bool:
        """
        下载历史数据
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'，默认为当前日期
            
        Returns:
            是否下载成功
        """
        try:
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
                
            start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
            
            # 计算需要获取的数据量
            timeframe_ms = self._timeframe_to_ms(timeframe)
            total_candles = (end_timestamp - start_timestamp) // timeframe_ms
            
            # 限制每次获取的数量，分批获取
            batch_size = 1000
            all_data = []
            
            for i in range(0, total_candles, batch_size):
                since = start_timestamp + i * timeframe_ms
                limit = min(batch_size, total_candles - i)
                
                logger.info(f"正在下载 {symbol} {timeframe} 数据: {i+limit}/{total_candles}")
                df = self.data_fetcher.fetch_ohlcv(symbol, timeframe, limit=limit, since=since)
                
                if df.empty:
                    break
                    
                all_data.append(df)
                
            # 合并所有数据
            if all_data:
                result_df = pd.concat(all_data)
                result_df = result_df[~result_df.index.duplicated(keep='last')]
                result_df = result_df.sort_index()
                
                # 保存数据
                return self.save_data(result_df, symbol, timeframe, overwrite=True)
            else:
                logger.warning("没有获取到数据")
                return False
                
        except Exception as e:
            logger.error(f"下载历史数据时出错: {e}")
            return False
    
    def _timeframe_to_ms(self, timeframe: str) -> int:
        """
        将时间框架转换为毫秒
        
        Args:
            timeframe: 时间框架，如 '1m', '5m', '1h', '1d'
            
        Returns:
            对应的毫秒数
        """
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        elif unit == 'w':
            return value * 7 * 24 * 60 * 60 * 1000
        else:
            raise ValueError(f"不支持的时间框架: {timeframe}")
    
    def list_available_data(self) -> Dict[str, List[str]]:
        """
        列出所有可用的数据
        
        Returns:
            交易对和时间框架的字典
        """
        result = {}
        exchange_dir = os.path.join(self.data_dir, self.exchange)
        
        if not os.path.exists(exchange_dir):
            return result
            
        for symbol_dir in os.listdir(exchange_dir):
            symbol_path = os.path.join(exchange_dir, symbol_dir)
            
            if os.path.isdir(symbol_path):
                # 将 '-' 替换回 '/'
                symbol = symbol_dir.replace('-', '/')
                timeframes = []
                
                for file in os.listdir(symbol_path):
                    if file.endswith('.parquet'):
                        timeframes.append(file.replace('.parquet', ''))
                
                if timeframes:
                    result[symbol] = timeframes
        
        return result
    
    def clear_data(self, symbol: str = None, timeframe: str = None):
        """
        清除数据
        
        Args:
            symbol: 交易对，如果为None则清除所有交易对
            timeframe: 时间框架，如果为None则清除所有时间框架
        """
        try:
            if symbol is None:
                # 清除所有数据
                exchange_dir = os.path.join(self.data_dir, self.exchange)
                if os.path.exists(exchange_dir):
                        shutil.rmtree(exchange_dir)
                        self._create_dir_structure()
                        logger.info("已清除所有数据")
            else:
                if timeframe is None:
                    # 清除指定交易对的所有数据
                    symbol_dir = self._get_symbol_dir(symbol)
                    if os.path.exists(symbol_dir):
                        shutil.rmtree(symbol_dir)
                        logger.info(f"已清除 {symbol} 的所有数据")
                else:
                    # 清除指定交易对和时间框架的数据
                    file_path = self._get_file_path(symbol, timeframe)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"已清除 {symbol} {timeframe} 数据")
                        
        except Exception as e:
            logger.error(f"清除数据时出错: {e}")