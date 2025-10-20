#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实盘交易脚本示例
演示如何使用实盘交易模块进行策略实盘交易
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import time
import signal
import threading
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.live.live_trader import LiveTrader
from core.strategy.grid_strategy import GridStrategy
from core.strategy.martingale_strategy import MartingaleStrategy
from examples.strategy_example import DualMovingAverageStrategy
from core.exchange.binance_api import BinanceAPI
from core.exchange.okx_api import OKXAPI
from core.utils.logger import get_logger
from core.utils.config import ConfigParser

logger = get_logger("LiveExample")


class LiveTradingExample:
    """实盘交易示例类"""
    
    def __init__(self, config_path: str):
        """
        初始化实盘交易示例
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = None
        self.trader = None
        self.running = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 加载配置
        self._load_config()
        
        # 初始化交易器
        self._init_trader()
    
    def _load_config(self):
        """加载配置文件"""
        parser = ConfigParser()
        self.config = parser.read_config(self.config_path)
        logger.info("配置文件加载完成")
    
    def _init_trader(self):
        """初始化交易器"""
        # 获取基本配置
        basic_config = self.config.get("basic", {})
        mode = basic_config.get("mode", "paper")  # 默认为模拟交易
        symbols = basic_config.get("symbols", ["BTC/USDT"])
        timeframes = basic_config.get("timeframes", ["1h"])
        
        # 获取交易所配置
        exchanges_config = self.config.get("exchanges", {})
        
        # 创建交易所实例
        exchanges = {}
        
        # 币安交易所
        binance_config = exchanges_config.get("binance", {})
        if binance_config.get("enabled", False):
            exchanges["binance"] = BinanceAPI({
                "api_key": binance_config.get("api_key", ""),
                "secret": binance_config.get("secret", ""),
                "sandbox": binance_config.get("sandbox", True),
                "testnet": binance_config.get("testnet", True)
            })
            logger.info("币安交易所初始化完成")
        
        # OKX交易所
        okx_config = exchanges_config.get("okx", {})
        if okx_config.get("enabled", False):
            exchanges["okx"] = OKXAPI({
                "api_key": okx_config.get("api_key", ""),
                "secret": okx_config.get("secret", ""),
                "passphrase": okx_config.get("passphrase", ""),
                "sandbox": okx_config.get("sandbox", True),
                "testnet": okx_config.get("testnet", True)
            })
            logger.info("OKX交易所初始化完成")
        
        if not exchanges:
            logger.warning("没有启用的交易所，将使用模拟交易")
            mode = "paper"
        
        # 获取策略配置
        strategies_config = self.config.get("strategies", [])
        strategies = []
        
        for strategy_config in strategies_config:
            if not strategy_config.get("enabled", False):
                continue
                
            strategy_name = strategy_config.get("name")
            strategy_symbols = strategy_config.get("symbols")
            strategy_timeframe = strategy_config.get("timeframe")
            strategy_params = strategy_config.get("params", {})
            
            # 创建策略实例
            if strategy_name == "GridStrategy":
                strategy = GridStrategy(strategy_params)
            elif strategy_name == "MartingaleStrategy":
                strategy = MartingaleStrategy(strategy_params)
            elif strategy_name == "DualMovingAverageStrategy":
                strategy = DualMovingAverageStrategy(strategy_params)
            else:
                logger.warning(f"未知策略: {strategy_name}")
                continue
            
            strategies.append({
                "strategy": strategy,
                "symbols": strategy_symbols,
                "timeframe": strategy_timeframe
            })
            
            logger.info(f"策略 {strategy_name} 初始化完成")
        
        if not strategies:
            logger.error("没有启用的策略")
            raise ValueError("至少需要启用一个策略")
        
        # 创建交易器
        self.trader = LiveTrader(
            mode=mode,
            exchanges=exchanges,
            strategies=strategies,
            config=self.config
        )
        
        logger.info(f"交易器初始化完成，模式: {mode}")
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        logger.info(f"接收到信号 {signum}，准备停止交易...")
        self.running = False
        if self.trader:
            self.trader.stop()
    
    def run(self):
        """运行实盘交易"""
        logger.info("开始实盘交易...")
        self.running = True
        
        try:
            # 启动交易器
            self.trader.start()
            
            # 主循环
            while self.running:
                # 检查交易器状态
                if not self.trader.is_running():
                    logger.error("交易器已停止")
                    break
                
                # 获取交易器状态
                status = self.trader.get_status()
                
                # 打印状态信息
                logger.info(f"交易器状态: {status}")
                
                # 等待一段时间
                time.sleep(60)  # 每分钟检查一次
                
        except Exception as e:
            logger.error(f"运行过程中发生错误: {e}")
        finally:
            # 停止交易器
            if self.trader:
                self.trader.stop()
            logger.info("实盘交易已停止")
    
    def run_in_thread(self):
        """在线程中运行实盘交易"""
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
        logger.info("实盘交易已在线程中启动")
        return self.thread


def run_paper_trading():
    """运行模拟交易"""
    logger.info("=" * 50)
    logger.info("运行模拟交易示例")
    logger.info("=" * 50)
    
    # 配置文件路径
    config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建实盘交易示例
    live_example = LiveTradingExample(config_path)
    
    # 运行模拟交易
    live_example.run()


def run_live_trading():
    """运行实盘交易"""
    logger.info("=" * 50)
    logger.info("运行实盘交易示例")
    logger.info("=" * 50)
    logger.warning("警告: 这将进行真实交易，请确保已正确配置API密钥并充分测试策略")
    
    # 确认是否继续
    confirm = input("是否继续实盘交易? (输入 'yes' 确认): ")
    if confirm.lower() != "yes":
        logger.info("用户取消实盘交易")
        return
    
    # 配置文件路径
    config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建实盘交易示例
    live_example = LiveTradingExample(config_path)
    
    # 运行实盘交易
    live_example.run()


def run_monitoring():
    """运行监控模式"""
    logger.info("=" * 50)
    logger.info("运行监控模式示例")
    logger.info("=" * 50)
    
    # 配置文件路径
    config_path = project_root / "configs" / "live_config.yaml"
    
    # 创建实盘交易示例
    live_example = LiveTradingExample(config_path)
    
    # 在线程中运行实盘交易
    thread = live_example.run_in_thread()
    
    # 监控循环
    try:
        while thread.is_alive():
            # 获取交易器状态
            status = live_example.trader.get_status()
            
            # 打印状态信息
            logger.info(f"交易器状态: {status}")
            
            # 获取账户信息
            for name, exchange in live_example.trader.exchanges.items():
                try:
                    balance = exchange.get_balance()
                    logger.info(f"{name} 账户余额: {balance}")
                except Exception as e:
                    logger.error(f"获取 {name} 账户余额失败: {e}")
            
            # 等待一段时间
            time.sleep(300)  # 每5分钟检查一次
            
    except KeyboardInterrupt:
        logger.info("用户中断监控")
    finally:
        # 停止交易器
        live_example.running = False
        live_example.trader.stop()
        thread.join(timeout=10)
        logger.info("监控已停止")


def main():
    """主函数"""
    import argparse
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="实盘交易示例")
    parser.add_argument("--mode", choices=["paper", "live", "monitor"], 
                       default="paper", help="运行模式")
    
    # 解析参数
    args = parser.parse_args()
    
    # 根据模式运行
    if args.mode == "paper":
        run_paper_trading()
    elif args.mode == "live":
        run_live_trading()
    elif args.mode == "monitor":
        run_monitoring()
    
    logger.info("实盘交易示例执行完成!")


if __name__ == "__main__":
    main()