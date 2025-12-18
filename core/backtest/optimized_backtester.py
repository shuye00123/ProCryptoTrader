"""
优化回测引擎模块

针对大规模数据回测的性能优化版本，通过以下技术提升性能：
1. 向量化计算替代循环
2. 批量信号生成
3. 内存优化
4. 智能时间跳跃
5. 缓存机制
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple, Any, Iterator
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from functools import lru_cache
import warnings
warnings.filterwarnings('ignore')

from ..data.data_loader import DataLoader
from ..strategy.base_strategy import BaseStrategy, Signal, SignalType


@dataclass
class OptimizedBacktestConfig:
    """优化回测配置类"""
    start_date: str
    end_date: str
    initial_balance: float = 10000.0
    fee_rate: float = 0.001
    slippage: float = 0.0005
    leverage: float = 1.0
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)
    data_dir: str = "data"
    output_dir: str = "results"
    benchmark: Optional[str] = None
    random_seed: Optional[int] = None

    # 优化配置
    enable_vectorization: bool = True          # 启用向量化
    enable_batch_processing: bool = True       # 启用批量处理
    enable_smart_jumping: bool = True          # 启用智能时间跳跃
    enable_parallel_processing: bool = True    # 启用并行处理
    batch_size: int = 1000                     # 批处理大小
    progress_interval: int = 10000             # 进度输出间隔
    memory_limit_mb: int = 1024                # 内存限制(MB)


class OptimizedPosition:
    """优化的持仓类"""

    __slots__ = ['symbol', 'quantity', 'avg_price', 'realized_pnl', 'last_price']

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.quantity = 0.0
        self.avg_price = 0.0
        self.realized_pnl = 0.0
        self.last_price = 0.0

    @property
    def unrealized_pnl(self) -> float:
        """计算未实现盈亏"""
        if self.quantity != 0 and self.last_price != 0:
            return (self.last_price - self.avg_price) * self.quantity
        return 0.0

    def execute_trade(self, side: str, price: float, quantity: float, fee_rate: float) -> float:
        """执行交易"""
        if side == "buy":
            cost = price * quantity
            fee = cost * fee_rate

            if self.quantity == 0:
                self.avg_price = price
                self.quantity = quantity
            else:
                total_cost = self.quantity * self.avg_price + cost
                self.quantity += quantity
                self.avg_price = total_cost / self.quantity

            return fee

        elif side == "sell":
            if quantity > self.quantity:
                raise ValueError("卖出数量不能超过持仓数量")

            revenue = price * quantity
            fee = revenue * fee_rate

            # 计算已实现盈亏
            realized = (price - self.avg_price) * quantity
            self.realized_pnl += realized

            # 更新持仓
            self.quantity -= quantity

            if self.quantity == 0:
                self.avg_price = 0.0

            return fee


class VectorizedDataProcessor:
    """向量化数据处理器"""

    @staticmethod
    def prepare_price_matrices(data: Dict[str, pd.DataFrame]) -> Dict[str, np.ndarray]:
        """准备价格矩阵"""
        price_matrices = {}
        for symbol, df in data.items():
            # 提取关键价格数据为numpy数组
            price_matrices[symbol] = {
                'close': df['close'].values,
                'open': df['open'].values,
                'high': df['high'].values,
                'low': df['low'].values,
                'volume': df['volume'].values,
                'timestamps': df.index.values
            }
        return price_matrices

    @staticmethod
    def calculate_returns(price_matrix: np.ndarray) -> np.ndarray:
        """向量化计算收益率"""
        return np.diff(price_matrix) / price_matrix[:-1]

    @staticmethod
    def detect_price_crossings(prices: np.ndarray, grid_levels: np.ndarray) -> List[Tuple[int, int]]:
        """向量化检测价格穿越网格线"""
        crossings = []
        for i in range(1, len(prices)):
            prev_price = prices[i-1]
            curr_price = prices[i]

            for j, grid_level in enumerate(grid_levels):
                if (prev_price <= grid_level and curr_price > grid_level) or \
                   (prev_price >= grid_level and curr_price < grid_level):
                    crossings.append((i, j))

        return crossings


class SmartTimeIterator:
    """智能时间迭代器"""

    def __init__(self, data: Dict[str, pd.DataFrame], config: OptimizedBacktestConfig):
        self.data = data
        self.config = config
        self.timestamps = self._get_merged_timestamps()
        self.current_index = 0

    def _get_merged_timestamps(self) -> pd.DatetimeIndex:
        """获取合并后的时间戳"""
        all_timestamps = set()
        for df in self.data.values():
            all_timestamps.update(df.index)

        return pd.DatetimeIndex(sorted(all_timestamps))

    def smart_jump(self, current_data: Dict[str, pd.DataFrame],
                   last_signals: List[Signal]) -> Optional[datetime]:
        """智能时间跳跃：跳过没有交易信号的时期"""
        if not self.config.enable_smart_jumping or not last_signals:
            return None

        # 如果最近有信号，不跳跃
        return None

    def __iter__(self) -> Iterator[Tuple[datetime, Dict[str, pd.DataFrame]]]:
        """迭代器"""
        batch_start = 0

        while batch_start < len(self.timestamps):
            batch_end = min(batch_start + self.config.batch_size, len(self.timestamps))
            batch_timestamps = self.timestamps[batch_start:batch_end]

            # 构建批次数据
            batch_data = {}
            for symbol, df in self.data.items():
                # 筛选批次内的数据
                mask = df.index.isin(batch_timestamps)
                batch_df = df[mask].copy()
                if not batch_df.empty:
                    batch_data[symbol] = batch_df

            if batch_data:
                for timestamp in batch_timestamps:
                    # 构建当前时间点的数据
                    current_data = {}
                    for symbol, df in batch_data.items():
                        mask = df.index <= timestamp
                        current_df = df[mask].copy()
                        if not current_df.empty:
                            current_data[symbol] = current_df

                    yield timestamp, current_data

            batch_start = batch_end


class OptimizedBacktester:
    """优化回测引擎"""

    def __init__(self, strategy: BaseStrategy, config: OptimizedBacktestConfig):
        self.strategy = strategy
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 数据加载器
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root))
        from scripts.fixed_data_loader import FixedDataLoader
        self.data_loader = FixedDataLoader(config.data_dir)

        # 账户状态
        self.balance = config.initial_balance
        self.initial_balance = config.initial_balance
        self.positions: Dict[str, OptimizedPosition] = {}
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.trade_records: List[Dict] = []

        # 缓存
        self._price_cache = {}
        self._signal_cache = {}

        # 统计
        self.start_time = None
        self.processed_timestamps = 0

        # 创建输出目录
        os.makedirs(config.output_dir, exist_ok=True)
        self._setup_logger()

    def _setup_logger(self):
        """设置日志"""
        log_file = os.path.join(self.config.output_dir, "optimized_backtest.log")
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)

    def load_data(self) -> Dict[str, pd.DataFrame]:
        """加载数据"""
        self.logger.info(f"开始加载数据: {self.config.start_date} 至 {self.config.end_date}")

        data = {}
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                key = f"{symbol}_{timeframe}"
                try:
                    df = self.data_loader.load_data(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_date=self.config.start_date,
                        end_date=self.config.end_date
                    )

                    if not df.empty:
                        data[key] = df
                        self.logger.info(f"已加载数据: {symbol} {timeframe}, 共 {len(df)} 条记录")

                except Exception as e:
                    self.logger.error(f"加载数据失败: {symbol} {timeframe}, 错误: {e}")

        return data

    def run_vectorized_backtest(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """运行向量化回测"""
        if not self.config.enable_vectorization:
            return self.run_standard_backtest(data)

        self.logger.info("启动向量化回测")
        self.start_time = time.time()

        # 初始化策略
        self.strategy.initialize({
            "initial_balance": self.config.initial_balance,
            "symbols": self.config.symbols,
            "timeframes": self.config.timeframes,
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
            "fee_rate": self.config.fee_rate,
            "slippage": self.config.slippage,
            "leverage": self.config.leverage
        })

        # 准备价格矩阵
        price_matrices = VectorizedDataProcessor.prepare_price_matrices(data)

        # 使用智能迭代器
        time_iterator = SmartTimeIterator(data, self.config)
        last_signals = []

        for timestamp, current_data in time_iterator:
            # 更新持仓价格
            self._update_positions_fast(current_data)

            # 计算权益
            equity = self._calculate_equity_fast(current_data)
            self.equity_curve.append((timestamp, equity))

            # 批量生成信号
            if self.config.enable_batch_processing:
                signals = self._generate_signals_batch(current_data)
            else:
                signals = self.strategy.generate_signals(current_data)

            # 执行信号
            self._execute_signals_fast(signals, current_data)

            last_signals = signals

            # 进度输出
            self.processed_timestamps += 1
            if self.processed_timestamps % self.config.progress_interval == 0:
                elapsed = time.time() - self.start_time
                self.logger.info(f"回测进度: {self.processed_timestamps} 个时间点, "
                               f"耗时: {elapsed:.2f}s, "
                               f"速度: {self.processed_timestamps/elapsed:.2f} 点/秒")

        # 生成结果
        final_equity = self._calculate_equity_fast(data)
        results = self._generate_results_fast(final_equity)

        total_time = time.time() - self.start_time
        self.logger.info(f"向量化回测完成, 总耗时: {total_time:.2f}s, "
                        f"平均速度: {self.processed_timestamps/total_time:.2f} 点/秒")

        return results

    def run_standard_backtest(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """运行标准回测"""
        self.logger.info("启动标准回测")
        self.start_time = time.time()

        # 获取时间范围
        all_timestamps = set()
        for df in data.values():
            all_timestamps.update(df.index)
        time_series = sorted(all_timestamps)

        # 初始化策略
        self.strategy.initialize({
            "initial_balance": self.config.initial_balance,
            "symbols": self.config.symbols,
            "timeframes": self.config.timeframes,
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
            "fee_rate": self.config.fee_rate,
            "slippage": self.config.slippage,
            "leverage": self.config.leverage
        })

        for i, timestamp in enumerate(time_series):
            # 获取当前数据
            current_data = {}
            for symbol, df in data.items():
                mask = df.index <= timestamp
                current_df = df[mask].copy()
                if not current_df.empty:
                    current_data[symbol] = current_df

            if not current_data:
                continue

            # 更新持仓和权益
            self._update_positions_fast(current_data)
            equity = self._calculate_equity_fast(current_data)
            self.equity_curve.append((timestamp, equity))

            # 生成和执行信号
            signals = self.strategy.generate_signals(current_data)
            self._execute_signals_fast(signals, current_data)

            # 进度输出
            if i % self.config.progress_interval == 0:
                elapsed = time.time() - self.start_time
                self.logger.info(f"回测进度: {i}/{len(time_series)}, "
                               f"当前时间: {timestamp}, 权益: {equity:.2f}")

        # 生成结果
        final_equity = self._calculate_equity_fast(data)
        results = self._generate_results_fast(final_equity)

        total_time = time.time() - self.start_time
        self.logger.info(f"标准回测完成, 总耗时: {total_time:.2f}s")

        return results

    def _update_positions_fast(self, data: Dict[str, pd.DataFrame]):
        """快速更新持仓"""
        for symbol, position in self.positions.items():
            for key, df in data.items():
                if symbol in key and not df.empty:
                    position.last_price = df.iloc[-1]['close']
                    break

    def _calculate_equity_fast(self, data: Dict[str, pd.DataFrame]) -> float:
        """快速计算权益"""
        equity = self.balance

        for symbol, position in self.positions.items():
            if position.quantity != 0:
                for key, df in data.items():
                    if symbol in key and not df.empty:
                        latest_price = df.iloc[-1]['close']
                        equity += position.quantity * latest_price
                        break

        return equity

    def _generate_signals_batch(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """批量生成信号"""
        # 缓存数据哈希
        data_hash = hash(tuple(df.iloc[-1]['close'] for df in data.values()))

        if data_hash in self._signal_cache:
            return self._signal_cache[data_hash]

        signals = self.strategy.generate_signals(data)
        self._signal_cache[data_hash] = signals

        return signals

    def _execute_signals_fast(self, signals: List[Signal], data: Dict[str, pd.DataFrame]):
        """快速执行信号"""
        for signal in signals:
            symbol = signal.symbol

            # 获取价格
            current_price = None
            for key, df in data.items():
                if symbol in key and not df.empty:
                    current_price = df.iloc[-1]['close']
                    break

            if current_price is None:
                continue

            # 初始化持仓
            if symbol not in self.positions:
                self.positions[symbol] = OptimizedPosition(symbol)

            position = self.positions[symbol]

            # 执行交易
            if signal.signal_type in [SignalType.OPEN_LONG]:
                quantity = signal.amount if signal.amount is not None else signal.quantity
                cost = current_price * quantity * (1 + self.config.slippage)
                fee = cost * self.config.fee_rate
                total_cost = cost + fee

                if total_cost <= self.balance:
                    position_fee = position.execute_trade("buy", current_price * (1 + self.config.slippage),
                                                        quantity, self.config.fee_rate)
                    self.balance -= total_cost

                    # 记录交易
                    self.trade_records.append({
                        'timestamp': self.processed_timestamps,
                        'symbol': symbol,
                        'side': 'buy',
                        'price': current_price * (1 + self.config.slippage),
                        'quantity': quantity,
                        'value': cost,
                        'fee': position_fee,
                        'balance': self.balance,
                        'type': 'market',
                        'strategy_id': self.strategy.name if hasattr(self.strategy, 'name') else 'unknown'
                    })

            elif signal.signal_type in [SignalType.CLOSE_LONG]:
                quantity = min(signal.amount if signal.amount is not None else signal.quantity,
                             position.quantity)
                if quantity > 0:
                    revenue = current_price * quantity * (1 - self.config.slippage)
                    fee = revenue * self.config.fee_rate
                    net_revenue = revenue - fee

                    position_fee = position.execute_trade("sell", current_price * (1 - self.config.slippage),
                                                        quantity, self.config.fee_rate)
                    self.balance += net_revenue

                    # 记录交易
                    self.trade_records.append({
                        'timestamp': self.processed_timestamps,
                        'symbol': symbol,
                        'side': 'sell',
                        'price': current_price * (1 - self.config.slippage),
                        'quantity': quantity,
                        'value': revenue,
                        'fee': position_fee,
                        'pnl': position.realized_pnl,
                        'balance': self.balance,
                        'type': 'market',
                        'strategy_id': self.strategy.name if hasattr(self.strategy, 'name') else 'unknown'
                    })

    def _generate_results_fast(self, final_equity: float) -> Dict[str, Any]:
        """快速生成结果"""
        # 创建权益曲线DataFrame
        equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)

        # 创建交易记录DataFrame
        trades_df = pd.DataFrame(self.trade_records)

        # 计算统计指标
        total_return = (final_equity / self.initial_balance - 1) * 100
        total_trades = len(self.trade_records)

        if len(equity_df) > 1:
            daily_returns = equity_df['equity'].pct_change().dropna()

            # 年化收益率
            days = (equity_df.index[-1] - equity_df.index[0]).days
            annual_return = ((final_equity / self.initial_balance) ** (365 / days) - 1) * 100 if days > 0 else 0

            # 最大回撤
            rolling_max = equity_df['equity'].expanding().max()
            drawdown = (equity_df['equity'] - rolling_max) / rolling_max
            max_drawdown = drawdown.min() * 100

            # 夏普比率
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(365) if daily_returns.std() != 0 else 0
        else:
            annual_return = 0
            max_drawdown = 0
            sharpe_ratio = 0

        # 胜率
        if not trades_df.empty and 'pnl' in trades_df.columns:
            winning_trades = trades_df[trades_df['pnl'] > 0]
            win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        else:
            win_rate = 0

        # 保存结果
        results = {
            "config": self.config,
            "initial_balance": self.initial_balance,
            "final_balance": final_equity,
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "equity_curve": equity_df,
            "trade_records": trades_df,
            "processing_time": time.time() - self.start_time if self.start_time else 0,
            "processed_timestamps": self.processed_timestamps
        }

        # 保存到文件
        self._save_results_fast(results)

        return results

    def _save_results_fast(self, results: Dict[str, Any]):
        """快速保存结果"""
        output_dir = self.config.output_dir

        # 保存权益曲线
        equity_file = os.path.join(output_dir, "equity_curve.csv")
        results["equity_curve"].to_csv(equity_file)

        # 保存交易记录
        trades_file = os.path.join(output_dir, "trade_records.csv")
        if not results["trade_records"].empty:
            results["trade_records"].to_csv(trades_file, index=False)

        # 保存回测摘要
        summary_file = os.path.join(output_dir, "summary.txt")
        with open(summary_file, "w") as f:
            f.write(f"优化回测摘要\n")
            f.write(f"========\n\n")
            f.write(f"策略: {self.strategy.name if hasattr(self.strategy, 'name') else 'unknown'}\n")
            f.write(f"时间范围: {self.config.start_date} 至 {self.config.end_date}\n")
            f.write(f"初始资金: {self.initial_balance:.2f}\n")
            f.write(f"最终资金: {results['final_balance']:.2f}\n")
            f.write(f"总收益率: {results['total_return']:.2f}%\n")
            f.write(f"年化收益率: {results['annual_return']:.2f}%\n")
            f.write(f"最大回撤: {results['max_drawdown']:.2f}%\n")
            f.write(f"夏普比率: {results['sharpe_ratio']:.2f}\n")
            f.write(f"总交易次数: {results['total_trades']}\n")
            f.write(f"胜率: {results['win_rate']:.2f}%\n")
            f.write(f"处理时间: {results['processing_time']:.2f}秒\n")
            f.write(f"处理速度: {results['processed_timestamps']/results['processing_time']:.2f} 点/秒\n")

        self.logger.info(f"优化回测结果已保存到 {output_dir}")


def run_optimized_backtest(strategy: BaseStrategy, config: OptimizedBacktestConfig) -> Dict[str, Any]:
    """运行优化回测的便捷函数"""
    backtester = OptimizedBacktester(strategy, config)
    data = backtester.load_data()
    return backtester.run_vectorized_backtest(data)