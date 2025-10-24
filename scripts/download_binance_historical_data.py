#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance历史数据下载脚本
下载从2018年至今的加密货币日线数据
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data.data_manager import DataManager
from core.data.data_fetcher import DataFetcher
from core.utils.logger import get_logger

logger = get_logger("BinanceHistoricalDataDownload")


def download_historical_data_since_2018(symbols, start_date="2018-01-01", end_date=None):
    """
    下载从2018年至今的历史数据

    Args:
        symbols: 要下载的交易对列表
        start_date: 开始日期，默认2018-01-01
        end_date: 结束日期，默认为当前日期
    """

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    print(f"开始下载历史数据")
    print(f"交易对: {', '.join(symbols)}")
    print(f"时间范围: {start_date} 至 {end_date}")
    print(f"时间框架: 1d (日线)")
    print("-" * 60)

    # 创建数据管理器
    data_dir = project_root / "data" / "binance"
    data_dir.mkdir(parents=True, exist_ok=True)

    manager = DataManager(str(data_dir), 'binance')

    # 统计信息
    success_count = 0
    failed_symbols = []
    total_downloaded = 0

    for symbol in symbols:
        try:
            print(f"\n📈 正在下载 {symbol} 日线数据...")

            # 检查是否已有数据
            existing_data = manager.load_data(symbol, '1d')
            if not existing_data.empty:
                print(f"  发现已有数据: {len(existing_data)} 条")
                print(f"  时间范围: {existing_data.index.min()} 至 {existing_data.index.max()}")

                # 如果已有数据且时间范围足够，跳过下载
                if existing_data.index.min() <= pd.to_datetime(start_date):
                    print(f"  ✓ 数据已完整，跳过下载")
                    success_count += 1
                    total_downloaded += len(existing_data)
                    continue
                else:
                    print(f"  数据不完整，需要重新下载...")

            # 下载数据
            result = manager.download_historical_data(symbol, '1d', start_date, end_date)

            if result:
                # 验证下载的数据
                downloaded_data = manager.load_data(symbol, '1d')
                if not downloaded_data.empty:
                    print(f"  ✓ {symbol} 下载成功")
                    print(f"  数据量: {len(downloaded_data)} 条")
                    print(f"  时间范围: {downloaded_data.index.min()} 至 {downloaded_data.index.max()}")
                    print(f"  价格范围: {downloaded_data['close'].min():.2f} - {downloaded_data['close'].max():.2f}")

                    success_count += 1
                    total_downloaded += len(downloaded_data)

                    # 显示一些统计信息
                    if len(downloaded_data) > 0:
                        latest_price = downloaded_data['close'].iloc[-1]
                        first_price = downloaded_data['close'].iloc[0]
                        total_return = ((latest_price / first_price) - 1) * 100
                        print(f"  总回报率: {total_return:+.2f}%")

                        # 计算年平均收益率
                        years = (downloaded_data.index.max() - downloaded_data.index.min()).days / 365.25
                        if years > 0:
                            annual_return = (latest_price / first_price) ** (1/years) - 1
                            print(f"  年化收益率: {annual_return*100:+.2f}%")
                else:
                    print(f"  ✗ {symbol} 下载失败：数据为空")
                    failed_symbols.append(symbol)
            else:
                print(f"  ✗ {symbol} 下载失败")
                failed_symbols.append(symbol)

        except Exception as e:
            print(f"  ✗ {symbol} 下载出错: {e}")
            logger.error(f"下载 {symbol} 数据时出错: {e}")
            failed_symbols.append(symbol)

        # 添加延迟避免API限制
        time.sleep(0.5)

    # 显示最终统计
    print("\n" + "=" * 60)
    print("下载完成统计:")
    print(f"✓ 成功下载: {success_count}/{len(symbols)} 个交易对")
    print(f"📊 总数据量: {total_downloaded:,} 条日线数据")
    print(f"📁 数据保存位置: {data_dir}")

    if failed_symbols:
        print(f"❌ 下载失败的交易对: {', '.join(failed_symbols)}")

    # 显示已下载的数据概览
    print("\n📋 已下载数据概览:")
    available_data = manager.list_available_data()
    for symbol, timeframes in available_data.items():
        if '1d' in timeframes:
            data = manager.load_data(symbol, '1d')
            if not data.empty:
                duration = (data.index.max() - data.index.min()).days
                print(f"  {symbol}: {len(data)} 条数据, 跨度 {duration} 天")

    return success_count, failed_symbols


def get_popular_symbols():
    """
    获取热门的加密货币交易对列表
    """
    return [
        # 主流币种
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT',
        'SOL/USDT', 'DOGE/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT',

        # DeFi币种
        'UNI/USDT', 'AAVE/USDT', 'SUSHI/USDT', 'COMP/USDT', 'MKR/USDT',

        # 其他热门币种
        'LTC/USDT', 'BCH/USDT', 'ETC/USDT', 'FIL/USDT', 'AVAX/USDT',

        # 新兴币种
        'APE/USDT', 'SAND/USDT', 'MANA/USDT', 'CRV/USDT', '1INCH/USDT'
    ]


def main():
    """
    主函数
    """
    print("=" * 80)
    print("ProCryptoTrader - Binance历史数据下载工具")
    print("下载2018年至今的加密货币日线数据")
    print("=" * 80)

    # 导入pandas（用于日期处理）
    try:
        import pandas as pd
    except ImportError:
        print("❌ 错误: 需要安装pandas库")
        print("请运行: pip install pandas")
        return 1

    try:
        # 检查网络连接
        print("\n🔍 检查Binance API连接...")
        fetcher = DataFetcher('binance', enable_rate_limit=True)

        # 测试连接
        test_data = fetcher.fetch_ohlcv('BTC/USDT', '1d', limit=1)
        if test_data.empty:
            print("❌ 无法连接到Binance API，请检查网络连接")
            return 1

        print("✓ Binance API连接正常")

        # 获取用户选择的交易对
        print("\n📊 选择要下载的交易对:")
        print("1. 下载主要币种 (BTC, ETH, BNB等10个)")
        print("2. 下载热门币种 (包含DeFi等共20个)")
        print("3. 下载所有币种 (包含新兴币种共30个)")
        print("4. 自定义交易对")

        choice = input("\n请选择 (1-4): ").strip()

        if choice == '1':
            symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT',
                      'SOL/USDT', 'DOGE/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT']
        elif choice == '2':
            symbols = get_popular_symbols()[:20]
        elif choice == '3':
            symbols = get_popular_symbols()
        elif choice == '4':
            print("请输入要下载的交易对，用逗号分隔 (例如: BTC/USDT,ETH/USDT,BNB/USDT)")
            input_symbols = input("交易对: ").strip()
            symbols = [s.strip().upper() for s in input_symbols.split(',') if s.strip()]
            if not symbols:
                print("❌ 未输入有效交易对")
                return 1
        else:
            print("❌ 无效选择")
            return 1

        # 确认下载
        print(f"\n准备下载 {len(symbols)} 个交易对的日线数据")
        print(f"交易对: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")

        confirm = input("\n确认下载? (y/N): ").strip().lower()
        if confirm != 'y':
            print("下载已取消")
            return 0

        # 开始下载
        start_time = time.time()
        success_count, failed_symbols = download_historical_data_since_2018(symbols)
        end_time = time.time()

        # 显示耗时
        duration = end_time - start_time
        print(f"\n⏱️  总耗时: {duration/60:.1f} 分钟")

        if success_count > 0:
            print(f"\n🎉 成功下载 {success_count} 个交易对的历史数据!")
            print(f"📂 数据位置: {project_root}/data/binance_historical/")
            print(f"\n💡 使用提示:")
            print(f"   - 可以在backtest中使用这些数据进行策略测试")
            print(f"   - 数据格式为parquet，便于快速读取和分析")
            print(f"   - 包含完整的OHLCV数据")

        if failed_symbols:
            print(f"\n⚠️  {len(failed_symbols)} 个交易对下载失败，可以稍后重试")

        return 0 if success_count > 0 else 1

    except KeyboardInterrupt:
        print("\n\n❌ 下载被用户中断")
        return 1
    except Exception as e:
        logger.error(f"下载过程中出现未预期的错误: {e}")
        print(f"\n❌ 下载过程中出现错误: {e}")
        print("请检查:")
        print("  - 网络连接是否正常")
        print("  - Binance API是否可访问")
        print("  - 磁盘空间是否充足")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)