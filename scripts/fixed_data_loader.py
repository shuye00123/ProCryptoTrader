#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复的数据加载器，直接读取下载的Binance数据
"""

import os
import sys
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class FixedDataLoader:
    """修复的数据加载器，直接读取下载的数据"""

    def __init__(self, data_dir: str = None):
        """
        初始化数据加载器

        Args:
            data_dir: 数据目录，默认为项目下的data/binance
        """
        if data_dir is None:
            data_dir = project_root / "data" / "binance"
        self.data_dir = Path(data_dir)

    def load_data(self, symbol: str, timeframe: str = "1d",
                  start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        加载指定交易对的数据

        Args:
            symbol: 交易对，如 'BTC/USDT'
            timeframe: 时间框架，如 '1d'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'

        Returns:
            包含OHLCV数据的DataFrame
        """
        # 将 '/' 替换为 '-'
        safe_symbol = symbol.replace('/', '-')

        # 构建文件路径
        file_path = self.data_dir / safe_symbol / f"{timeframe}.parquet"

        if not file_path.exists():
            print(f"数据文件不存在: {file_path}")
            return pd.DataFrame()

        try:
            # 读取Parquet文件
            df = pd.read_parquet(file_path)

            # 确保索引是datetime类型
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                else:
                    print(f"数据格式错误：缺少时间戳列")
                    return pd.DataFrame()

            # 按日期范围过滤
            if start_date:
                df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]

            return df

        except Exception as e:
            print(f"读取数据时出错: {e}")
            return pd.DataFrame()

    def list_available_symbols(self) -> list:
        """列出所有可用的交易对"""
        symbols = []

        if not self.data_dir.exists():
            return symbols

        for item in self.data_dir.iterdir():
            if item.is_dir():
                # 将 '-' 替换回 '/'
                symbol = item.name.replace('-', '/')
                symbols.append(symbol)

        return sorted(symbols)

    def get_data_info(self, symbol: str, timeframe: str = "1d") -> dict:
        """获取数据信息"""
        df = self.load_data(symbol, timeframe)

        if df.empty:
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'count': 0,
                'start_date': None,
                'end_date': None
            }

        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'count': len(df),
            'start_date': df.index.min().strftime('%Y-%m-%d'),
            'end_date': df.index.max().strftime('%Y-%m-%d')
        }

def test_fixed_loader():
    """测试修复的数据加载器"""
    print("=" * 60)
    print("测试修复的数据加载器")
    print("=" * 60)

    loader = FixedDataLoader()

    # 列出可用交易对
    symbols = loader.list_available_symbols()
    print(f"找到 {len(symbols)} 个交易对")
    print(f"前10个: {symbols[:10]}")

    # 测试加载BTC数据
    if 'BTC/USDT' in symbols:
        print(f"\n测试加载 BTC/USDT 数据...")
        data = loader.load_data('BTC/USDT', '1d', '2024-01-01', '2024-12-31')

        if not data.empty:
            print(f"✓ 成功加载 {len(data)} 条数据")
            print(f"时间范围: {data.index.min()} 至 {data.index.max()}")
            print(f"列名: {list(data.columns)}")
            print(f"数据类型: {data.dtypes.to_dict()}")

            # 显示基本统计
            print(f"\n基本统计:")
            print(f"  价格范围: ${data['close'].min():,.2f} - ${data['close'].max():,.2f}")
            print(f"  平均价格: ${data['close'].mean():,.2f}")

            return True
        else:
            print(f"❌ 加载失败")
            return False
    else:
        print(f"❌ 未找到 BTC/USDT 数据")
        return False

if __name__ == "__main__":
    success = test_fixed_loader()
    sys.exit(0 if success else 1)