"""
Tick数据管理器集成模块

提供与现有系统的最小侵入式集成功能。
"""

import asyncio
import logging
from typing import Optional
from pathlib import Path

from .tick_data_manager import TickDataManager
from .config_models import TickDataConfig
from ..websocket_client import set_tick_data_manager

logger = logging.getLogger(__name__)


class TickDataIntegration:
    """Tick数据管理器集成类

    负责将tick数据管理器集成到现有的交易系统中。
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化集成类

        Args:
            config_path: 配置文件路径，默认使用高频突破策略配置
        """
        self.config_path = config_path or "configs/hf_breakout_live_config.yaml"
        self.tick_manager: Optional[TickDataManager] = None
        self.is_running = False

        logger.info(f"TickDataIntegration初始化 - 配置文件: {self.config_path}")

    async def initialize(self) -> bool:
        """初始化tick数据管理器

        Returns:
            是否初始化成功
        """
        try:
            # 加载配置
            logger.info("加载tick数据配置...")
            config = TickDataConfig.from_yaml(self.config_path)

            if not config.enabled:
                logger.info("Tick数据转存功能已禁用")
                return True

            # 创建tick数据管理器
            logger.info("创建tick数据管理器...")
            self.tick_manager = TickDataManager(config)

            # 设置到WebSocket客户端
            logger.info("设置tick数据管理器到WebSocket客户端...")
            set_tick_data_manager(self.tick_manager)

            # 启动tick数据管理器
            logger.info("启动tick数据管理器...")
            await self.tick_manager.start()

            self.is_running = True
            logger.info("Tick数据管理器集成初始化完成")
            return True

        except Exception as e:
            logger.error(f"Tick数据管理器初始化失败: {e}")
            return False

    async def shutdown(self):
        """关闭tick数据管理器"""
        if self.tick_manager and self.is_running:
            logger.info("正在关闭tick数据管理器...")
            await self.tick_manager.stop()
            self.is_running = False
            logger.info("Tick数据管理器已关闭")

    async def get_status(self) -> dict:
        """获取tick数据管理器状态

        Returns:
            状态信息字典
        """
        if not self.tick_manager:
            return {
                'initialized': False,
                'running': False,
                'message': 'Tick数据管理器未初始化'
            }

        try:
            detailed_status = await self.tick_manager.get_detailed_status()
            return {
                'initialized': True,
                'running': self.is_running,
                **detailed_status
            }
        except Exception as e:
            return {
                'initialized': True,
                'running': self.is_running,
                'error': str(e)
            }

    async def force_save(self) -> dict:
        """强制保存所有缓冲数据

        Returns:
            保存结果
        """
        if not self.tick_manager:
            return {'success': False, 'error': 'Tick数据管理器未初始化'}

        try:
            results = await self.tick_manager.save_all()
            return {
                'success': True,
                'results': results,
                'total_symbols': len(results),
                'successful_saves': sum(results.values())
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def validate_data(self, symbol: Optional[str] = None) -> dict:
        """验证已保存的数据

        Args:
            symbol: 交易对符号，None表示验证所有

        Returns:
            验证结果
        """
        if not self.tick_manager:
            return {'valid': False, 'error': 'Tick数据管理器未初始化'}

        try:
            return await self.tick_manager.validate_saved_data(symbol)
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    def get_buffer_status(self, symbol: Optional[str] = None) -> dict:
        """获取缓冲区状态

        Args:
            symbol: 交易对符号，None表示返回所有

        Returns:
            缓冲区状态
        """
        if not self.tick_manager:
            return {'error': 'Tick数据管理器未初始化'}

        try:
            return self.tick_manager.get_buffer_status(symbol)
        except Exception as e:
            return {'error': str(e)}


# 全局集成实例
_integration_instance: Optional[TickDataIntegration] = None


async def initialize_tick_data_collection(config_path: Optional[str] = None) -> bool:
    """初始化tick数据收集（全局函数）

    Args:
        config_path: 配置文件路径

    Returns:
        是否初始化成功
    """
    global _integration_instance

    try:
        _integration_instance = TickDataIntegration(config_path)
        return await _integration_instance.initialize()
    except Exception as e:
        logger.error(f"全局tick数据收集初始化失败: {e}")
        return False


async def shutdown_tick_data_collection():
    """关闭tick数据收集（全局函数）"""
    global _integration_instance

    if _integration_instance:
        await _integration_instance.shutdown()
        _integration_instance = None


async def get_tick_data_status() -> dict:
    """获取tick数据收集状态（全局函数）

    Returns:
        状态信息字典
    """
    global _integration_instance

    if _integration_instance:
        return await _integration_instance.get_status()
    else:
        return {
            'initialized': False,
            'running': False,
            'message': 'Tick数据收集未初始化'
        }


async def force_save_tick_data() -> dict:
    """强制保存tick数据（全局函数）

    Returns:
        保存结果
    """
    global _integration_instance

    if _integration_instance:
        return await _integration_instance.force_save()
    else:
        return {'success': False, 'error': 'Tick数据收集未初始化'}


def get_buffer_status(symbol: Optional[str] = None) -> dict:
    """获取缓冲区状态（全局函数）

    Args:
        symbol: 交易对符号

    Returns:
        缓冲区状态
    """
    global _integration_instance

    if _integration_instance:
        return _integration_instance.get_buffer_status(symbol)
    else:
        return {'error': 'Tick数据收集未初始化'}


async def validate_tick_data(symbol: Optional[str] = None) -> dict:
    """验证tick数据（全局函数）

    Args:
        symbol: 交易对符号

    Returns:
        验证结果
    """
    global _integration_instance

    if _integration_instance:
        return await _integration_instance.validate_data(symbol)
    else:
        return {'valid': False, 'error': 'Tick数据收集未初始化'}


# 装饰器，用于在高频交易器中自动集成tick数据收集
def with_tick_data_collection(config_path: Optional[str] = None):
    """装饰器：为函数自动添加tick数据收集功能

    Args:
        config_path: 配置文件路径

    Returns:
        装饰后的函数
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 初始化tick数据收集
            success = await initialize_tick_data_collection(config_path)
            if not success:
                logger.error("Tick数据收集初始化失败，但继续执行主函数")

            try:
                # 执行原函数
                result = await func(*args, **kwargs)
                return result
            finally:
                # 清理tick数据收集
                await shutdown_tick_data_collection()

        return wrapper
    return decorator


# 上下文管理器，用于在代码块中管理tick数据收集
class TickDataCollectionContext:
    """Tick数据收集上下文管理器"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.integration: Optional[TickDataIntegration] = None

    async def __aenter__(self):
        """进入上下文"""
        self.integration = TickDataIntegration(self.config_path)
        success = await self.integration.initialize()
        if not success:
            raise RuntimeError("Tick数据收集初始化失败")
        return self.integration

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self.integration:
            await self.integration.shutdown()
        return False  # 不抑制异常


# 使用示例：
#
# # 方法1：使用全局函数
# await initialize_tick_data_collection()
# try:
#     # 运行交易逻辑
#     await run_trading_strategy()
# finally:
#     await shutdown_tick_data_collection()
#
# # 方法2：使用装饰器
# @with_tick_data_collection("configs/my_config.yaml")
# async def my_trading_function():
#     # 交易逻辑
#     pass
#
# # 方法3：使用上下文管理器
# async with TickDataCollectionContext("configs/my_config.yaml") as tick_integration:
#     # 交易逻辑
#     status = await tick_integration.get_status()
#     await tick_integration.force_save()