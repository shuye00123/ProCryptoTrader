"""
绩效评估指标模块

提供各种量化交易策略绩效评估指标的计算功能。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass
import scipy.stats as stats


@dataclass
class PerformanceMetrics:
    """绩效指标数据类"""
    # 收益指标
    total_return: float = 0.0  # 总收益率
    annual_return: float = 0.0  # 年化收益率
    monthly_return: float = 0.0  # 月均收益率
    
    # 风险指标
    volatility: float = 0.0  # 年化波动率
    max_drawdown: float = 0.0  # 最大回撤
    max_drawdown_duration: int = 0  # 最大回撤持续期(天)
    
    # 风险调整收益指标
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    calmar_ratio: float = 0.0  # 卡玛比率
    information_ratio: float = 0.0  # 信息比率
    
    # 交易相关指标
    total_trades: int = 0  # 总交易次数
    win_rate: float = 0.0  # 胜率
    profit_loss_ratio: float = 0.0  # 盈亏比
    avg_trade_return: float = 0.0  # 平均交易收益率
    avg_win_return: float = 0.0  # 平均盈利交易收益率
    avg_loss_return: float = 0.0  # 平均亏损交易收益率
    
    # 其他指标
    skewness: float = 0.0  # 收益率偏度
    kurtosis: float = 0.0  # 收益率峰度
    var_95: float = 0.0  # 95%置信度VaR
    cvar_95: float = 0.0  # 95%置信度CVaR
    beta: float = 0.0  # 贝塔系数
    alpha: float = 0.0  # 阿尔法系数
    
    # 基准比较
    benchmark_return: float = 0.0  # 基准收益率
    excess_return: float = 0.0  # 超额收益率
    tracking_error: float = 0.0  # 跟踪误差
    
    # 时间统计
    start_date: str = ""  # 开始日期
    end_date: str = ""  # 结束日期
    trading_days: int = 0  # 交易天数


class MetricsCalculator:
    """绩效指标计算器"""
    
    @staticmethod
    def calculate_returns(equity_curve: pd.Series, 
                          benchmark_curve: Optional[pd.Series] = None,
                          risk_free_rate: float = 0.02) -> PerformanceMetrics:
        """
        计算绩效指标
        
        Args:
            equity_curve: 权益曲线，索引为日期，值为权益值
            benchmark_curve: 基准曲线，可选
            risk_free_rate: 无风险利率，默认为2%
            
        Returns:
            PerformanceMetrics: 绩效指标对象
        """
        metrics = PerformanceMetrics()
        
        if equity_curve.empty:
            return metrics
            
        # 确保索引是日期类型
        if not isinstance(equity_curve.index, pd.DatetimeIndex):
            equity_curve.index = pd.to_datetime(equity_curve.index)
            
        if benchmark_curve is not None and not isinstance(benchmark_curve.index, pd.DatetimeIndex):
            benchmark_curve.index = pd.to_datetime(benchmark_curve.index)
            
        # 设置时间统计
        metrics.start_date = equity_curve.index[0].strftime('%Y-%m-%d')
        metrics.end_date = equity_curve.index[-1].strftime('%Y-%m-%d')
        metrics.trading_days = len(equity_curve)
        
        # 计算日收益率
        returns = equity_curve.pct_change().dropna()
        
        # 计算基准收益率（如果有）
        benchmark_returns = None
        if benchmark_curve is not None:
            # 对齐日期
            common_dates = equity_curve.index.intersection(benchmark_curve.index)
            if len(common_dates) > 0:
                aligned_equity = equity_curve.loc[common_dates]
                aligned_benchmark = benchmark_curve.loc[common_dates]
                benchmark_returns = aligned_benchmark.pct_change().dropna()
                returns = aligned_equity.pct_change().dropna()
        
        # 计算收益指标
        metrics.total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100
        
        # 计算年化收益率
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        if days > 0:
            years = days / 365.25
            metrics.annual_return = ((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1/years) - 1) * 100
            metrics.monthly_return = ((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1/(days/30)) - 1) * 100
        
        # 计算风险指标
        metrics.volatility = returns.std() * np.sqrt(365) * 100  # 年化波动率
        
        # 计算最大回撤
        rolling_max = equity_curve.expanding().max()
        drawdown = (equity_curve - rolling_max) / rolling_max
        metrics.max_drawdown = drawdown.min() * 100
        
        # 计算最大回撤持续期
        drawdown_duration = []
        current_duration = 0
        for dd in drawdown:
            if dd < 0:
                current_duration += 1
            else:
                if current_duration > 0:
                    drawdown_duration.append(current_duration)
                current_duration = 0
        if current_duration > 0:
            drawdown_duration.append(current_duration)
        metrics.max_drawdown_duration = max(drawdown_duration) if drawdown_duration else 0
        
        # 计算风险调整收益指标
        excess_daily_returns = returns - risk_free_rate/365
        if excess_daily_returns.std() != 0:
            metrics.sharpe_ratio = excess_daily_returns.mean() / excess_daily_returns.std() * np.sqrt(365)
        
        # 计算索提诺比率（只考虑下行波动）
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() != 0:
            metrics.sortino_ratio = excess_daily_returns.mean() / downside_returns.std() * np.sqrt(365)
        
        # 计算卡玛比率（年化收益率/最大回撤）
        if metrics.max_drawdown != 0:
            metrics.calmar_ratio = metrics.annual_return / abs(metrics.max_drawdown)
        
        # 计算信息比率（如果有基准）
        if benchmark_returns is not None:
            excess_returns = returns - benchmark_returns
            if excess_returns.std() != 0:
                metrics.information_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(365)
            
            # 计算基准收益率
            metrics.benchmark_return = (benchmark_curve.iloc[-1] / benchmark_curve.iloc[0] - 1) * 100
            metrics.excess_return = metrics.total_return - metrics.benchmark_return
            
            # 计算跟踪误差
            metrics.tracking_error = excess_returns.std() * np.sqrt(365) * 100
            
            # 计算贝塔系数
            if benchmark_returns.var() != 0:
                covariance = np.cov(returns, benchmark_returns)[0, 1]
                metrics.beta = covariance / benchmark_returns.var()
                
            # 计算阿尔法系数
            market_return = metrics.benchmark_return / 100
            risk_free_annual = risk_free_rate
            expected_return = risk_free_annual + metrics.beta * (market_return - risk_free_annual)
            metrics.alpha = (metrics.annual_return / 100 - expected_return) * 100
        
        # 计算收益率分布特征
        metrics.skewness = returns.skew()
        metrics.kurtosis = returns.kurtosis()
        
        # 计算VaR和CVaR
        metrics.var_95 = np.percentile(returns, 5) * 100
        metrics.cvar_95 = returns[returns <= np.percentile(returns, 5)].mean() * 100
        
        return metrics
    
    @staticmethod
    def calculate_trade_metrics(trade_records: pd.DataFrame) -> Dict[str, float]:
        """
        计算交易相关指标
        
        Args:
            trade_records: 交易记录DataFrame
            
        Returns:
            Dict[str, float]: 交易指标字典
        """
        if trade_records.empty:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_loss_ratio": 0.0,
                "avg_trade_return": 0.0,
                "avg_win_return": 0.0,
                "avg_loss_return": 0.0
            }
            
        # 计算每笔交易的盈亏
        if 'pnl' not in trade_records.columns:
            # 如果没有pnl列，尝试从交易记录中计算
            trade_records = MetricsCalculator._calculate_pnl_from_trades(trade_records)
            
        # 分离盈利和亏损交易
        winning_trades = trade_records[trade_records['pnl'] > 0]
        losing_trades = trade_records[trade_records['pnl'] < 0]
        
        # 计算指标
        total_trades = len(trade_records)
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        avg_win = winning_trades['pnl'].mean() if not winning_trades.empty else 0
        avg_loss = abs(losing_trades['pnl'].mean()) if not losing_trades.empty else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        
        avg_trade_return = trade_records['pnl'].mean() if not trade_records.empty else 0
        avg_win_return = avg_win
        avg_loss_return = -avg_loss
        
        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "avg_trade_return": avg_trade_return,
            "avg_win_return": avg_win_return,
            "avg_loss_return": avg_loss_return
        }
    
    @staticmethod
    def _calculate_pnl_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
        """
        从交易记录中计算每笔交易的盈亏
        
        Args:
            trades: 交易记录DataFrame
            
        Returns:
            pd.DataFrame: 包含pnl列的交易记录
        """
        # 按交易对分组
        result = trades.copy()
        result['pnl'] = 0.0
        
        for symbol, symbol_trades in trades.groupby('symbol'):
            # 按时间排序
            symbol_trades = symbol_trades.sort_values('timestamp')
            
            # 计算每笔交易的盈亏
            position = 0
            total_cost = 0
            
            for idx, trade in symbol_trades.iterrows():
                if trade['side'] == 'buy':
                    # 买入
                    position += trade['quantity']
                    total_cost += trade['value'] + trade['fee']
                elif trade['side'] == 'sell':
                    # 卖出
                    if position > 0:
                        # 计算已实现盈亏
                        sell_value = trade['value'] - trade['fee']
                        sell_ratio = min(trade['quantity'], position) / position
                        cost_of_sold = total_cost * sell_ratio
                        pnl = sell_value - cost_of_sold
                        
                        result.at[idx, 'pnl'] = pnl
                        
                        # 更新持仓和成本
                        sold_quantity = min(trade['quantity'], position)
                        position -= sold_quantity
                        total_cost -= cost_of_sold
                        
        return result
    
    @staticmethod
    def calculate_rolling_metrics(equity_curve: pd.Series, 
                                 window: int = 30) -> pd.DataFrame:
        """
        计算滚动指标
        
        Args:
            equity_curve: 权益曲线
            window: 滚动窗口大小（天）
            
        Returns:
            pd.DataFrame: 滚动指标DataFrame
        """
        if equity_curve.empty or len(equity_curve) < window:
            return pd.DataFrame()
            
        # 计算日收益率
        returns = equity_curve.pct_change().dropna()
        
        # 计算滚动指标
        rolling_return = returns.rolling(window=window).mean() * window * 100  # 滚动收益率
        rolling_volatility = returns.rolling(window=window).std() * np.sqrt(window) * 100  # 滚动波动率
        rolling_sharpe = rolling_return / rolling_volatility  # 滚动夏普比率
        
        # 计算滚动最大回撤
        rolling_max = equity_curve.rolling(window=window).max()
        rolling_drawdown = (equity_curve - rolling_max) / rolling_max * 100
        
        # 合并结果
        result = pd.DataFrame({
            'rolling_return': rolling_return,
            'rolling_volatility': rolling_volatility,
            'rolling_sharpe': rolling_sharpe,
            'rolling_drawdown': rolling_drawdown
        })
        
        return result
    
    @staticmethod
    def compare_strategies(results_dict: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
        """
        比较多个策略的绩效
        
        Args:
            results_dict: 策略结果字典，键为策略名称，值为回测结果
            
        Returns:
            pd.DataFrame: 策略比较表
        """
        comparison_data = []
        
        for strategy_name, results in results_dict.items():
            if 'equity_curve' in results and not results['equity_curve'].empty:
                # 计算绩效指标
                metrics = MetricsCalculator.calculate_returns(results['equity_curve'])
                
                # 添加交易指标
                if 'trade_records' in results and not results['trade_records'].empty:
                    trade_metrics = MetricsCalculator.calculate_trade_metrics(results['trade_records'])
                    metrics.total_trades = trade_metrics['total_trades']
                    metrics.win_rate = trade_metrics['win_rate']
                    metrics.profit_loss_ratio = trade_metrics['profit_loss_ratio']
                
                # 添加到比较数据
                comparison_data.append({
                    'Strategy': strategy_name,
                    'Total Return (%)': metrics.total_return,
                    'Annual Return (%)': metrics.annual_return,
                    'Max Drawdown (%)': metrics.max_drawdown,
                    'Sharpe Ratio': metrics.sharpe_ratio,
                    'Win Rate (%)': metrics.win_rate,
                    'Total Trades': metrics.total_trades,
                    'Profit/Loss Ratio': metrics.profit_loss_ratio
                })
        
        # 创建比较表
        comparison_df = pd.DataFrame(comparison_data)
        comparison_df.set_index('Strategy', inplace=True)
        
        return comparison_df
    
    @staticmethod
    def calculate_correlation_matrix(equity_curves: Dict[str, pd.Series]) -> pd.DataFrame:
        """
        计算多个策略收益率的 correlation matrix
        
        Args:
            equity_curves: 策略权益曲线字典，键为策略名称，值为权益曲线
            
        Returns:
            pd.DataFrame: 相关性矩阵
        """
        # 计算每个策略的日收益率
        returns_dict = {}
        
        for strategy_name, equity_curve in equity_curves.items():
            if not equity_curve.empty:
                returns = equity_curve.pct_change().dropna()
                returns_dict[strategy_name] = returns
        
        # 创建收益率DataFrame
        returns_df = pd.DataFrame(returns_dict)
        
        # 计算相关性矩阵
        correlation_matrix = returns_df.corr()
        
        return correlation_matrix