"""
Tick数据配置模型

定义tick数据转存相关的配置参数和数据结构。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """存储配置"""
    base_path: str = "data/tick"
    exchange: str = "binance"
    compression: str = "snappy"
    file_split_hours: int = 1

    def __post_init__(self):
        """验证配置参数"""
        if self.compression not in ["snappy", "gzip", "brotli", "none"]:
            raise ValueError(f"不支持的压缩算法: {self.compression}")

        if self.file_split_hours < 1 or self.file_split_hours > 24:
            raise ValueError("文件分割时间必须在1-24小时之间")


@dataclass
class BufferConfig:
    """内存缓冲配置"""
    max_size_mb: int = 100
    max_ticks_per_symbol: int = 50000
    cleanup_ratio: float = 0.8

    def __post_init__(self):
        """验证配置参数"""
        if self.max_size_mb < 10 or self.max_size_mb > 1000:
            raise ValueError("最大缓冲大小必须在10-1000MB之间")

        if self.max_ticks_per_symbol < 1000 or self.max_ticks_per_symbol > 1000000:
            raise ValueError("每个交易对最大tick数必须在1000-1000000之间")

        if not 0.5 <= self.cleanup_ratio <= 0.95:
            raise ValueError("清理比例必须在0.5-0.95之间")


@dataclass
class PerformanceConfig:
    """性能配置"""
    batch_size: int = 1000
    max_concurrent_writes: int = 4
    write_timeout_seconds: int = 30

    def __post_init__(self):
        """验证配置参数"""
        if self.batch_size < 100 or self.batch_size > 10000:
            raise ValueError("批量大小必须在100-10000之间")

        if self.max_concurrent_writes < 1 or self.max_concurrent_writes > 16:
            raise ValueError("最大并发写入数必须在1-16之间")

        if self.write_timeout_seconds < 5 or self.write_timeout_seconds > 300:
            raise ValueError("写入超时时间必须在5-300秒之间")


@dataclass
class IntegrityConfig:
    """数据完整性配置"""
    enable_validation: bool = True
    checksum_enabled: bool = True
    auto_repair: bool = False


@dataclass
class MonitoringConfig:
    """监控配置"""
    enable_metrics: bool = True
    log_level: str = "INFO"
    alert_memory_threshold: float = 80.0

    def __post_init__(self):
        """验证配置参数"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level not in valid_levels:
            raise ValueError(f"无效的日志级别: {self.log_level}")

        if not 50.0 <= self.alert_memory_threshold <= 95.0:
            raise ValueError("内存告警阈值必须在50-95%之间")


@dataclass
class TickDataConfig:
    """Tick数据转存配置"""
    # 基础配置
    enabled: bool = True
    save_interval_seconds: int = 300  # 5分钟

    # 子配置
    storage: StorageConfig = field(default_factory=StorageConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    integrity: IntegrityConfig = field(default_factory=IntegrityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    def __post_init__(self):
        """验证配置参数"""
        if self.save_interval_seconds < 60 or self.save_interval_seconds > 3600:
            raise ValueError("保存间隔必须在60-3600秒之间")

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'TickDataConfig':
        """从字典创建配置对象"""
        tick_config = config_dict.get('tick_data_persistence', {})

        # 创建子配置对象
        storage_config = StorageConfig(**tick_config.get('storage', {}))
        buffer_config = BufferConfig(**tick_config.get('buffer', {}))
        performance_config = PerformanceConfig(**tick_config.get('performance', {}))
        integrity_config = IntegrityConfig(**tick_config.get('integrity', {}))
        monitoring_config = MonitoringConfig(**tick_config.get('monitoring', {}))

        return cls(
            enabled=tick_config.get('enabled', True),
            save_interval_seconds=tick_config.get('save_interval_seconds', 300),
            storage=storage_config,
            buffer=buffer_config,
            performance=performance_config,
            integrity=integrity_config,
            monitoring=monitoring_config
        )

    @classmethod
    def from_yaml(cls, config_path: str) -> 'TickDataConfig':
        """从YAML文件加载配置"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
                return cls()

            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)

            return cls.from_dict(config_dict)

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            logger.info("使用默认配置")
            return cls()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'enabled': self.enabled,
            'save_interval_seconds': self.save_interval_seconds,
            'storage': {
                'base_path': self.storage.base_path,
                'exchange': self.storage.exchange,
                'compression': self.storage.compression,
                'file_split_hours': self.storage.file_split_hours
            },
            'buffer': {
                'max_size_mb': self.buffer.max_size_mb,
                'max_ticks_per_symbol': self.buffer.max_ticks_per_symbol,
                'cleanup_ratio': self.buffer.cleanup_ratio
            },
            'performance': {
                'batch_size': self.performance.batch_size,
                'max_concurrent_writes': self.performance.max_concurrent_writes,
                'write_timeout_seconds': self.performance.write_timeout_seconds
            },
            'integrity': {
                'enable_validation': self.integrity.enable_validation,
                'checksum_enabled': self.integrity.checksum_enabled,
                'auto_repair': self.integrity.auto_repair
            },
            'monitoring': {
                'enable_metrics': self.monitoring.enable_metrics,
                'log_level': self.monitoring.log_level,
                'alert_memory_threshold': self.monitoring.alert_memory_threshold
            }
        }

    def get_storage_path(self, symbol: str, timestamp: int) -> Path:
        """获取存储文件路径

        Args:
            symbol: 交易对符号 (如 BTC/USDT)
            timestamp: Unix时间戳

        Returns:
            完整的存储文件路径
        """
        from datetime import datetime, timezone

        # 标准化符号格式
        normalized_symbol = symbol.replace('/', '-')

        # 安全的时间戳转换
        try:
            # 检查时间戳是否在合理范围内 (2000-2030年)
            import time
            current_ms = int(time.time() * 1000)
            min_timestamp = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
            max_timestamp = int(datetime(2030, 12, 31, tzinfo=timezone.utc).timestamp() * 1000)

            # 如果时间戳异常，使用当前时间
            safe_timestamp = timestamp
            if timestamp < min_timestamp or timestamp > max_timestamp:
                logger.warning(f"[CONFIG_PATH] 异常时间戳: {timestamp}, 使用当前时间: {current_ms}")
                safe_timestamp = current_ms

            # 如果时间戳是秒级而不是毫秒级，转换为毫秒级
            if safe_timestamp < 1e12:
                safe_timestamp *= 1000
                logger.info(f"[CONFIG_PATH] 秒级时间戳转换为毫秒级: {timestamp} → {safe_timestamp}")

            # 转换为datetime (注意：fromtimestamp期望秒级时间戳)
            dt = datetime.fromtimestamp(safe_timestamp / 1000, tz=timezone.utc)
            logger.info(f"[CONFIG_PATH] 时间戳转换成功: {safe_timestamp} → {dt}")

        except Exception as e:
            logger.error(f"[CONFIG_PATH] 时间戳转换失败: {timestamp}, 错误: {e}")
            # 使用当前时间作为备选
            import time
            current_ms = int(time.time() * 1000)
            dt = datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc)
            logger.info(f"[CONFIG_PATH] 使用当前时间: {dt}")

        # 构建目录结构: base_path/exchange/symbol/YYYY/MM/DD/
        file_path = (
            Path(self.storage.base_path) /
            self.storage.exchange /
            normalized_symbol /
            f"{dt.year:04d}" /
            f"{dt.month:02d}" /
            f"{dt.day:02d}"
        )

        # 构建文件名: symbol_YYYYMMDDHH.parquet
        hour_str = f"{dt.hour:02d}"
        filename = f"{normalized_symbol}_{dt.year:04d}{dt.month:02d}{dt.day:02d}{hour_str}.parquet"

        return file_path / filename