"""
日志系统模块

统一日志格式与等级，支持多级别日志、文件输出等功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import logging
import sys
import time
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import threading


class PerformanceLogger:
    """
    性能日志记录器
    
    用于记录和统计策略性能指标，包括收益率、回撤、胜率等。
    """
    
    def __init__(self, name: str = "Performance", log_file: Optional[str] = None):
        """
        初始化性能日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
        """
        self.name = name
        self.logger = Logger.get_logger(name, log_file=log_file)
        self.metrics = {}
        self.start_time = time.time()
    
    def log_metric(self, metric_name: str, value: Any, timestamp: Optional[float] = None):
        """
        记录性能指标
        
        Args:
            metric_name: 指标名称
            value: 指标值
            timestamp: 时间戳，默认为当前时间
        """
        if timestamp is None:
            timestamp = time.time()
        
        # 记录到内存
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append((timestamp, value))
        
        # 记录到日志
        self.logger.info(f"METRIC: {metric_name} = {value} at {datetime.fromtimestamp(timestamp)}")
    
    def log_trade(self, symbol: str, side: str, quantity: float, price: float, 
                 pnl: Optional[float] = None, timestamp: Optional[float] = None):
        """
        记录交易信息
        
        Args:
            symbol: 交易对
            side: 交易方向
            quantity: 数量
            price: 价格
            pnl: 盈亏
            timestamp: 时间戳
        """
        if timestamp is None:
            timestamp = time.time()
        
        trade_info = f"TRADE: {symbol} {side} {quantity}@{price}"
        if pnl is not None:
            trade_info += f" PnL: {pnl}"
        
        self.logger.info(f"{trade_info} at {datetime.fromtimestamp(timestamp)}")
    
    def get_metrics(self, metric_name: str) -> List[tuple]:
        """
        获取指定指标的所有记录
        
        Args:
            metric_name: 指标名称
            
        Returns:
            List[tuple]: 指标记录列表，每个元素为(时间戳, 值)
        """
        return self.metrics.get(metric_name, [])
    
    def get_latest_metric(self, metric_name: str) -> Optional[Any]:
        """
        获取指定指标的最新值
        
        Args:
            metric_name: 指标名称
            
        Returns:
            Any: 最新指标值
        """
        records = self.get_metrics(metric_name)
        return records[-1][1] if records else None


class TradingLogger:
    """
    交易日志记录器
    
    专门用于记录交易相关的日志信息，包括订单、成交、持仓等。
    """
    
    def __init__(self, name: str = "Trading", log_file: Optional[str] = None):
        """
        初始化交易日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
        """
        self.name = name
        self.logger = Logger.get_logger(name, log_file=log_file)
    
    def log_order(self, symbol: str, side: str, order_type: str, quantity: float, 
                 price: Optional[float] = None, order_id: Optional[str] = None):
        """
        记录订单信息
        
        Args:
            symbol: 交易对
            side: 交易方向
            order_type: 订单类型
            quantity: 数量
            price: 价格
            order_id: 订单ID
        """
        order_info = f"ORDER: {symbol} {side} {order_type} {quantity}"
        if price is not None:
            order_info += f" @ {price}"
        if order_id is not None:
            order_info += f" ID: {order_id}"
        
        self.logger.info(order_info)
    
    def log_fill(self, symbol: str, side: str, quantity: float, price: float, 
                order_id: Optional[str] = None, fee: Optional[float] = None):
        """
        记录成交信息
        
        Args:
            symbol: 交易对
            side: 交易方向
            quantity: 成交数量
            price: 成交价格
            order_id: 订单ID
            fee: 手续费
        """
        fill_info = f"FILL: {symbol} {side} {quantity}@{price}"
        if order_id is not None:
            fill_info += f" ID: {order_id}"
        if fee is not None:
            fill_info += f" Fee: {fee}"
        
        self.logger.info(fill_info)
    
    def log_position(self, symbol: str, side: str, quantity: float, 
                    entry_price: Optional[float] = None, unrealized_pnl: Optional[float] = None):
        """
        记录持仓信息
        
        Args:
            symbol: 交易对
            side: 持仓方向
            quantity: 持仓数量
            entry_price: 开仓价格
            unrealized_pnl: 未实现盈亏
        """
        position_info = f"POSITION: {symbol} {side} {quantity}"
        if entry_price is not None:
            position_info += f" Entry: {entry_price}"
        if unrealized_pnl is not None:
            position_info += f" Unrealized PnL: {unrealized_pnl}"
        
        self.logger.info(position_info)


class StructuredLogger:
    """
    结构化日志记录器
    
    用于记录结构化的日志信息，支持JSON格式输出，便于日志分析。
    """
    
    def __init__(self, name: str = "Structured", log_file: Optional[str] = None):
        """
        初始化结构化日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
        """
        self.name = name
        self.logger = Logger.get_logger(name, log_file=log_file)
    
    def log_event(self, event_type: str, data: Dict[str, Any], 
                 timestamp: Optional[float] = None, level: str = "info"):
        """
        记录结构化事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            timestamp: 时间戳，默认为当前时间
            level: 日志级别，默认为info
        """
        if timestamp is None:
            timestamp = time.time()
        
        event_data = {
            "event_type": event_type,
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp).isoformat(),
            "data": data
        }
        
        # 转换为JSON字符串
        json_str = json.dumps(event_data, ensure_ascii=False)
        
        # 根据级别记录日志
        if level.lower() == "debug":
            self.logger.debug(json_str)
        elif level.lower() == "info":
            self.logger.info(json_str)
        elif level.lower() == "warning":
            self.logger.warning(json_str)
        elif level.lower() == "error":
            self.logger.error(json_str)
        elif level.lower() == "critical":
            self.logger.critical(json_str)
        else:
            self.logger.info(json_str)
    
    def log_error(self, error_type: str, error_message: str, 
                 context: Optional[Dict[str, Any]] = None, 
                 timestamp: Optional[float] = None):
        """
        记录错误事件
        
        Args:
            error_type: 错误类型
            error_message: 错误消息
            context: 错误上下文
            timestamp: 时间戳
        """
        error_data = {
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {}
        }
        
        self.log_event("error", error_data, timestamp, "error")
    
    def log_trade_event(self, symbol: str, side: str, quantity: float, price: float,
                       order_id: Optional[str] = None, trade_id: Optional[str] = None,
                       timestamp: Optional[float] = None):
        """
        记录交易事件
        
        Args:
            symbol: 交易对
            side: 交易方向
            quantity: 数量
            price: 价格
            order_id: 订单ID
            trade_id: 交易ID
            timestamp: 时间戳
        """
        trade_data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "order_id": order_id,
            "trade_id": trade_id
        }
        
        self.log_event("trade", trade_data, timestamp, "info")
    
    def log_strategy_event(self, strategy_name: str, event_type: str, 
                          data: Dict[str, Any], timestamp: Optional[float] = None):
        """
        记录策略事件
        
        Args:
            strategy_name: 策略名称
            event_type: 事件类型
            data: 事件数据
            timestamp: 时间戳
        """
        strategy_data = {
            "strategy_name": strategy_name,
            "event_type": event_type,
            "data": data
        }
        
        self.log_event("strategy", strategy_data, timestamp, "info")


class Logger:
    """
    统一日志记录器
    
    提供多级别日志记录、文件输出、格式化等功能，支持日志轮转和压缩。
    """
    
    _instances: Dict[str, logging.Logger] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_logger(cls, name: str, 
                  level: str = "INFO",
                  log_file: Optional[str] = None,
                  log_format: Optional[str] = None,
                  max_bytes: int = 10 * 1024 * 1024,  # 10MB
                  backup_count: int = 5,
                  when: str = 'midnight',
                  interval: int = 1,
                  encoding: str = 'utf-8') -> logging.Logger:
        """
        获取或创建日志记录器
        
        Args:
            name: 日志记录器名称
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: 日志文件路径，None表示不写入文件
            log_format: 日志格式，None表示使用默认格式
            max_bytes: 单个日志文件最大字节数
            backup_count: 保留的日志文件备份数量
            when: 日志轮转时间间隔 ('S', 'M', 'H', 'D', 'midnight', 'W0'-'W6')
            interval: 轮转间隔
            encoding: 日志文件编码
            
        Returns:
            logging.Logger: 日志记录器实例
        """
        with cls._lock:
            if name in cls._instances:
                return cls._instances[name]
            
            # 创建日志记录器
            logger = logging.getLogger(name)
            logger.setLevel(getattr(logging, level.upper(), logging.INFO))
            
            # 清除现有处理器
            logger.handlers.clear()
            
            # 设置日志格式
            if log_format is None:
                log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            
            formatter = logging.Formatter(log_format)
            
            # 添加控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # 添加文件处理器
            if log_file:
                # 确保日志目录存在
                log_dir = os.path.dirname(log_file)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                
                # 使用轮转文件处理器
                if when == 'midnight' or when.startswith('W'):
                    file_handler = TimedRotatingFileHandler(
                        log_file,
                        when=when,
                        interval=interval,
                        backupCount=backup_count,
                        encoding=encoding
                    )
                else:
                    file_handler = RotatingFileHandler(
                        log_file,
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding=encoding
                    )
                
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                
                # 立即创建日志文件
                logger.info("Logger initialized")
            
            # 缓存日志记录器
            cls._instances[name] = logger
            
            return logger
    
    @classmethod
    def setup_global_logging(cls,
                            level: str = "INFO",
                            log_file: Optional[str] = None,
                            log_format: Optional[str] = None,
                            max_bytes: int = 10 * 1024 * 1024,
                            backup_count: int = 5,
                            when: str = 'midnight',
                            interval: int = 1,
                            encoding: str = 'utf-8'):
        """
        设置全局日志配置
        
        Args:
            level: 日志级别
            log_file: 日志文件路径
            log_format: 日志格式
            max_bytes: 单个日志文件最大字节数
            backup_count: 保留的日志文件备份数量
            when: 日志轮转时间间隔
            interval: 轮转间隔
            encoding: 日志文件编码
        """
        # 设置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        
        # 清除现有处理器
        root_logger.handlers.clear()
        
        # 设置日志格式
        if log_format is None:
            log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        formatter = logging.Formatter(log_format)
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 添加文件处理器
        if log_file:
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            # 使用轮转文件处理器
            if when == 'midnight' or when.startswith('W'):
                file_handler = TimedRotatingFileHandler(
                    log_file,
                    when=when,
                    interval=interval,
                    backupCount=backup_count,
                    encoding=encoding
                )
            else:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding=encoding
                )
            
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)


def get_logger(name: str, **kwargs) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        **kwargs: 传递给Logger.get_logger的其他参数
        
    Returns:
        logging.Logger: 日志记录器实例
    """
    return Logger.get_logger(name, **kwargs)


def setup_logging(**kwargs):
    """
    设置全局日志的便捷函数
    
    Args:
        **kwargs: 传递给Logger.setup_global_logging的参数
    """
    Logger.setup_global_logging(**kwargs)