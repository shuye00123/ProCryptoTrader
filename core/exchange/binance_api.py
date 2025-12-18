import ccxt
import asyncio
import websockets
import json
import time
import hmac
import hashlib
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

        # WebSocket相关配置
        self.ws_connection = None
        self.ws_url = self._get_ws_url()
        self.ws_listen_key = None
        self.is_connected = False
        self.pending_orders = {}  # 待确认的订单
    
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

    def _get_ws_url(self) -> str:
        """获取WebSocket URL"""
        if self.sandbox:
            return "wss://stream.binancefuture.com/ws"
        else:
            return "wss://fstream.binance.com/ws"

    def _generate_signature(self, params: Dict) -> str:
        """生成签名"""
        if not self.api_secret:
            return ""

        # 创建查询字符串
        query_string = '&'.join([f"{key}={value}" for key, value in sorted(params.items())])

        # 生成HMAC签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    async def connect_websocket(self) -> bool:
        """连接WebSocket"""
        try:
            # 1. 获取listen key
            listen_key_result = self._create_listen_key()
            if not listen_key_result or 'listenKey' not in listen_key_result:
                logger.error("获取listen key失败")
                return False

            self.ws_listen_key = listen_key_result['listenKey']

            # 2. 建立WebSocket连接
            ws_url = f"{self.ws_url}/{self.ws_listen_key}"
            self.ws_connection = await websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10
            )

            # 3. 启动消息处理
            asyncio.create_task(self._handle_ws_messages())

            self.is_connected = True
            logger.info("WebSocket连接成功")
            return True

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    def _create_listen_key(self) -> Optional[Dict]:
        """创建listen key"""
        try:
            if not self.api_key:
                return None

            url = f"{self.exchange.urls['api']}/v1/listenKey"
            headers = {
                'X-MBX-APIKEY': self.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            # 发送请求
            import requests
            response = requests.post(url, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"创建listen key失败: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"创建listen key异常: {e}")
            return None

    async def _handle_ws_messages(self):
        """处理WebSocket消息"""
        try:
            async for message in self.ws_connection:
                data = json.loads(message)
                await self._process_ws_message(data)
        except Exception as e:
            logger.error(f"处理WebSocket消息异常: {e}")
            self.is_connected = False

    async def _process_ws_message(self, data: Dict):
        """处理WebSocket消息"""
        try:
            if 'e' in data:
                event_type = data['e']

                if event_type == 'ORDER_TRADE_UPDATE':
                    await self._handle_order_update(data)
                elif event_type == 'ACCOUNT_UPDATE':
                    await self._handle_account_update(data)
                elif event_type == 'error':
                    logger.error(f"WebSocket错误: {data}")

        except Exception as e:
            logger.error(f"处理WebSocket消息失败: {e}")

    async def _handle_order_update(self, data: Dict):
        """处理订单更新"""
        try:
            order_data = data.get('o', {})
            order_id = order_data.get('i')
            client_order_id = order_data.get('c')
            symbol = order_data.get('s')
            status = order_data.get('X')

            # 查找待确认的订单
            if client_order_id in self.pending_orders:
                order_request = self.pending_orders[client_order_id]
                order_request['exchange_order_id'] = order_id
                order_request['status'] = self._convert_ws_status(status)
                order_request['filled_amount'] = float(order_data.get('z', 0))
                order_request['cumulative_quote'] = float(order_data.get('Z', 0))

                logger.debug(f"订单更新: {client_order_id} - {status}")

        except Exception as e:
            logger.error(f"处理订单更新失败: {e}")

    async def _handle_account_update(self, data: Dict):
        """处理账户更新"""
        # 处理账户余额更新等
        pass

    def _convert_ws_status(self, ws_status: str) -> str:
        """转换WebSocket状态"""
        status_mapping = {
            'NEW': 'open',
            'PARTIALLY_FILLED': 'partially_filled',
            'FILLED': 'closed',
            'CANCELED': 'canceled',
            'REJECTED': 'rejected',
            'EXPIRED': 'expired'
        }
        return status_mapping.get(ws_status, 'unknown')

    async def place_order_websocket(self, order_params: Dict) -> Dict:
        """通过WebSocket下单"""
        try:
            if not self.is_connected:
                logger.warning("WebSocket未连接，使用REST API下单")
                return await self._fallback_to_rest(order_params)

            # 生成客户端订单ID
            client_order_id = f"ws_{int(time.time() * 1000)}_{order_params.get('symbol', 'unknown')}"

            # 构建下单参数
            params = {
                'symbol': order_params.get('symbol'),
                'side': order_params.get('side'),
                'type': order_params.get('type', 'MARKET'),
                'quantity': order_params.get('quantity'),
                'newClientOrderId': client_order_id
            }

            if order_params.get('type') == 'LIMIT':
                params['price'] = order_params.get('price')
                params['timeInForce'] = 'GTC'

            # 添加到待确认订单
            self.pending_orders[client_order_id] = {
                'client_order_id': client_order_id,
                'symbol': order_params.get('symbol'),
                'side': order_params.get('side'),
                'amount': order_params.get('quantity'),
                'price': order_params.get('price', 0),
                'status': 'submitted',
                'exchange_order_id': None,
                'filled_amount': 0,
                'timestamp': time.time()
            }

            # 发送下单请求
            order_request = {
                'id': int(time.time() * 1000),
                'method': 'order.place',
                'params': params
            }

            await self.ws_connection.send(json.dumps(order_request))

            # 等待订单确认（最多等待5秒）
            return await self._wait_for_order_confirmation(client_order_id, timeout=5)

        except Exception as e:
            logger.error(f"WebSocket下单失败: {e}")
            return await self._fallback_to_rest(order_params)

    async def _wait_for_order_confirmation(self, client_order_id: str, timeout: int = 5) -> Dict:
        """等待订单确认"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if client_order_id in self.pending_orders:
                order_request = self.pending_orders[client_order_id]

                if order_request['exchange_order_id'] and order_request['status'] != 'submitted':
                    return {
                        'success': True,
                        'orderId': order_request['exchange_order_id'],
                        'clientOrderId': client_order_id,
                        'status': order_request['status'],
                        'symbol': order_request['symbol'],
                        'side': order_request['side'],
                        'type': 'MARKET' if order_request['price'] == 0 else 'LIMIT',
                        'origQty': order_request['amount'],
                        'executedQty': str(order_request['filled_amount']),
                        'cummulativeQuoteQty': str(order_request.get('cumulative_quote', 0))
                    }

            await asyncio.sleep(0.1)  # 100ms

        # 超时
        self.pending_orders.pop(client_order_id, None)
        return {
            'success': False,
            'error': f'Order confirmation timeout after {timeout} seconds'
        }

    async def _fallback_to_rest(self, order_params: Dict) -> Dict:
        """回退到REST API"""
        try:
            logger.info("回退到REST API下单")

            if order_params.get('price'):
                # 限价单
                result = self.create_limit_order(
                    order_params.get('symbol'),
                    order_params.get('side'),
                    order_params.get('quantity'),
                    order_params.get('price')
                )
            else:
                # 市价单
                result = self.create_market_order(
                    order_params.get('symbol'),
                    order_params.get('side'),
                    order_params.get('quantity')
                )

            if 'error' not in result:
                return {
                    'success': True,
                    'orderId': result.get('id'),
                    'status': result.get('status', 'unknown'),
                    **result
                }
            else:
                return {
                    'success': False,
                    'error': result['error']
                }

        except Exception as e:
            logger.error(f"REST API下单也失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def disconnect_websocket(self):
        """断开WebSocket连接"""
        try:
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None

            if self.ws_listen_key:
                # 删除listen key
                await self._delete_listen_key()
                self.ws_listen_key = None

            self.is_connected = False
            logger.info("WebSocket连接已断开")

        except Exception as e:
            logger.error(f"断开WebSocket连接失败: {e}")

    async def _delete_listen_key(self):
        """删除listen key"""
        try:
            if not self.api_key or not self.ws_listen_key:
                return

            url = f"{self.exchange.urls['api']}/v1/listenKey"
            headers = {
                'X-MBX-APIKEY': self.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = f"listenKey={self.ws_listen_key}"

            import requests
            response = requests.delete(url, headers=headers, data=data, timeout=10)

            if response.status_code == 200:
                logger.info("listen key已删除")
            else:
                logger.warning(f"删除listen key失败: {response.status_code}")

        except Exception as e:
            logger.error(f"删除listen key异常: {e}")

    def get_ws_status(self) -> Dict:
        """获取WebSocket状态"""
        return {
            'is_connected': self.is_connected,
            'listen_key': self.ws_listen_key,
            'pending_orders_count': len(self.pending_orders),
            'connection_url': self.ws_url
        }