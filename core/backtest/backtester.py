"""
回测引擎模块

实现策略在历史数据上的回测功能，支持多策略、多时间框架、多交易对的回测。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
import pyarrow.parquet as pq

from ..data.data_loader import DataLoader
from ..strategy.base_strategy import BaseStrategy, Signal, SignalType
from ..exchange.base_exchange import BaseExchange


@dataclass
class BacktestConfig:
    """回测配置类"""
    start_date: str  # 开始日期 'YYYY-MM-DD'
    end_date: str    # 结束日期 'YYYY-MM-DD'
    initial_balance: float = 10000.0  # 初始资金
    fee_rate: float = 0.001  # 手续费率
    slippage: float = 0.0005  # 滑点
    leverage: float = 1.0  # 杠杆倍数
    symbols: List[str] = field(default_factory=list)  # 交易对列表
    timeframes: List[str] = field(default_factory=list)  # 时间框架列表
    data_dir: str = "data"  # 数据目录
    output_dir: str = "results"  # 输出目录
    benchmark: Optional[str] = None  # 基准指数
    random_seed: Optional[int] = None  # 随机种子
    
    def __post_init__(self):
        """验证配置参数"""
        try:
            self.start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            self.end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
            if self.start_dt >= self.end_dt:
                raise ValueError("开始日期必须早于结束日期")
        except ValueError as e:
            raise ValueError(f"日期格式错误，应为YYYY-MM-DD: {e}")
            
        if self.initial_balance <= 0:
            raise ValueError("初始资金必须大于0")
            
        if self.fee_rate < 0 or self.slippage < 0:
            raise ValueError("手续费率和滑点不能为负数")
            
        if self.leverage <= 0:
            raise ValueError("杠杆倍数必须大于0")


@dataclass
class TradeRecord:
    """交易记录"""
    timestamp: datetime
    symbol: str
    side: str  # 'buy' 或 'sell'
    price: float
    quantity: float
    value: float  # 交易价值
    fee: float
    pnl: float = 0.0  # 已实现盈亏
    balance: float = 0.0  # 交易后余额
    type: str = "market"  # 交易类型
    strategy_id: str = ""  # 策略ID


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: float = 0.0  # 持仓数量
    avg_price: float = 0.0  # 平均成本价
    unrealized_pnl: float = 0.0  # 未实现盈亏
    realized_pnl: float = 0.0  # 已实现盈亏
    last_price: float = 0.0  # 最新价格
    
    def update_price(self, price: float):
        """更新最新价格并计算未实现盈亏"""
        self.last_price = price
        if self.quantity != 0:
            self.unrealized_pnl = (price - self.avg_price) * self.quantity
            
    def execute_trade(self, side: str, price: float, quantity: float, fee_rate: float) -> float:
        """执行交易并返回手续费"""
        if side == "buy":
            # 买入
            cost = price * quantity
            fee = cost * fee_rate
            total_cost = cost + fee
            
            if self.quantity == 0:
                # 新建仓位
                self.avg_price = price
            else:
                # 加仓
                total_value = self.quantity * self.avg_price + cost
                self.quantity += quantity
                self.avg_price = total_value / self.quantity
                
            self.quantity += quantity
            return fee
            
        elif side == "sell":
            # 卖出
            if quantity > self.quantity:
                raise ValueError("卖出数量不能超过持仓数量")
                
            revenue = price * quantity
            fee = revenue * fee_rate
            net_revenue = revenue - fee
            
            # 计算已实现盈亏
            realized = (price - self.avg_price) * quantity
            self.realized_pnl += realized
            
            # 更新持仓
            self.quantity -= quantity
            
            # 如果全部卖出，重置平均价格
            if self.quantity == 0:
                self.avg_price = 0.0
                
            return fee
            
        else:
            raise ValueError("交易方向必须是'buy'或'sell'")


class Backtester:
    """回测引擎类"""
    
    def __init__(self, strategy: BaseStrategy, config: BacktestConfig):
        """
        初始化回测引擎
        
        Args:
            strategy: 策略实例
            config: 回测配置
        """
        self.strategy = strategy
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化数据加载器
        self.data_loader = DataLoader(config.data_dir)
        
        # 账户状态
        self.balance = config.initial_balance
        self.initial_balance = config.initial_balance
        self.positions: Dict[str, Position] = {}
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.trade_records: List[TradeRecord] = []
        
        # 回测状态
        self.current_time = None
        self.is_running = False
        
        # 设置随机种子
        if config.random_seed is not None:
            np.random.seed(config.random_seed)
            
        # 创建输出目录
        os.makedirs(config.output_dir, exist_ok=True)
        
        # 初始化日志
        self._setup_logger()
        
    def _setup_logger(self):
        """设置日志记录器"""
        log_file = os.path.join(self.config.output_dir, "backtest.log")
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
        
    def load_data(self) -> Dict[str, pd.DataFrame]:
        """
        加载回测数据
        
        Returns:
            Dict[str, pd.DataFrame]: 按symbol/timeframe组织的字典
        """
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
                    
                    if df.empty:
                        self.logger.warning(f"未找到数据: {symbol} {timeframe}")
                        continue
                        
                    data[key] = df
                    self.logger.info(f"已加载数据: {symbol} {timeframe}, 共 {len(df)} 条记录")
                    
                except Exception as e:
                    self.logger.error(f"加载数据失败: {symbol} {timeframe}, 错误: {e}")
                    
        if not data:
            raise ValueError("未能加载任何数据，请检查数据目录和日期范围")
            
        return data
        
    def get_universe_time_range(self, data: Dict[str, pd.DataFrame]) -> Tuple[datetime, datetime]:
        """
        获取所有数据的时间范围
        
        Args:
            data: 数据字典
            
        Returns:
            Tuple[datetime, datetime]: 开始时间和结束时间
        """
        all_times = []
        for df in data.values():
            all_times.extend(df.index.tolist())
            
        if not all_times:
            raise ValueError("数据为空")
            
        start_time = min(all_times)
        end_time = max(all_times)
        
        return start_time, end_time
        
    def run(self) -> Dict[str, Any]:
        """
        运行回测
        
        Returns:
            Dict[str, Any]: 回测结果
        """
        self.logger.info("开始回测")
        self.is_running = True
        
        try:
            # 加载数据
            data = self.load_data()
            
            # 获取时间范围
            start_time, end_time = self.get_universe_time_range(data)
            
            # 生成时间序列
            time_series = pd.date_range(start=start_time, end=end_time, freq="min")
            
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
            
            # 主循环
            for i, timestamp in enumerate(time_series):
                self.current_time = timestamp
                
                # 获取当前时间点的数据
                current_data = {}
                for key, df in data.items():
                    # 获取到当前时间为止的所有数据
                    mask = df.index <= timestamp
                    current_df = df[mask].copy()
                    
                    if not current_df.empty:
                        current_data[key] = current_df
                        
                if not current_data:
                    continue
                    
                # 更新持仓价格
                self._update_positions(current_data)
                
                # 计算当前权益
                equity = self._calculate_equity(current_data)
                self.equity_curve.append((timestamp, equity))
                
                # 生成交易信号
                signals = self.strategy.generate_signals(current_data)
                
                # 执行交易信号
                for signal in signals:
                    self._execute_signal(signal, current_data)
                    
                # 定期输出进度
                if i % 1000 == 0:
                    self.logger.info(f"回测进度: {i}/{len(time_series)}, 当前时间: {timestamp}, 权益: {equity:.2f}")
                    
            # 计算最终权益
            final_data = {}
            for key, df in data.items():
                final_data[key] = df.copy()
                
            self._update_positions(final_data)
            final_equity = self._calculate_equity(final_data)
            
            # 生成回测结果
            results = self._generate_results(final_equity)
            
            self.logger.info(f"回测完成, 最终权益: {final_equity:.2f}, 总收益率: {(final_equity/self.initial_balance - 1)*100:.2f}%")
            
            return results
            
        except Exception as e:
            self.logger.error(f"回测过程中发生错误: {e}")
            raise
            
        finally:
            self.is_running = False
            
    def _update_positions(self, data: Dict[str, pd.DataFrame]):
        """更新持仓价格"""
        for symbol, position in self.positions.items():
            for key, df in data.items():
                if symbol in key and not df.empty:
                    latest_price = df.iloc[-1]['close']
                    position.update_price(latest_price)
                    break
                    
    def _calculate_equity(self, data: Dict[str, pd.DataFrame]) -> float:
        """计算当前权益"""
        equity = self.balance
        
        for symbol, position in self.positions.items():
            if position.quantity != 0:
                # 获取最新价格
                for key, df in data.items():
                    if symbol in key and not df.empty:
                        latest_price = df.iloc[-1]['close']
                        equity += position.quantity * latest_price
                        break
                        
        return equity
        
    def _execute_signal(self, signal: Signal, data: Dict[str, pd.DataFrame]):
        """执行交易信号"""
        symbol = signal.symbol
        
        # 获取当前价格
        current_price = None
        for key, df in data.items():
            if symbol in key and not df.empty:
                current_price = df.iloc[-1]['close']
                break
                
        if current_price is None:
            self.logger.warning(f"无法获取 {symbol} 的当前价格，跳过信号")
            return
            
        # 初始化持仓
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
            
        position = self.positions[symbol]
        
        # 计算滑点后的价格
        if signal.signal_type == SignalType.BUY:
            execution_price = current_price * (1 + self.config.slippage)
        elif signal.signal_type == SignalType.SELL:
            execution_price = current_price * (1 - self.config.slippage)
        else:
            execution_price = current_price
            
        # 执行交易
        if signal.signal_type == SignalType.BUY:
            # 买入
            quantity = signal.quantity
            cost = execution_price * quantity
            fee = cost * self.config.fee_rate
            total_cost = cost + fee
            
            if total_cost > self.balance:
                self.logger.warning(f"资金不足，无法买入 {symbol}, 需要 {total_cost:.2f}, 余额 {self.balance:.2f}")
                return
                
            # 执行交易
            position_fee = position.execute_trade("buy", execution_price, quantity, self.config.fee_rate)
            self.balance -= total_cost
            
            # 记录交易
            trade = TradeRecord(
                timestamp=self.current_time,
                symbol=symbol,
                side="buy",
                price=execution_price,
                quantity=quantity,
                value=cost,
                fee=position_fee,
                balance=self.balance,
                strategy_id=self.strategy.name if hasattr(self.strategy, 'name') else "unknown"
            )
            self.trade_records.append(trade)
            
            self.logger.info(f"买入 {symbol}: 价格 {execution_price:.4f}, 数量 {quantity}, 价值 {cost:.2f}, 手续费 {position_fee:.2f}")
            
        elif signal.signal_type == SignalType.SELL:
            # 卖出
            quantity = min(signal.quantity, position.quantity)
            
            if quantity <= 0:
                self.logger.warning(f"持仓不足，无法卖出 {symbol}, 持仓 {position.quantity}")
                return
                
            revenue = execution_price * quantity
            fee = revenue * self.config.fee_rate
            net_revenue = revenue - fee
            
            # 执行交易
            position_fee = position.execute_trade("sell", execution_price, quantity, self.config.fee_rate)
            self.balance += net_revenue
            
            # 记录交易
            trade = TradeRecord(
                timestamp=self.current_time,
                symbol=symbol,
                side="sell",
                price=execution_price,
                quantity=quantity,
                value=revenue,
                fee=position_fee,
                pnl=position.realized_pnl,
                balance=self.balance,
                strategy_id=self.strategy.name if hasattr(self.strategy, 'name') else "unknown"
            )
            self.trade_records.append(trade)
            
            self.logger.info(f"卖出 {symbol}: 价格 {execution_price:.4f}, 数量 {quantity}, 价值 {revenue:.2f}, 手续费 {position_fee:.2f}, 已实现盈亏 {position.realized_pnl:.2f}")
            
        elif signal.signal_type == SignalType.CLOSE:
            # 平仓
            if position.quantity > 0:
                # 全部卖出
                revenue = execution_price * position.quantity
                fee = revenue * self.config.fee_rate
                net_revenue = revenue - fee
                
                # 执行交易
                position_fee = position.execute_trade("sell", execution_price, position.quantity, self.config.fee_rate)
                self.balance += net_revenue
                
                # 记录交易
                trade = TradeRecord(
                    timestamp=self.current_time,
                    symbol=symbol,
                    side="sell",
                    price=execution_price,
                    quantity=position.quantity,
                    value=revenue,
                    fee=position_fee,
                    pnl=position.realized_pnl,
                    balance=self.balance,
                    strategy_id=self.strategy.name if hasattr(self.strategy, 'name') else "unknown"
                )
                self.trade_records.append(trade)
                
                self.logger.info(f"平仓 {symbol}: 价格 {execution_price:.4f}, 数量 {position.quantity}, 价值 {revenue:.2f}, 手续费 {position_fee:.2f}, 已实现盈亏 {position.realized_pnl:.2f}")
                
    def _generate_results(self, final_equity: float) -> Dict[str, Any]:
        """生成回测结果"""
        # 创建权益曲线DataFrame
        equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)
        
        # 创建交易记录DataFrame
        trades_df = pd.DataFrame([vars(trade) for trade in self.trade_records])
        
        # 计算基本统计
        total_return = (final_equity / self.initial_balance - 1) * 100
        total_trades = len(self.trade_records)
        
        # 计算每日收益率
        daily_returns = equity_df['equity'].pct_change().dropna()
        
        # 计算年化收益率
        days = (equity_df.index[-1] - equity_df.index[0]).days
        if days > 0:
            annual_return = ((final_equity / self.initial_balance) ** (365 / days) - 1) * 100
        else:
            annual_return = 0
            
        # 计算最大回撤
        rolling_max = equity_df['equity'].expanding().max()
        drawdown = (equity_df['equity'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100
        
        # 计算夏普比率
        if daily_returns.std() != 0:
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(365)
        else:
            sharpe_ratio = 0
            
        # 计算胜率
        winning_trades = trades_df[trades_df['pnl'] > 0] if not trades_df.empty else pd.DataFrame()
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        # 计算盈亏比
        if not winning_trades.empty and not trades_df.empty:
            losing_trades = trades_df[trades_df['pnl'] < 0]
            avg_win = winning_trades['pnl'].mean() if not winning_trades.empty else 0
            avg_loss = abs(losing_trades['pnl'].mean()) if not losing_trades.empty else 1
            profit_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        else:
            profit_loss_ratio = 0
            
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
            "profit_loss_ratio": profit_loss_ratio,
            "equity_curve": equity_df,
            "trade_records": trades_df,
            "positions": self.positions
        }
        
        # 保存到文件
        self._save_results(results)
        
        return results
        
    def _save_results(self, results: Dict[str, Any]):
        """保存回测结果"""
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
            f.write(f"回测摘要\n")
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
            f.write(f"盈亏比: {results['profit_loss_ratio']:.2f}\n")
            
        self.logger.info(f"回测结果已保存到 {output_dir}")
