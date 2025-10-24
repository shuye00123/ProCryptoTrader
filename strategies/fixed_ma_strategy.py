#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复版移动平均策略
解决代码审查中发现的关键问题
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.strategy.base_strategy import BaseStrategy, Signal, SignalType

# 设置日志
logger = logging.getLogger(__name__)

class FixedMAStrategy(BaseStrategy):
    """
    修复版移动平均策略

    主要修复：
    1. 信号类型统一 - 使用统一的open_long/close_long信号类型
    2. 状态管理一致性 - 使用基类的持仓管理系统
    3. 异常处理增强 - 添加完整的边界检查
    4. 指标计算优化 - 避免重复计算
    5. 日志记录完善 - 便于调试和监控
    """

    def __init__(self, config: dict):
        """
        初始化策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 策略参数
        self.short_window = config.get('short_window', 10)
        self.long_window = config.get('long_window', 30)
        self.symbol = config.get('symbol', 'BTC/USDT')

        # 验证参数
        if self.short_window >= self.long_window:
            raise ValueError(f"短期窗口 ({self.short_window}) 必须小于长期窗口 ({self.long_window})")

        if self.short_window < 1 or self.long_window < 1:
            raise ValueError("移动平均窗口必须大于0")

        logger.info(f"初始化修复版移动平均策略:")
        logger.info(f"  短期窗口: {self.short_window}")
        logger.info(f"  长期窗口: {self.long_window}")
        logger.info(f"  交易对: {self.symbol}")

    def calculate_indicators(self, data: dict) -> dict:
        """
        计算技术指标

        Args:
            data: 交易对数据字典

        Returns:
            技术指标字典
        """
        indicators = {}

        for symbol, df in data.items():
            if symbol not in indicators:
                indicators[symbol] = {}

            try:
                if df.empty:
                    logger.warning(f"数据为空: {symbol}")
                    indicators[symbol]['short_ma'] = pd.Series([], dtype=float)
                    indicators[symbol]['long_ma'] = pd.Series([], dtype=float)
                    indicators[symbol]['price'] = pd.Series([], dtype=float)
                    continue

                if len(df) < self.long_window:
                    logger.debug(f"数据不足 ({len(df)} < {self.long_window}): {symbol}")
                    indicators[symbol]['short_ma'] = pd.Series([np.nan] * len(df), index=df.index)
                    indicators[symbol]['long_ma'] = pd.Series([np.nan] * len(df), index=df.index)
                    indicators[symbol]['price'] = df['close']
                else:
                    # 计算移动平均线
                    indicators[symbol]['short_ma'] = df['close'].rolling(window=self.short_window).mean()
                    indicators[symbol]['long_ma'] = df['close'].rolling(window=self.long_window).mean()
                    indicators[symbol]['price'] = df['close']

                    logger.debug(f"计算指标完成: {symbol}, 数据点: {len(df)}")

            except Exception as e:
                logger.error(f"计算指标时出错 {symbol}: {e}")
                indicators[symbol]['short_ma'] = pd.Series([], dtype=float)
                indicators[symbol]['long_ma'] = pd.Series([], dtype=float)
                indicators[symbol]['price'] = pd.Series([], dtype=float)

        return indicators

    def generate_signals(self, data: dict) -> list:
        """
        根据行情数据生成交易信号

        Args:
            data: 交易对数据字典

        Returns:
            交易信号列表
        """
        signals = []

        try:
            # 验证输入数据
            if not isinstance(data, dict):
                logger.error("输入数据不是字典类型")
                return signals

            # 获取当前交易对的数据
            if self.symbol not in data:
                logger.debug(f"交易对 {self.symbol} 不在数据中")
                return signals

            df = data[self.symbol]

            # 数据验证
            if df.empty:
                logger.debug(f"数据为空: {self.symbol}")
                return signals

            if len(df) < self.long_window + 1:  # 需要至少long_window+1个数据点来计算金叉死叉
                logger.debug(f"数据不足 ({len(df)} < {self.long_window + 1}): {self.symbol}")
                return signals

            # 使用已计算的指标
            symbol_indicators = self.indicators.get(self.symbol, {})

            if ('short_ma' not in symbol_indicators or
                'long_ma' not in symbol_indicators or
                symbol_indicators['short_ma'].empty or
                symbol_indicators['long_ma'].empty):
                logger.debug(f"指标未计算或为空: {self.symbol}")
                return signals

            # 获取最新的指标值
            try:
                current_price = df['close'].iloc[-1]
                if pd.isna(current_price) or current_price <= 0:
                    logger.warning(f"当前价格异常: {current_price}")
                    return signals

                short_ma_series = symbol_indicators['short_ma']
                long_ma_series = symbol_indicators['long_ma']

                # 获取最新的均线值
                short_ma = short_ma_series.iloc[-1]
                long_ma = long_ma_series.iloc[-1]

                # 检查均线值是否有效
                if pd.isna(short_ma) or pd.isna(long_ma):
                    logger.debug(f"均线值为NaN: short_ma={short_ma}, long_ma={long_ma}")
                    return signals

                # 计算前一个交易日的均线值
                if len(short_ma_series) >= 2 and len(long_ma_series) >= 2:
                    prev_short_ma = short_ma_series.iloc[-2]
                    prev_long_ma = long_ma_series.iloc[-2]

                    if pd.isna(prev_short_ma) or pd.isna(prev_long_ma):
                        logger.debug(f"前一日均线值为NaN: prev_short_ma={prev_short_ma}, prev_long_ma={prev_long_ma}")
                        return signals
                else:
                    logger.debug(f"数据不足计算前一日均线值")
                    return signals

                # 使用基类的持仓管理系统
                has_current_position = self.has_position(self.symbol)

                # 生成交易信号
                # 金叉：短期均线上穿长期均线，买入信号
                if (prev_short_ma <= prev_long_ma) and (short_ma > long_ma) and not has_current_position:
                    logger.info(f"检测到金叉信号: {self.symbol}")
                    logger.info(f"  价格: ${current_price:.2f}, 短期MA: {short_ma:.2f}, 长期MA: {long_ma:.2f}")

                    # 生成买入信号 - 使用统一的信号类型
                    signal = Signal(
                        signal_type=SignalType.OPEN_LONG,
                        symbol=self.symbol,
                        price=current_price,
                        amount=0.1,  # 使用10%资金
                        confidence=0.7,
                        metadata={
                            'strategy': 'FixedMA',
                            'short_ma': short_ma,
                            'long_ma': long_ma,
                            'trigger': 'golden_cross'
                        }
                    )

                    signals.append(signal)

                # 死叉：短期均线下穿长期均线，卖出信号
                elif (prev_short_ma >= prev_long_ma) and (short_ma < long_ma) and has_current_position:
                    logger.info(f"检测到死叉信号: {self.symbol}")
                    logger.info(f"  价格: ${current_price:.2f}, 短期MA: {short_ma:.2f}, 长期MA: {long_ma:.2f}")

                    # 生成卖出信号 - 使用统一的信号类型
                    signal = Signal(
                        signal_type=SignalType.CLOSE_LONG,
                        symbol=self.symbol,
                        price=current_price,
                        amount=1.0,  # 全部卖出
                        confidence=0.7,
                        metadata={
                            'strategy': 'FixedMA',
                            'short_ma': short_ma,
                            'long_ma': long_ma,
                            'trigger': 'death_cross'
                        }
                    )

                    signals.append(signal)

                logger.debug(f"生成信号数量: {len(signals)}")

            except IndexError as e:
                logger.error(f"索引错误 {self.symbol}: {e}")
            except KeyError as e:
                logger.error(f"键错误 {self.symbol}: {e}")
            except Exception as e:
                logger.error(f"生成信号时出错 {self.symbol}: {e}")

        except Exception as e:
            logger.error(f"生成信号时发生未预期错误: {e}")

        return signals

    def initialize(self, config: dict):
        """
        初始化策略（用于回测开始前）

        Args:
            config: 回测配置
        """
        logger.info("策略初始化完成")
        logger.info(f"初始资金: {config.get('initial_balance', 10000):.2f}")
        logger.info(f"交易对: {config.get('symbols', [])}")
        logger.info(f"时间范围: {config.get('start_date')} 至 {config.get('end_date')}")

        # 可以在这里添加其他初始化逻辑
        self.is_initialized = True

    def on_trade_executed(self, signal: Signal, execution_price: float, quantity: float):
        """
        交易执行后的回调

        Args:
            signal: 执行的信号
            execution_price: 执行价格
            quantity: 执行数量
        """
        logger.info(f"交易执行: {signal.signal_type.value} {quantity:.6f} @ ${execution_price:.2f}")

        # 可以在这里添加交易后的逻辑
        if signal.signal_type == SignalType.OPEN_LONG:
            logger.info(f"开仓成功: {self.symbol}")
        elif signal.signal_type == SignalType.CLOSE_LONG:
            logger.info(f"平仓成功: {self.symbol}")

    def get_strategy_status(self) -> dict:
        """
        获取策略详细状态

        Returns:
            策略状态字典
        """
        status = self.get_status()

        # 添加策略特定的状态信息
        status.update({
            'short_window': self.short_window,
            'long_window': self.long_window,
            'current_symbol': self.symbol,
            'indicators_status': {
                'short_ma_latest': self.indicators.get(self.symbol, {}).get('short_ma', pd.Series([])).iloc[-1] if not self.indicators.get(self.symbol, {}).get('short_ma', pd.Series([])).empty else None,
                'long_ma_latest': self.indicators.get(self.symbol, {}).get('long_ma', pd.Series([])).iloc[-1] if not self.indicators.get(self.symbol, {}).get('long_ma', pd.Series([])).empty else None,
            }
        })

        return status

    def reset(self):
        """重置策略状态"""
        super().reset()
        logger.info("策略状态已重置")


# 便捷函数：创建策略实例
def create_fixed_ma_strategy(**kwargs) -> FixedMAStrategy:
    """
    创建固定移动平均策略实例的便捷函数

    Args:
        **kwargs: 策略配置参数

    Returns:
        FixedMAStrategy实例
    """
    default_config = {
        'short_window': 10,
        'long_window': 30,
        'symbol': 'BTC/USDT',
        'max_positions': 1,
        'position_size': 0.1,
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.1
    }

    # 合并配置
    config = {**default_config, **kwargs}

    return FixedMAStrategy(config)


if __name__ == "__main__":
    # 简单测试
    import logging

    # 设置日志
    logging.basicConfig(level=logging.INFO)

    # 创建策略
    strategy = create_fixed_ma_strategy(
        short_window=5,
        long_window=20,
        symbol='BTC/USDT'
    )

    print("修复版移动平均策略创建成功！")
    print(f"策略配置: {strategy.get_strategy_status()}")