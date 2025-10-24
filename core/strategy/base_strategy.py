from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Tuple
import pandas as pd
import numpy as np
import logging
from enum import Enum

# 设置日志记录器
logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型枚举"""
    OPEN_LONG = "open_long"      # 开多仓
    OPEN_SHORT = "open_short"    # 开空仓
    CLOSE_LONG = "close_long"    # 平多仓
    CLOSE_SHORT = "close_short"  # 平空仓
    INCREASE_LONG = "increase_long"  # 加多仓
    INCREASE_SHORT = "increase_short"  # 加空仓
    HOLD = "hold"                # 持仓不动
    CLOSE = "close"              # 平仓（通用）


class Signal:
    """交易信号类"""
    
    def __init__(self, signal_type: SignalType, symbol: str, price: float = None,
                 amount: float = None, quantity: float = None, confidence: float = 1.0,
                 stop_loss: float = None, take_profit: float = None,
                 metadata: Dict = None):
        """
        初始化交易信号

        Args:
            signal_type: 信号类型
            symbol: 交易对
            price: 建议价格
            amount: 建议数量（与quantity同义，兼容性）
            quantity: 建议数量
            confidence: 信号置信度，范围[0,1]
            stop_loss: 止损价格
            take_profit: 止盈价格
            metadata: 额外元数据
        """
        self.signal_type = signal_type
        self.symbol = symbol
        self.price = price
        # 优先使用amount，如果没有则使用quantity
        self.amount = amount if amount is not None else quantity
        self.quantity = self.amount  # 保持向后兼容
        self.confidence = confidence
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.metadata = metadata or {}
        self.timestamp = pd.Timestamp.now()
    
    def to_dict(self) -> Dict:
        """将信号转换为字典"""
        return {
            'signal_type': self.signal_type.value,
            'symbol': self.symbol,
            'price': self.price,
            'amount': self.amount,
            'confidence': self.confidence,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


class Position:
    """持仓信息类"""
    
    def __init__(self, symbol: str, side: str, amount: float, 
                 entry_price: float, current_price: float = None):
        """
        初始化持仓信息
        
        Args:
            symbol: 交易对
            side: 持仓方向，'long' 或 'short'
            amount: 持仓数量
            entry_price: 开仓价格
            current_price: 当前价格
        """
        self.symbol = symbol
        self.side = side
        self.amount = amount
        self.entry_price = entry_price
        self.current_price = current_price or entry_price
        self.unrealized_pnl = self._calculate_unrealized_pnl()
        self.unrealized_pnl_pct = self._calculate_unrealized_pnl_pct()
    
    def update_price(self, new_price: float):
        """更新当前价格并重新计算盈亏"""
        self.current_price = new_price
        self.unrealized_pnl = self._calculate_unrealized_pnl()
        self.unrealized_pnl_pct = self._calculate_unrealized_pnl_pct()
    
    def _calculate_unrealized_pnl(self) -> float:
        """计算未实现盈亏"""
        if self.side == 'long':
            return (self.current_price - self.entry_price) * self.amount
        else:  # short
            return (self.entry_price - self.current_price) * self.amount
    
    def _calculate_unrealized_pnl_pct(self) -> float:
        """计算未实现盈亏百分比"""
        if self.entry_price == 0:
            return 0
        return self.unrealized_pnl / (self.entry_price * self.amount) * 100
    
    def to_dict(self) -> Dict:
        """将持仓信息转换为字典"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'amount': self.amount,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'unrealized_pnl_pct': self.unrealized_pnl_pct
        }


class BaseStrategy(ABC):
    """
    策略基类，定义策略接口和通用功能
    """
    
    def __init__(self, config: Dict):
        """
        初始化策略
        
        Args:
            config: 策略配置参数
        """
        self.config = config
        self.name = config.get('name', self.__class__.__name__)
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '1h')
        self.positions = {}  # 持仓信息字典 {symbol: Position}
        self.signals_history = []  # 信号历史记录
        self.is_initialized = False
        
        # 策略参数
        self.max_positions = config.get('max_positions', 1)  # 最大持仓数量
        self.position_size = config.get('position_size', 0.1)  # 每次开仓比例
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 止损百分比
        self.take_profit_pct = config.get('take_profit_pct', 0.1)  # 止盈百分比
        
        # 状态变量
        self.current_data = {}  # 当前数据 {symbol: DataFrame}
        self.indicators = {}  # 技术指标 {symbol: {indicator_name: value}}

    def initialize(self, config: Dict):
        """
        初始化策略（兼容回测器）

        Args:
            config: 回测配置参数
        """
        # 更新策略配置
        self.backtest_config = config
        self.initial_balance = config.get("initial_balance", 10000)
        self.start_date = config.get("start_date")
        self.end_date = config.get("end_date")

        # 标记为已初始化
        self.is_initialized = True

    @abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        根据行情数据生成交易信号
        
        Args:
            data: 交易对数据字典 {symbol: DataFrame}
            
        Returns:
            交易信号列表
        """
        pass
    
    @abstractmethod
    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """
        计算技术指标
        
        Args:
            data: 交易对数据字典
            
        Returns:
            技术指标字典 {symbol: {indicator_name: value}}
        """
        pass
    
    def update(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        更新策略状态并生成信号
        
        Args:
            data: 交易对数据字典
            
        Returns:
            交易信号列表
        """
        try:
            # 更新当前数据
            self.current_data = data
            
            # 计算技术指标
            self.indicators = self.calculate_indicators(data)
            
            # 更新持仓价格
            self._update_positions_price(data)
            
            # 生成交易信号
            signals = self.generate_signals(data)
            
            # 记录信号历史
            self.signals_history.extend(signals)
            
            # 首次运行后标记为已初始化
            if not self.is_initialized:
                self.is_initialized = True
                
            return signals
        except Exception as e:
            logger.error(f"更新策略状态时出错: {e}")
            return []
    
    def _update_positions_price(self, data: Dict[str, pd.DataFrame]):
        """更新持仓的当前价格"""
        for symbol, position in self.positions.items():
            if symbol in data and not data[symbol].empty:
                current_price = data[symbol]['close'].iloc[-1]
                position.update_price(current_price)
    
    def add_position(self, symbol: str, side: str, amount: float, entry_price: float):
        """
        添加持仓
        
        Args:
            symbol: 交易对
            side: 持仓方向
            amount: 持仓数量
            entry_price: 开仓价格
        """
        self.positions[symbol] = Position(symbol, side, amount, entry_price)
    
    def remove_position(self, symbol: str):
        """
        移除持仓
        
        Args:
            symbol: 交易对
        """
        if symbol in self.positions:
            del self.positions[symbol]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取持仓信息
        
        Args:
            symbol: 交易对
            
        Returns:
            持仓信息，如果没有则返回None
        """
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """
        检查是否有指定交易对的持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            是否有持仓
        """
        return symbol in self.positions
    
    def get_position_side(self, symbol: str) -> Optional[str]:
        """
        获取持仓方向
        
        Args:
            symbol: 交易对
            
        Returns:
            持仓方向，如果没有持仓则返回None
        """
        position = self.get_position(symbol)
        return position.side if position else None
    
    def can_open_position(self, symbol: str) -> bool:
        """
        检查是否可以开新仓
        
        Args:
            symbol: 交易对
            
        Returns:
            是否可以开新仓
        """
        # 检查是否已有持仓
        if self.has_position(symbol):
            return False
            
        # 检查是否达到最大持仓数量
        if len(self.positions) >= self.max_positions:
            return False
            
        return True
    
    def should_stop_loss(self, symbol: str) -> bool:
        """
        检查是否应该止损
        
        Args:
            symbol: 交易对
            
        Returns:
            是否应该止损
        """
        position = self.get_position(symbol)
        if not position:
            return False
            
        return position.unrealized_pnl_pct <= -self.stop_loss_pct * 100
    
    def should_take_profit(self, symbol: str) -> bool:
        """
        检查是否应该止盈
        
        Args:
            symbol: 交易对
            
        Returns:
            是否应该止盈
        """
        position = self.get_position(symbol)
        if not position:
            return False
            
        return position.unrealized_pnl_pct >= self.take_profit_pct * 100
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        获取最新价格
        
        Args:
            symbol: 交易对
            
        Returns:
            最新价格，如果没有数据则返回None
        """
        if symbol not in self.current_data or self.current_data[symbol].empty:
            return None
            
        return self.current_data[symbol]['close'].iloc[-1]
    
    def get_status(self) -> Dict:
        """
        获取策略状态
        
        Returns:
            策略状态字典
        """
        return {
            'name': self.name,
            'is_initialized': self.is_initialized,
            'positions': {symbol: pos.to_dict() for symbol, pos in self.positions.items()},
            'total_positions': len(self.positions),
            'signals_count': len(self.signals_history),
            'config': self.config
        }
    
    def reset(self):
        """重置策略状态"""
        self.positions = {}
        self.signals_history = []
        self.current_data = {}
        self.indicators = {}
        self.is_initialized = False
