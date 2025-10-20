from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging
from .base_strategy import BaseStrategy, Signal, SignalType

# 设置日志记录器
logger = logging.getLogger(__name__)


class MartingaleStrategy(BaseStrategy):
    """
    马丁格尔策略
    
    在亏损时加倍下注，直到盈利为止
    """
    
    def __init__(self, config: Dict):
        """
        初始化马丁格尔策略
        
        Args:
            config: 策略配置参数
        """
        super().__init__(config)
        
        # 马丁格尔参数
        self.multiplier = config.get('multiplier', 2.0)  # 加倍倍数
        self.max_levels = config.get('max_levels', 5)  # 最大加仓次数
        self.base_position_size = config.get('base_position_size', 0.01)  # 基础仓位大小
        self.profit_target_pct = config.get('profit_target_pct', 0.02)  # 盈利目标百分比
        self.entry_price = {}  # 入场价格 {symbol: price}
        self.position_levels = {}  # 持仓级别 {symbol: level}
        self.total_position_size = {}  # 总持仓大小 {symbol: size}
        self.average_entry_price = {}  # 平均入场价格 {symbol: price}
        self.trade_history = {}  # 交易历史 {symbol: [trades]}
        
        # 技术指标参数
        self.rsi_overbought = config.get('rsi_overbought', 70)  # RSI超买阈值
        self.rsi_oversold = config.get('rsi_oversold', 30)  # RSI超卖阈值
        self.trend_period = config.get('trend_period', 20)  # 趋势判断周期
        
        # 初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
    
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
                
                # 计算移动平均线
                if len(df) >= self.trend_period:
                    symbol_indicators['sma'] = df['close'].rolling(self.trend_period).mean().iloc[-1]
                    symbol_indicators['price_above_sma'] = df['close'].iloc[-1] > symbol_indicators['sma']
                
                # 计算RSI
                if len(df) >= 14:
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))
                    symbol_indicators['rsi_overbought'] = symbol_indicators['rsi'] > self.rsi_overbought
                    symbol_indicators['rsi_oversold'] = symbol_indicators['rsi'] < self.rsi_oversold
                
                # 计算布林带
                if len(df) >= 20:
                    sma = df['close'].rolling(20).mean()
                    std = df['close'].rolling(20).std()
                    symbol_indicators['bb_upper'] = (sma + 2 * std).iloc[-1]
                    symbol_indicators['bb_lower'] = (sma - 2 * std).iloc[-1]
                    symbol_indicators['bb_middle'] = sma.iloc[-1]
                    symbol_indicators['price_above_bb_upper'] = df['close'].iloc[-1] > symbol_indicators['bb_upper']
                    symbol_indicators['price_below_bb_lower'] = df['close'].iloc[-1] < symbol_indicators['bb_lower']
                
                # 计算MACD
                if len(df) >= 26:
                    exp1 = df['close'].ewm(span=12).mean()
                    exp2 = df['close'].ewm(span=26).mean()
                    symbol_indicators['macd'] = (exp1 - exp2).iloc[-1]
                    symbol_indicators['signal'] = (exp1 - exp2).ewm(span=9).mean().iloc[-1]
                    symbol_indicators['macd_histogram'] = symbol_indicators['macd'] - symbol_indicators['signal']
                    symbol_indicators['macd_bullish'] = symbol_indicators['macd'] > symbol_indicators['signal']
                
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
            if df.empty:
                continue
                
            latest_price = df['close'].iloc[-1]
            indicators = self.indicators.get(symbol, {})
            
            # 如果没有持仓，检查入场条件
            if not self.has_position(symbol):
                entry_signal = self._check_entry_conditions(symbol, latest_price, indicators)
                if entry_signal:
                    signals.append(entry_signal)
            else:
                # 如果有持仓，检查是否需要加仓或平仓
                position = self.get_position(symbol)
                
                # 检查是否需要加仓
                if self._should_add_position(symbol, latest_price, position):
                    add_signal = self._create_add_position_signal(symbol, latest_price, position)
                    signals.append(add_signal)
                
                # 检查是否应该平仓
                if self._should_close_position(symbol, latest_price, position):
                    close_signal = self._create_close_position_signal(symbol, latest_price, position)
                    signals.append(close_signal)
        
        return signals
    
    def _check_entry_conditions(self, symbol: str, price: float, indicators: Dict) -> Optional[Signal]:
        """
        检查入场条件
        
        Args:
            symbol: 交易对
            price: 当前价格
            indicators: 技术指标
            
        Returns:
            入场信号，如果没有则返回None
        """
        # 检查趋势方向
        trend_up = indicators.get('price_above_sma', False)
        
        # 检查RSI是否超卖
        rsi_oversold = indicators.get('rsi_oversold', False)
        
        # 检查价格是否低于布林带下轨
        price_below_bb_lower = indicators.get('price_below_bb_lower', False)
        
        # 检查MACD是否金叉
        macd_bullish = indicators.get('macd_bullish', False)
        
        # 综合判断入场条件
        # 这里简化处理，实际可以根据需要组合更多条件
        if (rsi_oversold or price_below_bb_lower) and macd_bullish:
            # 确定方向
            direction = 'long' if trend_up else 'short'
            
            # 记录入场价格和级别
            self.entry_price[symbol] = price
            self.position_levels[symbol] = 1
            self.total_position_size[symbol] = self.base_position_size
            self.average_entry_price[symbol] = price
            
            # 创建入场信号
            return Signal(
                signal_type=SignalType.OPEN_LONG if direction == 'long' else SignalType.OPEN_SHORT,
                symbol=symbol,
                price=price,
                amount=self.base_position_size,
                confidence=0.7,
                metadata={
                    'strategy': 'martingale',
                    'level': 1,
                    'reason': 'initial_entry',
                    'rsi': indicators.get('rsi'),
                    'price_above_sma': trend_up
                }
            )
        
        return None
    
    def _should_add_position(self, symbol: str, price: float, position) -> bool:
        """
        检查是否应该加仓
        
        Args:
            symbol: 交易对
            price: 当前价格
            position: 持仓信息
            
        Returns:
            是否应该加仓
        """
        # 检查是否达到最大级别
        if self.position_levels.get(symbol, 1) >= self.max_levels:
            return False
        
        # 检查是否亏损
        if position.unrealized_pnl_pct >= 0:
            return False
        
        # 检查亏损是否达到加仓阈值
        # 这里简化处理，实际可以设置更复杂的条件
        loss_threshold = -0.02 * self.position_levels.get(symbol, 1)  # 随级别提高降低阈值
        return position.unrealized_pnl_pct <= loss_threshold * 100
    
    def _create_add_position_signal(self, symbol: str, price: float, position) -> Signal:
        """
        创建加仓信号
        
        Args:
            symbol: 交易对
            price: 当前价格
            position: 持仓信息
            
        Returns:
            加仓信号
        """
        # 计算新的仓位大小
        current_level = self.position_levels.get(symbol, 1)
        new_position_size = self.base_position_size * (self.multiplier ** current_level)
        
        # 更新持仓信息
        self.position_levels[symbol] = current_level + 1
        self.total_position_size[symbol] += new_position_size
        
        # 计算新的平均入场价格
        total_cost = self.average_entry_price[symbol] * (self.total_position_size[symbol] - new_position_size) + price * new_position_size
        self.average_entry_price[symbol] = total_cost / self.total_position_size[symbol]
        
        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'add_position',
            'price': price,
            'amount': new_position_size,
            'level': self.position_levels[symbol],
            'timestamp': pd.Timestamp.now()
        })
        
        # 创建加仓信号
        return Signal(
            signal_type=SignalType.INCREASE_LONG if position.side == 'long' else SignalType.INCREASE_SHORT,
            symbol=symbol,
            price=price,
            amount=new_position_size,
            confidence=0.6,
            metadata={
                'strategy': 'martingale',
                'level': self.position_levels[symbol],
                'reason': 'add_position',
                'unrealized_pnl_pct': position.unrealized_pnl_pct
            }
        )
    
    def _should_close_position(self, symbol: str, price: float, position) -> bool:
        """
        检查是否应该平仓
        
        Args:
            symbol: 交易对
            price: 当前价格
            position: 持仓信息
            
        Returns:
            是否应该平仓
        """
        # 检查是否达到盈利目标
        if position.unrealized_pnl_pct >= self.profit_target_pct * 100:
            return True
        
        # 检查是否达到止损
        if self.should_stop_loss(symbol):
            return True
        
        # 检查技术指标是否发出反转信号
        indicators = self.indicators.get(symbol, {})
        
        # 如果是多头持仓，检查是否有看跌信号
        if position.side == 'long':
            rsi_overbought = indicators.get('rsi_overbought', False)
            price_above_bb_upper = indicators.get('price_above_bb_upper', False)
            macd_bullish = indicators.get('macd_bullish', False)
            
            # 如果RSI超买或价格突破布林带上轨且MACD死叉，考虑平仓
            if (rsi_overbought or price_above_bb_upper) and not macd_bullish:
                return True
        
        # 如果是空头持仓，检查是否有看涨信号
        else:
            rsi_oversold = indicators.get('rsi_oversold', False)
            price_below_bb_lower = indicators.get('price_below_bb_lower', False)
            macd_bullish = indicators.get('macd_bullish', False)
            
            # 如果RSI超卖或价格跌破布林带下轨且MACD金叉，考虑平仓
            if (rsi_oversold or price_below_bb_lower) and macd_bullish:
                return True
        
        return False
    
    def _create_close_position_signal(self, symbol: str, price: float, position) -> Signal:
        """
        创建平仓信号
        
        Args:
            symbol: 交易对
            price: 当前价格
            position: 持仓信息
            
        Returns:
            平仓信号
        """
        # 确定平仓原因
        if position.unrealized_pnl_pct >= self.profit_target_pct * 100:
            reason = 'profit_target'
        elif position.unrealized_pnl_pct <= -self.stop_loss_pct * 100:
            reason = 'stop_loss'
        else:
            reason = 'signal_reversal'
        
        # 记录交易历史
        self.trade_history[symbol].append({
            'type': 'close_position',
            'price': price,
            'amount': position.amount,
            'level': self.position_levels.get(symbol, 1),
            'pnl_pct': position.unrealized_pnl_pct,
            'reason': reason,
            'timestamp': pd.Timestamp.now()
        })
        
        # 创建平仓信号
        return Signal(
            signal_type=SignalType.CLOSE_LONG if position.side == 'long' else SignalType.CLOSE_SHORT,
            symbol=symbol,
            price=price,
            amount=position.amount,
            confidence=0.8,
            metadata={
                'strategy': 'martingale',
                'level': self.position_levels.get(symbol, 1),
                'reason': reason,
                'pnl_pct': position.unrealized_pnl_pct
            }
        )
    
    def get_martingale_status(self, symbol: str) -> Dict:
        """
        获取马丁格尔策略状态
        
        Args:
            symbol: 交易对
            
        Returns:
            马丁格尔策略状态字典
        """
        return {
            'symbol': symbol,
            'multiplier': self.multiplier,
            'max_levels': self.max_levels,
            'base_position_size': self.base_position_size,
            'profit_target_pct': self.profit_target_pct,
            'current_level': self.position_levels.get(symbol, 0),
            'total_position_size': self.total_position_size.get(symbol, 0),
            'average_entry_price': self.average_entry_price.get(symbol, 0),
            'entry_price': self.entry_price.get(symbol, 0),
            'trade_count': len(self.trade_history.get(symbol, [])),
            'has_position': self.has_position(symbol)
        }
    
    def reset(self):
        """重置策略状态"""
        super().reset()
        
        # 重置马丁格尔状态
        self.entry_price = {}
        self.position_levels = {}
        self.total_position_size = {}
        self.average_entry_price = {}
        
        # 重新初始化交易历史
        for symbol in self.symbols:
            self.trade_history[symbol] = []
