"""
增强网格策略

在原有GridStrategy基础上添加：
- 绝对价格限制
- 市场适应性配置
- 风险控制机制
- 智能重平衡策略
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
import logging
from .grid_strategy import GridStrategy
from .base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


class EnhancedGridStrategy(GridStrategy):
    """
    增强网格策略

    在原有网格策略基础上增加：
    - 绝对价格上限/下限制
    - 市场波动率自适应
    - 智能重平衡策略
    - 风险控制机制
    """

    def __init__(self, config: Dict):
        """
        初始化增强网格策略

        Args:
            config: 策略配置参数
        """
        super().__init__(config)

        # 增强配置参数
        self.absolute_upper_price = config.get('absolute_upper_price')  # 绝对上限价格
        self.absolute_lower_price = config.get('absolute_lower_price')  # 绝对下限价格
        self.max_range_pct = config.get('max_range_pct', 0.3)           # 最大网格范围 30%
        self.min_range_pct = config.get('min_range_pct', 0.02)          # 最小网格范围 2%
        self.volatility_adjustment = config.get('volatility_adjustment', True)  # 波动率自适应
        self.smart_rebalance = config.get('smart_rebalance', True)      # 智能重平衡
        self.rebalance_threshold_pct = config.get('rebalance_threshold_pct', 0.5)  # 重平衡阈值
        self.max_price_deviation = config.get('max_price_deviation', 0.8)  # 最大价格偏离度

        # 波动率跟踪
        self.volatility_history = {}  # {symbol: [volatility_values]}
        self.max_volatility_history = 20  # 保持最近20个波动率值

        # 🔧 新增：交易时间跟踪
        self.last_trade_time = {}  # {symbol: timestamp}

        # 🔧 新增：强制重平衡参数
        self.force_rebalance_threshold = config.get('force_rebalance_threshold', 0.1)  # 10%
        self.max_idle_time = config.get('max_idle_time', 3600)  # 1小时

    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """
        增强的技术指标计算，包含波动率分析

        Args:
            data: 交易对数据字典

        Returns:
            技术指标字典
        """
        indicators = super().calculate_indicators(data)

        # 添加波动率分析
        for symbol, df in data.items():
            if df.empty or len(df) < 20:
                continue

            symbol_indicators = indicators.get(symbol, {})

            # 计算多时间框架波动率
            if len(df) >= 50:
                symbol_indicators['volatility_50'] = df['close'].pct_change().rolling(50).std().iloc[-1]

            if len(df) >= 20:
                symbol_indicators['volatility_20'] = df['close'].pct_change().rolling(20).std().iloc[-1]

            if len(df) >= 10:
                symbol_indicators['volatility_10'] = df['close'].pct_change().rolling(10).std().iloc[-1]

            # 波动率趋势
            if 'volatility_20' in symbol_indicators and 'volatility_50' in symbol_indicators:
                vol_trend = symbol_indicators['volatility_20'] / symbol_indicators['volatility_50']
                symbol_indicators['volatility_trend'] = vol_trend
                symbol_indicators['volatility_increasing'] = vol_trend > 1.1
                symbol_indicators['volatility_decreasing'] = vol_trend < 0.9

            # 价格偏离度
            if symbol in self.grid_prices and len(self.grid_prices[symbol]) > 0:
                grid_range = (max(self.grid_prices[symbol]) - min(self.grid_prices[symbol]))
                current_price = df['close'].iloc[-1]
                grid_center = (max(self.grid_prices[symbol]) + min(self.grid_prices[symbol])) / 2
                price_deviation = abs(current_price - grid_center) / grid_range
                symbol_indicators['price_deviation'] = price_deviation
                symbol_indicators['outside_grid_range'] = price_deviation > 0.5

            # 更新波动率历史
            current_volatility = symbol_indicators.get('volatility_20', 0)
            if symbol not in self.volatility_history:
                self.volatility_history[symbol] = []

            self.volatility_history[symbol].append(current_volatility)
            if len(self.volatility_history[symbol]) > self.max_volatility_history:
                self.volatility_history[symbol].pop(0)

            indicators[symbol] = symbol_indicators

        return indicators

    def _initialize_grid(self, symbol: str, base_price: float):
        """
        增强的网格初始化，考虑绝对价格限制和市场适应性

        Args:
            symbol: 交易对
            base_price: 基准价格
        """
        logger.info(f"初始化增强网格 - 交易对: {symbol}, 基准价格: {base_price:.4f}")

        # 1. 确定网格范围
        adaptive_range_pct = self._calculate_adaptive_range(symbol, base_price)

        # 2. 应用绝对价格限制
        grid_range = base_price * adaptive_range_pct
        upper_price = base_price + grid_range
        lower_price = base_price - grid_range

        # 3. 应用绝对价格限制
        if self.absolute_upper_price is not None:
            upper_price = min(upper_price, self.absolute_upper_price)
            logger.info(f"应用绝对上限价格: {self.absolute_upper_price}")

        if self.absolute_lower_price is not None:
            lower_price = max(lower_price, self.absolute_lower_price)
            logger.info(f"应用绝对下限价格: {self.absolute_lower_price}")

        # 4. 确保价格范围有效
        if upper_price <= lower_price:
            logger.warning(f"无效的价格范围 [{lower_price}, {upper_price}]，使用默认范围")
            default_range = base_price * 0.1
            upper_price = base_price + default_range
            lower_price = base_price - default_range

        # 5. 计算网格价格
        grid_prices = np.linspace(lower_price, upper_price, self.grid_count + 1)

        # 6. 存储网格信息
        self.grid_prices[symbol] = grid_prices.tolist()
        self.grid_levels[symbol] = {price: i for i, price in enumerate(grid_prices)}

        # 7. 初始化网格订单状态
        self.grid_orders[symbol] = {}
        for price in grid_prices:
            if price < base_price:
                self.grid_orders[symbol][price] = 'buy'
            elif price > base_price:
                self.grid_orders[symbol][price] = 'sell'

        # 8. 记录网格配置信息
        actual_range_pct = (upper_price - lower_price) / (2 * base_price)
        logger.info(f"网格初始化完成 - {symbol}:")
        logger.info(f"  网格数量: {self.grid_count}")
        logger.info(f"  网格范围: {actual_range_pct:.2%}")
        logger.info(f"  价格区间: [{lower_price:.2f}, {upper_price:.2f}]")
        logger.info(f"  网格点数: {len(grid_prices)}")

    def _calculate_adaptive_range(self, symbol: str, base_price: float) -> float:
        """
        计算适应性的网格范围

        Args:
            symbol: 交易对
            base_price: 基准价格

        Returns:
            适应性的网格范围百分比
        """
        if not self.volatility_adjustment or symbol not in self.volatility_history:
            return self.grid_range_pct

        volatility_history = self.volatility_history[symbol]
        if len(volatility_history) < 5:
            return self.grid_range_pct

        # 计算平均波动率
        avg_volatility = np.mean(volatility_history)
        recent_volatility = volatility_history[-1]

        # 基于波动率调整范围
        if avg_volatility > 0.05:  # 高波动率 > 5%
            adaptive_range = min(self.max_range_pct, self.grid_range_pct * 2)
        elif avg_volatility < 0.01:  # 低波动率 < 1%
            adaptive_range = max(self.min_range_pct, self.grid_range_pct * 0.5)
        else:
            adaptive_range = self.grid_range_pct

        # 波动率趋势调整
        if len(volatility_history) >= 10:
            recent_avg = np.mean(volatility_history[-5:])
            historical_avg = np.mean(volatility_history[:-5])
            if recent_avg > historical_avg * 1.2:  # 波动率上升
                adaptive_range *= 1.2
            elif recent_avg < historical_avg * 0.8:  # 波动率下降
                adaptive_range *= 0.8

        logger.info(f"自适应网格范围 - {symbol}: {adaptive_range:.2%} (基准: {self.grid_range_pct:.2%})")
        return adaptive_range

    def _should_rebalance_grid(self, symbol: str, current_price: float) -> bool:
        """
        🔧 修改：更积极的智能重平衡判断

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            是否应该重平衡
        """
        # 🔧 如果没有启用智能重平衡，总是重平衡
        if not self.smart_rebalance:
            return True

        # 🔧 如果没有网格信息，总是重平衡
        if symbol not in self.grid_prices or not self.grid_prices[symbol]:
            return True

        # 检查价格偏离度
        grid_range = (max(self.grid_prices[symbol]) - min(self.grid_prices[symbol]))
        grid_center = (max(self.grid_prices[symbol]) + min(self.grid_prices[symbol])) / 2
        price_deviation = abs(current_price - grid_center) / grid_range

        # 🔧 降低重平衡阈值：使用force_rebalance_threshold而不是rebalance_threshold_pct
        effective_threshold = min(self.force_rebalance_threshold, self.rebalance_threshold_pct)

        # 如果价格偏离度超过阈值，立即重平衡
        if price_deviation > effective_threshold:
            logger.info(f"价格偏离度达到阈值 ({price_deviation:.2%} > {effective_threshold:.2%})，执行重平衡")
            return True

        # 🔧 如果价格在网格范围内但偏离度仍然较大，也考虑重平衡
        if price_deviation > effective_threshold * 0.5:
            logger.info(f"价格偏离度中等 ({price_deviation:.2%})，考虑重平衡")
            return True

        # 🔧 如果长时间没有交易，强制重平衡
        if hasattr(self, 'last_trade_time') and symbol in self.last_trade_time:
            import time
            current_time = time.time()
            time_since_last_trade = current_time - self.last_trade_time[symbol]

            if time_since_last_trade > self.max_idle_time:
                logger.info(f"长时间未交易 ({time_since_last_trade/3600:.1f}小时)，强制重平衡")
                return True

        # 只有在价格偏离度很小时才延迟重平衡
        if price_deviation < effective_threshold * 0.3:
            logger.debug(f"价格偏离度很低 ({price_deviation:.2%})，延迟重平衡")
            return False

        logger.info(f"价格偏离度适中 ({price_deviation:.2%})，执行重平衡")
        return True

    def _rebalance_grid(self, symbol: str, new_base_price: float):
        """
        增强的网格重平衡，包含风险检查

        Args:
            symbol: 交易对
            new_base_price: 新的基准价格
        """
        if not self._should_rebalance_grid(symbol, new_base_price):
            return

        logger.info(f"执行增强网格重平衡 - {symbol}: 新基准价格 {new_base_price:.4f}")

        # 清空已执行级别
        self.executed_levels[symbol].clear()

        # 重新初始化网格
        self._initialize_grid(symbol, new_base_price)

    def get_enhanced_grid_status(self, symbol: str) -> Dict:
        """
        获取增强的网格状态信息

        Args:
            symbol: 交易对

        Returns:
            增强的网格状态字典
        """
        base_status = super().get_grid_status(symbol)

        if not base_status:
            return base_status

        # 添加增强信息
        base_status.update({
            'absolute_upper_price': self.absolute_upper_price,
            'absolute_lower_price': self.absolute_lower_price,
            'max_range_pct': self.max_range_pct,
            'min_range_pct': self.min_range_pct,
            'volatility_adjustment': self.volatility_adjustment,
            'smart_rebalance': self.smart_rebalance,
            'current_volatility': self.volatility_history.get(symbol, [])[-1] if self.volatility_history.get(symbol) else None,
            'avg_volatility': np.mean(self.volatility_history.get(symbol, [0])) if self.volatility_history.get(symbol) else None,
            'adaptive_range_pct': self._calculate_adaptive_range(symbol, self._get_current_base_price(symbol)) if symbol in self.grid_prices else None
        })

        return base_status

    def validate_config(self) -> Dict[str, Any]:
        """
        验证策略配置的有效性

        Returns:
            配置验证结果
        """
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }

        # 检查绝对价格限制
        if self.absolute_upper_price is not None and self.absolute_lower_price is not None:
            if self.absolute_upper_price <= self.absolute_lower_price:
                validation_result['errors'].append("绝对上限价格必须大于绝对下限价格")
                validation_result['is_valid'] = False

        # 检查网格范围配置
        if self.min_range_pct >= self.max_range_pct:
            validation_result['errors'].append("最小网格范围不能大于等于最大网格范围")
            validation_result['is_valid'] = False

        # 检查网格数量
        if self.grid_count < 3:
            validation_result['warnings'].append("网格数量过少，可能影响策略效果")
        elif self.grid_count > 50:
            validation_result['warnings'].append("网格数量过多，可能增加交易成本")

        # 检查重平衡阈值
        if self.rebalance_threshold_pct < 0.1 or self.rebalance_threshold_pct > 1.0:
            validation_result['warnings'].append("重平衡阈值建议设置在10%-100%之间")

        return validation_result

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        增强的网格策略信号生成

        Args:
            data: 交易对数据字典

        Returns:
            交易信号列表
        """
        signals = []

        try:
            # 确保指标已计算（如果直接调用generate_signals而没有先调用update）
            if not hasattr(self, 'indicators') or not self.indicators:
                self.indicators = self.calculate_indicators(data)

            for symbol, df in data.items():
                if df.empty:
                    continue

                current_price = df['close'].iloc[-1]

                # 如果网格还未初始化，先初始化
                if symbol not in self.grid_prices:
                    self._initialize_grid(symbol, current_price)

                indicators = self.indicators.get(symbol, {})

                # 1. 检查网格触发信号
                grid_signals = self._check_grid_triggers(symbol, current_price)

                # 2. 更新网格订单状态 (买入变卖出，卖出变买入)
                if grid_signals:
                    self._update_grid_orders_after_trade(symbol, grid_signals)
                    signals.extend(grid_signals)

                # 3. 检查是否需要重平衡网格
                # 🔧 修复：无论是否有smart_rebalance，只要有交易就检查重平衡
                if self.rebalance_on_trade and (grid_signals or self._force_rebalance_check(symbol, current_price)):
                    # 更积极的重平衡策略
                    if self._should_rebalance_grid(symbol, current_price):
                        self._rebalance_grid(symbol, current_price)

                # 3. 检查止损止盈
                if self.has_position(symbol):
                    position = self.get_position(symbol)

                    # 止损检查
                    if self.should_stop_loss(symbol):
                        signals.append(Signal(
                            signal_type=SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT,
                            symbol=symbol,
                            price=current_price,
                            amount=position.amount,
                            confidence=1.0,
                            metadata={
                                'reason': 'stop_loss',
                                'strategy': 'enhanced_grid',
                                'unrealized_pnl_pct': position.unrealized_pnl_pct
                            }
                        ))

                    # 止盈检查
                    elif self.should_take_profit(symbol):
                        signals.append(Signal(
                            signal_type=SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT,
                            symbol=symbol,
                            price=current_price,
                            amount=position.amount,
                            confidence=1.0,
                            metadata={
                                'reason': 'take_profit',
                                'strategy': 'enhanced_grid',
                                'unrealized_pnl_pct': position.unrealized_pnl_pct
                            }
                        ))

                    # 增强风险控制：价格偏离度过高时强制平仓
                    if indicators.get('outside_grid_range', False):
                        signals.append(Signal(
                            signal_type=SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT,
                            symbol=symbol,
                            price=current_price,
                            amount=position.amount,
                            confidence=0.9,
                            metadata={
                                'reason': 'price_deviation_risk',
                                'strategy': 'enhanced_grid',
                                'price_deviation': indicators.get('price_deviation', 0)
                            }
                        ))

        except Exception as e:
            logger.error(f"生成增强网格策略信号时出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")

        return signals

    def _get_current_base_price(self, symbol: str) -> Optional[float]:
        """
        获取当前基准价格

        Args:
            symbol: 交易对

        Returns:
            当前基准价格
        """
        if symbol not in self.grid_prices or not self.grid_prices[symbol]:
            return None

        # 返回网格的中心价格作为基准价格
        grid_prices = self.grid_prices[symbol]
        return (max(grid_prices) + min(grid_prices)) / 2

    def _update_grid_orders_after_trade(self, symbol: str, trade_signals: List[Signal]):
        """
        在交易执行后更新网格订单状态
        买入的网格线变为卖出，卖出的网格线变为买入

        Args:
            symbol: 交易对
            trade_signals: 已执行的交易信号列表
        """
        if symbol not in self.grid_orders:
            return

        base_price = self._get_current_base_price(symbol)
        if base_price is None:
            return

        # 🔧 记录交易时间
        import time
        self.last_trade_time[symbol] = time.time()

        logger.info(f"更新网格订单状态 - {symbol}: 触发了 {len(trade_signals)} 个交易")

        for signal in trade_signals:
            trigger_price = signal.metadata.get('grid_price', signal.price)

            if trigger_price in self.grid_orders[symbol]:
                old_order_type = self.grid_orders[symbol][trigger_price]

                # 买入后变为卖出，卖出后变为买入
                if 'buy' in signal.signal_type.value and old_order_type == 'buy':
                    self.grid_orders[symbol][trigger_price] = 'sell'
                    logger.info(f"网格状态更新: ${trigger_price:.2f} buy → sell")

                    # 同时更新相邻网格的逻辑
                    self._update_adjacent_grid_orders(symbol, trigger_price)

                elif 'sell' in signal.signal_type.value and old_order_type == 'sell':
                    self.grid_orders[symbol][trigger_price] = 'buy'
                    logger.info(f"网格状态更新: ${trigger_price:.2f} sell → buy")

                    # 同时更新相邻网格的逻辑
                    self._update_adjacent_grid_orders(symbol, trigger_price)

    def _update_adjacent_grid_orders(self, symbol: str, trigger_price: float):
        """
        更新相邻网格的订单状态，确保网格逻辑一致性

        Args:
            symbol: 交易对
            trigger_price: 触发的网格价格
        """
        if symbol not in self.grid_prices or symbol not in self.grid_orders:
            return

        grid_prices = sorted(self.grid_prices[symbol])

        try:
            trigger_index = grid_prices.index(trigger_price)

            # 更新相邻网格的逻辑
            # 如果当前网格是买入变为卖出，那么下一个更高的买入网格应该保持买入
            # 如果当前网格是卖出变为买入，那么下一个更低的卖出网格应该保持卖出
            base_price = self._get_current_base_price(symbol)

            # 找到相邻的网格价格
            for i, price in enumerate(grid_prices):
                current_order_type = self.grid_orders[symbol].get(price)

                if current_order_type is None:
                    continue

                # 根据相对于基准价格的位置确定订单类型
                if price < base_price:
                    expected_type = 'buy'
                elif price > base_price:
                    expected_type = 'sell'
                else:
                    continue  # 基准价格不设置订单

                # 确保网格订单类型符合预期
                if self.grid_orders[symbol][price] != expected_type:
                    old_type = self.grid_orders[symbol][price]
                    self.grid_orders[symbol][price] = expected_type
                    logger.debug(f"修正相邻网格: ${price:.2f} {old_type} → {expected_type}")

        except ValueError:
            # trigger_price不在网格中，跳过
            pass

    def _force_rebalance_check(self, symbol: str, current_price: float) -> bool:
        """
        强制检查是否需要重平衡（更积极的策略）

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            是否应该强制重平衡
        """
        # 如果没有启用智能重平衡，总是检查
        if not self.smart_rebalance:
            return True

        # 检查价格偏离度
        if symbol not in self.grid_prices or not self.grid_prices[symbol]:
            return True

        grid_range = (max(self.grid_prices[symbol]) - min(self.grid_prices[symbol]))
        grid_center = (max(self.grid_prices[symbol]) + min(self.grid_prices[symbol])) / 2
        price_deviation = abs(current_price - grid_center) / grid_range

        # 🔧 降低重平衡阈值：从默认的30%降低到10%
        force_rebalance_threshold = getattr(self, 'force_rebalance_threshold', 0.1)

        if price_deviation > force_rebalance_threshold:
            logger.info(f"强制重平衡检查触发 - {symbol}: 价格偏离度 {price_deviation:.2%} > {force_rebalance_threshold:.2%}")
            return True

        # 检查是否有长时间未交易的情况
        if hasattr(self, 'last_trade_time'):
            import time
            current_time = time.time()
            time_since_last_trade = current_time - self.last_trade_time.get(symbol, 0)
            max_idle_time = getattr(self, 'max_idle_time', 3600)  # 1小时

            if time_since_last_trade > max_idle_time:
                logger.info(f"强制重平衡检查触发 - {symbol}: 空闲时间 {time_since_last_trade/3600:.1f}小时 > {max_idle_time/3600:.1f}小时")
                return True

        return False