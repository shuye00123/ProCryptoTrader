"""
业务异常类模块

定义系统中使用的各种业务异常，遵循RIPER-5原则。
提供具体的异常类型，避免使用过于宽泛的Exception。
"""

from typing import Optional, Any, Dict


class ProCryptoTraderError(Exception):
    """ProCryptoTrader系统基础异常类"""

    def __init__(self, message: str, error_code: Optional[str] = None,
                 context: Optional[Dict[str, Any]] = None):
        """
        初始化异常

        Args:
            message: 错误消息
            error_code: 错误代码
            context: 错误上下文信息
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'context': self.context
        }


# 数据相关异常
class DataError(ProCryptoTraderError):
    """数据相关异常基类"""
    pass


class DataFetchError(DataError):
    """数据获取异常"""
    pass


class DataValidationError(DataError):
    """数据验证异常"""
    pass


class DataStorageError(DataError):
    """数据存储异常"""
    pass


class StorageError(ProCryptoTraderError):
    """存储操作异常基类"""
    pass


class InsufficientDataError(DataError):
    """数据不足异常"""
    pass


# 交易相关异常
class TradingError(ProCryptoTraderError):
    """交易相关异常基类"""
    pass


class OrderError(TradingError):
    """订单异常"""
    pass


class OrderRejectedError(OrderError):
    """订单被拒绝异常"""
    pass


class OrderTimeoutError(OrderError):
    """订单超时异常"""
    pass


class PositionError(TradingError):
    """持仓异常"""
    pass


class InsufficientPositionError(PositionError):
    """持仓不足异常"""
    pass


class PositionNotFoundError(PositionError):
    """持仓不存在异常"""
    pass


# 策略相关异常
class StrategyError(ProCryptoTraderError):
    """策略相关异常基类"""
    pass


class StrategyNotFoundError(StrategyError):
    """策略不存在异常"""
    pass


class StrategyConfigError(StrategyError):
    """策略配置异常"""
    pass


class SignalGenerationError(StrategyError):
    """信号生成异常"""
    pass


# 交易所相关异常
class ExchangeError(ProCryptoTraderError):
    """交易所相关异常基类"""
    pass


class ExchangeConnectionError(ExchangeError):
    """交易所连接异常"""
    pass


class ExchangeAPIError(ExchangeError):
    """交易所API异常"""
    pass


class RateLimitError(ExchangeError):
    """速率限制异常"""
    pass


class AuthenticationError(ExchangeError):
    """认证异常"""
    pass


# 风险管理相关异常
class RiskError(ProCryptoTraderError):
    """风险管理相关异常基类"""
    pass


class RiskLimitExceededError(RiskError):
    """风险限制超出异常"""
    pass


class PositionSizeError(RiskError):
    """仓位大小异常"""
    pass


class StopLossError(RiskError):
    """止损异常"""
    pass


class DrawdownExceededError(RiskError):
    """回撤超出异常"""
    pass


# 回测相关异常
class BacktestError(ProCryptoTraderError):
    """回测相关异常基类"""
    pass


class BacktestConfigError(BacktestError):
    """回测配置异常"""
    pass


class InsufficientHistoryError(BacktestError):
    """历史数据不足异常"""
    pass


# 配置相关异常
class ConfigError(ProCryptoTraderError):
    """配置相关异常基类"""
    pass


class ConfigValidationError(ConfigError):
    """配置验证异常"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置文件未找到异常"""
    pass


# 向后兼容性别名
ConfigurationError = ConfigError


# 分析相关异常
class AnalysisError(ProCryptoTraderError):
    """分析相关异常基类"""
    pass


class MetricsCalculationError(AnalysisError):
    """指标计算异常"""
    pass


class ReportGenerationError(AnalysisError):
    """报告生成异常"""
    pass


# 实时交易相关异常
class LiveTradingError(ProCryptoTraderError):
    """实时交易相关异常基类"""
    pass


class ExecutionError(LiveTradingError):
    """执行异常"""
    pass


class SlippageError(ExecutionError):
    """滑点异常"""
    pass


class LiquidityError(ExecutionError):
    """流动性异常"""
    pass


# 工具类异常
class UtilsError(ProCryptoTraderError):
    """工具类异常基类"""
    pass


class LoggerError(UtilsError):
    """日志异常"""
    pass


class ValidationError(UtilsError):
    """验证异常"""
    pass


class CalculationError(UtilsError):
    """计算异常"""
    pass


# 便利函数
def create_data_error(message: str, error_code: Optional[str] = None,
                     context: Optional[Dict[str, Any]] = None) -> DataError:
    """创建数据异常的便利函数"""
    return DataError(message, error_code, context)


def create_trading_error(message: str, error_code: Optional[str] = None,
                        context: Optional[Dict[str, Any]] = None) -> TradingError:
    """创建交易异常的便利函数"""
    return TradingError(message, error_code, context)


def create_exchange_error(message: str, error_code: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None) -> ExchangeError:
    """创建交易所异常的便利函数"""
    return ExchangeError(message, error_code, context)


def create_risk_error(message: str, error_code: Optional[str] = None,
                     context: Optional[Dict[str, Any]] = None) -> RiskError:
    """创建风险异常的便利函数"""
    return RiskError(message, error_code, context)


def create_strategy_error(message: str, error_code: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None) -> StrategyError:
    """创建策略异常的便利函数"""
    return StrategyError(message, error_code, context)


# 错误代码常量
class ErrorCodes:
    """错误代码常量"""

    # 数据错误代码 (1000-1999)
    DATA_FETCH_FAILED = "E1001"
    DATA_VALIDATION_FAILED = "E1002"
    DATA_STORAGE_FAILED = "E1003"
    INSUFFICIENT_DATA = "E1004"

    # 交易错误代码 (2000-2999)
    ORDER_FAILED = "E2001"
    ORDER_REJECTED = "E2002"
    ORDER_TIMEOUT = "E2003"
    POSITION_INSUFFICIENT = "E2004"
    POSITION_NOT_FOUND = "E2005"

    # 策略错误代码 (3000-3999)
    STRATEGY_NOT_FOUND = "E3001"
    STRATEGY_CONFIG_INVALID = "E3002"
    SIGNAL_GENERATION_FAILED = "E3003"

    # 交易所错误代码 (4000-4999)
    EXCHANGE_CONNECTION_FAILED = "E4001"
    EXCHANGE_API_ERROR = "E4002"
    RATE_LIMIT_EXCEEDED = "E4003"
    AUTHENTICATION_FAILED = "E4004"

    # 风险管理错误代码 (5000-5999)
    RISK_LIMIT_EXCEEDED = "E5001"
    POSITION_SIZE_INVALID = "E5002"
    STOP_LOSS_FAILED = "E5003"
    DRAWDOWN_EXCEEDED = "E5004"

    # 回测错误代码 (6000-6999)
    BACKTEST_CONFIG_INVALID = "E6001"
    INSUFFICIENT_HISTORY = "E6002"

    # 配置错误代码 (7000-7999)
    CONFIG_VALIDATION_FAILED = "E7001"
    CONFIG_NOT_FOUND = "E7002"

    # 分析错误代码 (8000-8999)
    METRICS_CALCULATION_FAILED = "E8001"
    REPORT_GENERATION_FAILED = "E8002"

    # 实时交易错误代码 (9000-9999)
    EXECUTION_FAILED = "E9001"
    SLIPPAGE_EXCESSIVE = "E9002"
    LIQUIDITY_INSUFFICIENT = "E9003"


# 缓存相关异常
class CacheError(ProCryptoTraderError):
    """缓存操作异常"""
    pass


# 批处理相关异常
class BatchError(ProCryptoTraderError):
    """批处理操作异常"""
    pass


# 仓储相关异常
class RepositoryError(ProCryptoTraderError):
    """仓储操作异常"""
    pass


# 服务相关异常
class ServiceError(ProCryptoTraderError):
    """服务层异常"""
    pass