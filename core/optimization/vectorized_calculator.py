"""
向量化计算器

提供高性能的技术指标计算，使用NumPy向量化操作替代循环计算。
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
from abc import ABC, abstractmethod
from functools import lru_cache

from ..cache import cache_result, get_cache_manager
from ..exceptions import CalculationError


class VectorizedCalculator(ABC):
    """向量化计算器基类"""

    def __init__(self, cache_enabled: bool = True):
        """
        初始化计算器

        Args:
            cache_enabled: 是否启用缓存
        """
        self.cache_enabled = cache_enabled
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def calculate(self, data: pd.DataFrame, **kwargs) -> Union[float, np.ndarray, pd.Series]:
        """执行计算"""
        pass


class MovingAverageCalculator(VectorizedCalculator):
    """移动平均线计算器"""

    @cache_result(ttl=300, key_prefix="ma")
    def calculate(self, data: pd.DataFrame, period: int = 20, ma_type: str = 'sma') -> pd.Series:
        """
        计算移动平均线

        Args:
            data: 价格数据，必须包含'close'列
            period: 计算周期
            ma_type: 移动平均类型 ('sma', 'ema', 'wma', 'hma')

        Returns:
            pd.Series: 移动平均线值
        """
        if 'close' not in data.columns:
            raise CalculationError("Data must contain 'close' column")

        close_prices = data['close'].values

        if ma_type.lower() == 'sma':
            return self._calculate_sma(close_prices, period)
        elif ma_type.lower() == 'ema':
            return self._calculate_ema(close_prices, period)
        elif ma_type.lower() == 'wma':
            return self._calculate_wma(close_prices, period)
        elif ma_type.lower() == 'hma':
            return self._calculate_hma(close_prices, period)
        else:
            raise CalculationError(f"Unsupported MA type: {ma_type}")

    def _calculate_sma(self, prices: np.ndarray, period: int) -> pd.Series:
        """计算简单移动平均线"""
        return pd.Series(prices).rolling(window=period, min_periods=1).mean()

    def _calculate_ema(self, prices: np.ndarray, period: int) -> pd.Series:
        """计算指数移动平均线"""
        return pd.Series(prices).ewm(span=period, adjust=False).mean()

    def _calculate_wma(self, prices: np.ndarray, period: int) -> pd.Series:
        """计算加权移动平均线"""
        weights = np.arange(1, period + 1)
        weights = weights / weights.sum()

        result = np.full(len(prices), np.nan)
        for i in range(period - 1, len(prices)):
            result[i] = np.dot(prices[i - period + 1:i + 1], weights)

        return pd.Series(result)

    def _calculate_hma(self, prices: np.ndarray, period: int) -> pd.Series:
        """计算Hull移动平均线"""
        # HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        half_period = max(1, period // 2)
        sqrt_period = max(1, int(np.sqrt(period)))

        wma_half = self._calculate_wma(prices, half_period)
        wma_full = self._calculate_wma(prices, period)

        hull_data = 2 * wma_half - wma_full
        return self._calculate_wma(hull_data.dropna().values, sqrt_period)


class RSICalculator(VectorizedCalculator):
    """RSI计算器"""

    @cache_result(ttl=300, key_prefix="rsi")
    def calculate(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算RSI

        Args:
            data: 价格数据，必须包含'close'列
            period: 计算周期

        Returns:
            pd.Series: RSI值
        """
        if 'close' not in data.columns:
            raise CalculationError("Data must contain 'close' column")

        close_prices = data['close'].values
        delta = np.diff(close_prices)

        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)

        avg_gains = pd.Series(gains).rolling(window=period, min_periods=1).mean()
        avg_losses = pd.Series(losses).rolling(window=period, min_periods=1).mean()

        rs = avg_gains / (avg_losses + 1e-10)  # 避免除零
        rsi = 100 - (100 / (1 + rs))

        return pd.Series(rsi, index=data.index)


class BollingerBandsCalculator(VectorizedCalculator):
    """布林带计算器"""

    @cache_result(ttl=300, key_prefix="bb")
    def calculate(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        计算布林带

        Args:
            data: 价格数据，必须包含'close'列
            period: 计算周期
            std_dev: 标准差倍数

        Returns:
            Dict[str, pd.Series]: 包含上轨、中轨、下轨的字典
        """
        if 'close' not in data.columns:
            raise CalculationError("Data must contain 'close' column")

        close_prices = data['close']
        sma = close_prices.rolling(window=period, min_periods=1).mean()
        std = close_prices.rolling(window=period, min_periods=1).std()

        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)

        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band,
            'bandwidth': (upper_band - lower_band) / sma,
            'percent_b': (close_prices - lower_band) / (upper_band - lower_band)
        }


class MACDCalculator(VectorizedCalculator):
    """MACD计算器"""

    @cache_result(ttl=300, key_prefix="macd")
    def calculate(self, data: pd.DataFrame, fast_period: int = 12, slow_period: int = 26,
                  signal_period: int = 9) -> Dict[str, pd.Series]:
        """
        计算MACD

        Args:
            data: 价格数据，必须包含'close'列
            fast_period: 快线周期
            slow_period: 慢线周期
            signal_period: 信号线周期

        Returns:
            Dict[str, pd.Series]: 包含MACD线、信号线、直方图的字典
        """
        if 'close' not in data.columns:
            raise CalculationError("Data must contain 'close' column")

        close_prices = data['close']

        # 计算快慢EMA
        ema_fast = close_prices.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close_prices.ewm(span=slow_period, adjust=False).mean()

        # 计算MACD线
        macd_line = ema_fast - ema_slow

        # 计算信号线
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        # 计算直方图
        histogram = macd_line - signal_line

        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }


class StochasticCalculator(VectorizedCalculator):
    """随机指标计算器"""

    @cache_result(ttl=300, key_prefix="stoch")
    def calculate(self, data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, pd.Series]:
        """
        计算随机指标

        Args:
            data: 价格数据，必须包含'high', 'low', 'close'列
            k_period: %K周期
            d_period: %D周期

        Returns:
            Dict[str, pd.Series]: 包含%K和%D的字典
        """
        required_columns = ['high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            raise CalculationError(f"Data must contain columns: {missing_columns}")

        high_prices = data['high'].rolling(window=k_period, min_periods=1).max()
        low_prices = data['low'].rolling(window=k_period, min_periods=1).min()

        # 计算%K
        k_percent = 100 * ((data['close'] - low_prices) / (high_prices - low_prices + 1e-10))

        # 计算%D ( %K的移动平均)
        d_percent = k_percent.rolling(window=d_period, min_periods=1).mean()

        return {
            'k': k_percent,
            'd': d_percent
        }


class VectorizedIndicatorCalculator:
    """向量化技术指标计算器"""

    def __init__(self, cache_enabled: bool = True):
        """
        初始化计算器

        Args:
            cache_enabled: 是否启用缓存
        """
        self.cache_enabled = cache_enabled
        self.logger = logging.getLogger("VectorizedIndicatorCalculator")

        # 初始化各个计算器
        self.ma_calculator = MovingAverageCalculator(cache_enabled)
        self.rsi_calculator = RSICalculator(cache_enabled)
        self.bb_calculator = BollingerBandsCalculator(cache_enabled)
        self.macd_calculator = MACDCalculator(cache_enabled)
        self.stoch_calculator = StochasticCalculator(cache_enabled)

    def calculate_all_indicators(self, data: pd.DataFrame, config: Optional[Dict] = None) -> Dict[str, Union[pd.Series, Dict[str, pd.Series]]]:
        """
        计算所有技术指标

        Args:
            data: 价格数据
            config: 指标配置参数

        Returns:
            Dict[str, Union[pd.Series, Dict[str, pd.Series]]]: 所有指标结果
        """
        if config is None:
            config = self._get_default_config()

        indicators = {}

        try:
            # 移动平均线
            if config.get('moving_averages', {}).get('enabled', True):
                ma_config = config['moving_averages']
                indicators['sma_20'] = self.ma_calculator.calculate(data, period=20, ma_type='sma')
                indicators['sma_50'] = self.ma_calculator.calculate(data, period=50, ma_type='sma')
                indicators['sma_200'] = self.ma_calculator.calculate(data, period=200, ma_type='sma')
                indicators['ema_12'] = self.ma_calculator.calculate(data, period=12, ma_type='ema')
                indicators['ema_26'] = self.ma_calculator.calculate(data, period=26, ma_type='ema')

            # RSI
            if config.get('rsi', {}).get('enabled', True):
                rsi_config = config['rsi']
                indicators['rsi'] = self.rsi_calculator.calculate(
                    data, period=rsi_config.get('period', 14)
                )

            # 布林带
            if config.get('bollinger_bands', {}).get('enabled', True):
                bb_config = config['bollinger_bands']
                bb_result = self.bb_calculator.calculate(
                    data,
                    period=bb_config.get('period', 20),
                    std_dev=bb_config.get('std_dev', 2.0)
                )
                indicators['bb_upper'] = bb_result['upper']
                indicators['bb_middle'] = bb_result['middle']
                indicators['bb_lower'] = bb_result['lower']
                indicators['bb_bandwidth'] = bb_result['bandwidth']
                indicators['bb_percent_b'] = bb_result['percent_b']

            # MACD
            if config.get('macd', {}).get('enabled', True):
                macd_config = config['macd']
                macd_result = self.macd_calculator.calculate(
                    data,
                    fast_period=macd_config.get('fast_period', 12),
                    slow_period=macd_config.get('slow_period', 26),
                    signal_period=macd_config.get('signal_period', 9)
                )
                indicators['macd'] = macd_result['macd']
                indicators['macd_signal'] = macd_result['signal']
                indicators['macd_histogram'] = macd_result['histogram']

            # 随机指标
            if config.get('stochastic', {}).get('enabled', True):
                stoch_config = config['stochastic']
                stoch_result = self.stoch_calculator.calculate(
                    data,
                    k_period=stoch_config.get('k_period', 14),
                    d_period=stoch_config.get('d_period', 3)
                )
                indicators['stoch_k'] = stoch_result['k']
                indicators['stoch_d'] = stoch_result['d']

            self.logger.info(f"Successfully calculated {len(indicators)} indicators")
            return indicators

        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            raise CalculationError(f"Failed to calculate indicators: {e}")

    def calculate_single_indicator(self, data: pd.DataFrame, indicator_type: str, **params) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        计算单个指标

        Args:
            data: 价格数据
            indicator_type: 指标类型
            **params: 指标参数

        Returns:
            Union[pd.Series, Dict[str, pd.Series]]: 指标结果
        """
        try:
            if indicator_type.lower() in ['sma', 'ema', 'wma', 'hma']:
                return self.ma_calculator.calculate(data, **params)
            elif indicator_type.lower() == 'rsi':
                return self.rsi_calculator.calculate(data, **params)
            elif indicator_type.lower() == 'bollinger_bands':
                return self.bb_calculator.calculate(data, **params)
            elif indicator_type.lower() == 'macd':
                return self.macd_calculator.calculate(data, **params)
            elif indicator_type.lower() == 'stochastic':
                return self.stoch_calculator.calculate(data, **params)
            else:
                raise CalculationError(f"Unsupported indicator type: {indicator_type}")

        except Exception as e:
            self.logger.error(f"Error calculating {indicator_type}: {e}")
            raise CalculationError(f"Failed to calculate {indicator_type}: {e}")

    def _get_default_config(self) -> Dict:
        """获取默认指标配置"""
        return {
            'moving_averages': {
                'enabled': True
            },
            'rsi': {
                'enabled': True,
                'period': 14
            },
            'bollinger_bands': {
                'enabled': True,
                'period': 20,
                'std_dev': 2.0
            },
            'macd': {
                'enabled': True,
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9
            },
            'stochastic': {
                'enabled': True,
                'k_period': 14,
                'd_period': 3
            }
        }

    def get_calculation_stats(self) -> Dict[str, Any]:
        """获取计算统计信息"""
        cache_manager = get_cache_manager()
        cache_stats = cache_manager.get_stats()

        return {
            'cache_enabled': self.cache_enabled,
            'cache_stats': cache_stats,
            'available_indicators': [
                'SMA', 'EMA', 'WMA', 'HMA',
                'RSI',
                'Bollinger Bands',
                'MACD',
                'Stochastic'
            ]
        }


# 全局计算器实例
_global_calculator = None


def get_vectorized_calculator(cache_enabled: bool = True) -> VectorizedIndicatorCalculator:
    """获取全局向量化计算器实例"""
    global _global_calculator
    if _global_calculator is None:
        _global_calculator = VectorizedIndicatorCalculator(cache_enabled)
    return _global_calculator


def calculate_indicators_fast(data: pd.DataFrame, indicators: List[str] = None) -> Dict[str, Union[pd.Series, Dict[str, pd.Series]]]:
    """
    快速计算技术指标的便捷函数

    Args:
        data: 价格数据
        indicators: 要计算的指标列表，None表示计算所有

    Returns:
        Dict[str, Union[pd.Series, Dict[str, pd.Series]]]: 指标结果
    """
    calculator = get_vectorized_calculator()

    if indicators is None:
        return calculator.calculate_all_indicators(data)
    else:
        results = {}
        for indicator in indicators:
            try:
                results[indicator] = calculator.calculate_single_indicator(data, indicator)
            except Exception as e:
                logging.getLogger("FastIndicators").warning(f"Failed to calculate {indicator}: {e}")
        return results