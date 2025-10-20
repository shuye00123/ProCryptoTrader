"""
实盘交易模块

提供量化交易策略的实盘运行功能，支持多策略、多币种并行执行，包含实时交易执行、风险控制、状态监控等。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import time
import json
import threading
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np
from queue import Queue, Empty

from ..data.data_manager import DataManager
from ..exchange.base_exchange import BaseExchange
from ..strategy.base_strategy import BaseStrategy
from ..utils.logger import Logger
from ..utils.risk_control import RiskManager
from .config_loader import LiveConfig, ConfigLoader


class TradingState(Enum):
    """交易状态枚举"""
    STOPPED = "stopped"      # 已停止
    STARTING = "starting"    # 启动中
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 暂停中
    STOPPING = "stopping"    # 停止中
    ERROR = "error"          # 错误状态


@dataclass
class StrategyInstance:
    """策略实例信息"""
    name: str
    strategy: BaseStrategy
    exchange: BaseExchange
    symbols: List[str]
    timeframe: str
    risk_manager: RiskManager
    thread: Optional[threading.Thread] = None
    data_manager: Optional[DataManager] = None
    stats: Dict[str, Any] = field(default_factory=dict)


class LiveTrader:
    """实盘交易主控制器，支持多策略多币种并行执行"""
    
    def __init__(self, config_path: str):
        """
        初始化实盘交易控制器
        
        Args:
            config_path: 配置文件路径
        """
        # 初始化日志
        self.logger = Logger.get_logger("LiveTrader")
        
        # 加载配置
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.load_config(config_path)
        
        # 系统状态
        self.state = TradingState.STOPPED
        self.start_time = None
        self.stop_time = None
        
        # 组件管理
        self.exchanges: Dict[str, BaseExchange] = {}
        self.strategy_instances: List[StrategyInstance] = []
        
        # 线程控制
        self._running = False
        self._threads = []
        self._stop_event = threading.Event()
        
        # 全局风控
        self.global_risk_manager = RiskManager(**self.config.risk_control)
        
        # 全局统计
        self.global_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'current_drawdown': 0.0,
            'daily_pnl': 0.0,
            'last_trade_time': None,
            'active_strategies': 0,
            'active_symbols': set()
        }
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("实盘交易控制器初始化完成")
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        self.logger.info(f"接收到信号 {signum}，准备停止交易...")
        self.stop()
    
    def initialize(self) -> bool:
        """
        初始化实盘交易环境，加载所有交易所和策略
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.state = TradingState.STARTING
            self.logger.info("开始初始化实盘交易环境...")
            
            # 初始化所有交易所
            if not self._init_exchanges():
                self.logger.error("初始化交易所失败")
                self.state = TradingState.ERROR
                return False
            
            # 初始化所有策略
            if not self._init_strategies():
                self.logger.error("初始化策略失败")
                self.state = TradingState.ERROR
                return False
            
            # 初始化数据管理器
            self._init_data_managers()
            
            # 加载历史数据
            if not self._load_historical_data():
                self.logger.error("加载历史数据失败")
                self.state = TradingState.ERROR
                return False
            
            self.logger.info("实盘交易环境初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化实盘交易环境失败: {e}")
            self.state = TradingState.ERROR
            return False
    
    def _init_exchanges(self) -> bool:
        """初始化所有交易所"""
        try:
            for exchange_config in self.config.exchanges:
                try:
                    exchange = self.config_loader.create_exchange(exchange_config)
                    self.exchanges[exchange_config.name] = exchange
                    
                    # 验证交易所连接
                    if not self._validate_exchange(exchange, exchange_config.name):
                        return False
                    
                except Exception as e:
                    self.logger.error(f"初始化交易所 {exchange_config.name} 失败: {e}")
                    return False
            
            self.logger.info(f"成功初始化 {len(self.exchanges)} 个交易所连接")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化交易所失败: {e}")
            return False
    
    def _validate_exchange(self, exchange: BaseExchange, exchange_name: str) -> bool:
        """验证交易所连接和账户状态"""
        try:
            # 测试API连接
            if not exchange.test_connection():
                self.logger.error(f"交易所 {exchange_name} 连接测试失败")
                return False
            
            # 获取账户信息
            account_info = exchange.get_account_info()
            balance = account_info.get('total', {}).get('USDT', 0) or account_info.get('balance', 0)
            
            self.logger.info(f"交易所 {exchange_name} 验证通过，USDT余额: {balance}")
            return True
            
        except Exception as e:
            self.logger.error(f"验证交易所 {exchange_name} 失败: {e}")
            return False
    
    def _init_strategies(self) -> bool:
        """初始化所有策略"""
        try:
            for strategy_config in self.config.strategies:
                try:
                    # 创建策略实例
                    strategy = self.config_loader.create_strategy(strategy_config)
                    
                    # 获取交易所实例（默认使用第一个交易所）
                    exchange_name = next(iter(self.exchanges.keys()))
                    exchange = self.exchanges[exchange_name]
                    
                    # 创建风控管理器
                    risk_manager = RiskManager(**strategy_config.risk_params)
                    
                    # 初始化策略统计
                    stats = {
                        'name': strategy_config.name,
                        'symbols': strategy_config.symbols,
                        'timeframe': strategy_config.timeframe,
                        'total_trades': 0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'total_pnl': 0.0,
                        'max_drawdown': 0.0,
                        'current_drawdown': 0.0,
                        'daily_pnl': 0.0,
                        'last_trade_time': None,
                        'status': 'initialized'
                    }
                    
                    # 创建策略实例对象
                    strategy_instance = StrategyInstance(
                        name=strategy_config.name,
                        strategy=strategy,
                        exchange=exchange,
                        symbols=strategy_config.symbols,
                        timeframe=strategy_config.timeframe,
                        risk_manager=risk_manager,
                        stats=stats
                    )
                    
                    self.strategy_instances.append(strategy_instance)
                    
                    # 更新全局统计
                    for symbol in strategy_config.symbols:
                        self.global_stats['active_symbols'].add(symbol)
                    
                except Exception as e:
                    self.logger.error(f"初始化策略 {strategy_config.name} 失败: {e}")
                    return False
            
            self.global_stats['active_strategies'] = len(self.strategy_instances)
            self.logger.info(f"成功初始化 {len(self.strategy_instances)} 个策略")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化策略失败: {e}")
            return False
    
    def _init_data_managers(self):
        """初始化数据管理器"""
        for instance in self.strategy_instances:
            try:
                # 为每个策略创建一个数据管理器
                data_manager = DataManager(
                    exchange=instance.exchange,
                    symbols=instance.symbols,
                    timeframe=instance.timeframe
                )
                instance.data_manager = data_manager
                
            except Exception as e:
                self.logger.error(f"初始化策略 {instance.name} 的数据管理器失败: {e}")
        
        self.logger.info("数据管理器初始化完成")
    
    def _load_historical_data(self) -> bool:
        """加载所有策略的历史数据"""
        try:
            for instance in self.strategy_instances:
                try:
                    if not instance.data_manager:
                        self.logger.error(f"策略 {instance.name} 没有数据管理器")
                        continue
                    
                    # 获取最近1000根K线数据
                    end_time = datetime.now()
                    start_time = end_time - timedelta(days=100)  # 假设1小时K线，100天约2400根K线
                    
                    # 为每个交易对加载历史数据
                    for symbol in instance.symbols:
                        historical_data = instance.data_manager.get_historical_data(
                            symbol=symbol,
                            start_time=start_time,
                            end_time=end_time,
                            limit=1000
                        )
                        
                        if historical_data.empty:
                            self.logger.error(f"策略 {instance.name} 无法获取 {symbol} 的历史数据")
                            return False
                        
                        # 初始化策略数据
                        instance.strategy.on_data(symbol, historical_data)
                        self.logger.info(f"策略 {instance.name} 加载 {symbol} 历史数据完成，数据量: {len(historical_data)}")
                    
                except Exception as e:
                    self.logger.error(f"策略 {instance.name} 加载历史数据失败: {e}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"加载历史数据失败: {e}")
            return False
    
    def start(self) -> bool:
        """
        启动实盘交易，运行所有策略
        
        Returns:
            bool: 启动是否成功
        """
        if self.state != TradingState.STARTING:
            if not self.initialize():
                return False
        
        try:
            self.state = TradingState.RUNNING
            self.start_time = datetime.now()
            self._running = True
            self._stop_event.clear()
            
            # 启动每个策略的运行线程
            for instance in self.strategy_instances:
                try:
                    # 创建策略运行线程
                    thread = threading.Thread(
                        target=self._strategy_execution_worker,
                        args=(instance,)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    instance.thread = thread
                    instance.stats['status'] = 'running'
                    self._threads.append(thread)
                    
                    self.logger.info(f"策略 {instance.name} 线程启动成功")
                    
                except Exception as e:
                    self.logger.error(f"启动策略 {instance.name} 线程失败: {e}")
                    return False
            
            # 启动全局监控线程
            monitor_thread = threading.Thread(target=self._global_monitoring_loop)
            monitor_thread.daemon = True
            monitor_thread.start()
            self._threads.append(monitor_thread)
            
            # 启动心跳线程
            heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
            heartbeat_thread.daemon = True
            heartbeat_thread.start()
            self._threads.append(heartbeat_thread)
            
            self.logger.info(f"实盘交易启动成功，运行 {len(self.strategy_instances)} 个策略")
            return True
            
        except Exception as e:
            self.logger.error(f"启动实盘交易失败: {e}")
            self.state = TradingState.ERROR
            return False
    
    def stop(self):
        """
        停止实盘交易，安全关闭所有策略和线程
        """
        if self.state in [TradingState.RUNNING, TradingState.PAUSED]:
            self.state = TradingState.STOPPING
            self.logger.info("正在停止实盘交易...")
            
            # 设置停止事件
            self._stop_event.set()
            self._running = False
            
            # 取消所有未完成订单
            self._cancel_all_orders()
            
            # 等待所有线程结束
            for thread in self._threads:
                if thread.is_alive():
                    thread.join(timeout=10)
            
            # 更新策略状态
            for instance in self.strategy_instances:
                instance.stats['status'] = 'stopped'
            
            # 保存交易记录
            try:
                self._save_trading_records()
            except Exception as e:
                self.logger.error(f"保存交易记录失败: {e}")
            
            self.state = TradingState.STOPPED
            self.stop_time = datetime.now()
            self.logger.info("实盘交易已停止")
    
    def _strategy_execution_worker(self, instance: StrategyInstance):
        """
        单个策略的执行工作线程
        
        Args:
            instance: 策略实例
        """
        self.logger.info(f"策略 {instance.name} 执行线程启动")
        
        # 记录初始账户余额用于计算回撤
        try:
            initial_balance = instance.exchange.get_balance()
            peak_balance = initial_balance
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 获取初始余额失败: {e}")
            initial_balance = peak_balance = 0
        
        # 上次数据检查时间
        last_data_check = time.time() - self.config.data_check_interval
        
        while self._running and not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # 检查是否需要获取新数据
                if current_time - last_data_check >= self.config.data_check_interval:
                    self._update_strategy_data(instance)
                    last_data_check = current_time
                
                # 生成交易信号
                signals = self._generate_strategy_signals(instance)
                
                # 处理交易信号
                self._process_strategy_signals(instance, signals)
                
                # 检查订单状态
                self._check_strategy_orders(instance)
                
                # 更新统计信息
                self._update_strategy_stats(instance, initial_balance, peak_balance)
                
                # 检查全局风控
                if not self._check_global_risk():
                    self.logger.warning(f"策略 {instance.name} 检测到全局风险，暂停交易")
                    self._stop_event.wait(30)  # 暂停30秒再检查
                
                # 短暂休眠避免CPU占用过高
                self._stop_event.wait(0.5)
                
            except Exception as e:
                self.logger.error(f"策略 {instance.name} 执行异常: {e}")
                instance.stats['status'] = 'error'
                self._stop_event.wait(5)  # 异常时等待5秒再重试
        
        self.logger.info(f"策略 {instance.name} 执行线程停止")
    
    def _update_strategy_data(self, instance: StrategyInstance):
        """更新策略数据"""
        try:
            for symbol in instance.symbols:
                # 获取最新数据
                latest_data = instance.data_manager.get_latest_data(symbol=symbol)
                
                if not latest_data.empty:
                    # 更新策略数据
                    instance.strategy.on_data(symbol, latest_data)
                    self.logger.debug(f"策略 {instance.name} 更新 {symbol} 数据: {latest_data.index[-1]}")
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 更新数据失败: {e}")
            try:
                # 尝试重新初始化数据管理器
                if hasattr(instance, 'data_manager') and instance.data_manager:
                    instance.data_manager = self.config_loader.create_data_manager(
                        instance.exchange, symbol, instance.timeframe
                    )
                    self.logger.info(f"策略 {instance.name} 已重新初始化 {symbol} 数据管理器")
            except Exception as reinit_error:
                self.logger.error(f"策略 {instance.name} 重新初始化数据管理器失败: {reinit_error}")
    
    def _generate_strategy_signals(self, instance: StrategyInstance) -> List[Dict[str, Any]]:
        """生成策略交易信号"""
        try:
            signals = []
            for symbol in instance.symbols:
                # 为每个交易对生成信号
                symbol_signals = instance.strategy.generate_signals(symbol)
                signals.extend(symbol_signals)
            return signals
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 生成信号失败: {e}")
            return []
    
    def _process_strategy_signals(self, instance: StrategyInstance, signals: List[Dict[str, Any]]):
        """处理交易信号"""
        for signal in signals:
            try:
                # 验证信号完整性
                required_fields = ['symbol', 'side', 'quantity']
                if not all(field in signal for field in required_fields):
                    self.logger.warning(f"策略 {instance.name} 信号缺少必要字段: {signal}")
                    continue
                
                # 策略级别风控检查
                if not instance.risk_manager.check_signal(signal):
                    self.logger.warning(f"策略 {instance.name} 信号未通过风控: {signal}")
                    continue
                
                # 全局风控检查
                if not self.global_risk_manager.check_signal(signal):
                    self.logger.warning(f"策略 {instance.name} 信号未通过全局风控: {signal}")
                    continue
                
                # 执行交易
                order = self._execute_signal(instance, signal)
                
                if order and order.get('status') == 'filled':
                    self.logger.info(f"策略 {instance.name} 执行交易成功: {order}")
                    self._update_trade_stats(instance, order)
                elif order and order.get('status') == 'failed':
                    self.logger.error(f"策略 {instance.name} 执行交易失败: {order}")
                
            except Exception as e:
                self.logger.error(f"策略 {instance.name} 处理信号失败: {e}")
    
    def _execute_signal(self, instance: StrategyInstance, signal: Dict[str, Any]) -> Dict[str, Any]:
        """执行交易信号"""
        try:
            symbol = signal.get('symbol')
            side = signal.get('side')
            price = signal.get('price')
            quantity = signal.get('quantity')
            order_type = signal.get('type', 'limit')
            
            # 验证参数
            if not symbol or not side or not quantity:
                self.logger.error(f"策略 {instance.name} 信号参数不完整: symbol={symbol}, side={side}, quantity={quantity}")
                return {'status': 'failed', 'reason': '参数不完整'}
            
            # 检查交易对是否可用
            if symbol not in instance.symbols:
                self.logger.error(f"策略 {instance.name} 尝试交易未配置的交易对: {symbol}")
                return {'status': 'failed', 'reason': '交易对未配置'}
            
            # 执行下单
            if order_type == 'market':
                order = instance.exchange.place_market_order(symbol, side, quantity)
            else:
                order = instance.exchange.place_limit_order(symbol, side, price, quantity)
            
            return order
            
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 下单失败: {e}")
            return {'status': 'failed', 'reason': str(e)}
    
    def _check_strategy_orders(self, instance: StrategyInstance):
        """检查策略订单状态"""
        try:
            for symbol in instance.symbols:
                # 获取未完成订单
                try:
                    open_orders = instance.exchange.get_open_orders(symbol)
                except Exception as e:
                    self.logger.error(f"策略 {instance.name} 获取 {symbol} 未完成订单失败: {e}")
                    continue
                
                # 检查每个订单状态
                for order in open_orders:
                    try:
                        # 检查订单是否长时间未成交
                        order_time = datetime.fromtimestamp(order.get('timestamp', time.time()) / 1000)
                        time_diff = datetime.now() - order_time
                        
                        if time_diff.total_seconds() > 300:  # 5分钟未成交
                            self.logger.warning(f"策略 {instance.name} 订单 {order.get('id')} 长时间未成交，尝试取消")
                            try:
                                instance.exchange.cancel_order(symbol, order.get('id'))
                            except Exception as cancel_error:
                                self.logger.error(f"策略 {instance.name} 取消订单失败: {cancel_error}")
                    except Exception as order_error:
                        self.logger.error(f"策略 {instance.name} 处理订单 {order.get('id')} 失败: {order_error}")
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 检查订单状态失败: {e}")
    
    def _update_strategy_stats(self, instance: StrategyInstance, initial_balance: float, peak_balance: float):
        """更新策略统计信息"""
        try:
            # 获取当前余额
            try:
                current_balance = instance.exchange.get_balance()
            except Exception as e:
                self.logger.error(f"策略 {instance.name} 获取余额失败: {e}")
                return
            
            # 更新峰值余额
            if current_balance > peak_balance:
                peak_balance = current_balance
            
            # 计算回撤
            if initial_balance > 0:
                instance.stats['current_drawdown'] = (peak_balance - current_balance) / peak_balance
                instance.stats['max_drawdown'] = max(instance.stats['max_drawdown'], instance.stats['current_drawdown'])
                
                # 检查是否超过最大回撤限制
                max_drawdown_limit = self.config.risk_control.get('max_drawdown', 0.2)  # 默认20%
                if instance.stats['current_drawdown'] > max_drawdown_limit:
                    self.logger.warning(f"策略 {instance.name} 当前回撤 {instance.stats['current_drawdown']:.2%} 超过限制 {max_drawdown_limit:.2%}")
                    instance.stats['status'] = 'drawdown_limit'
        except Exception as e:
            self.logger.error(f"策略 {instance.name} 更新统计失败: {e}")
    
    def _update_trade_stats(self, instance: StrategyInstance, order: Dict[str, Any]):
        """更新交易统计"""
        try:
            # 更新策略统计
            instance.stats['total_trades'] += 1
            instance.stats['last_trade_time'] = datetime.now()
            
            # 如果是平仓订单，更新盈亏统计
            if order.get('side') == 'sell' or order.get('side') == 'close':
                pnl = order.get('pnl', 0)
                instance.stats['total_pnl'] += pnl
                instance.stats['daily_pnl'] += pnl
                
                if pnl > 0:
                    instance.stats['winning_trades'] += 1
                else:
                    instance.stats['losing_trades'] += 1
            
            # 更新全局统计
            self.global_stats['total_trades'] += 1
            self.global_stats['last_trade_time'] = datetime.now()
            
            if order.get('side') == 'sell' or order.get('side') == 'close':
                pnl = order.get('pnl', 0)
                self.global_stats['total_pnl'] += pnl
                self.global_stats['daily_pnl'] += pnl
                
                if pnl > 0:
                    self.global_stats['winning_trades'] += 1
                else:
                    self.global_stats['losing_trades'] += 1
        except Exception as e:
            self.logger.error(f"更新交易统计失败: {e}")
    
    def _global_monitoring_loop(self):
        """全局监控循环"""
        self.logger.info("全局监控线程启动")
        
        while self._running and not self._stop_event.is_set():
            try:
                # 更新全局性能统计
                self._update_global_performance_stats()
                
                # 检查是否触发风控断路器
                if not self._check_global_risk():
                    self.logger.warning("触发全局风控断路器，正在停止所有交易")
                    self.stop()
                    break
                
                # 记录系统状态
                self._log_system_status()
                
                # 等待下一次监控
                self._stop_event.wait(self.config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"全局监控异常: {e}")
                self._stop_event.wait(5)  # 异常时等待5秒再重试
        
        self.logger.info("全局监控线程停止")
    
    def _heartbeat_loop(self):
        """心跳发送循环"""
        self.logger.info("心跳线程启动")
        
        while self._running and not self._stop_event.is_set():
            try:
                # 发送心跳
                self._send_heartbeat()
                
                # 等待下一次心跳
                self._stop_event.wait(self.config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"发送心跳失败: {e}")
                self._stop_event.wait(5)  # 异常时等待5秒再重试
        
        self.logger.info("心跳线程停止")
    
    def _update_global_performance_stats(self):
        """更新全局性能统计"""
        try:
            # 汇总所有交易所的余额
            total_balance = 0
            for exchange in self.exchanges.values():
                try:
                    balance = exchange.get_balance()
                    total_balance += balance
                except Exception as e:
                    self.logger.error(f"获取交易所余额失败: {e}")
            
            # 初始化峰值余额
            if not hasattr(self, '_global_peak_balance'):
                self._global_peak_balance = total_balance
            
            # 计算当前回撤
            if self._global_peak_balance > 0:
                self.global_stats['current_drawdown'] = (self._global_peak_balance - total_balance) / self._global_peak_balance
                self.global_stats['max_drawdown'] = max(self.global_stats['max_drawdown'], self.global_stats['current_drawdown'])
            
            # 更新峰值
            if total_balance > self._global_peak_balance:
                self._global_peak_balance = total_balance
                
        except Exception as e:
            self.logger.error(f"更新全局性能统计失败: {e}")
    
    def _check_global_risk(self) -> bool:
        """检查全局风险"""
        try:
            # 检查最大回撤
            max_drawdown_limit = self.config.risk_control.get('max_drawdown', 0.2)
            if self.global_stats['max_drawdown'] >= max_drawdown_limit:
                self.logger.warning(f"触发最大回撤限制: {self.global_stats['max_drawdown']:.2%} >= {max_drawdown_limit:.2%}")
                return False
            
            # 检查日亏损限制
            daily_loss_limit = self.config.risk_control.get('daily_loss_limit', 0.05)
            if self.global_stats['daily_pnl'] <= -daily_loss_limit:
                self.logger.warning(f"触发日亏损限制: {self.global_stats['daily_pnl']:.2%} <= -{daily_loss_limit:.2%}")
                return False
            
            # 检查连续亏损次数
            consecutive_loss_limit = self.config.risk_control.get('consecutive_loss_limit', 10)
            if hasattr(self, '_consecutive_losses') and self._consecutive_losses >= consecutive_loss_limit:
                self.logger.warning(f"触发连续亏损限制: {self._consecutive_losses} >= {consecutive_loss_limit}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查全局风险失败: {e}")
            return False
    
    def _log_system_status(self):
        """记录系统状态"""
        try:
            # 收集所有策略状态
            strategy_statuses = []
            for instance in self.strategy_instances:
                status = {
                    'name': instance.name,
                    'status': instance.stats['status'],
                    'symbols': instance.symbols,
                    'total_trades': instance.stats['total_trades'],
                    'total_pnl': instance.stats['total_pnl'],
                    'max_drawdown': instance.stats['max_drawdown']
                }
                strategy_statuses.append(status)
            
            # 记录系统状态
            system_status = {
                'timestamp': datetime.now().isoformat(),
                'state': self.state.value,
                'uptime': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
                'global_stats': self.global_stats,
                'strategies': strategy_statuses
            }
            
            self.logger.info(f"系统状态: {json.dumps(system_status, ensure_ascii=False)}")
            
        except Exception as e:
            self.logger.error(f"记录系统状态失败: {e}")
    
    def _send_heartbeat(self):
        """发送心跳"""
        try:
            # 收集所有交易所信息
            exchange_info = {}
            for name, exchange in self.exchanges.items():
                try:
                    balance = exchange.get_balance()
                    exchange_info[name] = {'balance': balance}
                except Exception as e:
                    exchange_info[name] = {'error': str(e)}
            
            # 收集所有策略状态
            strategy_statuses = []
            for instance in self.strategy_instances:
                status = {
                    'name': instance.name,
                    'status': instance.stats['status'],
                    'symbols': instance.symbols,
                    'stats': instance.stats
                }
                strategy_statuses.append(status)
            
            # 构建心跳数据
            heartbeat_data = {
                'timestamp': datetime.now().isoformat(),
                'state': self.state.value,
                'exchanges': exchange_info,
                'global_stats': self.global_stats,
                'strategies': strategy_statuses
            }
            
            # 如果启用了通知，发送心跳
            if self.config.notification and self.config.notification.get('enabled', False):
                webhook = self.config.notification.get('webhook')
                if webhook:
                    self._send_notification(webhook, heartbeat_data)
            
            self.logger.debug("心跳发送成功")
            
        except Exception as e:
            self.logger.error(f"发送心跳失败: {e}")
    
    def _send_notification(self, webhook: str, data: Dict[str, Any]):
        """发送通知"""
        try:
            import requests
            
            response = requests.post(
                webhook,
                json=data,
                timeout=5
            )
            
            if response.status_code != 200:
                self.logger.warning(f"通知发送失败: {response.status_code}, {response.text}")
                
        except Exception as e:
            self.logger.error(f"发送通知异常: {e}")
    
    def _cancel_all_orders(self):
        """取消所有未完成订单"""
        try:
            for exchange_name, exchange in self.exchanges.items():
                try:
                    # 获取所有活跃交易对
                    active_symbols = set()
                    for instance in self.strategy_instances:
                        active_symbols.update(instance.symbols)
                    
                    # 为每个交易对取消订单
                    for symbol in active_symbols:
                        canceled_count = exchange.cancel_all_orders(symbol)
                        if canceled_count > 0:
                            self.logger.info(f"交易所 {exchange_name} 取消 {symbol} 的 {canceled_count} 个订单")
                except Exception as e:
                    self.logger.error(f"交易所 {exchange_name} 取消订单失败: {e}")
        except Exception as e:
            self.logger.error(f"取消所有订单失败: {e}")
    
    def _save_trading_records(self):
        """保存交易记录"""
        try:
            # 创建记录目录
            records_dir = "records"
            os.makedirs(records_dir, exist_ok=True)
            
            # 生成文件名
            filename = f"{records_dir}/trading_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            # 收集交易数据
            exchange_data = {}
            for name, exchange in self.exchanges.items():
                try:
                    # 获取交易所交易历史
                    trades = exchange.get_my_trades()
                    exchange_data[name] = {
                        'trades': trades,
                        'balance': exchange.get_balance()
                    }
                except Exception as e:
                    exchange_data[name] = {'error': str(e)}
            
            # 准备记录数据
            records = {
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'stop_time': self.stop_time.isoformat() if self.stop_time else None,
                'global_stats': self.global_stats,
                'strategy_stats': [instance.stats for instance in self.strategy_instances],
                'exchange_data': exchange_data
            }
            
            # 保存到文件
            with open(filename, 'w') as f:
                json.dump(records, f, indent=2, default=str, ensure_ascii=False)
            
            self.logger.info(f"交易记录已保存: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存交易记录失败: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取交易状态
        
        Returns:
            Dict[str, Any]: 交易状态信息
        """
        # 收集策略状态
        strategy_statuses = []
        for instance in self.strategy_instances:
            status = {
                'name': instance.name,
                'status': instance.stats['status'],
                'symbols': instance.symbols,
                'timeframe': instance.timeframe,
                'stats': instance.stats
            }
            strategy_statuses.append(status)
        
        return {
            'state': self.state.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'stop_time': self.stop_time.isoformat() if self.stop_time else None,
            'uptime': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'global_stats': self.global_stats,
            'strategies': strategy_statuses,
            'active_symbols': list(self.global_stats['active_symbols'])
        }
    
    def run(self):
        """运行实盘交易（阻塞模式）"""
        if not self.start():
            return False
        
        try:
            # 主循环
            while self._running and self.state == TradingState.RUNNING:
                time.sleep(1)
            
            return True
            
        except KeyboardInterrupt:
            self.logger.info("接收到键盘中断信号")
            self.stop()
            return True
            
        except Exception as e:
            self.logger.error(f"运行异常: {e}")
            self.stop()
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='实盘交易运行器')
    parser.add_argument('--config', '-c', default='configs/live_config.yaml',
                        help='配置文件路径')
    
    args = parser.parse_args()
    
    # 创建并运行实盘交易控制器
    try:
        trader = LiveTrader(args.config)
        trader.run()
    except Exception as e:
        print(f"运行实盘交易失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
