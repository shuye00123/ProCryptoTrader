#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProCryptoTrader - 加密货币量化交易框架
主入口程序，支持数据下载、回测、实盘交易等功能

遵循RIPER-5原则：
- Risk first（风险优先）
- Integration minimal（最小侵入）
- Predictability（可预期性）
- Expandability（可扩展性）
- Realistic evaluation（真实可评估）
"""

import argparse
import sys
import os
from pathlib import Path
import logging
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.utils.logger import get_logger, setup_logging
from core.utils.config import load_config

# 设置主日志
logger = get_logger("ProCryptoTrader")


class ProCryptoTrader:
    """ProCryptoTrader主程序类"""

    def __init__(self):
        """初始化主程序"""
        self.project_root = project_root
        self.config_dir = project_root / "configs"
        self.data_dir = project_root / "data"
        self.results_dir = project_root / "results"
        self.logs_dir = project_root / "logs"

        # 确保必要目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        directories = [
            self.config_dir,
            self.data_dir,
            self.results_dir,
            self.logs_dir,
            self.data_dir / "binance",
            self.data_dir / "okx"
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def download_data(self, exchange: str, symbols: list, timeframes: list,
                     start_date: Optional[str] = None, end_date: Optional[str] = None):
        """下载历史数据"""
        logger.info(f"开始下载{exchange}交易所数据")
        logger.info(f"交易对: {symbols}")
        logger.info(f"时间框架: {timeframes}")

        try:
            from core.data.data_downloader import DataDownloader

            # 创建数据下载器
            downloader = DataDownloader(data_dir=str(self.data_dir))

            # 下载数据
            success = downloader.download_data(
                exchange=exchange,
                symbols=symbols,
                timeframes=timeframes,
                start_date=start_date,
                end_date=end_date
            )

            if success:
                logger.info("数据下载完成")
                # 显示下载的数据统计
                available_data = downloader.list_available_data(exchange)
                if available_data:
                    data_info = available_data.get(exchange, {})
                    logger.info(f"已下载 {data_info.get('total_symbols', 0)} 个交易对的数据")
            else:
                logger.error("数据下载失败")

            return success

        except Exception as e:
            logger.error(f"下载数据时发生错误: {e}")
            return False

    def run_backtest(self, config_file: str, strategy: Optional[str] = None):
        """运行回测"""
        logger.info(f"开始回测，配置文件: {config_file}")

        config_path = self.config_dir / config_file
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            return False

        try:
            # 加载配置
            config = load_config(config_path)

            # 导入回测模块
            from core.backtest.backtester import Backtester, BacktestConfig
            from core.strategy.grid_strategy import GridStrategy
            from core.strategy.martingale_strategy import MartingaleStrategy
            from core.strategy.enhanced_grid_strategy import EnhancedGridStrategy

            # 获取回测配置
            basic_config = config.get('basic', {})
            data_config = config.get('data', {})
            strategy_config = config.get('strategy', {})
            trading_config = config.get('trading', {})
            output_config = config.get('output', {})

            # 创建回测配置
            backtest_config = BacktestConfig(
                start_date=basic_config.get('start_date', '2023-01-01'),
                end_date=basic_config.get('end_date', '2023-12-31'),
                initial_balance=basic_config.get('initial_balance', 10000.0),
                fee_rate=trading_config.get('commission', 0.001),
                slippage=trading_config.get('slippage', 0.0005),
                symbols=data_config.get('symbols', ['BTC/USDT']),
                timeframes=data_config.get('timeframes', ['1h']),
                data_dir=data_config.get('data_dir', './data') + '/' + data_config.get('exchange', 'binance'),
                output_dir=output_config.get('output_dir', './results')
            )

            # 创建策略实例
            strategy_name = strategy or strategy_config.get('name', 'GridStrategy')
            strategy_params = strategy_config.get('params', {})

            # 添加通用参数
            strategy_params.update({
                'symbols': backtest_config.symbols,
                'position_size': trading_config.get('position_size', 0.1),
                'stop_loss_pct': trading_config.get('stop_loss', 0.05),
                'take_profit_pct': trading_config.get('take_profit', 0.02),
                'name': strategy_name
            })

            if strategy_name == 'GridStrategy':
                strategy_instance = GridStrategy(strategy_params)
            elif strategy_name == 'EnhancedGridStrategy':
                strategy_instance = EnhancedGridStrategy(strategy_params)
            elif strategy_name == 'Martingale':
                strategy_instance = MartingaleStrategy(strategy_params)
            else:
                logger.error(f"不支持的策略: {strategy_name}")
                return False

            # 运行回测
            logger.info(f"运行{strategy_name}策略回测...")
            backtester = Backtester(strategy_instance, backtest_config)
            results = backtester.run()

            # 输出结果
            logger.info("回测完成!")
            logger.info(f"最终权益: {results['final_balance']:.2f}")
            logger.info(f"总收益率: {results['total_return']:.2f}%")
            logger.info(f"年化收益率: {results['annual_return']:.2f}%")
            logger.info(f"最大回撤: {results['max_drawdown']:.2f}%")
            logger.info(f"夏普比率: {results['sharpe_ratio']:.2f}")
            logger.info(f"总交易次数: {results['total_trades']}")
            logger.info(f"胜率: {results['win_rate']:.2f}%")

            logger.info(f"回测结果已保存到: {backtest_config.output_dir}")
            return True

        except ImportError as e:
            logger.error(f"导入回测模块失败: {e}")
            return False
        except Exception as e:
            logger.error(f"运行回测时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def run_live(self, config_file: str):
        """运行实盘交易"""
        logger.info(f"开始实盘交易，配置文件: {config_file}")

        config_path = self.config_dir / config_file
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            return False

        try:
            # 加载配置
            config = load_config(config_path)

            # 检查交易模式
            basic_config = config.get('basic', {})
            mode = basic_config.get('mode', 'paper')

            if mode == 'live':
                logger.warning("⚠️  即将开始实盘交易!")
                logger.warning("请确保:")
                logger.warning("1. API密钥配置正确")
                logger.warning("2. 风控参数设置合理")
                logger.warning("3. 资金管理策略适当")
                response = input("确认继续实盘交易? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("用户取消实盘交易")
                    return False
            else:
                logger.info("📊 开始模拟交易")

            # 导入实盘交易模块
            from core.live.live_trader import LiveTrader

            # 创建实盘交易实例
            trader = LiveTrader(config_path)

            # 运行实盘交易
            trader.run()

            return True

        except ImportError as e:
            logger.error(f"导入实盘交易模块失败: {e}")
            logger.error("请确保实盘交易模块已正确实现")
            return False
        except Exception as e:
            logger.error(f"运行实盘交易时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def list_strategies(self):
        """列出所有可用策略"""
        logger.info("可用策略:")

        try:
            from core.strategy.grid_strategy import GridStrategy
            from core.strategy.martingale_strategy import MartingaleStrategy
            from core.strategy.enhanced_grid_strategy import EnhancedGridStrategy

            strategies = {
                'GridStrategy': {
                    'name': '基础网格策略',
                    'description': '在价格区间内设置网格，低买高卖获取收益',
                    'suitable': '震荡行情',
                    'config_file': 'backtest_config.yaml'
                },
                'EnhancedGridStrategy': {
                    'name': '增强网格策略',
                    'description': '支持做多/做空方向配置的增强网格策略',
                    'suitable': '震荡行情、趋势行情',
                    'config_file': 'enhanced_grid_backtest_config.yaml',
                    'features': ['方向配置', '网格重平衡', '趋势确认']
                },
                'Martingale': {
                    'name': '马丁格尔策略',
                    'description': '亏损时加倍下注，直到盈利为止',
                    'suitable': '高胜率策略',
                    'config_file': 'backtest_config.yaml'
                }
            }

            for strategy_id, info in strategies.items():
                logger.info(f"  {strategy_id}:")
                logger.info(f"    名称: {info['name']}")
                logger.info(f"    描述: {info['description']}")
                logger.info(f"    适合: {info['suitable']}")
                logger.info(f"    配置文件: {info['config_file']}")
                logger.info("")

        except ImportError as e:
            logger.error(f"导入策略模块失败: {e}")

    def check_data(self):
        """检查本地数据"""
        logger.info("检查本地数据...")

        try:
            binance_dir = self.data_dir / "binance"
            okx_dir = self.data_dir / "okx"

            if binance_dir.exists():
                symbols = [d.name for d in binance_dir.iterdir() if d.is_dir()]
                logger.info(f"币安数据 - 交易对数量: {len(symbols)}")

                for symbol in symbols[:5]:  # 只显示前5个
                    symbol_dir = binance_dir / symbol
                    files = list(symbol_dir.glob("*.parquet"))
                    if files:
                        latest_file = max(files, key=lambda x: x.stat().st_mtime)
                        logger.info(f"  {symbol}: {len(files)}个文件, 最新: {latest_file.name}")

                if len(symbols) > 5:
                    logger.info(f"  ... 还有 {len(symbols) - 5} 个交易对")
            else:
                logger.info("币安数据: 无数据")

            if okx_dir.exists():
                symbols = [d.name for d in okx_dir.iterdir() if d.is_dir()]
                logger.info(f"OKX数据 - 交易对数量: {len(symbols)}")
            else:
                logger.info("OKX数据: 无数据")

        except Exception as e:
            logger.error(f"检查数据时发生错误: {e}")

    def validate_config(self, config_file: str):
        """验证配置文件"""
        logger.info(f"验证配置文件: {config_file}")

        config_path = self.config_dir / config_file
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            return False

        try:
            config = load_config(config_path)
            logger.info("✓ 配置文件格式正确")

            # 验证基本配置
            if 'basic' in config:
                basic = config['basic']
                logger.info("✓ 基本配置存在")

                if 'start_date' in basic and 'end_date' in basic:
                    logger.info(f"✓ 时间范围: {basic['start_date']} 至 {basic['end_date']}")

                if 'initial_balance' in basic:
                    logger.info(f"✓ 初始资金: {basic['initial_balance']}")

            # 验证数据配置
            if 'data' in config:
                data = config['data']
                logger.info("✓ 数据配置存在")

                if 'symbols' in data:
                    logger.info(f"✓ 交易对: {data['symbols']}")

                if 'timeframes' in data:
                    logger.info(f"✓ 时间框架: {data['timeframes']}")

            # 验证策略配置
            if 'strategy' in config:
                strategy = config['strategy']
                logger.info("✓ 策略配置存在")
                logger.info(f"✓ 策略名称: {strategy.get('name', 'Unknown')}")

            # 验证交易配置
            if 'trading' in config:
                trading = config['trading']
                logger.info("✓ 交易配置存在")

                if 'commission' in trading:
                    logger.info(f"✓ 手续费率: {trading['commission']}")

                if 'position_size' in trading:
                    logger.info(f"✓ 仓位大小: {trading['position_size']}")

            logger.info("配置文件验证通过")
            return True

        except Exception as e:
            logger.error(f"验证配置文件时发生错误: {e}")
            return False


def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='ProCryptoTrader - 加密货币量化交易框架',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 下载币安数据
  python main.py download binance --symbols BTC/USDT ETH/USDT --timeframes 1h 4h

  # 运行回测
  python main.py backtest --config backtest_config.yaml

  # 运行指定策略回测
  python main.py backtest --config backtest_config.yaml --strategy Martingale

  # 运行实盘交易
  python main.py live --config live_config.yaml

  # 列出所有策略
  python main.py list-strategies

  # 检查本地数据
  python main.py check-data

  # 验证配置文件
  python main.py validate-config --config backtest_config.yaml
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 数据下载命令
    download_parser = subparsers.add_parser('download', help='下载历史数据')
    download_parser.add_argument('exchange', choices=['binance', 'okx'], help='交易所名称')
    download_parser.add_argument('--symbols', nargs='+', help='交易对列表 (如: BTC/USDT ETH/USDT)')
    download_parser.add_argument('--timeframes', nargs='+', help='时间框架列表 (如: 1h 4h 1d)')
    download_parser.add_argument('--start-date', help='开始日期 (YYYY-MM-DD)')
    download_parser.add_argument('--end-date', help='结束日期 (YYYY-MM-DD)')

    # 回测命令
    backtest_parser = subparsers.add_parser('backtest', help='运行回测')
    backtest_parser.add_argument('--config', default='backtest_config.yaml', help='配置文件名')
    backtest_parser.add_argument('--strategy', help='策略名称 (覆盖配置文件中的策略)')

    # 实盘交易命令
    live_parser = subparsers.add_parser('live', help='运行实盘交易')
    live_parser.add_argument('--config', default='live_config.yaml', help='配置文件名')

    # 列出策略命令
    subparsers.add_parser('list-strategies', help='列出所有可用策略')

    # 检查数据命令
    subparsers.add_parser('check-data', help='检查本地数据')

    # 验证配置命令
    validate_parser = subparsers.add_parser('validate-config', help='验证配置文件')
    validate_parser.add_argument('--config', required=True, help='配置文件名')

    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 创建主程序实例
    app = ProCryptoTrader()

    # 设置日志
    try:
        setup_logging(
            level=logging.INFO,
            log_file=str(app.logs_dir / "main.log")
        )
    except Exception as e:
        print(f"设置日志失败: {e}")
        # 继续执行，使用默认日志设置

    logger.info("ProCryptoTrader 启动")
    logger.info(f"项目根目录: {app.project_root}")

    try:
        if args.command == 'download':
            success = app.download_data(
                exchange=args.exchange,
                symbols=args.symbols or [],
                timeframes=args.timeframes or [],
                start_date=args.start_date,
                end_date=args.end_date
            )

        elif args.command == 'backtest':
            success = app.run_backtest(
                config_file=args.config,
                strategy=args.strategy
            )

        elif args.command == 'live':
            success = app.run_live(config_file=args.config)

        elif args.command == 'list-strategies':
            app.list_strategies()
            success = True

        elif args.command == 'check-data':
            app.check_data()
            success = True

        elif args.command == 'validate-config':
            success = app.validate_config(config_file=args.config)

        else:
            logger.error(f"未知命令: {args.command}")
            success = False

        if success:
            logger.info("操作完成")
            sys.exit(0)
        else:
            logger.error("操作失败")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行时发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()