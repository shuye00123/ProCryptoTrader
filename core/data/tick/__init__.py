"""
Tick数据处理模块

提供tick数据的收集、缓冲、转存和管理功能。
支持定期将内存中的tick数据异步转存为Parquet格式。

核心组件:
- TickDataManager: 核心管理器
- AsyncTickSaver: 异步转存器
- MemoryBuffer: 内存缓冲管理器
- DataIntegrityManager: 数据完整性管理

使用示例:
    config = TickDataConfig.from_yaml('configs/hf_breakout_live_config.yaml')
    manager = TickDataManager(config)
    await manager.start()

    # 收集tick数据
    await manager.collect_tick(ticker_data)
"""

from .tick_data_manager import TickDataManager
from .async_tick_saver import AsyncTickSaver
from .memory_buffer import MemoryBuffer
from .data_integrity_manager import DataIntegrityManager
from .config_models import TickDataConfig

__all__ = [
    'TickDataManager',
    'AsyncTickSaver',
    'MemoryBuffer',
    'DataIntegrityManager',
    'TickDataConfig'
]