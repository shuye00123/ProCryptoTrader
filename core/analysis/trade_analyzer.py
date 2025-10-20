"""
交易结果分析模块

提供交易结果分析功能，包括交易统计、绩效评估、风险分析等。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    """交易方向枚举"""
    LONG = "long"
    SHORT = "short"


class TradeStatus(Enum):
    """交易状态枚举"""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass
class Trade:
    """交易记录"""
    id: str
    symbol: str
    direction: TradeDirection
    status: TradeStatus
    entry_time: datetime
    entry_price: float
    size: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    commission: float = 0.0
    slippage: float = 0.0
    notes: str = ""
    
    def __post_init__(self):
        """初始化后处理"""
        if self.exit_time is None:
            self.exit_time = self.entry_time
        if self.exit_price is None:
            self.exit_price = self.entry_price
    
    @property
    def is_closed(self) -> bool:
        """是否已平仓"""
        return self.status == TradeStatus.CLOSED
    
    @property
    def duration(self) -> timedelta:
        """持仓时间"""
        return self.exit_time - self.entry_time
    
    @property
    def pnl(self) -> float:
        """盈亏"""
        if not self.is_closed:
            return 0.0
        
        if self.direction == TradeDirection.LONG:
            return (self.exit_price - self.entry_price) * self.size - self.commission - self.slippage
        else:
            return (self.entry_price - self.exit_price) * self.size - self.commission - self.slippage
    
    @property
    def pnl_percent(self) -> float:
        """盈亏百分比"""
        if not self.is_closed or self.entry_price == 0:
            return 0.0
        
        if self.direction == TradeDirection.LONG:
            return (self.exit_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - self.exit_price) / self.entry_price * 100
    
    @property
    def return_rate(self) -> float:
        """收益率"""
        if not self.is_closed:
            return 0.0
        
        investment = self.entry_price * self.size
        if investment == 0:
            return 0.0
        
        return self.pnl / investment


@dataclass
class TradeStatistics:
    """交易统计数据"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_loss_ratio: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    total_return: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))
    longest_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))
    shortest_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))


class TradeAnalyzer:
    """交易分析器"""
    
    def __init__(self):
        """初始化交易分析器"""
        self.trades: List[Trade] = []
        self.statistics: Optional[TradeStatistics] = None
    
    def add_trade(self, trade: Trade):
        """
        添加交易记录
        
        Args:
            trade: 交易记录
        """
        self.trades.append(trade)
        self.statistics = None  # 重置统计数据
    
    def add_trades(self, trades: List[Trade]):
        """
        批量添加交易记录
        
        Args:
            trades: 交易记录列表
        """
        self.trades.extend(trades)
        self.statistics = None  # 重置统计数据
    
    def clear_trades(self):
        """清空交易记录"""
        self.trades.clear()
        self.statistics = None
    
    def calculate_statistics(self) -> TradeStatistics:
        """
        计算交易统计数据
        
        Returns:
            TradeStatistics: 交易统计数据
        """
        if self.statistics is not None:
            return self.statistics
        
        # 过滤已平仓的交易
        closed_trades = [trade for trade in self.trades if trade.is_closed]
        
        if not closed_trades:
            self.statistics = TradeStatistics()
            return self.statistics
        
        # 基本统计
        total_trades = len(closed_trades)
        winning_trades = [trade for trade in closed_trades if trade.pnl > 0]
        losing_trades = [trade for trade in closed_trades if trade.pnl < 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # 盈亏统计
        avg_win = np.mean([trade.pnl for trade in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([trade.pnl for trade in losing_trades]) if losing_trades else 0
        
        avg_win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        total_win = sum(trade.pnl for trade in winning_trades)
        total_loss = sum(abs(trade.pnl) for trade in losing_trades)
        profit_factor = total_win / total_loss if total_loss != 0 else float('inf')
        
        total_pnl = sum(trade.pnl for trade in closed_trades)
        
        # 计算总收益率（假设初始资金为100000）
        initial_capital = 100000.0
        total_return = total_pnl / initial_capital
        
        # 连续盈亏统计
        consecutive_wins, consecutive_losses = self._calculate_consecutive_trades(closed_trades)
        max_consecutive_wins = max(consecutive_wins) if consecutive_wins else 0
        max_consecutive_losses = max(consecutive_losses) if consecutive_losses else 0
        
        # 持仓时间统计
        durations = [trade.duration for trade in closed_trades]
        avg_trade_duration = sum(durations, timedelta(0)) / len(durations) if durations else timedelta(0)
        longest_trade_duration = max(durations) if durations else timedelta(0)
        shortest_trade_duration = min(durations) if durations else timedelta(0)
        
        # 创建统计数据对象
        self.statistics = TradeStatistics(
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_loss_ratio=avg_win_loss_ratio,
            profit_factor=profit_factor,
            total_pnl=total_pnl,
            total_return=total_return,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            avg_trade_duration=avg_trade_duration,
            longest_trade_duration=longest_trade_duration,
            shortest_trade_duration=shortest_trade_duration
        )
        
        return self.statistics
    
    def _calculate_consecutive_trades(self, trades: List[Trade]) -> Tuple[List[int], List[int]]:
        """
        计算连续盈亏次数
        
        Args:
            trades: 交易记录列表
            
        Returns:
            Tuple[List[int], List[int]]: 连续盈利次数列表，连续亏损次数列表
        """
        consecutive_wins = []
        consecutive_losses = []
        
        current_win_streak = 0
        current_loss_streak = 0
        
        for trade in trades:
            if trade.pnl > 0:
                current_win_streak += 1
                if current_loss_streak > 0:
                    consecutive_losses.append(current_loss_streak)
                    current_loss_streak = 0
            elif trade.pnl < 0:
                current_loss_streak += 1
                if current_win_streak > 0:
                    consecutive_wins.append(current_win_streak)
                    current_win_streak = 0
            else:  # pnl == 0
                if current_win_streak > 0:
                    consecutive_wins.append(current_win_streak)
                    current_win_streak = 0
                if current_loss_streak > 0:
                    consecutive_losses.append(current_loss_streak)
                    current_loss_streak = 0
        
        # 添加最后一个序列
        if current_win_streak > 0:
            consecutive_wins.append(current_win_streak)
        if current_loss_streak > 0:
            consecutive_losses.append(current_loss_streak)
        
        return consecutive_wins, consecutive_losses
    
    def get_trades_by_symbol(self, symbol: str) -> List[Trade]:
        """
        获取指定交易对的交易记录
        
        Args:
            symbol: 交易对
            
        Returns:
            List[Trade]: 交易记录列表
        """
        return [trade for trade in self.trades if trade.symbol == symbol]
    
    def get_trades_by_direction(self, direction: TradeDirection) -> List[Trade]:
        """
        获取指定方向的交易记录
        
        Args:
            direction: 交易方向
            
        Returns:
            List[Trade]: 交易记录列表
        """
        return [trade for trade in self.trades if trade.direction == direction]
    
    def get_trades_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Trade]:
        """
        获取指定日期范围内的交易记录
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            List[Trade]: 交易记录列表
        """
        return [
            trade for trade in self.trades
            if start_date <= trade.entry_time <= end_date
        ]
    
    def get_daily_pnl(self) -> pd.DataFrame:
        """
        获取每日盈亏
        
        Returns:
            pd.DataFrame: 每日盈亏数据框，包含日期、盈亏、累计盈亏等列
        """
        if not self.trades:
            return pd.DataFrame(columns=['date', 'pnl', 'cumulative_pnl'])
        
        # 创建交易记录数据框
        trades_data = []
        for trade in self.trades:
            if trade.is_closed:
                trades_data.append({
                    'date': trade.exit_time.date(),
                    'pnl': trade.pnl
                })
        
        if not trades_data:
            return pd.DataFrame(columns=['date', 'pnl', 'cumulative_pnl'])
        
        df = pd.DataFrame(trades_data)
        
        # 按日期分组并计算每日盈亏
        daily_pnl = df.groupby('date')['pnl'].sum().reset_index()
        daily_pnl = daily_pnl.sort_values('date')
        
        # 计算累计盈亏
        daily_pnl['cumulative_pnl'] = daily_pnl['pnl'].cumsum()
        
        return daily_pnl
    
    def get_monthly_pnl(self) -> pd.DataFrame:
        """
        获取每月盈亏
        
        Returns:
            pd.DataFrame: 每月盈亏数据框，包含年月、盈亏、累计盈亏等列
        """
        if not self.trades:
            return pd.DataFrame(columns=['year_month', 'pnl', 'cumulative_pnl'])
        
        # 创建交易记录数据框
        trades_data = []
        for trade in self.trades:
            if trade.is_closed:
                trades_data.append({
                    'year_month': trade.exit_time.strftime('%Y-%m'),
                    'pnl': trade.pnl
                })
        
        if not trades_data:
            return pd.DataFrame(columns=['year_month', 'pnl', 'cumulative_pnl'])
        
        df = pd.DataFrame(trades_data)
        
        # 按年月分组并计算每月盈亏
        monthly_pnl = df.groupby('year_month')['pnl'].sum().reset_index()
        monthly_pnl = monthly_pnl.sort_values('year_month')
        
        # 计算累计盈亏
        monthly_pnl['cumulative_pnl'] = monthly_pnl['pnl'].cumsum()
        
        return monthly_pnl
    
    def get_symbol_performance(self) -> pd.DataFrame:
        """
        获取各交易对的表现
        
        Returns:
            pd.DataFrame: 各交易对表现数据框，包含交易对、交易次数、盈亏、胜率等列
        """
        if not self.trades:
            return pd.DataFrame(columns=['symbol', 'trades', 'pnl', 'win_rate', 'avg_pnl'])
        
        # 创建交易记录数据框
        trades_data = []
        for trade in self.trades:
            if trade.is_closed:
                trades_data.append({
                    'symbol': trade.symbol,
                    'pnl': trade.pnl,
                    'is_win': trade.pnl > 0
                })
        
        if not trades_data:
            return pd.DataFrame(columns=['symbol', 'trades', 'pnl', 'win_rate', 'avg_pnl'])
        
        df = pd.DataFrame(trades_data)
        
        # 按交易对分组并计算统计数据
        symbol_stats = df.groupby('symbol').agg({
            'pnl': ['sum', 'mean', 'count'],
            'is_win': 'sum'
        }).reset_index()
        
        # 扁平化列名
        symbol_stats.columns = ['symbol', 'total_pnl', 'avg_pnl', 'trades', 'winning_trades']
        
        # 计算胜率
        symbol_stats['win_rate'] = symbol_stats['winning_trades'] / symbol_stats['trades']
        
        # 选择需要的列
        result = symbol_stats[['symbol', 'trades', 'total_pnl', 'win_rate', 'avg_pnl']]
        result = result.rename(columns={'total_pnl': 'pnl'})
        
        # 按总盈亏排序
        result = result.sort_values('pnl', ascending=False)
        
        return result
    
    def get_trade_distribution(self) -> Dict[str, Any]:
        """
        获取交易分布统计
        
        Returns:
            Dict[str, Any]: 交易分布统计，包含盈亏分布、持仓时间分布等
        """
        if not self.trades:
            return {}
        
        # 过滤已平仓的交易
        closed_trades = [trade for trade in self.trades if trade.is_closed]
        
        if not closed_trades:
            return {}
        
        # 盈亏分布
        pnl_values = [trade.pnl for trade in closed_trades]
        pnl_stats = {
            'min': min(pnl_values),
            'max': max(pnl_values),
            'mean': np.mean(pnl_values),
            'median': np.median(pnl_values),
            'std': np.std(pnl_values),
            'percentiles': {
                '5%': np.percentile(pnl_values, 5),
                '25%': np.percentile(pnl_values, 25),
                '75%': np.percentile(pnl_values, 75),
                '95%': np.percentile(pnl_values, 95)
            }
        }
        
        # 持仓时间分布（以小时为单位）
        duration_hours = [trade.duration.total_seconds() / 3600 for trade in closed_trades]
        duration_stats = {
            'min_hours': min(duration_hours),
            'max_hours': max(duration_hours),
            'mean_hours': np.mean(duration_hours),
            'median_hours': np.median(duration_hours),
            'std_hours': np.std(duration_hours),
            'percentiles': {
                '5%': np.percentile(duration_hours, 5),
                '25%': np.percentile(duration_hours, 25),
                '75%': np.percentile(duration_hours, 75),
                '95%': np.percentile(duration_hours, 95)
            }
        }
        
        # 按交易方向统计
        long_trades = [trade for trade in closed_trades if trade.direction == TradeDirection.LONG]
        short_trades = [trade for trade in closed_trades if trade.direction == TradeDirection.SHORT]
        
        direction_stats = {
            'long': {
                'count': len(long_trades),
                'win_rate': sum(1 for trade in long_trades if trade.pnl > 0) / len(long_trades) if long_trades else 0,
                'avg_pnl': np.mean([trade.pnl for trade in long_trades]) if long_trades else 0,
                'total_pnl': sum(trade.pnl for trade in long_trades)
            },
            'short': {
                'count': len(short_trades),
                'win_rate': sum(1 for trade in short_trades if trade.pnl > 0) / len(short_trades) if short_trades else 0,
                'avg_pnl': np.mean([trade.pnl for trade in short_trades]) if short_trades else 0,
                'total_pnl': sum(trade.pnl for trade in short_trades)
            }
        }
        
        return {
            'pnl_distribution': pnl_stats,
            'duration_distribution': duration_stats,
            'direction_stats': direction_stats
        }
    
    def export_trades(self, file_path: str, format: str = 'csv'):
        """
        导出交易记录
        
        Args:
            file_path: 文件路径
            format: 文件格式 ('csv', 'excel', 'json')
        """
        if not self.trades:
            logger.warning("No trades to export")
            return
        
        # 转换交易记录为字典列表
        trades_data = []
        for trade in self.trades:
            trade_dict = {
                'id': trade.id,
                'symbol': trade.symbol,
                'direction': trade.direction.value,
                'status': trade.status.value,
                'entry_time': trade.entry_time.isoformat(),
                'entry_price': trade.entry_price,
                'size': trade.size,
                'exit_time': trade.exit_time.isoformat(),
                'exit_price': trade.exit_price,
                'commission': trade.commission,
                'slippage': trade.slippage,
                'pnl': trade.pnl,
                'pnl_percent': trade.pnl_percent,
                'return_rate': trade.return_rate,
                'duration_hours': trade.duration.total_seconds() / 3600,
                'notes': trade.notes
            }
            trades_data.append(trade_dict)
        
        # 创建数据框
        df = pd.DataFrame(trades_data)
        
        # 根据格式导出
        if format.lower() == 'csv':
            df.to_csv(file_path, index=False)
        elif format.lower() == 'excel':
            df.to_excel(file_path, index=False)
        elif format.lower() == 'json':
            df.to_json(file_path, orient='records', date_format='iso')
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        logger.info(f"Exported {len(self.trades)} trades to {file_path}")
    
    def generate_report(self) -> Dict[str, Any]:
        """
        生成交易分析报告
        
        Returns:
            Dict[str, Any]: 交易分析报告
        """
        # 计算统计数据
        stats = self.calculate_statistics()
        
        # 获取每日盈亏
        daily_pnl = self.get_daily_pnl()
        
        # 获取每月盈亏
        monthly_pnl = self.get_monthly_pnl()
        
        # 获取各交易对表现
        symbol_performance = self.get_symbol_performance()
        
        # 获取交易分布
        trade_distribution = self.get_trade_distribution()
        
        # 构建报告
        report = {
            'summary': {
                'total_trades': stats.total_trades,
                'winning_trades': stats.winning_trades,
                'losing_trades': stats.losing_trades,
                'win_rate': stats.win_rate,
                'avg_win': stats.avg_win,
                'avg_loss': stats.avg_loss,
                'avg_win_loss_ratio': stats.avg_win_loss_ratio,
                'profit_factor': stats.profit_factor,
                'total_pnl': stats.total_pnl,
                'total_return': stats.total_return,
                'max_consecutive_wins': stats.max_consecutive_wins,
                'max_consecutive_losses': stats.max_consecutive_losses,
                'avg_trade_duration_hours': stats.avg_trade_duration.total_seconds() / 3600,
                'longest_trade_duration_hours': stats.longest_trade_duration.total_seconds() / 3600,
                'shortest_trade_duration_hours': stats.shortest_trade_duration.total_seconds() / 3600
            },
            'daily_pnl': daily_pnl.to_dict('records') if not daily_pnl.empty else [],
            'monthly_pnl': monthly_pnl.to_dict('records') if not monthly_pnl.empty else [],
            'symbol_performance': symbol_performance.to_dict('records') if not symbol_performance.empty else [],
            'trade_distribution': trade_distribution
        }
        
        return report