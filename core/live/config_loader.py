"""
实盘配置加载模块

负责解析live_config.yaml配置文件，实例化策略和交易所连接，为实盘交易模块提供配置支持。
"""

import os
import yaml
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ..utils.logger import Logger
from ..exchange.base_exchange import BaseExchange
from ..strategy.base_strategy import BaseStrategy
from ..utils.config import load_config


@dataclass
class ExchangeConfig:
    """交易所配置"""
    name: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    testnet: bool = False
    sandbox: bool = False
    timeout: int = 30
    rate_limit: int = 10


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    symbols: List[str]
    timeframe: str
    params: Dict[str, Any] = field(default_factory=dict)
    risk_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveConfig:
    """实盘配置"""
    exchanges: List[ExchangeConfig]
    strategies: List[StrategyConfig]
    risk_control: Dict[str, Any] = field(default_factory=dict)
    logging: Dict[str, Any] = field(default_factory=dict)
    notification: Dict[str, Any] = field(default_factory=dict)
    heartbeat_interval: int = 30
    data_check_interval: int = 60
    order_check_interval: int = 10


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self):
        self.logger = Logger.get_logger("ConfigLoader")
    
    def load_config(self, config_path: str) -> LiveConfig:
        """
        加载实盘配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            LiveConfig: 实盘配置对象
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        try:
            # 使用通用配置加载器
            config_data = load_config(config_path)
            
            # 解析交易所配置
            exchange_configs = []
            for exchange_name, exchange_data in config_data.get("exchanges", {}).items():
                exchange_config = ExchangeConfig(
                    name=exchange_name,
                    **exchange_data
                )
                exchange_configs.append(exchange_config)
            
            # 解析策略配置
            strategy_configs = []
            for strategy_data in config_data.get("strategies", []):
                strategy_config = StrategyConfig(
                    name=strategy_data["name"],
                    symbols=strategy_data["symbols"],
                    timeframe=strategy_data["timeframe"],
                    params=strategy_data.get("params", {}),
                    risk_params=strategy_data.get("risk_params", {})
                )
                strategy_configs.append(strategy_config)
            
            # 解析全局配置
            risk_control = config_data.get("risk_control", {})
            logging_config = config_data.get("logging", {})
            notification = config_data.get("notification", {})
            heartbeat_interval = config_data.get("heartbeat_interval", 30)
            data_check_interval = config_data.get("data_check_interval", 60)
            order_check_interval = config_data.get("order_check_interval", 10)
            
            # 创建并返回配置对象
            live_config = LiveConfig(
                exchanges=exchange_configs,
                strategies=strategy_configs,
                risk_control=risk_control,
                logging=logging_config,
                notification=notification,
                heartbeat_interval=heartbeat_interval,
                data_check_interval=data_check_interval,
                order_check_interval=order_check_interval
            )
            
            self.logger.info(f"成功加载配置文件: {config_path}")
            return live_config
            
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            raise
    
    def create_exchange(self, exchange_config: ExchangeConfig) -> BaseExchange:
        """
        根据配置创建交易所实例
        
        Args:
            exchange_config: 交易所配置
            
        Returns:
            BaseExchange: 交易所实例
        """
        exchange_name = exchange_config.name.lower()
        
        try:
            if exchange_name == "binance":
                from ..exchange.binance_api import BinanceAPI
                exchange = BinanceAPI(
                    api_key=exchange_config.api_key,
                    api_secret=exchange_config.api_secret,
                    testnet=exchange_config.testnet,
                    timeout=exchange_config.timeout
                )
            elif exchange_name == "okx":
                from ..exchange.okx_api import OKXAPI
                exchange = OKXAPI(
                    api_key=exchange_config.api_key,
                    api_secret=exchange_config.api_secret,
                    passphrase=exchange_config.passphrase,
                    sandbox=exchange_config.sandbox,
                    timeout=exchange_config.timeout
                )
            else:
                raise ValueError(f"不支持的交易所: {exchange_name}")
            
            self.logger.info(f"成功创建交易所实例: {exchange_name}")
            return exchange
            
        except Exception as e:
            self.logger.error(f"创建交易所实例失败: {e}")
            raise
    
    def create_strategy(self, strategy_config: StrategyConfig) -> BaseStrategy:
        """
        根据配置创建策略实例
        
        Args:
            strategy_config: 策略配置
            
        Returns:
            BaseStrategy: 策略实例
        """
        strategy_name = strategy_config.name.lower()
        
        try:
            if strategy_name == "grid":
                from ..strategy.grid_strategy import GridStrategy
                strategy = GridStrategy(
                    symbols=strategy_config.symbols,
                    timeframe=strategy_config.timeframe,
                    **strategy_config.params
                )
            elif strategy_name == "martingale":
                from ..strategy.martingale_strategy import MartingaleStrategy
                strategy = MartingaleStrategy(
                    symbols=strategy_config.symbols,
                    timeframe=strategy_config.timeframe,
                    **strategy_config.params
                )
            else:
                # 尝试动态导入自定义策略
                try:
                    module_path, class_name = strategy_name.rsplit(".", 1)
                    module = __import__(module_path, fromlist=[class_name])
                    strategy_class = getattr(module, class_name)
                    strategy = strategy_class(
                        symbols=strategy_config.symbols,
                        timeframe=strategy_config.timeframe,
                        **strategy_config.params
                    )
                except Exception as e:
                    self.logger.error(f"动态导入策略失败: {strategy_name}, 错误: {e}")
                    raise ValueError(f"不支持的策略: {strategy_name}, 错误: {e}")
            
            self.logger.info(f"成功创建策略实例: {strategy_name}")
            return strategy
            
        except Exception as e:
            self.logger.error(f"创建策略实例失败: {e}")
            raise
    
    def create_data_manager(self, exchange: BaseExchange, symbol: str, timeframe: str):
        """
        根据配置创建数据管理器实例
        
        Args:
            exchange: 交易所实例
            symbol: 交易对
            timeframe: 时间框架
            
        Returns:
            DataManager: 数据管理器实例
        """
        try:
            from ..data.data_manager import DataManager
            data_manager = DataManager(exchange, symbol, timeframe)
            self.logger.info(f"成功创建数据管理器实例: {symbol} {timeframe}")
            return data_manager
        except Exception as e:
            self.logger.error(f"创建数据管理器实例失败: {e}")
            raise


def get_config_loader() -> ConfigLoader:
    """
    获取配置加载器实例
    
    Returns:
        ConfigLoader: 配置加载器实例
    """
    return ConfigLoader()