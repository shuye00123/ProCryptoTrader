from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging
from .base_strategy import BaseStrategy, Signal, SignalType

# 设置日志记录器
logger = logging.getLogger(__name__)


class GridStrategy(BaseStrategy):
    """
    网格策略
    
    在价格区间内设置网格，价格触及网格线时进行买卖操作
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
        self.base_price = None  # 基准价格
        self.grid_prices = {}  # 网格价格 {symbol: [grid_prices]}
        self.grid_levels = {}  # 网格级别 {symbol: {price: level}}
        self.last_price = {}  # 上次价格 {symbol: price}
        self.trade_history = {}  # 交易历史 {symbol: [trades]}
        
        # 网格交易状态
        self.grid_orders = {}  # 当前网格订单 {symbol: {price: order_type}}
        self.executed_levels = {}  # 已执行的网格级别 {symbol: set(levels)}
        
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
                
                # 如果没有基准价格，使用最新价格作为基准
                if self.base_price is None or symbol not in self.last_price:
                    self.base_price = latest_price
                    self._initialize_grid(symbol, latest_price)
                
                # 更新上次价格
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
            # 在基准价格以下设置买单，以上设置卖单
            if price < base_price:
                self.grid_orders[symbol][price] = 'buy'
            elif price > base_price:
                self.grid_orders[symbol][price] = 'sell'
    
    def _check_grid_triggers(self, symbol: str, current_price: float) -> List[Signal]:
        """
        检查网格触发条件
        
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
        
        # 找到当前价格所在的网格区间
        for i in range(len(grid_prices) - 1):
            lower_grid = grid_prices[i]
            upper_grid = grid_prices[i + 1]
            
            # 检查是否从下往上穿过网格线
            if (self.last_price.get(symbol, 0) <= lower_grid and current_price > lower_grid):
                # 触发下网格线，执行买入
                if i not in self.executed_levels[symbol]:
                    signals.append(self._create_buy_signal(symbol, lower_grid))
                    self.executed_levels[symbol].add(i)
                    
                    # 更新网格订单状态
                    self.grid_orders[symbol][lower_grid] = 'sell'  # 买入后，该级别变为卖出级别
                    
                    # 如果有上网格线，将其状态更新为买入
                    if i + 1 < len(grid_prices):
                        self.grid_orders[symbol][upper_grid] = 'buy'
            
            # 检查是否从上往下穿过网格线
            elif (self.last_price.get(symbol, 0) >= upper_grid and current_price < upper_grid):
                # 触发上网格线，执行卖出
                if i + 1 not in self.executed_levels[symbol]:
                    signals.append(self._create_sell_signal(symbol, upper_grid))
                    self.executed_levels[symbol].add(i + 1)
                    
                    # 更新网格订单状态
                    self.grid_orders[symbol][upper_grid] = 'buy'  # 卖出后，该级别变为买入级别
                    
                    # 如果有下网格线，将其状态更新为卖出
                    if i < len(grid_prices):
                        self.grid_orders[symbol][lower_grid] = 'sell'
        
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
        # 计算买入数量
        amount = self._calculate_position_size(symbol, price)
        
        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'buy',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now()
        })
        
        return Signal(
            signal_type=SignalType.OPEN_LONG,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={'strategy': 'grid', 'grid_level': self.grid_levels[symbol].get(price, -1)}
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
        # 计算卖出数量
        amount = self._calculate_position_size(symbol, price)
        
        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'sell',
            'price': price,
            'amount': amount,
            'timestamp': pd.Timestamp.now()
        })
        
        return Signal(
            signal_type=SignalType.OPEN_SHORT,
            symbol=symbol,
            price=price,
            amount=amount,
            confidence=0.8,
            metadata={'strategy': 'grid', 'grid_level': self.grid_levels[symbol].get(price, -1)}
        )
    
    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """
        计算持仓大小
        
        Args:
            symbol: 交易对
            price: 价格
            
        Returns:
            持仓大小
        """
        # 使用固定比例计算持仓大小
        # 这里简化处理，实际应该考虑账户余额
        return self.position_size
    
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
            'base_price': self.base_price,
            'grid_count': self.grid_count,
            'grid_range_pct': self.grid_range_pct,
            'grid_prices': self.grid_prices[symbol],
            'executed_levels': list(self.executed_levels[symbol]),
            'last_price': self.last_price.get(symbol, 0),
            'trade_count': len(self.trade_history.get(symbol, [])),
            'grid_orders': self.grid_orders.get(symbol, {})
        }
    
    def reset(self):
        """重置策略状态"""
        super().reset()
        
        # 重置网格状态
        self.base_price = None
        self.grid_prices = {}
        self.grid_levels = {}
        self.last_price = {}
        self.grid_orders = {}
        self.executed_levels = {}
        
        # 重新初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
            self.executed_levels[symbol] = set()
