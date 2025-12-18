#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步日志修复模块
解决高频交易系统中异步线程日志输出不可见的问题

在高频交易系统启动时自动调用此模块，确保：
1. 所有异步线程的日志都能正确输出到控制台
2. WebSocket客户端、突破检测器等组件的日志正常显示
3. 线程安全的日志配置
"""

import sys
import logging
from pathlib import Path
from typing import Optional


def setup_async_logging_fix(log_level: str = "INFO", log_file_path: Optional[str] = None) -> logging.Logger:
    """
    设置异步日志修复配置

    Args:
        log_level: 日志级别，默认为INFO，让配置文件控制
        log_file_path: 可选的日志文件路径，如果为None则使用默认路径

    Returns:
        配置好的logger实例
    """

    # 获取项目根目录
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # 设置默认日志文件路径
    if log_file_path is None:
        log_file_path = log_dir / "high_frequency_trading.log"

    # 解析日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)

    # 只在没有配置过或者必须强制时才重新配置
    # 检查是否已经有配置的处理器
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        # 没有处理器时才配置基础设置
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(threadName)-12s - %(name)-25s - %(levelname)-8s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),  # 确保输出到标准输出
                logging.FileHandler(
                    log_file_path,
                    mode='a',
                    encoding='utf-8'
                )  # 文件输出
                ]
        )

    # 设置特定模块的日志级别，不再强制DEBUG，尊重配置文件设置
    # logging.getLogger('core.data.websocket_client').setLevel(logging.DEBUG)  # 注释掉强制DEBUG
    # 移除所有强制DEBUG设置，让配置文件控制日志级别
    # logging.getLogger('core.strategy.high_frequency_breakout').setLevel(logging.DEBUG)
    # logging.getLogger('core.live.high_frequency_trader').setLevel(logging.DEBUG)
    # logging.getLogger('core.strategy.breakout_detector').setLevel(logging.DEBUG)
    logging.getLogger('websockets').setLevel(logging.INFO)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    # 返回主logger
    return logging.getLogger("AsyncLoggerFix")


def test_async_logging():
    """测试异步日志是否修复成功"""
    logger = setup_async_logging_fix()

    logger.info("=" * 60)
    logger.info("异步日志修复测试")
    logger.info("=" * 60)

    # 测试主线程日志
    logger.info("主线程日志测试")

    # 测试异步任务日志
    import asyncio

    async def async_test():
        task_logger = logging.getLogger("AsyncTaskTest")
        task_logger.info("异步任务日志测试开始")
        for i in range(2):
            task_logger.info(f"异步日志测试步骤 {i+1}")
            await asyncio.sleep(0.2)
        task_logger.info("异步任务日志测试完成")

    # 测试线程日志
    import threading

    def thread_test(thread_id):
        thread_logger = logging.getLogger(f"ThreadTest{thread_id}")
        thread_logger.info(f"线程 {thread_id} 日志测试开始")
        for i in range(2):
            thread_logger.info(f"线程 {thread_id} 日志步骤 {i+1}")
            import time
            time.sleep(0.1)
        thread_logger.info(f"线程 {thread_id} 日志测试完成")

    # 创建测试线程
    thread = threading.Thread(target=thread_test, args=(1,))
    thread.start()

    # 运行异步测试
    asyncio.run(async_test())

    # 等待线程完成
    thread.join()

    logger.info("异步日志修复测试完成")
    logger.info("现在高频交易系统的所有日志都应该正常显示")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_async_logging()