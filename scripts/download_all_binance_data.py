#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载Binance自2018年以来所有交易对的日线数据
注意：这是一个大规模数据下载任务，可能需要数小时完成
"""

import os
import sys
import time
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data.data_fetcher import DataFetcher
from core.data.data_manager import DataManager
from core.utils.logger import get_logger

logger = get_logger("DownloadAllBinanceData")

# 全局变量用于优雅退出
is_interrupted = False
download_stats = {
    'total_symbols': 0,
    'successful_downloads': 0,
    'failed_downloads': 0,
    'start_time': None,
    'end_time': None,
    'failed_symbols': [],
    'processed_symbols': []
}

def signal_handler(signum, frame):
    """处理中断信号"""
    global is_interrupted
    is_interrupted = True
    print("\n\n⚠️  收到中断信号，正在优雅退出...")
    print("已完成的下载信息将被保存")


def get_active_symbols(fetcher: DataFetcher, min_volume: float = 1000000) -> List[str]:
    """
    获取活跃的交易对列表

    Args:
        fetcher: DataFetcher实例
        min_volume: 最小24小时交易量（USDT）

    Returns:
        活跃交易对列表
    """
    print("📊 获取Binance交易对信息...")

    try:
        # 获取市场信息
        markets = fetcher.get_exchange_info()

        active_symbols = []
        for symbol, info in markets.items():
            # 只选择USDT交易对
            if not symbol.endswith('/USDT'):
                continue

            # 只选择现货交易对
            if info.get('type') != 'spot':
                continue

            # 只选择活跃的交易对
            if not info.get('active', False):
                continue

            # 过滤掉稳定币对和特殊符号
            quote = symbol.split('/')[1]
            if quote in ['BUSD', 'USDC', 'TUSD', 'PAX', 'USDP']:
                continue

            # 过滤掉一些特殊符号
            base = symbol.split('/')[0]
            if any(char in base for char in ['UP', 'DOWN', 'BEAR', 'BULL']):
                continue

            active_symbols.append(symbol)

        # 按字母顺序排序
        active_symbols.sort()

        print(f"✓ 找到 {len(active_symbols)} 个活跃的USDT交易对")
        return active_symbols

    except Exception as e:
        logger.error(f"获取交易对信息失败: {e}")
        # 如果获取失败，返回一些热门交易对
        fallback_symbols = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT',
            'XRP/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT',
            'LINK/USDT', 'UNI/USDT', 'LTC/USDT', 'BCH/USDT', 'FIL/USDT',
            'ETC/USDT', 'XLM/USDT', 'VET/USDT', 'THETA/USDT', 'TRX/USDT',
            'ICP/USDT', 'SHIB/USDT', 'FTM/USDT', 'NEAR/USDT', 'ATOM/USDT'
        ]
        print(f"⚠️  获取市场信息失败，使用默认的 {len(fallback_symbols)} 个热门交易对")
        return fallback_symbols


def download_symbol_data(manager: DataManager, fetcher: DataFetcher, symbol: str,
                        start_date: str, end_date: str, timeframe: str = '1d') -> bool:
    """
    下载单个交易对的数据

    Args:
        manager: DataManager实例
        fetcher: DataFetcher实例
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期
        timeframe: 时间框架

    Returns:
        是否下载成功
    """
    try:
        # 检查数据是否已存在
        existing_data = manager.load_data(symbol, timeframe, start_date, end_date)
        if not existing_data.empty:
            expected_days = (datetime.strptime(end_date, '%Y-%m-%d') -
                           datetime.strptime(start_date, '%Y-%m-%d')).days + 1
            if len(existing_data) >= expected_days * 0.95:  # 95%完整度
                print(f"  ✓ {symbol} 数据已存在 ({len(existing_data)} 条)")
                return True

        print(f"  ⬇️  正在下载 {symbol} 日线数据...")

        # 下载数据
        result = manager.download_historical_data(symbol, timeframe, start_date, end_date)

        if result:
            # 验证下载数据
            data = manager.load_data(symbol, timeframe, start_date, end_date)
            if not data.empty:
                print(f"  ✓ {symbol} 下载成功 ({len(data)} 条数据)")
                download_stats['successful_downloads'] += 1
                download_stats['processed_symbols'].append(symbol)
                return True
            else:
                print(f"  ✗ {symbol} 下载后数据为空")
                download_stats['failed_downloads'] += 1
                download_stats['failed_symbols'].append(symbol)
                return False
        else:
            print(f"  ✗ {symbol} 下载失败")
            download_stats['failed_downloads'] += 1
            download_stats['failed_symbols'].append(symbol)
            return False

    except Exception as e:
        logger.error(f"下载 {symbol} 数据时出错: {e}")
        print(f"  ✗ {symbol} 下载出错: {str(e)[:50]}...")
        download_stats['failed_downloads'] += 1
        download_stats['failed_symbols'].append(symbol)
        return False


def save_progress_stats():
    """保存下载进度统计"""
    stats_file = project_root / "data" / "download_stats.json"
    stats_file.parent.mkdir(parents=True, exist_ok=True)

    # 添加时间戳
    download_stats['end_time'] = datetime.now().isoformat()
    if download_stats['start_time']:
        duration = datetime.now() - download_stats['start_time']
        download_stats['duration_seconds'] = duration.total_seconds()
        download_stats['duration_formatted'] = str(duration).split('.')[0]

    try:
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(download_stats, f, indent=2, ensure_ascii=False)
        print(f"\n📊 下载统计已保存到: {stats_file}")
    except Exception as e:
        logger.error(f"保存统计信息失败: {e}")


def main():
    """主函数"""
    global download_stats

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 80)
    print("🚀 Binance 全量历史数据下载工具")
    print("   下载自2018年以来所有活跃交易对的日线数据")
    print("=" * 80)

    # 配置参数
    data_dir = project_root / "data" / "binance"
    data_dir.mkdir(parents=True, exist_ok=True)

    start_date = "2018-01-01"
    end_date = datetime.now().strftime('%Y-%m-%d')
    timeframe = "1d"

    print(f"📁 数据目录: {data_dir}")
    print(f"📅 时间范围: {start_date} 至 {end_date}")
    print(f"⏰ 时间框架: {timeframe}")

    try:
        # 初始化数据获取器和管理器
        print("\n🔧 初始化数据获取器...")
        fetcher = DataFetcher('binance', enable_rate_limit=True)
        # 修改为现货交易
        fetcher.exchange.options['defaultType'] = 'spot'
        manager = DataManager(str(data_dir), 'binance')

        # 获取活跃交易对列表
        symbols = get_active_symbols(fetcher)
        download_stats['total_symbols'] = len(symbols)
        download_stats['start_time'] = datetime.now()

        print(f"\n🎯 准备下载 {len(symbols)} 个交易对的日线数据")
        print(f"⏱️  预计耗时: {len(symbols) * 2:.0f} 分钟 (按每个交易对2分钟估算)")

        # 确认是否继续
        user_input = input("\n是否继续下载？(y/N): ").strip().lower()
        if user_input not in ['y', 'yes']:
            print("下载已取消")
            return 0

        # 开始下载
        print(f"\n🚀 开始下载 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 80)

        batch_size = 10  # 每批处理10个交易对
        batch_delay = 30  # 批次间延迟30秒（避免API限制）

        for i in range(0, len(symbols), batch_size):
            if is_interrupted:
                break

            batch = symbols[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(symbols) + batch_size - 1) // batch_size

            print(f"\n📦 批次 {batch_num}/{total_batches}: {', '.join(batch)}")

            # 处理当前批次
            for symbol in batch:
                if is_interrupted:
                    break

                success = download_symbol_data(manager, fetcher, symbol, start_date, end_date, timeframe)

                # 每个交易对间延迟，避免触发API限制
                if symbol != batch[-1]:  # 不是批次中最后一个
                    time.sleep(2)

            # 批次间延迟
            if i + batch_size < len(symbols) and not is_interrupted:
                print(f"⏳ 等待 {batch_delay} 秒以避免API限制...")
                for remaining in range(batch_delay, 0, -1):
                    if is_interrupted:
                        break
                    print(f"   {remaining} 秒", end='\r')
                    time.sleep(1)
                print()  # 换行

        # 输出最终统计
        print("\n" + "=" * 80)
        print("📊 下载完成统计:")
        print(f"   总交易对数: {download_stats['total_symbols']}")
        print(f"   成功下载: {download_stats['successful_downloads']}")
        print(f"   下载失败: {download_stats['failed_downloads']}")
        print(f"   成功率: {(download_stats['successful_downloads'] / download_stats['total_symbols'] * 100):.1f}%")

        if download_stats['failed_symbols']:
            print(f"\n❌ 失败的交易对:")
            for symbol in download_stats['failed_symbols'][:20]:  # 只显示前20个
                print(f"   - {symbol}")
            if len(download_stats['failed_symbols']) > 20:
                print(f"   ... 还有 {len(download_stats['failed_symbols']) - 20} 个")

        # 列出已下载的数据
        available_data = manager.list_available_data()
        print(f"\n📁 已下载的数据目录: {data_dir}")
        print(f"   交易对数量: {len(available_data)}")

        total_size = 0
        for symbol, timeframes in available_data.items():
            for timeframe in timeframes:
                file_path = manager._get_file_path(symbol, timeframe)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)

        if total_size > 0:
            print(f"   总数据大小: {total_size / 1024 / 1024:.1f} MB")

        # 保存统计信息
        save_progress_stats()

        if is_interrupted:
            print("\n⚠️  下载被中断")
            print("💡 提示：可以重新运行此脚本继续下载")
            return 1
        else:
            print("\n🎉 所有数据下载完成！")
            return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断下载")
        save_progress_stats()
        return 1
    except Exception as e:
        logger.error(f"下载过程中发生错误: {e}")
        print(f"\n❌ 下载失败: {e}")
        save_progress_stats()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)