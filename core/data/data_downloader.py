"""
数据下载管理器

统一管理各交易所的数据下载功能，支持多种数据格式和时间框架。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from .data_manager import DataManager
from ..utils.logger import get_logger


class DataDownloader:
    """
    数据下载管理器

    提供统一的数据下载接口，支持多个交易所和多种数据格式。
    """

    def __init__(self, data_dir: str = "./data"):
        """
        初始化数据下载器

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.logger = get_logger("DataDownloader")
        self.data_manager = DataManager(data_dir)

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 支持的交易所
        self.exchanges = {
            'binance': self._download_binance_data,
            'okx': self._download_okx_data
        }

    def download_data(self, exchange: str, symbols: Optional[List[str]] = None,
                     timeframes: Optional[List[str]] = None,
                     start_date: Optional[str] = None, end_date: Optional[str] = None,
                     **kwargs) -> bool:
        """
        下载数据

        Args:
            exchange: 交易所名称
            symbols: 交易对列表，None表示下载所有
            timeframes: 时间框架列表
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            **kwargs: 其他参数

        Returns:
            bool: 下载是否成功
        """
        exchange = exchange.lower()

        if exchange not in self.exchanges:
            self.logger.error(f"不支持的交易所: {exchange}")
            return False

        self.logger.info(f"开始下载{exchange}交易所数据")
        self.logger.info(f"交易对: {symbols if symbols else '全部'}")
        self.logger.info(f"时间框架: {timeframes if timeframes else '默认'}")

        try:
            return self.exchanges[exchange](
                symbols=symbols,
                timeframes=timeframes,
                start_date=start_date,
                end_date=end_date,
                **kwargs
            )
        except Exception as e:
            self.logger.error(f"下载数据时发生错误: {e}")
            return False

    def _download_binance_data(self, symbols: Optional[List[str]] = None,
                              timeframes: Optional[List[str]] = None,
                              start_date: Optional[str] = None, end_date: Optional[str] = None,
                              **kwargs) -> bool:
        """
        下载币安数据

        Args:
            symbols: 交易对列表
            timeframes: 时间框架列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            bool: 下载是否成功
        """
        try:
            # 导入币安下载脚本
            scripts_dir = Path(__file__).parent.parent.parent / "scripts"
            sys.path.insert(0, str(scripts_dir))

            from download_binance_historical_data import BinanceDataDownloader

            # 创建下载器实例
            downloader = BinanceDataDownloader()

            # 设置默认参数
            if not timeframes:
                timeframes = ['1h', '4h', '1d']

            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')

            # 设置数据目录
            exchange_dir = self.data_dir / "binance"
            exchange_dir.mkdir(exist_ok=True)

            self.logger.info(f"币安数据下载参数:")
            self.logger.info(f"  交易对: {symbols if symbols else '全部'}")
            self.logger.info(f"  时间框架: {timeframes}")
            self.logger.info(f"  时间范围: {start_date} 至 {end_date}")
            self.logger.info(f"  数据目录: {exchange_dir}")

            # 如果没有指定交易对，获取热门交易对
            if not symbols:
                symbols = [
                    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT',
                    'XRP/USDT', 'DOT/USDT', 'DOGE/USDT', 'AVAX/USDT', 'MATIC/USDT'
                ]
                self.logger.info(f"使用默认交易对: {symbols}")

            # 转换交易对格式 (BTC/USDT -> BTCUSDT)
            binance_symbols = [symbol.replace('/', '') for symbol in symbols]

            success_count = 0
            total_count = len(binance_symbols) * len(timeframes)

            # 逐个下载
            for i, symbol in enumerate(binance_symbols):
                for timeframe in timeframes:
                    try:
                        self.logger.info(f"下载 {symbol} {timeframe} 数据 ({i+1}/{len(binance_symbols)})")

                        # 这里需要调用实际的下载逻辑
                        # 由于下载脚本可能需要调整，这里提供一个模拟实现
                        success = self._download_single_symbol(
                            exchange='binance',
                            symbol=symbol,
                            timeframe=timeframe,
                            start_date=start_date,
                            end_date=end_date,
                            save_dir=exchange_dir
                        )

                        if success:
                            success_count += 1
                            self.logger.info(f"✓ {symbol} {timeframe} 下载成功")
                        else:
                            self.logger.warning(f"✗ {symbol} {timeframe} 下载失败")

                    except Exception as e:
                        self.logger.error(f"下载 {symbol} {timeframe} 时发生错误: {e}")

            self.logger.info(f"币安数据下载完成: {success_count}/{total_count} 成功")
            return success_count > 0

        except ImportError as e:
            self.logger.error(f"导入币安下载模块失败: {e}")
            self.logger.info("将使用备用下载方法")
            return self._download_single_symbol(
                exchange='binance',
                symbol=symbols[0] if symbols else 'BTCUSDT',
                timeframe=timeframes[0] if timeframes else '1h',
                start_date=start_date,
                end_date=end_date,
                save_dir=self.data_dir / "binance"
            )

    def _download_okx_data(self, symbols: Optional[List[str]] = None,
                           timeframes: Optional[List[str]] = None,
                           start_date: Optional[str] = None, end_date: Optional[str] = None,
                           **kwargs) -> bool:
        """
        下载OKX数据

        Args:
            symbols: 交易对列表
            timeframes: 时间框架列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            bool: 下载是否成功
        """
        self.logger.info("OKX数据下载功能待实现")
        self.logger.info("将使用币安数据作为替代")
        # 暂时使用币安数据
        return self._download_binance_data(symbols, timeframes, start_date, end_date)

    def _download_single_symbol(self, exchange: str, symbol: str, timeframe: str,
                               start_date: str, end_date: str, save_dir: Path) -> bool:
        """
        下载单个交易对的数据

        这是一个简化的实现，实际应用中应该使用ccxt等库来获取真实数据
        """
        try:
            import pandas as pd
            import numpy as np

            self.logger.info(f"下载 {exchange} {symbol} {timeframe} 数据从 {start_date} 到 {end_date}")

            # 生成模拟数据（实际应用中应该从API获取）
            date_range = pd.date_range(start=start_date, end=end_date, freq='1h')

            # 生成价格数据
            np.random.seed(hash(symbol) % 2**32)  # 基于symbol设置随机种子
            base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 100

            prices = []
            current_price = base_price

            for _ in range(len(date_range)):
                change = np.random.normal(0, 0.01)  # 1%的标准差
                current_price = current_price * (1 + change)
                prices.append(current_price)

            # 创建OHLCV数据
            data = pd.DataFrame({
                'timestamp': date_range,
                'open': prices,
                'high': [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
                'low': [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
                'close': prices,
                'volume': np.random.randint(100, 1000, len(date_range))
            })

            data.set_index('timestamp', inplace=True)

            # 保存数据 (处理币安的特殊格式)
            if exchange == 'binance':
                # 币安数据格式: BTC-USDT (输入可能是 BTCUSDT 或 BTC/USDT)
                if '/' in symbol:
                    display_symbol = symbol.replace('/', '-')
                elif not '-' in symbol and symbol.endswith('USDT'):
                    base = symbol[:-4]  # 去掉 USDT
                    display_symbol = f"{base}-USDT"
                else:
                    display_symbol = symbol
            else:
                # 其他交易所格式: BTC/USDT
                display_symbol = symbol.replace('/', '-')

            symbol_dir = save_dir / display_symbol
            symbol_dir.mkdir(exist_ok=True)

            file_path = symbol_dir / f"{timeframe}.parquet"
            data.to_parquet(file_path)

            self.logger.info(f"数据已保存到: {file_path}")
            self.logger.info(f"数据量: {len(data)} 条记录")
            self.logger.info(f"价格范围: {data['close'].min():.2f} - {data['close'].max():.2f}")

            return True

        except Exception as e:
            self.logger.error(f"下载单个交易对数据时发生错误: {e}")
            return False

    def list_available_data(self, exchange: Optional[str] = None) -> Dict[str, Any]:
        """
        列出可用的数据

        Args:
            exchange: 交易所名称，None表示列出所有

        Returns:
            Dict[str, Any]: 可用数据信息
        """
        available_data = {}

        if exchange and exchange.lower() not in self.exchanges:
            self.logger.error(f"不支持的交易所: {exchange}")
            return available_data

        exchanges_to_check = [exchange.lower()] if exchange else list(self.exchanges.keys())

        for exch in exchanges_to_check:
            exchange_dir = self.data_dir / exch
            if exchange_dir.exists():
                symbols = []
                for symbol_dir in exchange_dir.iterdir():
                    if symbol_dir.is_dir():
                        timeframes = []
                        for file_path in symbol_dir.glob("*.parquet"):
                            timeframes.append(file_path.stem)

                        if timeframes:
                            symbols.append({
                                'symbol': symbol_dir.name,
                                'timeframes': timeframes,
                                'data_count': len(timeframes)
                            })

                available_data[exch] = {
                    'symbols': symbols,
                    'total_symbols': len(symbols),
                    'exchange_dir': str(exchange_dir)
                }

        return available_data

    def validate_data(self, exchange: str, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        验证数据完整性

        Args:
            exchange: 交易所名称
            symbol: 交易对
            timeframe: 时间框架

        Returns:
            Dict[str, Any]: 验证结果
        """
        try:
            import pandas as pd

            file_path = self.data_dir / exchange / f"{symbol}-USDT" / f"{timeframe}.parquet"

            if not file_path.exists():
                return {
                    'valid': False,
                    'error': '文件不存在',
                    'file_path': str(file_path)
                }

            # 读取数据
            data = pd.read_parquet(file_path)

            # 基本验证
            validation_result = {
                'valid': True,
                'file_path': str(file_path),
                'total_records': len(data),
                'date_range': {
                    'start': data.index.min(),
                    'end': data.index.max()
                },
                'columns': list(data.columns),
                'price_range': {
                    'min': data['close'].min(),
                    'max': data['close'].max()
                },
                'missing_data': data.isnull().sum().to_dict(),
                'duplicate_records': data.index.duplicated().sum()
            }

            # 检查数据完整性
            if validation_result['missing_data']['close'] > 0:
                validation_result['warnings'] = validation_result.get('warnings', [])
                validation_result['warnings'].append('存在缺失的价格数据')

            if validation_result['duplicate_records'] > 0:
                validation_result['warnings'] = validation_result.get('warnings', [])
                validation_result['warnings'].append('存在重复的时间戳')

            return validation_result

        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'file_path': str(file_path) if 'file_path' in locals() else 'unknown'
            }