"""
快速执行引擎 - 高频突破策略专用执行系统

提供低延迟、高可靠性的订单执行服务，支持WebSocket和REST API
双重执行方式，专为秒级高频交易优化。

核心特性:
1. 低延迟订单提交
2. 多通道执行支持
3. 智能订单路由
4. 实时执行监控
5. 执行性能分析
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import json

from ..models.order import Order, OrderStatus, OrderType, OrderSide
from ..models.signal import Signal
from ..exchange.base_exchange import BaseExchange

# 设置日志
logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"           # 待执行
    SUBMITTED = "submitted"       # 已提交
    PARTIAL_FILLED = "partial_filled"  # 部分成交
    FILLED = "filled"            # 完全成交
    CANCELLED = "cancelled"       # 已取消
    REJECTED = "rejected"         # 被拒绝
    FAILED = "failed"             # 执行失败
    TIMEOUT = "timeout"           # 超时


class ExecutionPriority(Enum):
    """执行优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ExecutionRequest:
    """执行请求"""
    request_id: str
    signal: Signal
    priority: ExecutionPriority = ExecutionPriority.NORMAL
    created_time: datetime = field(default_factory=datetime.now)
    timeout_ms: int = 5000  # 5秒超时
    retry_count: int = 0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'request_id': self.request_id,
            'signal': self.signal.to_dict(),
            'priority': self.priority.value,
            'created_time': self.created_time.isoformat(),
            'timeout_ms': self.timeout_ms,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'metadata': self.metadata
        }


@dataclass
class ExecutionReport:
    """执行报告"""
    request_id: str
    status: ExecutionStatus
    order: Optional[Order] = None
    exchange_order_id: Optional[str] = None
    filled_amount: float = 0.0
    filled_price: float = 0.0
    average_price: float = 0.0
    commission: float = 0.0
    execution_time_ms: float = 0.0
    retry_count: int = 0
    error_message: Optional[str] = None
    created_time: datetime = field(default_factory=datetime.now)
    completed_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_successful(self) -> bool:
        """判断执行是否成功"""
        return self.status in [ExecutionStatus.FILLED, ExecutionStatus.PARTIAL_FILLED]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'request_id': self.request_id,
            'status': self.status.value,
            'order_id': self.order.order_id if self.order else None,
            'exchange_order_id': self.exchange_order_id,
            'filled_amount': self.filled_amount,
            'filled_price': self.filled_price,
            'average_price': self.average_price,
            'commission': self.commission,
            'execution_time_ms': self.execution_time_ms,
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'created_time': self.created_time.isoformat(),
            'completed_time': self.completed_time.isoformat() if self.completed_time else None,
            'is_successful': self.is_successful(),
            'metadata': self.metadata
        }


class OrderQueue:
    """订单队列管理器"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queues = {
            ExecutionPriority.CRITICAL: deque(),
            ExecutionPriority.HIGH: deque(),
            ExecutionPriority.NORMAL: deque(),
            ExecutionPriority.LOW: deque()
        }

    def put(self, request: ExecutionRequest):
        """添加执行请求"""
        queue = self.queues[request.priority]
        if len(queue) >= self.max_size:
            # 移除最旧的请求
            old_request = queue.popleft()
            logger.warning(f"队列已满，移除最旧请求: {old_request.request_id}")
        queue.append(request)

    def get(self) -> Optional[ExecutionRequest]:
        """获取下一个执行请求"""
        for priority in [ExecutionPriority.CRITICAL, ExecutionPriority.HIGH,
                       ExecutionPriority.NORMAL, ExecutionPriority.LOW]:
            if self.queues[priority]:
                return self.queues[priority].popleft()
        return None

    def size(self) -> int:
        """获取队列大小"""
        return sum(len(queue) for queue in self.queues.values())

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self.size() == 0


class FastExecutionEngine:
    """快速执行引擎

    提供低延迟的订单执行服务，支持多种执行策略和监控
    """

    def __init__(self, exchange: BaseExchange, config: Optional[Dict[str, Any]] = None):
        """
        初始化快速执行引擎

        Args:
            exchange: 交易所接口
            config: 执行配置
        """
        self.exchange = exchange
        self.config = config or {}

        # 执行配置
        self.use_websocket = self.config.get('use_websocket', True)
        self.max_concurrent_requests = self.config.get('max_concurrent_requests', 10)
        self.default_timeout = self.config.get('default_timeout_ms', 5000)
        self.enable_batch_execution = self.config.get('enable_batch_execution', False)

        # 执行队列
        self.order_queue = OrderQueue(max_size=self.config.get('queue_size', 1000))

        # 执行状态
        self.active_requests: Dict[str, ExecutionRequest] = {}
        self.execution_reports: Dict[str, ExecutionReport] = {}
        self.pending_orders: Dict[str, Order] = {}

        # 执行统计
        self.stats = {
            'total_requests': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'timeout_executions': 0,
            'average_execution_time_ms': 0.0,
            'min_execution_time_ms': float('inf'),
            'max_execution_time_ms': 0.0,
            'total_volume': 0.0,
            'total_commission': 0.0,
            'queue_size': 0,
            'active_requests': 0
        }

        # 性能监控
        self.execution_times = deque(maxlen=1000)
        self.error_log = deque(maxlen=100)

        # 回调函数
        self.execution_callbacks: List[Callable[[ExecutionReport], None]] = []

        # 执行任务
        self.execution_task: Optional[asyncio.Task] = None
        self.monitor_task: Optional[asyncio.Task] = None
        self.is_running = False

        # 并发控制
        self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        logger.info("快速执行引擎初始化完成")

    async def start(self):
        """启动执行引擎"""
        if self.is_running:
            logger.warning("执行引擎已在运行")
            return

        self.is_running = True

        # 启动执行任务
        self.execution_task = asyncio.create_task(self._execution_loop())
        self.monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("快速执行引擎已启动")

    async def stop(self):
        """停止执行引擎"""
        if not self.is_running:
            return

        self.is_running = False

        # 取消任务
        if self.execution_task:
            self.execution_task.cancel()
        if self.monitor_task:
            self.monitor_task.cancel()

        # 等待任务完成
        try:
            await asyncio.gather(self.execution_task, self.monitor_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

        logger.info("快速执行引擎已停止")

    async def execute_signal(self, signal: Signal,
                            priority: ExecutionPriority = ExecutionPriority.NORMAL,
                            timeout_ms: Optional[int] = None,
                            max_retries: int = 2) -> ExecutionReport:
        """
        执行交易信号

        Args:
            signal: 交易信号
            priority: 执行优先级
            timeout_ms: 超时时间（毫秒）
            max_retries: 最大重试次数

        Returns:
            执行报告
        """
        # 生成请求ID
        request_id = str(uuid.uuid4())

        # 创建执行请求
        request = ExecutionRequest(
            request_id=request_id,
            signal=signal,
            priority=priority,
            timeout_ms=timeout_ms or self.default_timeout,
            max_retries=max_retries,
            metadata={
                'strategy': signal.metadata.get('strategy', 'unknown'),
                'symbol': signal.symbol,
                'signal_type': signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
            }
        )

        # 添加到队列
        self.order_queue.put(request)
        self.stats['total_requests'] += 1

        logger.debug(f"执行信号已入队: {signal.symbol} {request_id}")

        # 等待执行完成
        return await self._wait_for_completion(request_id, request.timeout_ms)

    async def execute_signal_batch(self, signals: List[Signal],
                                 priority: ExecutionPriority = ExecutionPriority.NORMAL) -> List[ExecutionReport]:
        """批量执行交易信号"""
        if not self.enable_batch_execution:
            # 逐个执行
            reports = []
            for signal in signals:
                report = await self.execute_signal(signal, priority)
                reports.append(report)
            return reports

        # 批量执行（需要实现）
        reports = []
        for signal in signals:
            report = await self.execute_signal(signal, priority)
            reports.append(report)

        return reports

    async def _execution_loop(self):
        """执行循环"""
        logger.info("执行循环已启动")

        while self.is_running:
            try:
                # 获取下一个执行请求
                request = self.order_queue.get()
                if not request:
                    await asyncio.sleep(0.001)  # 1ms
                    continue

                # 异步执行请求
                asyncio.create_task(self._execute_request(request))

            except Exception as e:
                logger.error(f"执行循环异常: {e}")
                await asyncio.sleep(0.1)

    async def _execute_request(self, request: ExecutionRequest):
        """执行单个请求"""
        async with self.semaphore:  # 并发控制
            start_time = time.time()

            try:
                self.active_requests[request.request_id] = request

                # 执行交易信号
                report = await self._perform_execution(request)

                # 记录执行时间
                execution_time = (time.time() - start_time) * 1000
                report.execution_time_ms = execution_time

                # 更新统计
                self._update_execution_stats(report)

                # 存储报告
                self.execution_reports[request.request_id] = report

                # 调用回调函数
                await self._call_execution_callbacks(report)

                # 清理活跃请求
                self.active_requests.pop(request.request_id, None)

                logger.debug(f"执行完成: {request.request_id}, "
                           f"状态: {report.status.value}, "
                           f"耗时: {execution_time:.2f}ms")

            except Exception as e:
                logger.error(f"执行请求失败 {request.request_id}: {e}")
                self.log_error("Execution failed", str(e))

                # 创建失败报告
                error_report = ExecutionReport(
                    request_id=request.request_id,
                    status=ExecutionStatus.FAILED,
                    error_message=str(e),
                    execution_time_ms=(time.time() - start_time) * 1000,
                    retry_count=request.retry_count
                )

                self.execution_reports[request.request_id] = error_report
                self.active_requests.pop(request.request_id, None)

    async def _perform_execution(self, request: ExecutionRequest) -> ExecutionReport:
        """执行具体的交易操作"""
        try:
            # 1. 预检查
            if not self._pre_trade_check(request.signal):
                return ExecutionReport(
                    request_id=request.request_id,
                    status=ExecutionStatus.REJECTED,
                    error_message="Pre-trade check failed",
                    retry_count=request.retry_count
                )

            # 2. 创建订单
            order = self._create_order(request.signal)

            # 3. 选择执行方式
            if self.use_websocket and hasattr(self.exchange, 'place_order_websocket'):
                result = await self._execute_via_websocket(order)
            else:
                result = await self._execute_via_rest(order)

            # 4. 处理执行结果
            return self._process_execution_result(request, order, result)

        except Exception as e:
            logger.error(f"执行操作失败 {request.request_id}: {e}")
            raise

    async def _execute_via_websocket(self, order: Order) -> Dict[str, Any]:
        """通过WebSocket执行订单"""
        try:
            result = await self.exchange.place_order_websocket({
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.order_type.value,
                'quantity': order.amount,
                'price': order.price,
                'timeInForce': 'GTC',  # Good Till Cancel
                'newClientOrderId': order.order_id
            })

            return {
                'success': True,
                'exchange_order_id': result.get('orderId'),
                'status': result.get('status', 'NEW'),
                'raw_response': result
            }

        except Exception as e:
            logger.error(f"WebSocket执行失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _execute_via_rest(self, order: Order) -> Dict[str, Any]:
        """通过REST API执行订单"""
        try:
            result = self.exchange.place_order({
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.order_type.value,
                'quantity': order.amount,
                'price': order.price,
                'timeInForce': 'GTC'
            })

            return {
                'success': True,
                'exchange_order_id': result.get('orderId'),
                'status': result.get('status', 'NEW'),
                'raw_response': result
            }

        except Exception as e:
            logger.error(f"REST执行失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _process_execution_result(self, request: ExecutionRequest,
                                  order: Order, result: Dict[str, Any]) -> ExecutionReport:
        """处理执行结果"""
        if result['success']:
            # 执行成功
            return ExecutionReport(
                request_id=request.request_id,
                status=ExecutionStatus.SUBMITTED,
                order=order,
                exchange_order_id=result['exchange_order_id'],
                filled_amount=order.filled,
                filled_price=order.price,
                retry_count=request.retry_count,
                metadata={
                    'exchange': 'binance',
                    'execution_method': 'websocket' if self.use_websocket else 'rest'
                }
            )
        else:
            # 执行失败，检查是否需要重试
            if request.retry_count < request.max_retries:
                request.retry_count += 1
                self.order_queue.put(request)  # 重新入队
                logger.info(f"执行失败，重新入队: {request.request_id} (重试 {request.retry_count}/{request.max_retries})")

            return ExecutionReport(
                request_id=request.request_id,
                status=ExecutionStatus.REJECTED,
                error_message=result.get('error', 'Unknown error'),
                retry_count=request.retry_count
            )

    async def _wait_for_completion(self, request_id: str, timeout_ms: int) -> ExecutionReport:
        """等待执行完成"""
        timeout_seconds = timeout_ms / 1000.0
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if request_id in self.execution_reports:
                report = self.execution_reports[request_id]
                if report.status in [ExecutionStatus.FILLED, ExecutionStatus.FAILED,
                                  ExecutionStatus.REJECTED, ExecutionStatus.TIMEOUT]:
                    return report
            await asyncio.sleep(0.01)  # 10ms

        # 超时
        timeout_report = ExecutionReport(
            request_id=request_id,
            status=ExecutionStatus.TIMEOUT,
            error_message=f"Execution timeout after {timeout_ms}ms"
        )
        self.execution_reports[request_id] = timeout_report
        return timeout_report

    async def _monitor_loop(self):
        """监控循环"""
        logger.info("监控循环已启动")

        while self.is_running:
            try:
                # 更新统计信息
                self.stats['queue_size'] = self.order_queue.size()
                self.stats['active_requests'] = len(self.active_requests)

                # 监控订单状态
                await self._monitor_order_status()

                # 清理过期数据
                await self._cleanup_expired_data()

                await asyncio.sleep(1.0)  # 1秒

            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(1.0)

    async def _monitor_order_status(self):
        """监控订单状态"""
        for report in list(self.execution_reports.values()):
            if (report.status == ExecutionStatus.SUBMITTED and
                report.exchange_order_id and
                report.exchange_order_id not in self.pending_orders):

                # 获取订单状态
                try:
                    order_info = self.exchange.get_order(report.exchange_order_id)
                    if order_info:
                        self._update_order_report(report, order_info)
                except Exception as e:
                    logger.error(f"获取订单状态失败 {report.exchange_order_id}: {e}")

    def _update_order_report(self, report: ExecutionReport, order_info: Dict):
        """更新订单报告"""
        try:
            # 解析订单状态
            exchange_status = order_info.get('status', '')
            filled_amount = float(order_info.get('executedQty', 0))
            avg_price = float(order_info.get('avgPrice', 0)) or report.filled_price

            # 更新报告
            report.filled_amount = filled_amount
            report.average_price = avg_price

            if exchange_status == 'FILLED':
                report.status = ExecutionStatus.FILLED
                report.completed_time = datetime.now()
            elif exchange_status == 'PARTIALLY_FILLED':
                report.status = ExecutionStatus.PARTIAL_FILLED
            elif exchange_status == 'CANCELED':
                report.status = ExecutionStatus.CANCELLED
                report.completed_time = datetime.now()
            elif exchange_status == 'REJECTED':
                report.status = ExecutionStatus.REJECTED
                report.completed_time = datetime.now()

        except Exception as e:
            logger.error(f"更新订单报告失败: {e}")

    async def _cleanup_expired_data(self):
        """清理过期数据"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=24)

        # 清理执行报告
        expired_reports = [
            request_id for request_id, report in self.execution_reports.items()
            if report.created_time < cutoff_time
        ]

        for request_id in expired_reports:
            del self.execution_reports[request_id]

        if expired_reports:
            logger.debug(f"清理了 {len(expired_reports)} 个过期执行报告")

    def _pre_trade_check(self, signal: Signal) -> bool:
        """预交易检查"""
        # 基本验证
        if not signal.symbol or signal.amount <= 0:
            return False

        # 价格验证
        if signal.price and signal.price <= 0:
            return False

        # 这里可以添加更多的预检查逻辑
        return True

    def _create_order(self, signal: Signal) -> Order:
        """创建订单对象"""
        # 确定订单类型和方向
        order_type = OrderType.MARKET if signal.price is None else OrderType.LIMIT

        if signal.signal_type.value in ['open_long', 'increase_long']:
            side = OrderSide.BUY
        elif signal.signal_type.value in ['open_short', 'increase_short']:
            side = OrderSide.SELL
        elif signal.signal_type.value in ['close_long']:
            side = OrderSide.SELL
        elif signal.signal_type.value in ['close_short']:
            side = OrderSide.BUY
        else:
            # 默认做多
            side = OrderSide.BUY

        return Order(
            order_id=str(uuid.uuid4()),
            symbol=signal.symbol,
            order_type=order_type,
            side=side,
            amount=signal.amount,
            price=signal.price or 0.0,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit
        )

    def _update_execution_stats(self, report: ExecutionReport):
        """更新执行统计"""
        self.execution_times.append(report.execution_time_ms)

        # 更新成功/失败统计
        if report.is_successful():
            self.stats['successful_executions'] += 1
        else:
            self.stats['failed_executions'] += 1

        if report.status == ExecutionStatus.TIMEOUT:
            self.stats['timeout_executions'] += 1

        # 更新执行时间统计
        if self.execution_times:
            times = list(self.execution_times)
            self.stats['average_execution_time_ms'] = sum(times) / len(times)
            self.stats['min_execution_time_ms'] = min(times)
            self.stats['max_execution_time_ms'] = max(times)

        # 更新交易量和手续费
        if report.order:
            self.stats['total_volume'] += report.filled_amount * report.filled_price
            self.stats['total_commission'] += report.commission

    async def _call_execution_callbacks(self, report: ExecutionReport):
        """调用执行回调函数"""
        for callback in self.execution_callbacks:
            try:
                await callback(report) if asyncio.iscoroutinefunction(callback) else callback(report)
            except Exception as e:
                logger.error(f"执行回调函数失败: {e}")

    def add_execution_callback(self, callback: Callable[[ExecutionReport], None]):
        """添加执行回调函数"""
        self.execution_callbacks.append(callback)

    def get_execution_report(self, request_id: str) -> Optional[ExecutionReport]:
        """获取执行报告"""
        return self.execution_reports.get(request_id)

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        stats = self.stats.copy()

        # 添加额外统计
        if self.execution_times:
            times = list(self.execution_times)
            stats['execution_time_p95'] = np.percentile(times, 95)
            stats['execution_time_p99'] = np.percentile(times, 99)

        # 计算成功率
        total_executions = stats['successful_executions'] + stats['failed_executions']
        if total_executions > 0:
            stats['success_rate'] = stats['successful_executions'] / total_executions

        return stats

    def log_error(self, operation: str, error_message: str):
        """记录错误"""
        self.error_log.append({
            'timestamp': datetime.now(),
            'operation': operation,
            'error': error_message
        })

    def get_error_log(self, limit: int = 50) -> List[Dict]:
        """获取错误日志"""
        return list(self.error_log)[-limit:]


# 示例使用
async def example_usage():
    """示例用法"""
    from ..exchange.binance_api import BinanceAPI
    from ..models.signal import Signal, SignalType

    # 创建交易所实例（测试）
    exchange_config = {
        'api_key': 'test_key',
        'secret': 'test_secret',
        'sandbox': True
    }
    exchange = BinanceAPI(exchange_config)

    # 创建快速执行引擎
    execution_config = {
        'use_websocket': False,  # 示例中使用REST
        'max_concurrent_requests': 5,
        'default_timeout_ms': 3000
    }
    engine = FastExecutionEngine(exchange, execution_config)

    try:
        # 启动引擎
        await engine.start()

        # 创建测试信号
        signal = Signal(
            signal_type=SignalType.OPEN_LONG,
            symbol="BTCUSDT",
            amount=0.001,
            price=50000.0,
            confidence=0.8
        )

        # 执行信号
        print("执行交易信号...")
        report = await engine.execute_signal(signal, ExecutionPriority.HIGH)

        # 打印结果
        print(f"执行结果: {report.status.value}")
        print(f"执行时间: {report.execution_time_ms:.2f}ms")
        if report.error_message:
            print(f"错误信息: {report.error_message}")

        # 获取统计信息
        stats = engine.get_execution_stats()
        print(f"\n执行统计:")
        print(f"总请求数: {stats['total_requests']}")
        print(f"成功率: {stats.get('success_rate', 0):.2%}")
        print(f"平均执行时间: {stats['average_execution_time_ms']:.2f}ms")

        # 等待一段时间
        await asyncio.sleep(5)

    finally:
        # 停止引擎
        await engine.stop()


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    asyncio.run(example_usage())