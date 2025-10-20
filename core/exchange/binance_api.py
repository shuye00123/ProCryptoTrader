import ccxt
from typing import Dict, List, Optional, Union, Tuple
import pandas as pd
from datetime import datetime
from .base_exchange import BaseExchange
import logging

logger = logging.getLogger(__name__)


class BinanceAPI(BaseExchange):
    """
    Binance交易接口实现
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, sandbox: bool = False):
        """
        初始化Binance API
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            sandbox: 是否使用沙盒环境
        """
        super().__init__(api_key, api_secret, sandbox)
        
        # 初始化ccxt Binance实例
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': sandbox,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # 默认使用合约交易
            },
        })
        
        # 加载市场信息
        self.markets = self.exchange.load_markets()
    
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
        try:
            if params is None:
                params = {}
                
            order = self.exchange.create_market_order(symbol, side, amount, None, params)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"创建市价单时出错: {e}")
            return {'error': str(e)}
    
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
        try:
            if params is None:
                params = {}
                
            # 格式化价格和数量到交易所精度
            price = self.format_price(symbol, price)
            amount = self.format_amount(symbol, amount)
            
            order = self.exchange.create_limit_order(symbol, side, amount, price, params)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"创建限价单时出错: {e}")
            return {'error': str(e)}
    
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
        try:
            if params is None:
                params = {}
                
            result = self.exchange.cancel_order(order_id, symbol, params)
            return self._format_order(result)
        except Exception as e:
            logger.error(f"撤销订单时出错: {e}")
            return {'error': str(e)}
    
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
        try:
            if params is None:
                params = {}
                
            order = self.exchange.fetch_order(order_id, symbol, params)
            return self._format_order(order)
        except Exception as e:
            logger.error(f"获取订单信息时出错: {e}")
            return {'error': str(e)}
    
    def get_open_orders(self, symbol: str = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取未成交订单
        
        Args:
            symbol: 交易对，如果为None则获取所有交易对的未成交订单
            params: 额外参数
            
        Returns:
            未成交订单列表
        """
        try:
            if params is None:
                params = {}
                
            orders = self.exchange.fetch_open_orders(symbol, params)
            return [self._format_order(order) for order in orders]
        except Exception as e:
            logger.error(f"获取未成交订单时出错: {e}")
            return [{'error': str(e)}]
    
    def get_balance(self, params: Optional[Dict] = None) -> Dict:
        """
        获取账户资产
        
        Args:
            params: 额外参数
            
        Returns:
            账户资产信息
        """
        try:
            if params is None:
                params = {}
                
            balance = self.exchange.fetch_balance(params)
            
            # 格式化余额信息
            result = {
                'info': balance.get('info', {}),
                'total': {},
                'free': {},
                'used': {}
            }
            
            for currency in balance.get('total', {}):
                if balance['total'][currency] > 0:  # 只包含有余额的资产
                    result['total'][currency] = balance['total'][currency]
                    result['free'][currency] = balance['free'][currency]
                    result['used'][currency] = balance['used'][currency]
            
            return result
        except Exception as e:
            logger.error(f"获取账户资产时出错: {e}")
            return {'error': str(e)}
    
    def get_ticker(self, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        获取行情信息
        
        Args:
            symbol: 交易对
            params: 额外参数
            
        Returns:
            行情信息字典
        """
        try:
            if params is None:
                params = {}
                
            ticker = self.exchange.fetch_ticker(symbol, params)
            
            return {
                'symbol': symbol,
                'bid': ticker.get('bid', 0),
                'ask': ticker.get('ask', 0),
                'last': ticker.get('last', 0),
                'high': ticker.get('high', 0),
                'low': ticker.get('low', 0),
                'volume': ticker.get('baseVolume', 0),
                'timestamp': ticker.get('timestamp', 0),
                'datetime': ticker.get('datetime', ''),
                'info': ticker.get('info', {})
            }
        except Exception as e:
            logger.error(f"获取行情信息时出错: {e}")
            return {'error': str(e)}
    
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
        try:
            if params is None:
                params = {}
                
            orderbook = self.exchange.fetch_order_book(symbol, limit, params)
            
            return {
                'symbol': symbol,
                'bids': orderbook.get('bids', []),
                'asks': orderbook.get('asks', []),
                'timestamp': orderbook.get('timestamp', 0),
                'datetime': orderbook.get('datetime', ''),
                'nonce': orderbook.get('nonce', None),
                'info': orderbook.get('info', {})
            }
        except Exception as e:
            logger.error(f"获取订单簿时出错: {e}")
            return {'error': str(e)}
    
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
        try:
            if params is None:
                params = {}
                
            trades = self.exchange.fetch_trades(symbol, since, limit, params)
            
            result = []
            for trade in trades:
                result.append({
                    'id': trade.get('id', ''),
                    'symbol': symbol,
                    'side': trade.get('side', ''),
                    'amount': trade.get('amount', 0),
                    'price': trade.get('price', 0),
                    'timestamp': trade.get('timestamp', 0),
                    'datetime': trade.get('datetime', ''),
                    'info': trade.get('info', {})
                })
            
            return result
        except Exception as e:
            logger.error(f"获取成交记录时出错: {e}")
            return [{'error': str(e)}]
    
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
        try:
            if params is None:
                params = {}
                
            return self.exchange.fetch_ohlcv(symbol, timeframe, since, limit, params)
        except Exception as e:
            logger.error(f"获取K线数据时出错: {e}")
            return []
    
    def get_markets(self, params: Optional[Dict] = None) -> Dict:
        """
        获取所有交易对信息
        
        Args:
            params: 额外参数
            
        Returns:
            交易对信息字典
        """
        try:
            if params is None:
                params = {}
                
            return self.markets
        except Exception as e:
            logger.error(f"获取交易对信息时出错: {e}")
            return {}
    
    def get_position(self, symbol: str = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取持仓信息
        
        Args:
            symbol: 交易对，如果为None则获取所有持仓
            params: 额外参数
            
        Returns:
            持仓信息列表
        """
        try:
            if params is None:
                params = {}
                
            positions = self.exchange.fetch_positions(symbol, params)
            
            result = []
            for position in positions:
                if float(position.get('contracts', 0)) != 0:  # 只返回有持仓的
                    result.append({
                        'symbol': position.get('symbol', ''),
                        'side': position.get('side', ''),
                        'contracts': position.get('contracts', 0),
                        'size': position.get('size', 0),
                        'entryPrice': position.get('entryPrice', 0),
                        'markPrice': position.get('markPrice', 0),
                        'unrealizedPnl': position.get('unrealizedPnl', 0),
                        'percentage': position.get('percentage', 0),
                        'info': position.get('info', {})
                    })
            
            return result
        except Exception as e:
            logger.error(f"获取持仓信息时出错: {e}")
            return [{'error': str(e)}]
    
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
        try:
            if params is None:
                params = {}
                
            result = self.exchange.set_leverage(leverage, symbol, params)
            return {'success': True, 'leverage': leverage, 'symbol': symbol, 'info': result}
        except Exception as e:
            logger.error(f"设置杠杆倍数时出错: {e}")
            return {'error': str(e)}
    
    def close_position(self, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        平仓
        
        Args:
            symbol: 交易对
            params: 额外参数
            
        Returns:
            平仓结果
        """
        try:
            if params is None:
                params = {}
                
            # 获取当前持仓
            positions = self.get_position(symbol)
            if not positions:
                return {'error': f'没有{symbol}的持仓'}
            
            position = positions[0]
            side = position['side']
            contracts = float(position['contracts'])
            
            # 创建平仓订单
            if side == 'long':
                result = self.create_market_order(symbol, 'sell', contracts, params)
            else:  # short
                result = self.create_market_order(symbol, 'buy', contracts, params)
            
            return result
        except Exception as e:
            logger.error(f"平仓时出错: {e}")
            return {'error': str(e)}
    
    def _format_order(self, order: Dict) -> Dict:
        """
        格式化订单信息
        
        Args:
            order: 原始订单信息
            
        Returns:
            格式化后的订单信息
        """
        return {
            'id': order.get('id', ''),
            'symbol': order.get('symbol', ''),
            'side': order.get('side', ''),
            'type': order.get('type', ''),
            'amount': order.get('amount', 0),
            'price': order.get('price', 0),
            'filled': order.get('filled', 0),
            'remaining': order.get('remaining', 0),
            'status': order.get('status', ''),
            'timestamp': order.get('timestamp', 0),
            'datetime': order.get('datetime', ''),
            'fee': order.get('fee', {}),
            'info': order.get('info', {})
        }