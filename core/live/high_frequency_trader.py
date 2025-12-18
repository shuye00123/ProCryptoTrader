"""
高频交易模块

专门为高频突破策略设计的异步交易执行器，支持WebSocket实时数据流、
低延迟信号处理和快速订单执行。

遵循RIPER-5原则：
- Risk first：多层风险控制和实时监控
- Integration minimal：与现有架构最小侵入集成
- Predictability：确定性的事件处理流程
- Expandability：模块化设计便于扩展
- Realistic evaluation：完整的性能监控和统计
"""

import asyncio
import logging
import signal
import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from ..strategy.high_frequency_breakout import HighFrequencyBreakoutStrategy
from ..exchange.binance_api import BinanceAPI
from ..trading.fast_execution import FastExecutionEngine
from ..utils.config import load_config
from ..utils.logger import get_logger, setup_logging
from ..utils.async_logger_fix import setup_async_logging_fix

# 应用异步日志修复 - 确保所有异步线程的日志都能正确输出
# 延迟到配置加载后再调用，这样可以正确设置日志级别

# 设置日志
logger = get_logger("HighFrequencyTrader")


class HighFrequencyTrader:
    """高频交易器

    专门为高频策略设计的异步交易执行器，支持：
    - WebSocket实时数据流处理
    - 事件驱动的信号生成和执行
    - 多层次风险控制
    - 实时性能监控
    """

    def __init__(self, config_path: str):
        """
        初始化高频交易器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = load_config(self.config_path)

        # 设置日志级别（基于配置文件）
        self._setup_logging_from_config()

        # 基础配置
        self.is_running = False
        self.shutdown_requested = False

        # 初始化组件
        self.strategy = None
        self.exchange = None
        self.execution_engine = None

        # 运行统计
        self.start_time = None
        self.stats = {
            'signals_generated': 0,
            'signals_executed': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'order_execution_latency_ms': [],
            'signal_processing_latency_ms': [],
            'websocket_messages': 0,
            'errors': 0,
            'last_update': None
        }

        # 设置信号处理
        self._setup_signal_handlers()

        logger.info(f"高频交易器初始化完成，配置文件: {config_path}")

    def _setup_logging_from_config(self):
        """从配置文件设置日志级别"""
        try:
            logging_config = self.config.get('logging', {})
            log_level = logging_config.get('level', 'INFO').upper()

            # 只设置特定模块的日志级别，不重复设置全局日志
            module_configs = logging_config.get('modules', {})

            # 设置当前logger的级别
            logger.setLevel(getattr(logging, log_level, logging.INFO))

            # 应用异步日志修复，传递配置的日志级别
            setup_async_logging_fix(log_level=log_level)

            logger.info(f"日志级别设置为: {log_level}")

            # 设置特定模块的日志级别
            for module_name, module_level in module_configs.items():
                module_logger = logging.getLogger(module_name)
                module_logger.setLevel(getattr(logging, module_level.upper(), logging.INFO))

        except Exception as e:
            logger.warning(f"设置日志配置失败，使用默认设置: {e}")
            # 使用默认设置
            logger.setLevel(logging.INFO)
            # 即使失败也要应用异步日志修复
            setup_async_logging_fix(log_level="INFO")

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，正在安全关闭...")
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def initialize(self):
        """异步初始化所有组件"""
        try:
            logger.info("开始初始化高频交易组件...")

            # 1. 初始化交易所接口
            exchange_config = self.config.get('exchange', {})
            self.exchange = BinanceAPI(
                api_key=exchange_config.get('api_key'),
                api_secret=exchange_config.get('api_secret'),
                sandbox=exchange_config.get('sandbox', True)  # 默认使用沙盒环境
            )

            # 2. 初始化快速执行引擎
            execution_config = self.config.get('execution', {})
            self.execution_engine = FastExecutionEngine(
                exchange=self.exchange,
                config=execution_config
            )

            # 3. 初始化高频策略
            strategy_config = self.config.get('strategy', {})
            self.strategy = HighFrequencyBreakoutStrategy(self.config)

            # 4. 初始化策略
            initial_balance = strategy_config.get('initial_balance', 10000.0)
            await self.strategy.initialize(initial_balance)

            # 5. 设置策略的执行引擎
            self.strategy.execution_engine = self.execution_engine

            logger.info("高频交易组件初始化完成")
            return True

        except Exception as e:
            logger.error(f"初始化失败: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return False

    async def start(self):
        """启动高频交易"""
        if not await self.initialize():
            return False

        logger.info("启动高频交易...")
        self.is_running = True
        self.start_time = datetime.now()

        try:
            # 启动策略异步处理
            await self.strategy.start_async_processing()

            # 主监控循环
            while self.is_running and not self.shutdown_requested:
                try:
                    # 更新统计信息
                    self.stats['last_update'] = datetime.now()

                    # 每10秒检查一次
                    await asyncio.sleep(10)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"主监控循环异常: {e}")
                    self.stats['errors'] += 1
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("收到取消信号，正在停止...")
        except Exception as e:
            logger.error(f"高频交易运行异常: {e}")
            self.stats['errors'] += 1
        finally:
            await self.shutdown()

        return True

    def run(self):
        """同步运行入口（兼容main.py调用）"""
        try:
            # 设置事件循环策略
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

            # 运行异步主循环
            success = asyncio.run(self.start())
            return 0 if success else 1

        except KeyboardInterrupt:
            logger.info("用户中断高频交易")
            return 130
        except Exception as e:
            logger.error(f"高频交易运行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 1

    async def shutdown(self):
        """安全关闭高频交易"""
        logger.info("正在关闭高频交易...")
        self.is_running = False

        try:
            # 关闭策略
            if self.strategy:
                await self.strategy.shutdown()

            # 关闭执行引擎
            if self.execution_engine:
                await self.execution_engine.shutdown()

            # 关闭交易所连接
            if self.exchange:
                # 如果有WebSocket连接，关闭它
                if hasattr(self.exchange, 'ws_connection') and self.exchange.ws_connection:
                    await self.exchange.close_websocket()

            logger.info("高频交易已安全关闭")

        except Exception as e:
            logger.error(f"关闭过程中发生错误: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取交易器状态"""
        runtime = None
        if self.start_time:
            runtime = (datetime.now() - self.start_time).total_seconds()

        status = {
            'is_running': self.is_running,
            'runtime_seconds': runtime,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'stats': self.stats.copy()
        }

        # 添加策略状态
        if self.strategy:
            status['strategy'] = self.strategy.get_strategy_status()

        # 添加执行引擎状态
        if self.execution_engine:
            status['execution_engine'] = {
                'pending_orders': len(self.execution_engine.pending_orders),
                'execution_stats': getattr(self.execution_engine, 'execution_stats', {})
            }

        return status

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self.start_time:
            return {}

        runtime_hours = (datetime.now() - self.start_time).total_seconds() / 3600

        # 计算平均延迟
        avg_signal_latency = 0
        avg_execution_latency = 0
        if self.stats['signal_processing_latency_ms']:
            avg_signal_latency = sum(self.stats['signal_processing_latency_ms']) / len(self.stats['signal_processing_latency_ms'])
        if self.stats['order_execution_latency_ms']:
            avg_execution_latency = sum(self.stats['order_execution_latency_ms']) / len(self.stats['order_execution_latency_ms'])

        metrics = {
            'runtime_hours': runtime_hours,
            'signals_per_hour': self.stats['signals_generated'] / max(runtime_hours, 0.001),
            'execution_success_rate': self.stats['successful_trades'] / max(self.stats['signals_executed'], 1),
            'average_signal_latency_ms': avg_signal_latency,
            'average_execution_latency_ms': avg_execution_latency,
            'total_pnl': self.stats['total_pnl'],
            'max_drawdown': self.stats['max_drawdown'],
            'websocket_messages_per_hour': self.stats['websocket_messages'] / max(runtime_hours, 0.001),
            'error_rate': self.stats['errors'] / max(runtime_hours, 0.001)
        }

        return metrics


def main():
    """主函数（命令行运行）"""
    import argparse

    parser = argparse.ArgumentParser(description='高频交易运行器')
    parser.add_argument('--config', '-c', required=True,
                        help='配置文件路径')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别')

    args = parser.parse_args()

    # 设置日志
    setup_logging(level=getattr(logging, args.log_level))

    # 创建并运行高频交易器
    try:
        trader = HighFrequencyTrader(args.config)
        exit_code = trader.run()
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"运行高频交易失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()