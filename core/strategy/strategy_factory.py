"""
策略工厂 - 动态创建策略实例

支持所有高频和传统策略的统一创建接口。
"""

from typing import Dict, Optional
from core.strategy.base_strategy import BaseStrategy
from core.utils.logger import get_logger

logger = get_logger("StrategyFactory")


class StrategyFactory:
    """策略工厂 - 根据配置动态创建策略实例"""

    # 策略注册表
    _strategies = {}

    @classmethod
    def register_strategy(cls, name: str, strategy_class):
        """注册策略"""
        cls._strategies[name] = strategy_class
        logger.debug(f"注册策略: {name} -> {strategy_class.__name__}")

    @classmethod
    def create_strategy(cls, config: Dict) -> BaseStrategy:
        """
        根据配置创建策略实例

        Args:
            config: 完整的配置字典（包含strategy部分）

        Returns:
            策略实例

        Raises:
            ValueError: 不支持的策略类型
        """
        # 获取策略配置
        strategy_config = config.get('strategy', {})
        strategy_name = strategy_config.get('name', '')
        strategy_class_name = strategy_config.get('class', '')

        # 优先使用class字段，其次使用name字段
        identifier = strategy_class_name or strategy_name

        if not identifier:
            raise ValueError("配置中缺少strategy.name或strategy.class")

        # 标准化策略名称
        identifier = cls._normalize_strategy_name(identifier)

        # 延迟导入策略类（避免循环依赖）
        strategy_class = cls._load_strategy_class(identifier)

        if strategy_class is None:
            raise ValueError(f"不支持的策略: {identifier}")

        # 创建策略实例
        try:
            strategy = strategy_class(config)
            logger.info(f"✅ 创建策略成功: {identifier} -> {strategy_class.__name__}")
            return strategy
        except Exception as e:
            logger.error(f"创建策略失败 {identifier}: {e}")
            raise

    @staticmethod
    def _normalize_strategy_name(name: str) -> str:
        """标准化策略名称"""
        # 移除Strategy后缀
        if name.endswith('Strategy'):
            name = name[:-8]  # 移除'Strategy'

        # 转换为驼峰命名
        return name

    @staticmethod
    def _load_strategy_class(identifier: str):
        """
        动态加载策略类

        Args:
            identifier: 策略标识符

        Returns:
            策略类或None
        """
        # 策略映射表
        strategy_map = {
            # 高频策略
            'HighFrequencyBreakout': 'core.strategy.high_frequency_breakout.HighFrequencyBreakoutStrategy',
            'HighFrequency': 'core.strategy.high_frequency_breakout.HighFrequencyBreakoutStrategy',
            'HFBreakout': 'core.strategy.high_frequency_breakout.HighFrequencyBreakoutStrategy',

            # 多时间框架1秒K线策略
            'MultiTimeframeKlineBreakout': 'core.strategy.multi_timeframe_kline_breakout.MultiTimeframeKlineBreakoutStrategy',
            'MultiTimeframeBreakout': 'core.strategy.multi_timeframe_kline_breakout.MultiTimeframeKlineBreakoutStrategy',
            'MTKlineBreakout': 'core.strategy.multi_timeframe_kline_breakout.MultiTimeframeKlineBreakoutStrategy',

            # 传统策略（用于回测）
            'Grid': 'core.strategy.grid_strategy.GridStrategy',
            'GridStrategy': 'core.strategy.grid_strategy.GridStrategy',
            'Martingale': 'core.strategy.martingale_strategy.MartingaleStrategy',
            'MartingaleStrategy': 'core.strategy.martingale_strategy.MartingaleStrategy',
            'DualMA': 'core.strategy.dual_ma_strategy.DualMAStrategy',
            'DualMAStrategy': 'core.strategy.dual_ma_strategy.DualMAStrategy',
            'TraditionalGrid': 'core.strategy.traditional_grid_strategy.TraditionalGridStrategy',
            'TraditionalGridStrategy': 'core.strategy.traditional_grid_strategy.TraditionalGridStrategy',
        }

        module_path = strategy_map.get(identifier)

        if not module_path:
            logger.warning(f"未找到策略映射: {identifier}")
            return None

        try:
            # 动态导入模块
            module_parts = module_path.rsplit('.', 1)
            module_name = module_parts[0]
            class_name = module_parts[1] if len(module_parts) > 1 else None

            module = __import__(module_name, fromlist=[class_name] if class_name else [])

            if class_name:
                strategy_class = getattr(module, class_name)
            else:
                # 如果没有指定类名，使用模块中导出的主类
                strategy_class = getattr(module, identifier + 'Strategy', None)

            logger.debug(f"动态加载策略: {identifier} -> {module_path}")
            return strategy_class

        except ImportError as e:
            logger.error(f"导入策略模块失败: {module_path}, 错误: {e}")
            return None
        except AttributeError as e:
            logger.error(f"策略类不存在: {class_name} in {module_path}, 错误: {e}")
            return None

    @classmethod
    def list_strategies(cls) -> Dict[str, str]:
        """列出所有已注册的策略"""
        return cls._strategies.copy()

    @classmethod
    def is_hf_strategy(cls, strategy_name: str) -> bool:
        """
        判断是否为高频策略

        Args:
            strategy_name: 策略名称

        Returns:
            是否为高频策略
        """
        # 高频策略需要特殊的交易器和执行环境
        hf_strategies = {
            'HighFrequencyBreakout',
            'HighFrequency',
            'HFBreakout',
            'MultiTimeframeKlineBreakout',
            'MultiTimeframeBreakout',
            'MTKlineBreakout',
        }

        # 标准化策略名称
        normalized = cls._normalize_strategy_name(strategy_name)

        return normalized in hf_strategies
