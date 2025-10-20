"""
配置管理模块

封装配置加载（YAML/JSON）功能，支持多种配置格式。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, Union
from pathlib import Path

from .logger import Logger


class ConfigLoader:
    """
    配置加载器
    
    支持加载YAML和JSON格式的配置文件，并提供配置访问接口。
    """
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.logger = Logger.get_logger("ConfigLoader")
        self._config: Dict[str, Any] = {}
        
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Dict[str, Any]: 配置数据字典
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            self.logger.error(f"Config file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    self._config = yaml.safe_load(f) or {}
                elif config_path.suffix.lower() == '.json':
                    self._config = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")
            
            self.logger.info(f"Loaded config from {config_path}")
            return self._config
        
        except Exception as e:
            self.logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键（如 'exchanges.binance.api_key'）
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键
            value: 配置值
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save_config(self, config_path: Union[str, Path]) -> None:
        """
        保存配置到文件
        
        Args:
            config_path: 配置文件路径
        """
        config_path = Path(config_path)
        
        try:
            # 确保目录存在
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
                elif config_path.suffix.lower() == '.json':
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")
            
            self.logger.info(f"Saved config to {config_path}")
        
        except Exception as e:
            self.logger.error(f"Failed to save config to {config_path}: {e}")
            raise
    
    def get_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """
        获取交易所配置
        
        Args:
            exchange_name: 交易所名称
            
        Returns:
            Dict[str, Any]: 交易所配置
        """
        return self.get(f'exchanges.{exchange_name}', {})
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """
        获取策略配置
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            Dict[str, Any]: 策略配置
        """
        return self.get(f'strategies.{strategy_name}', {})
    
    def get_risk_config(self) -> Dict[str, Any]:
        """
        获取风险控制配置
        
        Returns:
            Dict[str, Any]: 风险控制配置
        """
        return self.get('risk_control', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """
        获取日志配置
        
        Returns:
            Dict[str, Any]: 日志配置
        """
        return self.get('logging', {})
    
    def to_dict(self) -> Dict[str, Any]:
        """
        获取完整配置字典
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        return self._config.copy()


def load_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    加载配置文件的便捷函数
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        Dict[str, Any]: 配置数据字典
    """
    loader = ConfigLoader()
    return loader.load_config(config_path)


def find_config_file(config_name: str, search_paths: Optional[list] = None) -> Optional[Path]:
    """
    查找配置文件
    
    Args:
        config_name: 配置文件名
        search_paths: 搜索路径列表，如果为None则使用默认路径
        
    Returns:
        Optional[Path]: 找到的配置文件路径，如果未找到则返回None
    """
    if search_paths is None:
        # 默认搜索路径
        project_root = Path(__file__).parent.parent.parent
        search_paths = [
            project_root / 'configs',
            project_root,
            Path.cwd() / 'configs',
            Path.cwd(),
        ]
    
    for path in search_paths:
        config_path = Path(path) / config_name
        if config_path.exists():
            return config_path
    
    return None