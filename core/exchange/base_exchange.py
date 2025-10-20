from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, Tuple
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseExchange(ABC):
    """
    交易所接口基类，定义标准接口，包括下单、撤单、获取账户资产、获取订单状态等
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, sandbox: bool = False):
        """
        初始化交易所接口
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            sandbox: 是否使用沙盒环境
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.exchange_name = self.__class__.__name__.replace('API', '').lower()
    
    @abstractmethod
    def create_market_order(self, symbol: str, side: str, amount: float, 
                           params: Optional[Dict] = None) -> Dict:
        """
        创建市价单
        
        Args:
            symbol: 交易对
            side: 买卖方向，'buy' 或 'sell'
            amount: 数量
            params: 额外参数
            
        Returns:
            订单信息字典
        """
        pass
    
    @abstractmethod
    def create_limit_order(self, symbol: str, side: str, amount: float, 
                          price: float, params: Optional[Dict] = None) -> Dict:
        """
        创建限价单
        
        Args:
            symbol: 交易对
            side: 买卖方向，'buy' 或 'sell'
            amount: 数量
            price: 价格
            params: 额外参数
            
        Returns:
            订单信息字典
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        撤销订单
        
        Args:
            order_id: 订单ID
            symbol: 交易对
            params: 额外参数
            
        Returns:
            撤单结果
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            symbol: 交易对
            params: 额外参数
            
        Returns:
            订单信息字典
        """
        pass
    
    @abstractmethod
    def get_open_orders(self, symbol: str = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取未成交订单
        
        Args:
            symbol: 交易对，如果为None则获取所有交易对的未成交订单
            params: 额外参数
            
        Returns:
            未成交订单列表
        """
        pass
    
    @abstractmethod
    def get_balance(self, params: Optional[Dict] = None) -> Dict:
        """
        获取账户资产
        
        Args:
            params: 额外参数
            
        Returns:
            账户资产信息
        """
        pass
    
    @abstractmethod
    def get_ticker(self, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        获取行情信息
        
        Args:
            symbol: 交易对
            params: 额外参数
            
        Returns:
            行情信息字典
        """
        pass
    
    @abstractmethod
    def get_orderbook(self, symbol: str, limit: int = None, params: Optional[Dict] = None) -> Dict:
        """
        获取订单簿
        
        Args:
            symbol: 交易对
            limit: 订单簿深度
            params: 额外参数
            
        Returns:
            订单簿信息
        """
        pass
    
    @abstractmethod
    def get_trades(self, symbol: str, since: Optional[int] = None, 
                  limit: Optional[int] = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取最近成交记录
        
        Args:
            symbol: 交易对
            since: 开始时间戳（毫秒）
            limit: 限制数量
            params: 额外参数
            
        Returns:
            成交记录列表
        """
        pass
    
    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str = '1h', since: Optional[int] = None, 
                 limit: Optional[int] = None, params: Optional[Dict] = None) -> List[List]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            timeframe: 时间框架
            since: 开始时间戳（毫秒）
            limit: 限制数量
            params: 额外参数
            
        Returns:
            K线数据列表
        """
        pass
    
    @abstractmethod
    def get_markets(self, params: Optional[Dict] = None) -> Dict:
        """
        获取所有交易对信息
        
        Args:
            params: 额外参数
            
        Returns:
            交易对信息字典
        """
        pass
    
    def get_precision(self, symbol: str) -> Dict:
        """
        获取交易对精度信息
        
        Args:
            symbol: 交易对
            
        Returns:
            精度信息字典
        """
        markets = self.get_markets()
        if symbol in markets:
            market = markets[symbol]
            return {
                'price': market.get('precision', {}).get('price', 8),
                'amount': market.get('precision', {}).get('amount', 8)
            }
        return {'price': 8, 'amount': 8}
    
    def get_fees(self, symbol: str) -> Dict:
        """
        获取交易手续费信息
        
        Args:
            symbol: 交易对
            
        Returns:
            手续费信息字典
        """
        markets = self.get_markets()
        if symbol in markets:
            market = markets[symbol]
            return market.get('fee', {})
        return {}
    
    def format_price(self, symbol: str, price: float) -> float:
        """
        格式化价格到交易所精度
        
        Args:
            symbol: 交易对
            price: 原始价格
            
        Returns:
            格式化后的价格
        """
        precision = self.get_precision(symbol)['price']
        return round(price, precision)
    
    def format_amount(self, symbol: str, amount: float) -> float:
        """
        格式化数量到交易所精度
        
        Args:
            symbol: 交易对
            amount: 原始数量
            
        Returns:
            格式化后的数量
        """
        precision = self.get_precision(symbol)['amount']
        return round(amount, precision)
    
    def calculate_order_cost(self, symbol: str, side: str, amount: float, 
                           price: float = None, order_type: str = 'market') -> float:
        """
        计算订单成本
        
        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            price: 价格（限价单需要）
            order_type: 订单类型
            
        Returns:
            订单成本
        """
        if order_type == 'market':
            # 市价单，使用当前市场价格估算
            ticker = self.get_ticker(symbol)
            if side == 'buy':
                price = float(ticker.get('ask', ticker.get('last', 0)))
            else:
                price = float(ticker.get('bid', ticker.get('last', 0)))
        
        if price is None:
            raise ValueError("无法确定订单价格")
            
        cost = amount * price
        fees = self.get_fees(symbol)
        fee_rate = fees.get(side, 0.001)  # 默认0.1%手续费
        
        return cost * (1 + fee_rate)
    
    def get_position(self, symbol: str = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取持仓信息
        
        Args:
            symbol: 交易对，如果为None则获取所有持仓
            params: 额外参数
            
        Returns:
            持仓信息列表
        """
        # 默认实现，子类可以重写
        return []
    
    def set_leverage(self, symbol: str, leverage: int, params: Optional[Dict] = None) -> Dict:
        """
        设置杠杆倍数
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            params: 额外参数
            
        Returns:
            设置结果
        """
        # 默认实现，子类可以重写
        return {'info': 'Not implemented'}
    
    def close_position(self, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        平仓
        
        Args:
            symbol: 交易对
            params: 额外参数
            
        Returns:
            平仓结果
        """
        # 默认实现，子类可以重写
        return {'info': 'Not implemented'}