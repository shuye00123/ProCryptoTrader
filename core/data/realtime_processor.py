"""
实时数据处理器 - 高频突破策略数据处理层

负责处理从WebSocket接收的实时Ticker数据，提供数据缓存、
技术指标计算、异常检测等功能，为突破检测算法提供数据支持。

核心功能:
- 实时数据缓存和管理
- 多时间窗口技术指标计算
- 异常数据检测和过滤
- 性能优化和内存管理
"""

import asyncio
import logging
import time
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from dataclasses import dataclass

from .websocket_client import TickerData

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class ProcessedTickerData:
    """处理后的Ticker数据"""
    symbol: str
    timestamp: datetime
    price: float
    volume: float
    price_change: float
    price_change_pct: float

    # 技术指标
    sma_5m: float = 0.0        # 5分钟简单移动平均
    sma_15m: float = 0.0       # 15分钟简单移动平均
    volume_sma_10m: float = 0.0 # 10分钟成交量移动平均
    volatility_5m: float = 0.0  # 5分钟波动率

    # 突破检测指标
    price_breakout_strength: float = 0.0  # 价格突破强度
    volume_surge_ratio: float = 0.0       # 成交量激增比率
    volatility_ratio: float = 0.0          # 波动率比率

    # 数据质量指标
    data_quality_score: float = 1.0       # 数据质量评分
    anomaly_detected: bool = False        # 是否检测到异常


class RealtimeDataProcessor:
    """实时数据处理器

    处理高频突破策略的实时数据，包括缓存、指标计算、异常检测等
    """

    def __init__(self,
                 max_symbols: int = 1000,
                 price_window_size: int = 300,    # 5分钟窗口 (300秒)
                 volume_window_size: int = 600,   # 10分钟窗口 (600秒)
                 anomaly_threshold: float = 3.0):
        """
        初始化实时数据处理器

        Args:
            max_symbols: 最大支持交易对数量
            price_window_size: 价格数据窗口大小（秒）
            volume_window_size: 成交量数据窗口大小（秒）
            anomaly_threshold: 异常检测阈值（标准差倍数）
        """
        self.max_symbols = max_symbols
        self.price_window_size = price_window_size
        self.volume_window_size = volume_window_size
        self.anomaly_threshold = anomaly_threshold

        # 数据缓存 - 使用deque提高性能
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=price_window_size))
        self.volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=volume_window_size))
        self.timestamp_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max(price_window_size, volume_window_size)))

        # 最新数据缓存
        self.latest_data: Dict[str, ProcessedTickerData] = {}
        self.last_update_time: Dict[str, datetime] = {}

        # 技术指标缓存
        self.indicators_cache: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.last_indicator_update: Dict[str, datetime] = {}

        # 统计信息
        self.stats = {
            'processed_messages': 0,
            'anomalies_detected': 0,
            'symbols_tracked': 0,
            'cache_size': 0,
            'processing_time_avg': 0.0,
            'last_update_time': None
        }

        # 性能监控
        self.processing_times = deque(maxlen=1000)  # 保留最近1000次处理时间

        logger.info(f"实时数据处理器初始化完成，最大支持{max_symbols}个交易对")

    async def process_ticker_data(self, ticker_data: TickerData) -> Optional[ProcessedTickerData]:
        """
        处理Ticker数据

        Args:
            ticker_data: 原始Ticker数据

        Returns:
            处理后的数据，如果处理失败返回None
        """
        start_time = time.time()

        try:
            # 1. 数据验证
            if not self._validate_ticker_data(ticker_data):
                return None

            # 2. 更新历史数据缓存
            self._update_history_cache(ticker_data)

            # 3. 计算技术指标
            indicators = await self._calculate_indicators(ticker_data.symbol)

            # 4. 异常检测
            anomaly_score, is_anomaly = await self._detect_anomaly(ticker_data, indicators)

            # 5. 创建处理后的数据
            processed_data = self._create_processed_data(ticker_data, indicators, anomaly_score, is_anomaly)

            # 6. 更新缓存
            self._update_cache(processed_data)

            # 7. 更新统计信息
            processing_time = time.time() - start_time
            self._update_stats(processing_time, is_anomaly)

            return processed_data

        except Exception as e:
            logger.error(f"处理Ticker数据失败 {ticker_data.symbol}: {e}")
            return None

    def _validate_ticker_data(self, ticker_data: TickerData) -> bool:
        """验证Ticker数据有效性"""
        if not ticker_data:
            return False

        # 检查必要字段
        if ticker_data.price <= 0 or ticker_data.volume < 0:
            logger.warning(f"无效的价格或成交量数据: {ticker_data.symbol}, price={ticker_data.price}, volume={ticker_data.volume}")
            return False

        # 检查数据时效性（不能是太久远的数据）
        current_time = datetime.now()
        ticker_time = datetime.fromtimestamp(ticker_data.close_time / 1000) if ticker_data.close_time else current_time

        if abs((current_time - ticker_time).total_seconds()) > 300:  # 5分钟
            logger.warning(f"数据过时: {ticker_data.symbol}, 时间差: {(current_time - ticker_time).total_seconds()}秒")
            return False

        return True

    def _update_history_cache(self, ticker_data: TickerData):
        """更新历史数据缓存"""
        symbol = ticker_data.symbol
        current_time = datetime.now()

        # 更新价格历史
        self.price_history[symbol].append({
            'price': ticker_data.price,
            'timestamp': current_time.timestamp()
        })

        # 更新成交量历史
        self.volume_history[symbol].append({
            'volume': ticker_data.volume,
            'timestamp': current_time.timestamp()
        })

        # 更新时间戳历史
        self.timestamp_history[symbol].append(current_time.timestamp())

        # 清理过期的数据（由deque的maxlen自动处理）

    async def _calculate_indicators(self, symbol: str) -> Dict[str, float]:
        """计算技术指标"""
        # 检查是否需要重新计算
        current_time = datetime.now()
        last_update = self.last_indicator_update.get(symbol)

        if (last_update and
            (current_time - last_update).total_seconds() < 1):  # 1秒内不重复计算
            return self.indicators_cache.get(symbol, {})

        indicators = {}

        try:
            # 价格数据
            price_data = list(self.price_history[symbol])
            volume_data = list(self.volume_history[symbol])

            if len(price_data) >= 5:  # 至少需要5个数据点
                prices = [item['price'] for item in price_data]

                # 简单移动平均
                if len(prices) >= 300:  # 5分钟数据
                    indicators['sma_5m'] = np.mean(prices[-300:])
                elif len(prices) >= 60:  # 1分钟数据
                    indicators['sma_5m'] = np.mean(prices[-60:])

                if len(prices) >= 900:  # 15分钟数据
                    indicators['sma_15m'] = np.mean(prices[-900:])
                elif len(prices) >= 180:  # 3分钟数据
                    indicators['sma_15m'] = np.mean(prices[-180:])

                # 价格波动率（5分钟）
                if len(prices) >= 60:  # 1分钟数据
                    price_returns = np.diff(np.log(prices[-60:]))
                    indicators['volatility_5m'] = np.std(price_returns) * np.sqrt(60)  # 年化波动率

            # 成交量数据
            if len(volume_data) >= 600:  # 10分钟数据
                volumes = [item['volume'] for item in volume_data[-600:]]
                indicators['volume_sma_10m'] = np.mean(volumes)
            elif len(volume_data) >= 60:  # 1分钟数据
                volumes = [item['volume'] for item in volume_data[-60:]]
                indicators['volume_sma_10m'] = np.mean(volumes)

            # 计算突破检测相关指标
            indicators = await self._calculate_breakout_indicators(symbol, indicators)

        except Exception as e:
            logger.error(f"计算技术指标失败 {symbol}: {e}")

        # 缓存结果
        self.indicators_cache[symbol] = indicators
        self.last_indicator_update[symbol] = current_time

        return indicators

    async def _calculate_breakout_indicators(self, symbol: str, indicators: Dict[str, float]) -> Dict[str, float]:
        """计算突破检测相关指标"""
        price_data = list(self.price_history[symbol])
        volume_data = list(self.volume_history[symbol])

        if len(price_data) < 10:
            return indicators

        current_price = price_data[-1]['price']

        # 价格突破强度
        if len(price_data) >= 60:  # 1分钟数据
            recent_prices = [item['price'] for item in price_data[-60:]]
            min_price = min(recent_prices)
            max_price = max(recent_prices)
            price_range = max_price - min_price

            if price_range > 0:
                # 当前价格在区间中的位置
                price_position = (current_price - min_price) / price_range
                indicators['price_breakout_strength'] = price_position

        # 成交量激增比率
        if len(volume_data) >= 120:  # 2分钟数据
            recent_volumes = [item['volume'] for item in volume_data[-60:]]  # 最近1分钟
            historical_volumes = [item['volume'] for item in volume_data[-120:-60]]  # 前1分钟

            if historical_volumes:
                avg_historical_volume = np.mean(historical_volumes)
                if avg_historical_volume > 0:
                    current_avg_volume = np.mean(recent_volumes)
                    indicators['volume_surge_ratio'] = current_avg_volume / avg_historical_volume

        # 波动率比率
        if 'volatility_5m' in indicators:
            # 与历史平均波动率的比较
            historical_volatilities = []
            for i in range(0, len(price_data) - 60, 60):  # 每1分钟计算一次波动率
                if i + 120 <= len(price_data):
                    window_prices = [item['price'] for item in price_data[i:i+120]]
                    if len(window_prices) >= 60:
                        price_returns = np.diff(np.log(window_prices))
                        vol = np.std(price_returns) * np.sqrt(60)
                        historical_volatilities.append(vol)

            if historical_volatilities:
                avg_historical_vol = np.mean(historical_volatilities)
                if avg_historical_vol > 0:
                    indicators['volatility_ratio'] = indicators['volatility_5m'] / avg_historical_vol

        return indicators

    async def _detect_anomaly(self, ticker_data: TickerData, indicators: Dict[str, float]) -> Tuple[float, bool]:
        """检测异常数据

        Args:
            ticker_data: Ticker数据
            indicators: 技术指标

        Returns:
            (异常评分, 是否异常)
        """
        anomaly_score = 0.0
        is_anomaly = False

        try:
            symbol = ticker_data.symbol
            price_data = list(self.price_history[symbol])
            volume_data = list(self.volume_history[symbol])

            if len(price_data) < 10:
                return 1.0, False  # 数据不足，给予中等评分

            current_price = ticker_data.price
            current_volume = ticker_data.volume

            # 1. 价格异常检测
            prices = [item['price'] for item in price_data[-60:]]  # 最近1分钟
            if len(prices) >= 10:
                mean_price = np.mean(prices[:-1])  # 排除当前价格
                std_price = np.std(prices[:-1])

                if std_price > 0:
                    price_z_score = abs(current_price - mean_price) / std_price
                    if price_z_score > self.anomaly_threshold:
                        anomaly_score += min(price_z_score / self.anomaly_threshold, 1.0) * 0.4

            # 2. 成交量异常检测
            if len(volume_data) >= 10:
                volumes = [item['volume'] for item in volume_data[-60:-1]]  # 排除当前成交量
                if volumes:
                    mean_volume = np.mean(volumes)
                    std_volume = np.std(volumes)

                    if std_volume > 0:
                        volume_z_score = abs(current_volume - mean_volume) / std_volume
                        if volume_z_score > self.anomaly_threshold:
                            anomaly_score += min(volume_z_score / self.anomaly_threshold, 1.0) * 0.3

            # 3. 价格变化率异常检测
            if len(price_data) >= 2:
                prev_price = price_data[-2]['price']
                price_change_rate = abs(current_price - prev_price) / prev_price

                # 正常情况下1秒内价格变化不应该超过5%
                if price_change_rate > 0.05:
                    anomaly_score += min(price_change_rate / 0.1, 1.0) * 0.3

            # 判断是否异常
            is_anomaly = anomaly_score > 0.7  # 阈值可调整

            if is_anomaly:
                self.stats['anomalies_detected'] += 1
                logger.warning(f"检测到异常数据: {symbol}, 异常评分: {anomaly_score:.2f}")

        except Exception as e:
            logger.error(f"异常检测失败 {ticker_data.symbol}: {e}")
            anomaly_score = 1.0  # 检测失败时给予最高异常评分

        return anomaly_score, is_anomaly

    def _create_processed_data(self, ticker_data: TickerData, indicators: Dict[str, float],
                             anomaly_score: float, is_anomaly: bool) -> ProcessedTickerData:
        """创建处理后的数据对象"""
        return ProcessedTickerData(
            symbol=ticker_data.symbol,
            timestamp=datetime.now(),
            price=ticker_data.price,
            volume=ticker_data.volume,
            price_change=ticker_data.price_change,
            price_change_pct=ticker_data.price_change_percent,
            sma_5m=indicators.get('sma_5m', 0.0),
            sma_15m=indicators.get('sma_15m', 0.0),
            volume_sma_10m=indicators.get('volume_sma_10m', 0.0),
            volatility_5m=indicators.get('volatility_5m', 0.0),
            price_breakout_strength=indicators.get('price_breakout_strength', 0.0),
            volume_surge_ratio=indicators.get('volume_surge_ratio', 1.0),
            volatility_ratio=indicators.get('volatility_ratio', 1.0),
            data_quality_score=1.0 - anomaly_score,
            anomaly_detected=is_anomaly
        )

    def _update_cache(self, processed_data: ProcessedTickerData):
        """更新缓存"""
        symbol = processed_data.symbol

        # 更新最新数据缓存
        self.latest_data[symbol] = processed_data
        self.last_update_time[symbol] = processed_data.timestamp

        # 限制缓存大小
        if len(self.latest_data) > self.max_symbols:
            # 删除最久未更新的数据
            oldest_symbol = min(self.last_update_time.items(), key=lambda x: x[1])[0]
            del self.latest_data[oldest_symbol]
            del self.last_update_time[oldest_symbol]
            if oldest_symbol in self.indicators_cache:
                del self.indicators_cache[oldest_symbol]
            if oldest_symbol in self.last_indicator_update:
                del self.last_indicator_update[oldest_symbol]

    def _update_stats(self, processing_time: float, is_anomaly: bool):
        """更新统计信息"""
        self.stats['processed_messages'] += 1
        self.stats['last_update_time'] = datetime.now()

        # 更新处理时间统计
        self.processing_times.append(processing_time)
        self.stats['processing_time_avg'] = np.mean(self.processing_times)

        # 更新其他统计
        self.stats['symbols_tracked'] = len(self.latest_data)
        self.stats['cache_size'] = sum(len(self.price_history[s]) for s in self.price_history)

    def get_latest_data(self, symbol: str) -> Optional[ProcessedTickerData]:
        """获取指定交易对的最新处理数据"""
        return self.latest_data.get(symbol)

    def get_price_history(self, symbol: str, limit: Optional[int] = None) -> List[Dict]:
        """获取价格历史数据"""
        history = list(self.price_history[symbol])
        if limit:
            return history[-limit:]
        return history

    def get_volume_history(self, symbol: str, limit: Optional[int] = None) -> List[Dict]:
        """获取成交量历史数据"""
        history = list(self.volume_history[symbol])
        if limit:
            return history[-limit:]
        return history

    def get_indicators(self, symbol: str) -> Dict[str, float]:
        """获取技术指标"""
        return self.indicators_cache.get(symbol, {}).copy()

    def get_all_symbols(self) -> List[str]:
        """获取所有跟踪的交易对"""
        return list(self.latest_data.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        stats = self.stats.copy()

        # 添加额外的统计信息
        if self.processing_times:
            stats['processing_time_max'] = max(self.processing_times)
            stats['processing_time_min'] = min(self.processing_times)
            stats['processing_time_p95'] = np.percentile(list(self.processing_times), 95)

        # 缓存内存使用估算
        total_price_points = sum(len(history) for history in self.price_history.values())
        total_volume_points = sum(len(history) for history in self.volume_history.values())
        stats['cached_data_points'] = total_price_points + total_volume_points

        return stats

    def clear_cache(self, symbol: Optional[str] = None):
        """清理缓存

        Args:
            symbol: 要清理的交易对，如果为None则清理所有
        """
        if symbol:
            self.price_history.pop(symbol, None)
            self.volume_history.pop(symbol, None)
            self.timestamp_history.pop(symbol, None)
            self.latest_data.pop(symbol, None)
            self.last_update_time.pop(symbol, None)
            self.indicators_cache.pop(symbol, None)
            self.last_indicator_update.pop(symbol, None)
            logger.info(f"已清理交易对 {symbol} 的缓存")
        else:
            self.price_history.clear()
            self.volume_history.clear()
            self.timestamp_history.clear()
            self.latest_data.clear()
            self.last_update_time.clear()
            self.indicators_cache.clear()
            self.last_indicator_update.clear()
            logger.info("已清理所有缓存")

    def cleanup_old_data(self, max_age_minutes: int = 60):
        """清理过期数据

        Args:
            max_age_minutes: 数据最大保留时间（分钟）
        """
        current_time = datetime.now()
        max_age = timedelta(minutes=max_age_minutes)

        symbols_to_remove = []

        for symbol, last_update in self.last_update_time.items():
            if current_time - last_update > max_age:
                symbols_to_remove.append(symbol)

        for symbol in symbols_to_remove:
            self.clear_cache(symbol)

        if symbols_to_remove:
            logger.info(f"清理了 {len(symbols_to_remove)} 个交易对的过期数据")


# 示例使用
async def example_usage():
    """示例用法"""
    from .websocket_client import TickerData

    processor = RealtimeDataProcessor()

    # 模拟处理Ticker数据
    for i in range(100):
        ticker = TickerData(
            symbol="BTCUSDT",
            price=50000 + i * 10,
            price_change=100 + i,
            price_change_percent=0.2 + i * 0.01,
            weighted_avg_price=50000,
            open_price=49000,
            high_price=51000,
            low_price=48000,
            volume=1000 + i * 10,
            quote_volume=50000000,
            open_time=int(time.time() * 1000),
            close_time=int(time.time() * 1000),
            first_id=1,
            last_id=1000,
            count=1000
        )

        processed_data = await processor.process_ticker_data(ticker)

        if processed_data and i % 10 == 0:
            print(f"处理数据 {processed_data.symbol}: "
                  f"价格=${processed_data.price:.2f}, "
                  f"突破强度={processed_data.price_breakout_strength:.2f}, "
                  f"数据质量={processed_data.data_quality_score:.2f}")

        # 模拟实时数据间隔
        await asyncio.sleep(0.1)

    # 打印统计信息
    stats = processor.get_stats()
    print(f"\n处理统计: {stats}")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    asyncio.run(example_usage())