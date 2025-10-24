import ccxt
import pandas as pd
import numpy as np
import os
import time
import logging
from datetime import datetime, timedelta
import pyarrow as pa
import pyarrow.parquet as pq
from typing import List, Dict, Optional, Union

# 设置日志记录器
logger = logging.getLogger(__name__)


class DataFetcher:
    """
    数据获取类，通过 ccxt 获取实时与历史K线数据
    """
    
    def __init__(self, exchange_name: str = 'binance', enable_rate_limit: bool = True,
                 market_type: str = 'spot'):
        """
        初始化数据获取器

        Args:
            exchange_name: 交易所名称，默认为 'binance'
            enable_rate_limit: 是否启用频率限制
            market_type: 市场类型，'spot' 现货 或 'future' 期货
        """
        self.exchange_name = exchange_name
        self.market_type = market_type

        # 设置交易所配置
        config = {
            'enableRateLimit': enable_rate_limit,
            'timeout': 30000,  # 30秒超时
            'options': {}
        }

        # 根据市场类型设置默认类型
        if market_type == 'future':
            config['options']['defaultType'] = 'future'
        elif market_type == 'spot':
            config['options']['defaultType'] = 'spot'
        else:
            config['options']['defaultType'] = 'spot'  # 默认现货

        self.exchange = getattr(ccxt, exchange_name)(config)
        
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 500,
                    since: Optional[int] = None, params: Optional[Dict] = None,
                    max_retries: int = 3, retry_delay: float = 1.0) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            symbol: 交易对，如 'BTC/USDT'
            timeframe: 时间框架，如 '1m', '5m', '1h', '1d'
            limit: 获取数量限制
            since: 开始时间戳（毫秒）
            params: 额外参数
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            包含OHLCV数据的DataFrame
        """
        if params is None:
            params = {}

        for attempt in range(max_retries):
            try:
                logger.debug(f"获取 {symbol} {timeframe} 数据 (尝试 {attempt + 1}/{max_retries})")
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit, params=params)

                if not ohlcv:
                    logger.warning(f"获取到空数据: {symbol} {timeframe}")
                    return pd.DataFrame()

                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)

                # 转换数据类型
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                logger.info(f"成功获取 {symbol} {timeframe} 数据: {len(df)} 条")
                return df

            except ccxt.NetworkError as e:
                logger.warning(f"网络错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # 指数退避
                    continue

            except ccxt.ExchangeError as e:
                logger.error(f"交易所错误: {e}")
                break

            except Exception as e:
                logger.error(f"获取数据时出错 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue

        logger.error(f"获取 {symbol} {timeframe} 数据失败，已达到最大重试次数")
        return pd.DataFrame()
    
    def fetch_multiple_symbols(self, symbols: List[str], timeframe: str = '1h', 
                              limit: int = 500, since: Optional[int] = None) -> Dict[str, pd.DataFrame]:
        """
        批量获取多个交易对的OHLCV数据
        
        Args:
            symbols: 交易对列表
            timeframe: 时间框架
            limit: 获取数量限制
            since: 开始时间戳
            
        Returns:
            包含多个交易对数据的字典
        """
        result = {}
        
        for symbol in symbols:
            try:
                print(f"正在获取 {symbol} 数据...")
                df = self.fetch_ohlcv(symbol, timeframe, limit, since)
                if not df.empty:
                    result[symbol] = df
                time.sleep(0.1)  # 避免请求过快
            except Exception as e:
                logger.error(f"获取 {symbol} 数据时出错: {e}")
                
        return result
    
    def get_exchange_info(self) -> Dict:
        """
        获取交易所信息
        
        Returns:
            交易所信息字典
        """
        try:
            return self.exchange.load_markets()
        except Exception as e:
            logger.error(f"获取交易所信息时出错: {e}")
            return {}
    
    def get_timeframes(self) -> List[str]:
        """
        获取支持的时间框架
        
        Returns:
            支持的时间框架列表
        """
        try:
            return list(self.exchange.timeframes.keys())
        except Exception as e:
            logger.error(f"获取时间框架时出错: {e}")
            return []
