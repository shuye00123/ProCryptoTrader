from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging
import bisect
from .base_strategy import BaseStrategy, Signal, SignalType

# 设置日志记录器
logger = logging.getLogger(__name__)


class GridStrategy(BaseStrategy):
    """
    网格策略

    在价格区间内设置网格，价格触及网格线时进行买卖操作
    核心逻辑：低买高卖，动态重平衡
    """

    def __init__(self, config: Dict):
        """
        初始化网格策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 网格参数
        self.grid_count = config.get('grid_count', 10)  # 网格数量
        self.grid_range_pct = config.get('grid_range_pct', 0.1)  # 网格范围百分比
        self.rebalance_on_trade = config.get('rebalance_on_trade', True)  # 交易后是否重平衡

        # 网格状态（每个交易对独立管理）
        self.grid_prices = {}  # {symbol: [grid_prices]}
        self.grid_levels = {}  # {symbol: {price: level}}
        self.last_price = {}  # {symbol: price}
        self.trade_history = {}  # {symbol: [trades]}

        # 网格交易状态
        self.grid_orders = {}  # {symbol: {price: 'buy'/'sell'}}
        self.executed_levels = {}  # {symbol: set(levels)}

        # 初始化网格状态
        for symbol in self.symbols:
            self.trade_history[symbol] = []
            self.executed_levels[symbol] = set()

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

                # 获取最新价格
                latest_price = df['close'].iloc[-1]

                # 计算移动平均线
                if len(df) >= 20:
                    symbol_indicators['sma_20'] = df['close'].rolling(20).mean().iloc[-1]
                if len(df) >= 50:
                    symbol_indicators['sma_50'] = df['close'].rolling(50).mean().iloc[-1]

                # 计算价格波动率
                if len(df) >= 20:
                    symbol_indicators['volatility_20'] = df['close'].pct_change().rolling(20).std().iloc[-1]

                # 计算价格区间
                if len(df) >= 20:
                    symbol_indicators['high_20'] = df['high'].rolling(20).max().iloc[-1]
                    symbol_indicators['low_20'] = df['low'].rolling(20).min().iloc[-1]

                # 计算RSI
                if len(df) >= 14:
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))

                # 初始化网格（如果还没有初始化）
                if symbol not in self.grid_prices:
                    self._initialize_grid(symbol, latest_price)

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
        signals = []

        for symbol, df in data.items():
            if df.empty or symbol not in self.grid_prices:
                continue

            latest_price = df['close'].iloc[-1]

            # 检查是否触及网格线
            grid_signals = self._check_grid_triggers(symbol, latest_price)
            signals.extend(grid_signals)

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

    def _initialize_grid(self, symbol: str, base_price: float):
        """
        初始化网格

        Args:
            symbol: 交易对
            base_price: 基准价格
        """
        logger.info(f"初始化网格 - 交易对: {symbol}, 基准价格: {base_price:.4f}")

        # 计算网格价格范围
        grid_range = base_price * self.grid_range_pct
        upper_price = base_price + grid_range
        lower_price = base_price - grid_range

        # 计算网格价格
        grid_prices = np.linspace(lower_price, upper_price, self.grid_count + 1)

        # 存储网格价格和级别
        self.grid_prices[symbol] = grid_prices.tolist()
        self.grid_levels[symbol] = {price: i for i, price in enumerate(grid_prices)}

        # 初始化网格订单状态
        self.grid_orders[symbol] = {}
        for price in grid_prices:
            # 低于基准价格的网格线为买入格（低买）
            # 高于基准价格的网格线为卖出格（高卖）
            if price < base_price:
                self.grid_orders[symbol][price] = 'buy'
            elif price > base_price:
                self.grid_orders[symbol][price] = 'sell'
            # 基准价格本身不设置订单

        logger.info(f"网格初始化完成 - {symbol}: {len(grid_prices)}个网格点")

    def _check_grid_triggers(self, symbol: str, current_price: float) -> List[Signal]:
        """
        高效的网格触发检测 - 基于价格区间的批量处理

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            交易信号列表
        """
        signals = []

        if symbol not in self.grid_prices:
            return signals

        grid_prices = self.grid_prices[symbol]
        grid_orders = self.grid_orders[symbol]
        current_base_price = self._get_current_base_price(symbol)

        if current_base_price is None:
            return signals

        # 计算价格变化方向和幅度
        price_change = current_price - current_base_price

        if price_change > 0:
            # 价格上涨：执行基准价格到当前价格之间的所有卖出网格
            signals = self._execute_sell_grids_in_range(
                symbol, current_base_price, current_price, grid_prices, grid_orders
            )
        elif price_change < 0:
            # 价格下跌：执行当前价格到基准价格之间的所有买入网格
            signals = self._execute_buy_grids_in_range(
                symbol, current_price, current_base_price, grid_prices, grid_orders
            )
        # 如果价格变化很小，不执行任何网格交易

        # 如果有交易执行且启用重平衡，更新基准价格
        if signals and self.rebalance_on_trade:
            logger.info(f"执行 {len(signals)} 个网格交易后重平衡 - {symbol}")
            self._rebalance_grid(symbol, current_price)

        return signals

    def _execute_sell_grids_in_range(self, symbol: str, start_price: float, end_price: float,
                                   grid_prices: List[float], grid_orders: Dict) -> List[Signal]:
        """
        执行价格区间内的所有卖出网格 - 高效实现

        Args:
            symbol: 交易对
            start_price: 起始价格（基准价格）
            end_price: 结束价格（当前价格，高于起始价格）
            grid_prices: 所有网格价格（已排序）
            grid_orders: 网格订单状态

        Returns:
            卖出信号列表
        """
        signals = []

        # 使用 bisect 找到价格区间内的网格索引范围
        start_idx = bisect.bisect_right(grid_prices, start_price)
        end_idx = bisect.bisect_right(grid_prices, end_price)

        # 只处理区间内的卖出网格
        for i in range(start_idx, end_idx):
            grid_price = grid_prices[i]
            if (grid_orders.get(grid_price) == 'sell' and
                grid_price not in self.executed_levels.get(symbol, set())):

                signals.append(self._create_sell_signal(symbol, grid_price))
                self.executed_levels.setdefault(symbol, set()).add(grid_price)
                logger.debug(f"网格卖出执行 - {symbol}: 价格 {grid_price:.4f}")

        return signals

    def _execute_buy_grids_in_range(self, symbol: str, start_price: float, end_price: float,
                                  grid_prices: List[float], grid_orders: Dict) -> List[Signal]:
        """
        执行价格区间内的所有买入网格 - 高效实现

        Args:
            symbol: 交易对
            start_price: 起始价格（当前价格，低于结束价格）
            end_price: 结束价格（基准价格）
            grid_prices: 所有网格价格（已排序）
            grid_orders: 网格订单状态

        Returns:
            买入信号列表
        """
        signals = []

        # 使用 bisect 找到价格区间内的网格索引范围
        start_idx = bisect.bisect_left(grid_prices, start_price)
        end_idx = bisect.bisect_left(grid_prices, end_price)

        # 只处理区间内的买入网格
        for i in range(start_idx, end_idx):
            grid_price = grid_prices[i]
            if (grid_orders.get(grid_price) == 'buy' and
                grid_price not in self.executed_levels.get(symbol, set())):

                signals.append(self._create_buy_signal(symbol, grid_price))
                self.executed_levels.setdefault(symbol, set()).add(grid_price)
                logger.debug(f"网格买入执行 - {symbol}: 价格 {grid_price:.4f}")

        return signals

    def _rebalance_grid(self, symbol: str, new_base_price: float):
        """
        重新平衡网格 - 交易后更新基准价格并重建网格

        Args:
            symbol: 交易对
            new_base_price: 新的基准价格
        """
        logger.info(f"重新平衡网格 - {symbol}: 新基准价格 {new_base_price:.4f}")

        # 清空已执行级别（重新开始计数）
        self.executed_levels[symbol].clear()

        # 重新初始化网格
        self._initialize_grid(symbol, new_base_price)

    def _create_buy_signal(self, symbol: str, price: float) -> Signal:
        """
        创建买入信号

        Args:
            symbol: 交易对
            price: 价格

        Returns:
            买入信号
        """
        # 计算买入数量
        amount = self._calculate_position_size(symbol, price)

        # 记录交易历史
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        self.trade_history[symbol].append({
            'type': 'buy',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now(),
            'reason': 'grid_buy'
        })

        logger.info(f"网格买入信号 - {symbol}: 价格 {price:.4f}, 数量 {amount:.6f}")

        return Signal(
            signal_type=SignalType.OPEN_LONG,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={
                'strategy': 'grid',
                'grid_price': price,
                'grid_level': self.grid_levels[symbol].get(price, -1),
                'reason': 'grid_cross_buy'
            }
        )

    def _create_sell_signal(self, symbol: str, price: float) -> Signal:
        """
        创建卖出信号 (修改为平仓信号)

        Args:
            symbol: 交易对
            price: 价格

        Returns:
            卖出信号
        """
        # 🔧 修改：如果有持仓，卖出平仓；如果没有持仓，开空仓
        if self.has_position(symbol):
            position = self.get_position(symbol)
            amount = position.amount  # 平掉全部持仓
            signal_type = SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT
            reason = 'grid_profit_take'
        else:
            # 没有持仓时，开空仓（对冲策略）
            amount = self._calculate_position_size(symbol, price)
            signal_type = SignalType.OPEN_SHORT
            reason = 'grid_hedge_sell'

        # 记录交易历史
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        self.trade_history[symbol].append({
            'type': 'sell',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now(),
            'reason': reason
        })

        logger.info(f"网格卖出信号 - {symbol}: 价格 {price:.4f}, 数量 {amount:.6f}, 类型: {signal_type.value}")

        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={
                'strategy': 'grid',
                'grid_price': price,
                'grid_level': self.grid_levels[symbol].get(price, -1),
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
        # 优先使用backtest_config中的initial_balance，如果没有则使用默认值
        available_balance = getattr(self, 'backtest_config', {}).get('initial_balance', 10000.0)
        if not available_balance:
            available_balance = getattr(self, 'initial_balance', 10000.0)

        # 计算基于资金比例的交易金额
        trade_amount_usd = available_balance * self.position_size

        # 计算BTC数量
        btc_quantity = trade_amount_usd / price

        logger.info(f"计算仓位大小: 可用资金=${available_balance:.2f}, 比例={self.position_size:.1%}, "
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
            'grid_count': self.grid_count,
            'grid_range_pct': self.grid_range_pct,
            'grid_prices': self.grid_prices[symbol],
            'grid_orders': self.grid_orders.get(symbol, {}),
            'executed_levels': list(self.executed_levels[symbol]),
            'last_price': self.last_price.get(symbol, 0),
            'trade_count': len(self.trade_history.get(symbol, [])),
            'rebalance_on_trade': self.rebalance_on_trade,
            'current_base_price': self._get_current_base_price(symbol)
        }

    def _get_current_base_price(self, symbol: str) -> Optional[float]:
        """
        获取当前基准价格（网格中间点）

        Args:
            symbol: 交易对

        Returns:
            基准价格
        """
        if symbol not in self.grid_prices:
            return None

        grid_prices = self.grid_prices[symbol]
        return (grid_prices[0] + grid_prices[-1]) / 2

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
        self.grid_levels = {}
        self.last_price = {}
        self.grid_orders = {}
        self.executed_levels = {}

        # 重新初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
            self.executed_levels[symbol] = set()

        logger.info("网格策略状态已重置")

    def calculate_grid_pnl(self, symbol: str, current_price: float) -> Dict:
        """
        计算网格策略的盈亏情况

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            盈亏统计字典
        """
        trades = self.trade_history.get(symbol, [])
        if not trades:
            return {'total_pnl': 0, 'total_trades': 0, 'win_rate': 0}

        total_pnl = 0
        buy_volume = 0
        sell_volume = 0

        for trade in trades:
            if trade['type'] == 'buy':
                buy_volume += trade['price'] * trade['amount']
            else:  # sell
                sell_volume += trade['price'] * trade['amount']

        # 简化计算：卖出金额 - 买入金额
        total_pnl = sell_volume - buy_volume
        total_trades = len(trades)

        # 计算胜率（简化版本）
        profitable_trades = 0
        paired_trades = min(len([t for t in trades if t['type'] == 'buy']),
                           len([t for t in trades if t['type'] == 'sell']))
        win_rate = (profitable_trades / paired_trades * 100) if paired_trades > 0 else 0

        return {
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'buy_trades': len([t for t in trades if t['type'] == 'buy']),
            'sell_trades': len([t for t in trades if t['type'] == 'sell']),
            'win_rate': win_rate,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume
        }