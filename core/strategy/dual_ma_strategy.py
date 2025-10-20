from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging
from .base_strategy import BaseStrategy, Signal, SignalType

# 设置日志记录器
logger = logging.getLogger(__name__)


class DualMovingAverageStrategy(BaseStrategy):
    """
    双均线策略
    
    使用短期和长期移动平均线的交叉来生成交易信号
    """
    
    def __init__(self, config: Dict):
        """
        初始化双均线策略
        
        Args:
            config: 策略配置参数
        """
        super().__init__(config)
        
        # 双均线参数
        self.short_period = config.get('short_period', 10)  # 短期均线周期
        self.long_period = config.get('long_period', 20)  # 长期均线周期
        
        # 验证参数有效性
        if self.short_period >= self.long_period:
            raise ValueError("短期均线周期必须小于长期均线周期")
        
        # 交易参数
        self.position_size = config.get('position_size', 0.5)  # 仓位大小
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 止损百分比
        self.take_profit_pct = config.get('take_profit_pct', 0.1)  # 止盈百分比
        
        # 状态变量
        self.short_ma = {}  # 短期均线 {symbol: value}
        self.long_ma = {}  # 长期均线 {symbol: value}
        self.prev_short_ma = {}  # 前一期短期均线 {symbol: value}
        self.prev_long_ma = {}  # 前一期长期均线 {symbol: value}
        self.position_opened = {}  # 持仓是否已开仓 {symbol: bool}
        self.entry_price = {}  # 入场价格 {symbol: price}
        
        # 初始化状态
        for symbol in self.symbols:
            self.position_opened[symbol] = False
    
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
                if df.empty or len(df) < self.long_period:
                    continue
                    
                symbol_indicators = {}
                
                # 保存前一期均线值
                self.prev_short_ma[symbol] = self.short_ma.get(symbol)
                self.prev_long_ma[symbol] = self.long_ma.get(symbol)
                
                # 计算短期均线
                self.short_ma[symbol] = df['close'].rolling(window=self.short_period).mean().iloc[-1]
                
                # 计算长期均线
                self.long_ma[symbol] = df['close'].rolling(window=self.long_period).mean().iloc[-1]
                
                # 判断均线方向
                symbol_indicators['short_ma'] = self.short_ma[symbol]
                symbol_indicators['long_ma'] = self.long_ma[symbol]
                symbol_indicators['short_ma_above_long'] = self.short_ma[symbol] > self.long_ma[symbol]
                
                # 判断均线交叉
                if self.prev_short_ma.get(symbol) is not None and self.prev_long_ma.get(symbol) is not None:
                    symbol_indicators['golden_cross'] = (
                        self.prev_short_ma[symbol] <= self.prev_long_ma[symbol] and 
                        self.short_ma[symbol] > self.long_ma[symbol]
                    )
                    symbol_indicators['death_cross'] = (
                        self.prev_short_ma[symbol] >= self.prev_long_ma[symbol] and 
                        self.short_ma[symbol] < self.long_ma[symbol]
                    )
                
                # 计算价格与均线的距离
                symbol_indicators['price_above_short_ma'] = df['close'].iloc[-1] > self.short_ma[symbol]
                symbol_indicators['price_above_long_ma'] = df['close'].iloc[-1] > self.long_ma[symbol]
                
                # 计算RSI
                if len(df) >= 14:
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    symbol_indicators['rsi'] = 100 - (100 / (1 + rs.iloc[-1]))
                
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
                # 如果有持仓，检查平仓条件
                position = self.get_position(symbol)
                
                # 检查是否应该平仓
                if self._should_close_position(symbol, latest_price, position, indicators):
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
        # 检查是否有金叉信号
        golden_cross = indicators.get('golden_cross', False)
        
        # 检查短期均线是否在长期均线之上
        short_above_long = indicators.get('short_ma_above_long', False)
        
        # 检查RSI是否在合理范围
        rsi = indicators.get('rsi', 50)
        rsi_reasonable = 30 < rsi < 70
        
        # 综合判断入场条件
        if (golden_cross or short_above_long) and rsi_reasonable:
            # 记录入场价格
            self.entry_price[symbol] = price
            self.position_opened[symbol] = True
            
            # 创建入场信号
            return Signal(
                signal_type=SignalType.OPEN_LONG,
                symbol=symbol,
                price=price,
                amount=self.position_size,
                confidence=0.7,
                metadata={
                    'strategy': 'dual_ma',
                    'short_ma': indicators.get('short_ma'),
                    'long_ma': indicators.get('long_ma'),
                    'rsi': rsi,
                    'reason': 'golden_cross' if golden_cross else 'short_above_long'
                }
            )
        
        return None
    
    def _should_close_position(self, symbol: str, price: float, position, indicators: Dict) -> bool:
        """
        检查是否应该平仓
        
        Args:
            symbol: 交易对
            price: 当前价格
            position: 持仓信息
            indicators: 技术指标
            
        Returns:
            是否应该平仓
        """
        # 检查是否有死叉信号
        death_cross = indicators.get('death_cross', False)
        
        # 检查短期均线是否在长期均线之下
        short_below_long = not indicators.get('short_ma_above_long', False)
        
        # 检查止损条件
        entry_price = self.entry_price.get(symbol, price)
        stop_loss_triggered = False
        
        if position.is_long:
            # 多头止损
            stop_loss_price = entry_price * (1 - self.stop_loss_pct)
            stop_loss_triggered = price <= stop_loss_price
        else:
            # 空头止损
            stop_loss_price = entry_price * (1 + self.stop_loss_pct)
            stop_loss_triggered = price >= stop_loss_price
        
        # 检查止盈条件
        take_profit_triggered = False
        
        if position.is_long:
            # 多头止盈
            take_profit_price = entry_price * (1 + self.take_profit_pct)
            take_profit_triggered = price >= take_profit_price
        else:
            # 空头止盈
            take_profit_price = entry_price * (1 - self.take_profit_pct)
            take_profit_triggered = price <= take_profit_price
        
        # 综合判断平仓条件
        return death_cross or short_below_long or stop_loss_triggered or take_profit_triggered
    
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
        # 确定平仓信号类型
        signal_type = SignalType.CLOSE_LONG if position.is_long else SignalType.CLOSE_SHORT
        
        # 计算盈亏百分比
        entry_price = self.entry_price.get(symbol, price)
        pnl_pct = 0
        
        if position.is_long:
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price
        
        # 重置状态
        self.position_opened[symbol] = False
        
        # 创建平仓信号
        return Signal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            amount=position.size,
            confidence=0.9,
            metadata={
                'strategy': 'dual_ma',
                'entry_price': entry_price,
                'pnl_pct': pnl_pct,
                'reason': 'close_position'
            }
        )