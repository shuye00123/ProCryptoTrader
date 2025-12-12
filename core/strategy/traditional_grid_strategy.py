"""
传统网格策略

基于固定价格边界和网格数量的经典网格交易策略：
- 价格下穿网格线时触发买入，并将该网格线从买入变为卖出
- 价格上穿网格线时触发卖出，并将该网格线从卖出变为买入
- 使用固定的价格上下边界，不进行动态调整
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
import logging
import bisect
from .base_strategy import BaseStrategy, Signal, SignalType

logger = logging.getLogger(__name__)


class TraditionalGridStrategy(BaseStrategy):
    """
    传统网格策略

    基于固定价格边界的经典网格交易实现：
    - 固定价格范围：[absolute_lower_price, absolute_upper_price]
    - 固定网格数量：grid_count
    - 固定基准点：base_price（用于确定买卖网格分布）
    - 传统触发逻辑：价格穿越检测 + 网格状态切换
    """

    def __init__(self, config: Dict):
        """
        初始化传统网格策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 网格参数
        self.grid_count = config.get('grid_count', 20)
        self.absolute_upper_price = config.get('absolute_upper_price')
        self.absolute_lower_price = config.get('absolute_lower_price')
        self.base_price = config.get('base_price')

        # 验证必要参数
        if not self.absolute_upper_price or not self.absolute_lower_price:
            raise ValueError("必须配置 absolute_upper_price 和 absolute_lower_price")
        if not self.base_price:
            raise ValueError("必须配置 base_price")
        if self.absolute_upper_price <= self.absolute_lower_price:
            raise ValueError("absolute_upper_price 必须大于 absolute_lower_price")
        if not (self.absolute_lower_price < self.base_price < self.absolute_upper_price):
            raise ValueError("base_price 必须在 absolute_lower_price 和 absolute_upper_price 之间")

        # 网格状态管理
        self.grid_prices = {}          # {symbol: [grid_prices]}
        self.grid_orders = {}          # {symbol: {price: 'buy'/'sell'/'inactive'}}
        self.last_triggered_grid = {}  # {symbol: last_triggered_grid_price}  # 记录最后触发的网格
        self.last_price = {}           # {symbol: last_price}
        self.last_timestamp = {}       # {symbol: last_timestamp}  # 新增：记录最后处理的时间戳
        self.trade_history = {}        # {symbol: [trades]}

        # 初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
            self.last_triggered_grid[symbol] = None

        logger.info(f"传统网格策略初始化完成:")
        logger.info(f"  价格范围: ${self.absolute_lower_price:,.2f} - ${self.absolute_upper_price:,.2f}")
        logger.info(f"  基准价格: ${self.base_price:,.2f}")
        logger.info(f"  网格数量: {self.grid_count}")

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """
        计算技术指标

        Args:
            data: 交易对数据字典

        Returns:
            技术指标字典
        """
        indicators = {}

        try:
            for symbol, df in data.items():
                if df.empty:
                    continue

                symbol_indicators = {}
                latest_price = df['close'].iloc[-1]

                # 基础统计指标
                symbol_indicators['current_price'] = latest_price
                symbol_indicators['price_change'] = df['close'].pct_change().iloc[-1] if len(df) > 1 else 0

                # 移动平均线
                if len(df) >= 20:
                    symbol_indicators['sma_20'] = df['close'].rolling(20).mean().iloc[-1]
                if len(df) >= 50:
                    symbol_indicators['sma_50'] = df['close'].rolling(50).mean().iloc[-1]

                # RSI
                if len(df) >= 14:
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))

                # 初始化网格（如果还没有初始化）
                if symbol not in self.grid_prices:
                    self._initialize_grid(symbol)

                # 更新上次价格（用于穿越检测）
                self.last_price[symbol] = latest_price

                indicators[symbol] = symbol_indicators

        except Exception as e:
            logger.error(f"计算技术指标时出错: {e}")

        return indicators

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        根据行情数据生成交易信号

        Args:
            data: 交易对数据字典

        Returns:
            交易信号列表
        """
        # 移除调试输出，恢复正常日志

        signals = []

        for symbol, df in data.items():
            if df.empty:
                continue

            # 获取最新数据的时间戳和价格
            latest_timestamp = df.index[-1]
            latest_price = df['close'].iloc[-1]

            # 检查是否是新的数据点（避免重复处理相同时间的数据）
            if symbol in self.last_timestamp and latest_timestamp == self.last_timestamp[symbol]:
                continue

            if symbol not in self.grid_prices:
                self._initialize_grid(symbol)
                logger.info(f"网格策略 {symbol}: 网格初始化完成，网格数量: {len(self.grid_prices.get(symbol, []))}")

            # 检查网格触发信号
            grid_signals = self._check_grid_triggers(symbol, latest_price)
            signals.extend(grid_signals)

            # 更新最后处理的时间戳
            self.last_timestamp[symbol] = latest_timestamp

            # 检查止损止盈
            if self.has_position(symbol):
                if self.should_stop_loss(symbol):
                    side = self.get_position_side(symbol)
                    signals.append(Signal(
                        signal_type=SignalType.CLOSE_LONG if side == 'long' else SignalType.CLOSE_SHORT,
                        symbol=symbol,
                        price=latest_price,
                        amount=self.get_position(symbol).amount,
                        confidence=1.0,
                        metadata={'reason': 'stop_loss'}
                    ))
                elif self.should_take_profit(symbol):
                    side = self.get_position_side(symbol)
                    signals.append(Signal(
                        signal_type=SignalType.CLOSE_LONG if side == 'long' else SignalType.CLOSE_SHORT,
                        symbol=symbol,
                        price=latest_price,
                        amount=self.get_position(symbol).amount,
                        confidence=1.0,
                        metadata={'reason': 'take_profit'}
                    ))

        return signals

    def _initialize_grid(self, symbol: str):
        """
        初始化传统网格

        Args:
            symbol: 交易对
        """
        logger.info(f"初始化传统网格 - 交易对: {symbol}")

        # 计算等间距网格点
        grid_prices = np.linspace(
            self.absolute_lower_price,
            self.absolute_upper_price,
            self.grid_count
        )

        # 存储网格价格
        self.grid_prices[symbol] = grid_prices.tolist()
        self.grid_orders[symbol] = {}

        # 初始化网格订单状态
        for price in grid_prices:
            # 低于基准价格的网格线为买入格（低买）
            # 高于基准价格的网格线为卖出格（高卖）
            if price < self.base_price:
                self.grid_orders[symbol][price] = 'buy'
            elif price > self.base_price:
                self.grid_orders[symbol][price] = 'sell'
            # 基准价格本身不设置订单

        logger.info(f"传统网格初始化完成 - {symbol}:")
        logger.info(f"  网格数量: {self.grid_count}")
        logger.info(f"  价格范围: ${self.absolute_lower_price:,.2f} - ${self.absolute_upper_price:,.2f}")
        logger.info(f"  网格间距: ${(self.absolute_upper_price - self.absolute_lower_price) / self.grid_count:,.2f}")

        # 统计买卖网格数量
        buy_grids = sum(1 for v in self.grid_orders[symbol].values() if v == 'buy')
        sell_grids = sum(1 for v in self.grid_orders[symbol].values() if v == 'sell')
        logger.info(f"  买入网格: {buy_grids}, 卖出网格: {sell_grids}")

    def _check_grid_triggers(self, symbol: str, current_price: float) -> List[Signal]:
        """
        检查传统网格触发条件

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            交易信号列表
        """
        signals = []

        if symbol not in self.grid_prices:
            return signals

        # 第一次运行，记录价格但不触发交易
        if symbol not in self.last_price:
            self.last_price[symbol] = current_price
            logger.info(f"网格策略启动 - {symbol}: 记录初始价格 ${current_price:.2f}")
            return signals

        last_price = self.last_price[symbol]
        grid_prices = sorted(self.grid_prices[symbol])

        # 检查价格变化方向和穿越的网格线
        price_change_pct = (current_price - last_price) / last_price * 100
        logger.info(f"网格策略 {symbol}: 价格变化 {last_price:.2f} → {current_price:.2f} ({price_change_pct:+.2f}%)")

        if current_price > last_price:
            # 价格上涨：检查向上穿越的卖出网格
            logger.info(f"网格策略 {symbol}: 价格上涨，检查向上穿越")
            signals = self._check_upward_crossings(
                symbol, last_price, current_price, grid_prices
            )
        elif current_price < last_price:
            # 价格下跌：检查向下穿越的买入网格
            logger.info(f"网格策略 {symbol}: 价格下跌，检查向下穿越")
            signals = self._check_downward_crossings(
                symbol, last_price, current_price, grid_prices
            )
        else:
            logger.info(f"网格策略 {symbol}: 价格无变化，跳过")

        # 更新最后价格
        self.last_price[symbol] = current_price
        logger.info(f"网格策略 {symbol}: 生成了 {len(signals)} 个信号")
        return signals

    def _check_upward_crossings(self, symbol: str, last_price: float, current_price: float,
                             grid_prices: List[float]) -> List[Signal]:
        """
        检查向上穿越的卖出网格

        Args:
            symbol: 交易对
            last_price: 上次价格
            current_price: 当前价格
            grid_prices: 网格价格列表（已排序）

        Returns:
            卖出信号列表
        """
        signals = []

        # 使用二分查找找到价格区间
        start_idx = bisect.bisect_right(grid_prices, last_price)
        end_idx = bisect.bisect_right(grid_prices, current_price)

        logger.info(f"网格策略 {symbol}: 向上穿越检查，区间[{start_idx}:{end_idx}]，价格范围[{last_price:.2f}:{current_price:.2f}]")

        # 检查区间内的卖出网格
        for i in range(start_idx, end_idx):
            grid_price = grid_prices[i]
            grid_status = self.grid_orders[symbol].get(grid_price, 'unknown')

            logger.info(f"网格策略 {symbol}: 检查网格${grid_price:.2f}，状态: {grid_status}")

            if grid_status == 'sell':
                # 处理前一个触发网格的状态
                if self.last_triggered_grid.get(symbol) is not None:
                    last_grid = self.last_triggered_grid[symbol]
                    if last_grid != grid_price:  # 确保不是同一个网格
                        # 上穿时，将前一个失效网格改为买入格
                        self.grid_orders[symbol][last_grid] = 'buy'
                        logger.info(f"网格状态更新 - {symbol}: 网格 ${last_grid:.2f} 从失效改为买入")

                # 触发当前网格
                sell_signal = self._create_sell_signal(symbol, grid_price)
                signals.append(sell_signal)

                # 将当前触发网格改为失效状态
                self.grid_orders[symbol][grid_price] = 'inactive'
                self.last_triggered_grid[symbol] = grid_price

                logger.info(f"向上穿越触发卖出 - {symbol}: 网格价格 ${grid_price:.2f}，信号类型: {sell_signal.signal_type.value}，改为失效状态")

        return signals

    def _check_downward_crossings(self, symbol: str, last_price: float, current_price: float,
                               grid_prices: List[float]) -> List[Signal]:
        """
        检查向下穿越的买入网格

        Args:
            symbol: 交易对
            last_price: 上次价格
            current_price: 当前价格
            grid_prices: 网格价格列表（已排序）

        Returns:
            买入信号列表
        """
        signals = []

        # 使用二分查找找到价格区间
        start_idx = bisect.bisect_left(grid_prices, current_price)
        end_idx = bisect.bisect_left(grid_prices, last_price)

        # 检查区间内的买入网格
        for i in range(start_idx, end_idx):
            grid_price = grid_prices[i]

            if self.grid_orders[symbol].get(grid_price) == 'buy':
                # 处理前一个触发网格的状态
                if self.last_triggered_grid.get(symbol) is not None:
                    last_grid = self.last_triggered_grid[symbol]
                    if last_grid != grid_price:  # 确保不是同一个网格
                        # 下穿时，将前一个失效网格改为卖出格
                        self.grid_orders[symbol][last_grid] = 'sell'
                        logger.debug(f"网格状态更新 - {symbol}: 网格 ${last_grid:.2f} 从失效改为卖出")

                # 触发当前网格
                buy_signal = self._create_buy_signal(symbol, grid_price)
                signals.append(buy_signal)

                # 将当前触发网格改为失效状态
                self.grid_orders[symbol][grid_price] = 'inactive'
                self.last_triggered_grid[symbol] = grid_price

                logger.debug(f"向下穿越触发买入 - {symbol}: 网格价格 ${grid_price:.2f}，改为失效状态")

        return signals

    def _create_buy_signal(self, symbol: str, price: float) -> Signal:
        """
        创建买入信号

        Args:
            symbol: 交易对
            price: 价格

        Returns:
            买入信号
        """
        # 传统网格策略：根据当前持仓状态决定买入信号类型
        if self.has_position(symbol):
            position = self.get_position(symbol)

            if position.side == 'short':
                # 有空仓时，买入 = 平空仓
                # 传统网格策略：每次只平一个网格的仓位，而不是平所有仓位
                grid_amount = self._calculate_position_size(symbol, price)
                # 但是不能超过实际持仓数量
                amount = min(grid_amount, position.amount)
                signal_type = SignalType.CLOSE_SHORT
                reason = 'grid_close_short'
                logger.info(f"传统网格平空信号 - {symbol}: 价格 ${price:.2f}, 网格仓位 {grid_amount:.6f}, 实际平仓 {amount:.6f}, 总持仓 {position.amount:.6f}")
            else:
                # 有多仓时，买入 = 加多仓
                amount = self._calculate_position_size(symbol, price)
                signal_type = SignalType.INCREASE_LONG
                reason = 'grid_increase_long'
                logger.info(f"传统网格加多信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}")
        else:
            # 没有持仓时，买入 = 开多仓
            amount = self._calculate_position_size(symbol, price)
            signal_type = SignalType.OPEN_LONG
            reason = 'grid_open_long'
            logger.info(f"传统网格开多信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}")

        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'buy',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now(),
            'reason': reason
        })

        logger.info(f"传统网格买入信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}, 类型: {signal_type.value}")

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={
                'strategy': 'traditional_grid',
                'grid_price': price,
                'reason': reason
            }
        )

    def _create_sell_signal(self, symbol: str, price: float) -> Signal:
        """
        创建卖出信号

        Args:
            symbol: 交易对
            price: 价格

        Returns:
            卖出信号
        """
        # 传统网格策略：根据当前持仓状态决定卖出信号类型
        if self.has_position(symbol):
            position = self.get_position(symbol)

            if position.side == 'long':
                # 有多仓时，卖出 = 平多仓
                # 传统网格策略：每次只平一个网格的仓位，而不是平所有仓位
                grid_amount = self._calculate_position_size(symbol, price)
                # 但是不能超过实际持仓数量
                amount = min(grid_amount, position.amount)
                signal_type = SignalType.CLOSE_LONG
                reason = 'grid_close_long'
                logger.info(f"传统网格平多信号 - {symbol}: 价格 ${price:.2f}, 网格仓位 {grid_amount:.6f}, 实际平仓 {amount:.6f}, 总持仓 {position.amount:.6f}")
            else:
                # 有空仓时，卖出 = 加空仓
                amount = self._calculate_position_size(symbol, price)
                signal_type = SignalType.INCREASE_SHORT
                reason = 'grid_increase_short'
                logger.info(f"传统网格加空信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}")
        else:
            # 没有持仓时，卖出 = 开空仓
            amount = self._calculate_position_size(symbol, price)
            signal_type = SignalType.OPEN_SHORT
            reason = 'grid_open_short'
            logger.info(f"传统网格开空信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}")

        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'sell',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now(),
            'reason': reason
        })

        logger.info(f"传统网格卖出信号 - {symbol}: 价格 ${price:.2f}, 数量 {amount:.6f}, 类型: {signal_type.value}")

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={
                'strategy': 'traditional_grid',
                'grid_price': price,
                'reason': reason
            }
        )

    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """
        计算持仓大小（基于资金比例）

        Args:
            symbol: 交易对
            price: 价格

        Returns:
            持仓大小（基于总资金比例计算的BTC数量）
        """
        # 获取当前可用资金
        available_balance = getattr(self, 'backtest_config', {}).get('initial_balance', 10000.0)
        if not available_balance:
            available_balance = getattr(self, 'initial_balance', 10000.0)

        # 计算基于资金比例的交易金额
        trade_amount_usd = available_balance * self.position_size

        # 计算BTC数量
        btc_quantity = trade_amount_usd / price

        logger.debug(f"计算仓位大小: 可用资金=${available_balance:.2f}, 比例={self.position_size:.1%}, "
                    f"交易金额=${trade_amount_usd:.2f}, BTC数量={btc_quantity:.6f}")

        return btc_quantity

    def get_grid_status(self, symbol: str) -> Dict:
        """
        获取网格状态

        Args:
            symbol: 交易对

        Returns:
            网格状态字典
        """
        if symbol not in self.grid_prices:
            return {}

        return {
            'symbol': symbol,
            'strategy_type': 'traditional_grid',
            'grid_count': self.grid_count,
            'price_range': {
                'lower': self.absolute_lower_price,
                'upper': self.absolute_upper_price,
                'base': self.base_price
            },
            'grid_prices': self.grid_prices[symbol],
            'grid_orders': self.grid_orders.get(symbol, {}),
            'last_triggered_grid': self.last_triggered_grid.get(symbol, None),
            'last_price': self.last_price.get(symbol, 0),
            'trade_count': len(self.trade_history.get(symbol, []))
        }

    def get_trade_history(self, symbol: str) -> List[Dict]:
        """
        获取交易历史

        Args:
            symbol: 交易对

        Returns:
            交易历史列表
        """
        return self.trade_history.get(symbol, [])

    def reset(self):
        """重置策略状态"""
        super().reset()

        # 重置网格状态
        self.grid_prices = {}
        self.grid_orders = {}
        self.last_price = {}
        self.last_triggered_grid = {}

        # 重新初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
            self.last_triggered_grid[symbol] = None

        logger.info("传统网格策略状态已重置")