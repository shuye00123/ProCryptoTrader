"""
异常处理助手

提供统一的异常处理机制，替换宽泛的Exception使用。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import logging
import traceback
from typing import Optional, Dict, Any, Type, List, Callable, Union
from functools import wraps
from datetime import datetime

from ..exceptions import (
    ProCryptoTraderError, DataError, TradingError, ExchangeError,
    RiskError, StrategyError, BacktestError, LiveTradingError,
    UtilsError, ValidationError, ExecutionError, PositionError,
    OrderError, SignalGenerationError
)


class ExceptionHandler:
    """
    统一异常处理器

    提供结构化的异常处理、记录和恢复机制。
    """

    def __init__(self, logger_name: str = "ExceptionHandler"):
        """
        初始化异常处理器

        Args:
            logger_name: 日志记录器名称
        """
        self.logger = logging.getLogger(logger_name)
        self._exception_handlers: Dict[Type[Exception], Callable] = {}
        self._fallback_handlers: List[Callable] = []
        self._error_stats: Dict[str, Dict[str, Any]] = {}
        self._setup_default_handlers()

    def handle_exception(self,
                        exception: Exception,
                        context: Optional[Dict[str, Any]] = None,
                        reraise: bool = True,
                        fallback_value: Any = None) -> Any:
        """
        处理异常

        Args:
            exception: 异常对象
            context: 异常上下文信息
            reraise: 是否重新抛出异常
            fallback_value: 发生异常时的默认返回值

        Returns:
            Any: 处理结果或fallback_value
        """
        try:
            # 记录异常统计
            self._record_exception_stats(exception, context)

            # 查找特定异常处理器
            exception_type = type(exception)
            if exception_type in self._exception_handlers:
                handler = self._exception_handlers[exception_type]
                result = handler(exception, context or {})
                self.logger.info(f"Exception handled by {exception_type.__name__} handler")
                return result

            # 查找父类异常处理器
            for exc_type, handler in self._exception_handlers.items():
                if isinstance(exception, exc_type):
                    result = handler(exception, context or {})
                    self.logger.info(f"Exception handled by {exc_type.__name__} handler")
                    return result

            # 使用fallback处理器
            for fallback_handler in self._fallback_handlers:
                try:
                    result = fallback_handler(exception, context or {})
                    if result is not None:
                        self.logger.info(f"Exception handled by fallback handler")
                        return result
                except Exception as handler_error:
                    self.logger.error(f"Fallback handler failed: {handler_error}")

            # 默认处理
            self._log_exception(exception, context)

            if reraise:
                raise

            return fallback_value

        except Exception as handling_error:
            self.logger.critical(f"Exception handling failed: {handling_error}")
            self.logger.critical(f"Original exception: {exception}")
            if reraise:
                raise exception
            return fallback_value

    def register_handler(self,
                         exception_type: Type[Exception],
                         handler: Callable[[Exception, Dict[str, Any]], Any]) -> None:
        """
        注册异常处理器

        Args:
            exception_type: 异常类型
            handler: 处理器函数
        """
        self._exception_handlers[exception_type] = handler
        self.logger.info(f"Registered handler for {exception_type.__name__}")

    def register_fallback_handler(self,
                                   handler: Callable[[Exception, Dict[str, Any]], Any]) -> None:
        """
        注册fallback处理器

        Args:
            handler: 处理器函数
        """
        self._fallback_handlers.append(handler)

    def get_error_stats(self) -> Dict[str, Any]:
        """
        获取错误统计信息

        Returns:
            Dict[str, Any]: 错误统计
        """
        return {
            'total_error_types': len(self._error_stats),
            'error_details': self._error_stats,
            'registered_handlers': len(self._exception_handlers),
            'fallback_handlers': len(self._fallback_handlers)
        }

    def _setup_default_handlers(self) -> None:
        """设置默认异常处理器"""
        # 数据相关异常
        self.register_handler(DataError, self._handle_data_error)
        self.register_handler(FileNotFoundError, self._handle_file_not_found)
        self.register_handler(PermissionError, self._handle_permission_error)

        # 交易相关异常
        self.register_handler(TradingError, self._handle_trading_error)
        self.register_handler(OrderError, self._handle_order_error)
        self.register_handler(PositionError, self._handle_position_error)
        self.register_handler(ExecutionError, self._handle_execution_error)

        # 交易所异常
        self.register_handler(ExchangeError, self._handle_exchange_error)
        self.register_handler(ConnectionError, self._handle_connection_error)

        # 策略异常
        self.register_handler(StrategyError, self._handle_strategy_error)
        self.register_handler(SignalGenerationError, self._handle_signal_generation_error)

        # 配置和验证异常
        self.register_handler(ValidationError, self._handle_validation_error)
        self.register_handler(ValueError, self._handle_value_error)

        # 网络和超时异常
        self.register_handler(TimeoutError, self._handle_timeout_error)
        self.register_handler(ConnectionRefusedError, self._handle_connection_refused)

        # 通用fallback处理器
        self.register_fallback_handler(self._handle_generic_error)

    def _record_exception_stats(self, exception: Exception, context: Optional[Dict[str, Any]]) -> None:
        """记录异常统计信息"""
        exc_type = exception.__class__.__name__

        if exc_type not in self._error_stats:
            self._error_stats[exc_type] = {
                'count': 0,
                'first_occurrence': datetime.now().isoformat(),
                'last_occurrence': None,
                'contexts': []
            }

        stats = self._error_stats[exc_type]
        stats['count'] += 1
        stats['last_occurrence'] = datetime.now().isoformat()

        if context:
            stats['contexts'].append({
                'timestamp': datetime.now().isoformat(),
                'context': context
            })
            # 只保留最近10个上下文
            if len(stats['contexts']) > 10:
                stats['contexts'] = stats['contexts'][-10:]

    def _log_exception(self, exception: Exception, context: Optional[Dict[str, Any]]) -> None:
        """记录异常信息"""
        exc_type = type(exception).__name__
        exc_msg = str(exception)
        exc_traceback = traceback.format_exc()

        log_msg = f"[{exc_type}] {exc_msg}"

        if context:
            log_msg += f" | Context: {context}"

        self.logger.error(log_msg)
        self.logger.debug(f"Exception traceback:\n{exc_traceback}")

    # 默认异常处理器
    def _handle_data_error(self, exception: DataError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据错误"""
        return {
            'error_type': 'data_error',
            'message': str(exception),
            'recovery_action': 'Check data source and format',
            'retry_recommended': True
        }

    def _handle_file_not_found(self, exception: FileNotFoundError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理文件未找到错误"""
        filename = str(exception.filename) if hasattr(exception, 'filename') else 'unknown'
        return {
            'error_type': 'file_not_found',
            'message': f"File not found: {filename}",
            'recovery_action': 'Create file or check file path',
            'retry_recommended': False
        }

    def _handle_permission_error(self, exception: PermissionError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理权限错误"""
        return {
            'error_type': 'permission_error',
            'message': str(exception),
            'recovery_action': 'Check file permissions',
            'retry_recommended': False
        }

    def _handle_trading_error(self, exception: TradingError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理交易错误"""
        return {
            'error_type': 'trading_error',
            'message': str(exception),
            'recovery_action': 'Check trading parameters and account status',
            'retry_recommended': True
        }

    def _handle_order_error(self, exception: OrderError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理订单错误"""
        return {
            'error_type': 'order_error',
            'message': str(exception),
            'recovery_action': 'Check order parameters and market conditions',
            'retry_recommended': True
        }

    def _handle_position_error(self, exception: PositionError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理持仓错误"""
        return {
            'error_type': 'position_error',
            'message': str(exception),
            'recovery_action': 'Check position size and availability',
            'retry_recommended': True
        }

    def _handle_execution_error(self, exception: ExecutionError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理执行错误"""
        return {
            'error_type': 'execution_error',
            'message': str(exception),
            'recovery_action': 'Check exchange connection and market status',
            'retry_recommended': True
        }

    def _handle_exchange_error(self, exception: ExchangeError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理交易所错误"""
        return {
            'error_type': 'exchange_error',
            'message': str(exception),
            'recovery_action': 'Check exchange API status and credentials',
            'retry_recommended': True
        }

    def _handle_connection_error(self, exception: ConnectionError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理连接错误"""
        return {
            'error_type': 'connection_error',
            'message': str(exception),
            'recovery_action': 'Check network connection and API endpoints',
            'retry_recommended': True
        }

    def _handle_strategy_error(self, exception: StrategyError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理策略错误"""
        return {
            'error_type': 'strategy_error',
            'message': str(exception),
            'recovery_action': 'Review strategy configuration and parameters',
            'retry_recommended': False
        }

    def _handle_signal_generation_error(self, exception: SignalGenerationError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理信号生成错误"""
        return {
            'error_type': 'signal_generation_error',
            'message': str(exception),
            'recovery_action': 'Check data quality and strategy logic',
            'retry_recommended': True
        }

    def _handle_validation_error(self, exception: ValidationError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理验证错误"""
        return {
            'error_type': 'validation_error',
            'message': str(exception),
            'recovery_action': 'Fix validation criteria or input data',
            'retry_recommended': False
        }

    def _handle_value_error(self, exception: ValueError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理值错误"""
        return {
            'error_type': 'value_error',
            'message': str(exception),
            'recovery_action': 'Check input values and expected ranges',
            'retry_recommended': False
        }

    def _handle_timeout_error(self, exception: TimeoutError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理超时错误"""
        return {
            'error_type': 'timeout_error',
            'message': str(exception),
            'recovery_action': 'Increase timeout or check network latency',
            'retry_recommended': True
        }

    def _handle_connection_refused(self, exception: ConnectionRefusedError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理连接被拒绝错误"""
        return {
            'error_type': 'connection_refused',
            'message': str(exception),
            'recovery_action': 'Check service availability and firewall settings',
            'retry_recommended': True
        }

    def _handle_generic_error(self, exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理通用错误"""
        return {
            'error_type': 'generic_error',
            'message': str(exception),
            'recovery_action': 'Review error context and logs',
            'retry_recommended': True
        }


# 全局异常处理器实例
global_exception_handler = ExceptionHandler("GlobalExceptionHandler")


# 便捷函数
def handle_exception(exception: Exception,
                    context: Optional[Dict[str, Any]] = None,
                    reraise: bool = True,
                    fallback_value: Any = None) -> Any:
    """
    便捷的异常处理函数

    Args:
        exception: 异常对象
        context: 异常上下文
        reraise: 是否重新抛出
        fallback_value: 默认返回值

    Returns:
        Any: 处理结果
    """
    return global_exception_handler.handle_exception(exception, context, reraise, fallback_value)


def safe_execute(func: Callable,
                 fallback_value: Any = None,
                 log_errors: bool = True,
                 context: Optional[Dict[str, Any]] = None) -> Any:
    """
    安全执行函数，自动处理异常

    Args:
        func: 要执行的函数
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误
        context: 执行上下文

    Returns:
        Any: 函数执行结果或fallback_value
    """
    try:
        return func()
    except Exception as e:
        if log_errors:
            global_exception_handler.handle_exception(e, context, reraise=False)
        return fallback_value


def exception_handler_decorator(exception_type: Optional[Type[Exception]] = None,
                               fallback_value: Any = None,
                               log_errors: bool = True,
                               context: Optional[Dict[str, Any]] = None):
    """
    异常处理装饰器

    Args:
        exception_type: 要捕获的异常类型，None表示捕获所有异常
        fallback_value: 异常时的默认返回值
        log_errors: 是否记录错误
        context: 执行上下文

    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if exception_type and not isinstance(e, exception_type):
                    raise

                if log_errors:
                    exec_context = context or {}
                    exec_context.update({
                        'function': func.__name__,
                        'args': args,
                        'kwargs': kwargs
                    })
                    global_exception_handler.handle_exception(e, exec_context, reraise=False)

                return fallback_value
        return wrapper
    return decorator