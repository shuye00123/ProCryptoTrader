"""
Binance交易接口 - 基于python-binance SDK实现

## 核心功能
- 使用python-binance的AsyncClient进行异步REST API调用
- 使用BinanceSocketManager进行用户数据流WebSocket连接
- 保持与ccxt的兼容性（作为备用）
- 提供同步和异步两种API调用方式
"""

import ccxt
import asyncio
import json
import time
from typing import Dict, List, Optional, Union
from datetime import datetime

from .base_exchange import BaseExchange
import logging

# python-binance SDK
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)


class BinanceAPI(BaseExchange):
    """
    Binance交易接口实现 - 基于python-binance SDK

    提供功能：
    - REST API：订单管理、账户查询、市场数据
    - WebSocket：用户数据流（订单更新、账户更新）
    - 同步和异步双模式支持
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

        # python-binance AsyncClient（异步操作）
        self._async_client: Optional[AsyncClient] = None
        self._async_client_initialized = False
        self._bm: Optional[BinanceSocketManager] = None  # BinanceSocketManager
        self._user_socket = None  # 用户数据流socket

        # 保留ccxt作为备用（同步操作和其他交易所兼容）
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
        try:
            self.markets = self.exchange.load_markets()
        except Exception as e:
            logger.warning(f"加载市场信息失败: {e}")
            self.markets = {}

        # WebSocket相关配置（用户数据流）
        self.ws_listen_key = None
        self.is_connected = False
        self.pending_orders = {}  # 待确认的订单

    # ============================================================================
    # AsyncClient 管理
    # ============================================================================

    async def _get_async_client(self) -> AsyncClient:
        """Lazy初始化AsyncClient"""
        if not self._async_client_initialized:
            self._async_client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.sandbox
            )
            self._async_client_initialized = True
        return self._async_client

    async def close_async_client(self):
        """关闭AsyncClient连接"""
        if self._async_client:
            await self._async_client.close_connection()
            self._async_client = None
            self._async_client_initialized = False

    # ============================================================================
    # 订单管理 - 保持原有同步接口（兼容ccxt）
    # ============================================================================

    def create_market_order(self, symbol: str, side: str, amount: float,
                           params: Optional[Dict] = None) -> Dict:
        """
        创建市价单（同步版本，使用ccxt）

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
        创建限价单（同步版本，使用ccxt）

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
        撤销订单（同步版本，使用ccxt）

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
        获取订单信息（同步版本，使用ccxt）

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
        获取未成交订单（同步版本，使用ccxt）

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

    # ============================================================================
    # 订单管理 - 异步版本（使用python-binance）
    # ============================================================================

    async def create_market_order_async(self, symbol: str, side: str, amount: float,
                                       params: Optional[Dict] = None) -> Dict:
        """
        创建市价单（异步版本，使用python-binance）

        Args:
            symbol: 交易对（格式：BTC/USDT 或 BTCUSDT）
            side: 买卖方向，'buy' 或 'sell'
            amount: 数量
            params: 额外参数

        Returns:
            订单信息字典
        """
        try:
            client = await self._get_async_client()

            # 参数转换
            binance_side = 'BUY' if side.upper() == 'BUY' else 'SELL'
            # 统一symbol格式（移除斜杠）
            binance_symbol = symbol.replace('/', '').upper()

            # 调用python-binance
            result = await client.new_order(
                symbol=binance_symbol,
                side=binance_side,
                type='MARKET',
                quantity=amount
            )

            # 格式化为统一格式
            return self._format_binance_order(result, symbol)

        except BinanceAPIException as e:
            logger.error(f"创建市价单时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"创建市价单异常: {e}")
            return {'error': str(e)}

    async def create_limit_order_async(self, symbol: str, side: str, amount: float,
                                      price: float, params: Optional[Dict] = None) -> Dict:
        """
        创建限价单（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            price: 价格
            params: 额外参数

        Returns:
            订单信息字典
        """
        try:
            client = await self._get_async_client()

            # 参数转换
            binance_side = 'BUY' if side.upper() == 'BUY' else 'SELL'
            binance_symbol = symbol.replace('/', '').upper()

            # 调用python-binance
            result = await client.new_order(
                symbol=binance_symbol,
                side=binance_side,
                type='LIMIT',
                quantity=amount,
                price=price,
                timeInForce='GTC'  # 成交为止
            )

            return self._format_binance_order(result, symbol)

        except BinanceAPIException as e:
            logger.error(f"创建限价单时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"创建限价单异常: {e}")
            return {'error': str(e)}

    async def cancel_order_async(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        撤销订单（异步版本，使用python-binance）

        Args:
            order_id: 订单ID
            symbol: 交易对
            params: 额外参数

        Returns:
            撤单结果
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            result = await client.cancel_order(
                symbol=binance_symbol,
                orderId=order_id
            )

            return {
                'success': True,
                'orderId': result.get('orderId'),
                'symbol': symbol,
                'status': self._convert_binance_status(result.get('status')),
                'info': result
            }

        except BinanceAPIException as e:
            logger.error(f"撤销订单时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"撤销订单异常: {e}")
            return {'error': str(e)}

    async def get_order_async(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        获取订单信息（异步版本，使用python-binance）

        Args:
            order_id: 订单ID
            symbol: 交易对
            params: 额外参数

        Returns:
            订单信息字典
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            result = await client.get_order(
                symbol=binance_symbol,
                orderId=order_id
            )

            return self._format_binance_order(result, symbol)

        except BinanceAPIException as e:
            logger.error(f"获取订单信息时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"获取订单信息异常: {e}")
            return {'error': str(e)}

    async def get_open_orders_async(self, symbol: str = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取未成交订单（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            params: 额外参数

        Returns:
            未成交订单列表
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper() if symbol else None

            result = await client.get_open_orders(symbol=binance_symbol)

            return [self._format_binance_order(order, symbol or order.get('symbol'))
                    for order in result]

        except BinanceAPIException as e:
            logger.error(f"获取未成交订单时出错: {e}")
            return [{'error': str(e)}]
        except Exception as e:
            logger.error(f"获取未成交订单异常: {e}")
            return [{'error': str(e)}]

    # ============================================================================
    # 账户和市场数据
    # ============================================================================

    def get_balance(self, params: Optional[Dict] = None) -> Dict:
        """
        获取账户资产（同步版本）

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

    async def get_balance_async(self, params: Optional[Dict] = None) -> Dict:
        """
        获取账户资产（异步版本，使用python-binance）

        Args:
            params: 额外参数

        Returns:
            账户资产信息
        """
        try:
            client = await self._get_async_client()

            account = await client.get_account()

            # 格式化余额信息
            result = {
                'info': account,
                'total': {},
                'free': {},
                'used': {}
            }

            for balance in account.get('balances', []):
                asset = balance['asset']
                free = float(balance['free'])
                locked = float(balance['locked'])
                total = free + locked

                if total > 0:  # 只包含有余额的资产
                    result['total'][asset] = total
                    result['free'][asset] = free
                    result['used'][asset] = locked

            return result

        except BinanceAPIException as e:
            logger.error(f"获取账户资产时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"获取账户资产异常: {e}")
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

    async def get_ticker_async(self, symbol: str, params: Optional[Dict] = None) -> Dict:
        """
        获取行情信息（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            params: 额外参数

        Returns:
            行情信息字典
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            result = await client.get_symbol_ticker(symbol=binance_symbol)

            # 格式化为统一格式
            return {
                'symbol': symbol,
                'bid': float(result.get('bidPrice', 0)),
                'ask': float(result.get('askPrice', 0)),
                'last': float(result.get('lastPrice', 0)),
                'high': float(result.get('highPrice', 0)),
                'low': float(result.get('lowPrice', 0)),
                'volume': float(result.get('volume', 0)),
                'quoteVolume': float(result.get('quoteVolume', 0)),
                'priceChange': float(result.get('priceChange', 0)),
                'priceChangePercent': float(result.get('priceChangePercent', 0)),
                'timestamp': result.get('closeTime', 0),
                'datetime': datetime.fromtimestamp(result.get('closeTime', 0) / 1000).isoformat() if result.get('closeTime') else '',
                'info': result
            }

        except BinanceAPIException as e:
            logger.error(f"获取行情信息时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"获取行情信息异常: {e}")
            return {'error': str(e)}

    def get_trades(self, symbol: str, since: Optional[int] = None,
                  limit: Optional[int] = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取最近成交记录（同步版本，使用ccxt）

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

            return [{
                'id': trade.get('id', ''),
                'symbol': trade.get('symbol', ''),
                'side': trade.get('side', ''),
                'amount': trade.get('amount', 0),
                'price': trade.get('price', 0),
                'timestamp': trade.get('timestamp', 0),
                'datetime': trade.get('datetime', ''),
                'fee': trade.get('fee', {}),
                'info': trade.get('info', {})
            } for trade in trades]
        except Exception as e:
            logger.error(f"获取成交记录时出错: {e}")
            return [{'error': str(e)}]

    async def get_trades_async(self, symbol: str, since: Optional[int] = None,
                              limit: Optional[int] = None, params: Optional[Dict] = None) -> List[Dict]:
        """
        获取最近成交记录（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            since: 开始时间戳（毫秒）
            limit: 限制数量
            params: 额外参数

        Returns:
            成交记录列表
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            result = await client.get_recent_trades(symbol=binance_symbol, limit=limit)

            return [{
                'id': str(trade.get('id', '')),
                'symbol': symbol,
                'side': 'buy' if trade.get('isBuyerMaker', False) else 'sell',
                'amount': float(trade.get('qty', 0)),
                'price': float(trade.get('price', 0)),
                'timestamp': trade.get('time', 0),
                'datetime': datetime.fromtimestamp(trade.get('time', 0) / 1000).isoformat() if trade.get('time') else '',
                'info': trade
            } for trade in result]

        except BinanceAPIException as e:
            logger.error(f"获取成交记录时出错: {e}")
            return [{'error': str(e)}]
        except Exception as e:
            logger.error(f"获取成交记录异常: {e}")
            return [{'error': str(e)}]

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

    async def get_orderbook_async(self, symbol: str, limit: int = None, params: Optional[Dict] = None) -> Dict:
        """
        获取订单簿（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            limit: 订单簿深度
            params: 额外参数

        Returns:
            订单簿信息
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            # limit参数转换
            limit_map = {5: 5, 10: 10, 20: 20}
            binance_limit = limit_map.get(limit, 20) if limit else None

            result = await client.get_order_book(symbol=binance_symbol, limit=binance_limit)

            # 格式化订单簿
            bids = [[float(bid[0]), float(bid[1])] for bid in result.get('bids', [])]
            asks = [[float(ask[0]), float(ask[1])] for ask in result.get('asks', [])]

            return {
                'symbol': symbol,
                'bids': bids,
                'asks': asks,
                'timestamp': result.get('lastUpdateId', 0),
                'datetime': datetime.fromtimestamp(result.get('lastUpdateId', 0) / 1000).isoformat() if result.get('lastUpdateId') else '',
                'info': result
            }

        except BinanceAPIException as e:
            logger.error(f"获取订单簿时出错: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"获取订单簿异常: {e}")
            return {'error': str(e)}

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

    async def get_ohlcv_async(self, symbol: str, timeframe: str = '1h', since: Optional[int] = None,
                            limit: Optional[int] = None, params: Optional[Dict] = None) -> List[List]:
        """
        获取K线数据（异步版本，使用python-binance）

        Args:
            symbol: 交易对
            timeframe: 时间框架
            since: 开始时间戳
            limit: 限制数量
            params: 额外参数

        Returns:
            K线数据列表
        """
        try:
            client = await self._get_async_client()

            binance_symbol = symbol.replace('/', '').upper()

            # 时间框架映射
            interval_map = {
                '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
                '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M'
            }
            interval = interval_map.get(timeframe, '1h')

            result = await client.get_klines(
                symbol=binance_symbol,
                interval=interval,
                startTime=since,
                limit=limit
            )

            # python-binance返回格式：[time, open, high, low, close, volume, ...]
            return result

        except BinanceAPIException as e:
            logger.error(f"获取K线数据时出错: {e}")
            return []
        except Exception as e:
            logger.error(f"获取K线数据异常: {e}")
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

    # ============================================================================
    # WebSocket 用户数据流（使用python-binance BinanceSocketManager）
    # ============================================================================

    async def connect_websocket(self) -> bool:
        """
        连接用户数据流WebSocket（使用python-binance）

        Returns:
            连接成功返回True
        """
        try:
            client = await self._get_async_client()

            # 创建listen key
            listen_key_response = await client.stream_get_listen_key()
            self.ws_listen_key = listen_key_response['listenKey']
            logger.info(f"获取listen key成功: {self.ws_listen_key[:20]}...")

            # 创建BinanceSocketManager
            self._bm = BinanceSocketManager(client)

            # 获取user socket（包含订单更新和账户更新）
            self._user_socket = self._bm.user_socket()

            # 启动消息处理
            asyncio.create_task(self._handle_user_socket_messages())

            self.is_connected = True
            logger.info("用户数据流WebSocket连接成功 (python-binance)")
            return True

        except BinanceAPIException as e:
            logger.error(f"创建listen key失败: {e}")
            return False
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    async def _handle_user_socket_messages(self):
        """处理用户Socket消息"""
        try:
            async with self._user_socket as uscm:
                while self.is_connected:
                    message = await uscm.recv()
                    await self._process_user_message(message)

        except Exception as e:
            logger.error(f"处理用户Socket消息异常: {e}")
            self.is_connected = False

    async def _process_user_message(self, message: Dict):
        """处理用户数据流消息"""
        try:
            event_type = message.get('e', '')

            if event_type == 'ORDER_TRADE_UPDATE':
                await self._handle_order_update(message)
            elif event_type == 'ACCOUNT_UPDATE':
                await self._handle_account_update(message)
            elif event_type == 'error':
                logger.error(f"用户数据流错误: {message}")

        except Exception as e:
            logger.error(f"处理用户消息失败: {e}")

    async def _handle_order_update(self, data: Dict):
        """处理订单更新"""
        try:
            order_data = data.get('o', {})
            order_id = order_data.get('i')
            client_order_id = order_data.get('c')
            status = order_data.get('X')

            # 查找待确认的订单
            if client_order_id in self.pending_orders:
                order_request = self.pending_orders[client_order_id]
                order_request['exchange_order_id'] = order_id
                order_request['status'] = self._convert_binance_status(status)
                order_request['filled_amount'] = float(order_data.get('z', 0))

                logger.debug(f"订单更新: {client_order_id} - {status}")

        except Exception as e:
            logger.error(f"处理订单更新失败: {e}")

    async def _handle_account_update(self, data: Dict):
        """处理账户更新"""
        try:
            # 可以更新余额等信息
            logger.debug(f"账户更新: {data}")
        except Exception as e:
            logger.error(f"处理账户更新失败: {e}")

    async def disconnect_websocket(self):
        """断开WebSocket连接"""
        try:
            self.is_connected = False

            # 退出socket上下文
            if self._user_socket:
                try:
                    await self._user_socket.__aexit__(None, None, None)
                except Exception:
                    pass
                self._user_socket = None

            # 删除listen key
            if self.ws_listen_key:
                await self._delete_listen_key_async()
                self.ws_listen_key = None

            logger.info("用户数据流WebSocket已断开")

        except Exception as e:
            logger.error(f"断开WebSocket连接失败: {e}")

    async def _delete_listen_key_async(self):
        """删除listen key（异步版本）"""
        try:
            client = await self._get_async_client()

            await client.stream_close_listen_key(listenKey=self.ws_listen_key)
            logger.info("listen key已删除")

        except BinanceAPIException as e:
            logger.warning(f"删除listen key失败: {e}")
        except Exception as e:
            logger.error(f"删除listen key异常: {e}")

    # ============================================================================
    # 工具方法
    # ============================================================================

    def _format_order(self, order: Dict) -> Dict:
        """格式化订单信息（ccxt格式）"""
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

    def _format_binance_order(self, binance_order: Dict, symbol: str) -> Dict:
        """
        格式化python-binance订单响应为标准格式

        Args:
            binance_order: python-binance返回的订单
            symbol: 交易对

        Returns:
            格式化后的订单信息
        """
        return {
            'id': str(binance_order.get('orderId', '')),
            'symbol': symbol,
            'side': 'buy' if binance_order.get('side') == 'BUY' else 'sell',
            'type': 'market' if binance_order.get('type') == 'MARKET' else 'limit',
            'amount': float(binance_order.get('origQty', 0)),
            'price': float(binance_order.get('price', 0)) if binance_order.get('price') else 0,
            'filled': float(binance_order.get('executedQty', 0)),
            'remaining': float(binance_order.get('origQty', 0)) - float(binance_order.get('executedQty', 0)),
            'status': self._convert_binance_status(binance_order.get('status')),
            'timestamp': binance_order.get('transactTime', 0),
            'datetime': datetime.fromtimestamp(binance_order.get('transactTime', 0) / 1000).isoformat() if binance_order.get('transactTime') else '',
            'info': binance_order
        }

    def _convert_binance_status(self, status: Optional[str]) -> str:
        """转换Binance状态到标准状态"""
        if not status:
            return 'unknown'

        status_mapping = {
            'NEW': 'open',
            'PARTIALLY_FILLED': 'partially_filled',
            'FILLED': 'closed',
            'CANCELED': 'canceled',
            'REJECTED': 'rejected',
            'EXPIRED': 'expired',
            'PENDING_CANCEL': 'open'
        }
        return status_mapping.get(status, 'unknown')

    def format_price(self, symbol: str, price: float) -> float:
        """格式化价格到交易所精度"""
        try:
            if symbol in self.markets:
                market = self.markets[symbol]
                precision = market.get('precision', {})
                price_precision = precision.get('price', 8)
                return round(price, price_precision)
            return price
        except Exception:
            return price

    def format_amount(self, symbol: str, amount: float) -> float:
        """格式化数量到交易所精度"""
        try:
            if symbol in self.markets:
                market = self.markets[symbol]
                precision = market.get('precision', {})
                amount_precision = precision.get('amount', 8)
                return round(amount, amount_precision)
            return amount
        except Exception:
            return amount

    def get_ws_status(self) -> Dict:
        """获取WebSocket状态"""
        return {
            'is_connected': self.is_connected,
            'listen_key': self.ws_listen_key,
            'pending_orders_count': len(self.pending_orders)
        }
