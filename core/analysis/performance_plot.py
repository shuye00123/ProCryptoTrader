"""
可视化绘图模块

提供交易结果可视化功能，包括收益曲线、回撤分析、交易分布图等。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Union, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 设置样式
sns.set_style('whitegrid')
plt.style.use('seaborn-v0_8')


@dataclass
class PlotConfig:
    """绘图配置"""
    figsize: Tuple[int, int] = (12, 8)
    dpi: int = 100
    style: str = 'seaborn-v0_8'
    title_fontsize: int = 16
    label_fontsize: int = 12
    tick_fontsize: int = 10
    legend_fontsize: int = 12
    color_palette: str = 'viridis'
    save_format: str = 'png'
    transparent: bool = False


class PerformancePlotter:
    """绩效绘图器"""
    
    def __init__(self, config: Optional[PlotConfig] = None):
        """
        初始化绩效绘图器
        
        Args:
            config: 绘图配置
        """
        self.config = config or PlotConfig()
        plt.style.use(self.config.style)
        sns.set_palette(self.config.color_palette)
    
    def plot_equity_curve(self, data: pd.DataFrame, title: str = "Equity Curve", 
                         save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制资金曲线
        
        Args:
            data: 数据框，包含日期和权益列
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        fig, ax = plt.subplots(figsize=self.config.figsize, dpi=self.config.dpi)
        
        # 绘制资金曲线
        ax.plot(data['date'], data['equity'], linewidth=2, label='Equity')
        
        # 设置标题和标签
        ax.set_title(title, fontsize=self.config.title_fontsize)
        ax.set_xlabel('Date', fontsize=self.config.label_fontsize)
        ax.set_ylabel('Equity', fontsize=self.config.label_fontsize)
        
        # 设置日期格式
        if 'date' in data.columns and pd.api.types.is_datetime64_any_dtype(data['date']):
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            plt.xticks(rotation=45)
        
        # 添加图例
        ax.legend(fontsize=self.config.legend_fontsize)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Equity curve saved to {save_path}")
        
        return fig
    
    def plot_drawdown(self, data: pd.DataFrame, title: str = "Drawdown", 
                     save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制回撤图
        
        Args:
            data: 数据框，包含日期和回撤列
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        fig, ax = plt.subplots(figsize=self.config.figsize, dpi=self.config.dpi)
        
        # 绘制回撤
        ax.fill_between(data['date'], data['drawdown'], 0, alpha=0.3, color='red', label='Drawdown')
        ax.plot(data['date'], data['drawdown'], color='red', linewidth=1)
        
        # 设置标题和标签
        ax.set_title(title, fontsize=self.config.title_fontsize)
        ax.set_xlabel('Date', fontsize=self.config.label_fontsize)
        ax.set_ylabel('Drawdown (%)', fontsize=self.config.label_fontsize)
        
        # 设置日期格式
        if 'date' in data.columns and pd.api.types.is_datetime64_any_dtype(data['date']):
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            plt.xticks(rotation=45)
        
        # 添加图例
        ax.legend(fontsize=self.config.legend_fontsize)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Drawdown plot saved to {save_path}")
        
        return fig
    
    def plot_monthly_returns(self, data: pd.DataFrame, title: str = "Monthly Returns", 
                           save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制月度收益热力图
        
        Args:
            data: 数据框，包含年月和收益率列
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        # 准备数据
        if 'year_month' in data.columns:
            # 提取年份和月份
            data['year'] = data['year_month'].str[:4].astype(int)
            data['month'] = data['year_month'].str[5:7].astype(int)
            
            # 创建透视表
            pivot_data = data.pivot_table(index='year', columns='month', values='return', aggfunc='sum')
            
            # 设置月份名称
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            pivot_data.columns = [month_names[i-1] for i in pivot_data.columns]
        else:
            # 假设数据已经是透视表格式
            pivot_data = data
        
        # 创建图表
        fig, ax = plt.subplots(figsize=self.config.figsize, dpi=self.config.dpi)
        
        # 绘制热力图
        sns.heatmap(pivot_data, annot=True, fmt=".2f", cmap="RdYlGn", center=0,
                   ax=ax, cbar_kws={'label': 'Return (%)'})
        
        # 设置标题
        ax.set_title(title, fontsize=self.config.title_fontsize)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Monthly returns heatmap saved to {save_path}")
        
        return fig
    
    def plot_trade_distribution(self, data: pd.DataFrame, title: str = "Trade Distribution", 
                              save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制交易分布图
        
        Args:
            data: 数据框，包含盈亏列
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), dpi=self.config.dpi)
        
        # 盈亏分布直方图
        ax1.hist(data['pnl'], bins=30, alpha=0.7, edgecolor='black')
        ax1.axvline(data['pnl'].mean(), color='red', linestyle='dashed', 
                   linewidth=2, label=f"Mean: {data['pnl'].mean():.2f}")
        ax1.set_title('P&L Distribution', fontsize=self.config.title_fontsize)
        ax1.set_xlabel('P&L', fontsize=self.config.label_fontsize)
        ax1.set_ylabel('Frequency', fontsize=self.config.label_fontsize)
        ax1.legend(fontsize=self.config.legend_fontsize)
        ax1.grid(True, alpha=0.3)
        
        # 盈亏散点图
        ax2.scatter(range(len(data)), data['pnl'], alpha=0.7, s=10)
        ax2.axhline(0, color='black', linestyle='-', linewidth=1)
        ax2.set_title('Trade P&L Sequence', fontsize=self.config.title_fontsize)
        ax2.set_xlabel('Trade Number', fontsize=self.config.label_fontsize)
        ax2.set_ylabel('P&L', fontsize=self.config.label_fontsize)
        ax2.grid(True, alpha=0.3)
        
        # 设置总标题
        fig.suptitle(title, fontsize=self.config.title_fontsize + 2)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Trade distribution plot saved to {save_path}")
        
        return fig
    
    def plot_symbol_performance(self, data: pd.DataFrame, title: str = "Symbol Performance", 
                              save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制交易对表现图
        
        Args:
            data: 数据框，包含交易对、盈亏、胜率等列
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), dpi=self.config.dpi)
        
        # 按盈亏排序
        sorted_data = data.sort_values('pnl', ascending=True)
        
        # 盈亏柱状图
        colors = ['green' if x >= 0 else 'red' for x in sorted_data['pnl']]
        ax1.barh(sorted_data['symbol'], sorted_data['pnl'], color=colors, alpha=0.7)
        ax1.set_title('P&L by Symbol', fontsize=self.config.title_fontsize)
        ax1.set_xlabel('P&L', fontsize=self.config.label_fontsize)
        ax1.grid(True, alpha=0.3)
        
        # 胜率柱状图
        ax2.bar(sorted_data['symbol'], sorted_data['win_rate'], alpha=0.7, color='blue')
        ax2.set_title('Win Rate by Symbol', fontsize=self.config.title_fontsize)
        ax2.set_xlabel('Symbol', fontsize=self.config.label_fontsize)
        ax2.set_ylabel('Win Rate', fontsize=self.config.label_fontsize)
        ax2.set_ylim(0, 1)
        ax2.grid(True, alpha=0.3)
        plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
        
        # 设置总标题
        fig.suptitle(title, fontsize=self.config.title_fontsize + 2)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Symbol performance plot saved to {save_path}")
        
        return fig
    
    def plot_risk_metrics(self, data: Dict[str, Any], title: str = "Risk Metrics", 
                         save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制风险指标图
        
        Args:
            data: 风险指标字典
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        # 提取风险指标
        metrics = {
            'Sharpe Ratio': data.get('sharpe_ratio', 0),
            'Sortino Ratio': data.get('sortino_ratio', 0),
            'Calmar Ratio': data.get('calmar_ratio', 0),
            'Max Drawdown': data.get('max_drawdown', 0) * 100,  # 转换为百分比
            'Volatility': data.get('volatility', 0) * 100,  # 转换为百分比
            'Beta': data.get('beta', 0),
            'Alpha': data.get('alpha', 0) * 100,  # 转换为百分比
            'Information Ratio': data.get('information_ratio', 0)
        }
        
        # 创建图表
        fig, ax = plt.subplots(figsize=self.config.figsize, dpi=self.config.dpi)
        
        # 绘制风险指标
        metrics_names = list(metrics.keys())
        metrics_values = list(metrics.values())
        
        bars = ax.bar(metrics_names, metrics_values, alpha=0.7)
        
        # 为正值和负值设置不同颜色
        for bar, value in zip(bars, metrics_values):
            if value >= 0:
                bar.set_color('green')
            else:
                bar.set_color('red')
        
        # 添加数值标签
        for i, v in enumerate(metrics_values):
            ax.text(i, v + (0.01 if v >= 0 else -0.01), 
                   f"{v:.2f}", ha='center', va='bottom' if v >= 0 else 'top')
        
        # 设置标题和标签
        ax.set_title(title, fontsize=self.config.title_fontsize)
        ax.set_xlabel('Risk Metric', fontsize=self.config.label_fontsize)
        ax.set_ylabel('Value', fontsize=self.config.label_fontsize)
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # 添加水平线
        ax.axhline(0, color='black', linestyle='-', linewidth=0.5)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Risk metrics plot saved to {save_path}")
        
        return fig
    
    def plot_correlation_matrix(self, data: pd.DataFrame, title: str = "Correlation Matrix", 
                              save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制相关性矩阵热力图
        
        Args:
            data: 数据框
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        # 计算相关性矩阵
        corr_matrix = data.corr()
        
        # 创建图表
        fig, ax = plt.subplots(figsize=self.config.figsize, dpi=self.config.dpi)
        
        # 绘制热力图
        sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", center=0,
                   ax=ax, square=True, cbar_kws={'label': 'Correlation'})
        
        # 设置标题
        ax.set_title(title, fontsize=self.config.title_fontsize)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Correlation matrix plot saved to {save_path}")
        
        return fig
    
    def plot_rolling_metrics(self, data: pd.DataFrame, window: int = 30, 
                           title: str = "Rolling Metrics", save_path: Optional[str] = None) -> plt.Figure:
        """
        绘制滚动指标图
        
        Args:
            data: 数据框，包含日期和收益率列
            window: 滚动窗口大小
            title: 图表标题
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        # 计算滚动指标
        rolling_mean = data['return'].rolling(window=window).mean()
        rolling_std = data['return'].rolling(window=window).std()
        rolling_sharpe = rolling_mean / rolling_std * np.sqrt(252) if rolling_std.std() != 0 else 0
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), dpi=self.config.dpi, 
                                      sharex=True)
        
        # 绘制滚动收益率
        ax1.plot(data['date'], data['return'], alpha=0.5, label='Daily Return')
        ax1.plot(data['date'], rolling_mean, color='red', linewidth=2, 
                label=f'{window}-Day Rolling Mean')
        ax1.fill_between(data['date'], rolling_mean - rolling_std, rolling_mean + rolling_std, 
                        alpha=0.2, color='red', label=f'{window}-Day Rolling Std')
        ax1.set_title('Rolling Returns', fontsize=self.config.title_fontsize)
        ax1.set_ylabel('Return', fontsize=self.config.label_fontsize)
        ax1.legend(fontsize=self.config.legend_fontsize)
        ax1.grid(True, alpha=0.3)
        
        # 绘制滚动夏普比率
        ax2.plot(data['date'], rolling_sharpe, color='green', linewidth=2, 
                label=f'{window}-Day Rolling Sharpe')
        ax2.axhline(0, color='black', linestyle='-', linewidth=0.5)
        ax2.set_title('Rolling Sharpe Ratio', fontsize=self.config.title_fontsize)
        ax2.set_xlabel('Date', fontsize=self.config.label_fontsize)
        ax2.set_ylabel('Sharpe Ratio', fontsize=self.config.label_fontsize)
        ax2.legend(fontsize=self.config.legend_fontsize)
        ax2.grid(True, alpha=0.3)
        
        # 设置日期格式
        if 'date' in data.columns and pd.api.types.is_datetime64_any_dtype(data['date']):
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            plt.xticks(rotation=45)
        
        # 设置总标题
        fig.suptitle(title, fontsize=self.config.title_fontsize + 2)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Rolling metrics plot saved to {save_path}")
        
        return fig
    
    def create_dashboard(self, equity_data: pd.DataFrame, drawdown_data: pd.DataFrame, 
                        monthly_returns: pd.DataFrame, trade_data: pd.DataFrame, 
                        risk_metrics: Dict[str, Any], save_path: Optional[str] = None) -> plt.Figure:
        """
        创建综合仪表板
        
        Args:
            equity_data: 权益数据
            drawdown_data: 回撤数据
            monthly_returns: 月度收益数据
            trade_data: 交易数据
            risk_metrics: 风险指标
            save_path: 保存路径
            
        Returns:
            plt.Figure: 图表对象
        """
        # 创建4x2的子图布局
        fig = plt.figure(figsize=(20, 16), dpi=self.config.dpi)
        
        # 1. 资金曲线
        ax1 = plt.subplot(3, 3, 1)
        ax1.plot(equity_data['date'], equity_data['equity'], linewidth=2)
        ax1.set_title('Equity Curve', fontsize=self.config.title_fontsize)
        ax1.set_ylabel('Equity', fontsize=self.config.label_fontsize)
        if 'date' in equity_data.columns and pd.api.types.is_datetime64_any_dtype(equity_data['date']):
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax1.get_xticklabels(), rotation=45)
        
        # 2. 回撤图
        ax2 = plt.subplot(3, 3, 2)
        ax2.fill_between(drawdown_data['date'], drawdown_data['drawdown'], 0, 
                        alpha=0.3, color='red')
        ax2.plot(drawdown_data['date'], drawdown_data['drawdown'], color='red', linewidth=1)
        ax2.set_title('Drawdown', fontsize=self.config.title_fontsize)
        ax2.set_ylabel('Drawdown (%)', fontsize=self.config.label_fontsize)
        if 'date' in drawdown_data.columns and pd.api.types.is_datetime64_any_dtype(drawdown_data['date']):
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax2.get_xticklabels(), rotation=45)
        
        # 3. 月度收益热力图
        ax3 = plt.subplot(3, 3, 3)
        if 'year_month' in monthly_returns.columns:
            # 提取年份和月份
            monthly_returns['year'] = monthly_returns['year_month'].str[:4].astype(int)
            monthly_returns['month'] = monthly_returns['year_month'].str[5:7].astype(int)
            
            # 创建透视表
            pivot_data = monthly_returns.pivot_table(index='year', columns='month', 
                                                   values='return', aggfunc='sum')
            
            # 绘制热力图
            sns.heatmap(pivot_data, annot=True, fmt=".2f", cmap="RdYlGn", center=0,
                       ax=ax3, cbar_kws={'label': 'Return (%)'})
        ax3.set_title('Monthly Returns', fontsize=self.config.title_fontsize)
        
        # 4. 交易分布
        ax4 = plt.subplot(3, 3, 4)
        ax4.hist(trade_data['pnl'], bins=20, alpha=0.7, edgecolor='black')
        ax4.axvline(trade_data['pnl'].mean(), color='red', linestyle='dashed', 
                   linewidth=2, label=f"Mean: {trade_data['pnl'].mean():.2f}")
        ax4.set_title('P&L Distribution', fontsize=self.config.title_fontsize)
        ax4.set_xlabel('P&L', fontsize=self.config.label_fontsize)
        ax4.set_ylabel('Frequency', fontsize=self.config.label_fontsize)
        ax4.legend(fontsize=self.config.legend_fontsize)
        
        # 5. 交易对表现
        ax5 = plt.subplot(3, 3, 5)
        if 'symbol' in trade_data.columns:
            symbol_performance = trade_data.groupby('symbol')['pnl'].sum().sort_values()
            colors = ['green' if x >= 0 else 'red' for x in symbol_performance.values]
            ax5.barh(symbol_performance.index, symbol_performance.values, color=colors, alpha=0.7)
        ax5.set_title('P&L by Symbol', fontsize=self.config.title_fontsize)
        ax5.set_xlabel('P&L', fontsize=self.config.label_fontsize)
        
        # 6. 风险指标
        ax6 = plt.subplot(3, 3, 6)
        metrics = {
            'Sharpe': risk_metrics.get('sharpe_ratio', 0),
            'Sortino': risk_metrics.get('sortino_ratio', 0),
            'Calmar': risk_metrics.get('calmar_ratio', 0),
            'Max DD': risk_metrics.get('max_drawdown', 0) * 100,
            'Vol': risk_metrics.get('volatility', 0) * 100
        }
        metrics_names = list(metrics.keys())
        metrics_values = list(metrics.values())
        
        bars = ax6.bar(metrics_names, metrics_values, alpha=0.7)
        for bar, value in zip(bars, metrics_values):
            if value >= 0:
                bar.set_color('green')
            else:
                bar.set_color('red')
        
        ax6.set_title('Risk Metrics', fontsize=self.config.title_fontsize)
        ax6.set_ylabel('Value', fontsize=self.config.label_fontsize)
        plt.setp(ax6.get_xticklabels(), rotation=45)
        
        # 7. 滚动夏普比率
        ax7 = plt.subplot(3, 3, 7)
        if 'return' in equity_data.columns:
            rolling_sharpe = equity_data['return'].rolling(window=30).mean() / \
                           equity_data['return'].rolling(window=30).std() * np.sqrt(252)
            ax7.plot(equity_data['date'], rolling_sharpe, color='green', linewidth=2)
            ax7.axhline(0, color='black', linestyle='-', linewidth=0.5)
        ax7.set_title('Rolling Sharpe Ratio (30D)', fontsize=self.config.title_fontsize)
        ax7.set_xlabel('Date', fontsize=self.config.label_fontsize)
        ax7.set_ylabel('Sharpe Ratio', fontsize=self.config.label_fontsize)
        if 'date' in equity_data.columns and pd.api.types.is_datetime64_any_dtype(equity_data['date']):
            ax7.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax7.get_xticklabels(), rotation=45)
        
        # 8. 交易统计
        ax8 = plt.subplot(3, 3, 8)
        if 'symbol' in trade_data.columns:
            win_rate = len(trade_data[trade_data['pnl'] > 0]) / len(trade_data) * 100
            profit_factor = trade_data[trade_data['pnl'] > 0]['pnl'].sum() / \
                           abs(trade_data[trade_data['pnl'] < 0]['pnl'].sum()) \
                           if len(trade_data[trade_data['pnl'] < 0]) > 0 else float('inf')
            
            stats = {
                'Total Trades': len(trade_data),
                'Win Rate (%)': win_rate,
                'Profit Factor': profit_factor,
                'Avg Trade': trade_data['pnl'].mean(),
                'Total P&L': trade_data['pnl'].sum()
            }
            
            stats_names = list(stats.keys())
            stats_values = list(stats.values())
            
            bars = ax8.bar(stats_names, stats_values, alpha=0.7)
            for bar, value in zip(bars, stats_values):
                if value >= 0:
                    bar.set_color('green')
                else:
                    bar.set_color('red')
            
            for i, v in enumerate(stats_values):
                ax8.text(i, v + (0.01 if v >= 0 else -0.01), 
                        f"{v:.2f}", ha='center', va='bottom' if v >= 0 else 'top')
        
        ax8.set_title('Trade Statistics', fontsize=self.config.title_fontsize)
        ax8.set_ylabel('Value', fontsize=self.config.label_fontsize)
        plt.setp(ax8.get_xticklabels(), rotation=45)
        
        # 9. 累计收益
        ax9 = plt.subplot(3, 3, 9)
        if 'return' in equity_data.columns:
            cumulative_return = (1 + equity_data['return']).cumprod()
            ax9.plot(equity_data['date'], cumulative_return, linewidth=2, color='blue')
            ax9.set_title('Cumulative Return', fontsize=self.config.title_fontsize)
            ax9.set_xlabel('Date', fontsize=self.config.label_fontsize)
            ax9.set_ylabel('Cumulative Return', fontsize=self.config.label_fontsize)
            ax9.set_yscale('log')
            if 'date' in equity_data.columns and pd.api.types.is_datetime64_any_dtype(equity_data['date']):
                ax9.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax9.get_xticklabels(), rotation=45)
        
        # 设置总标题
        fig.suptitle('Trading Performance Dashboard', fontsize=self.config.title_fontsize + 4)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        if save_path:
            plt.savefig(save_path, format=self.config.save_format, 
                       transparent=self.config.transparent, bbox_inches='tight')
            logger.info(f"Dashboard saved to {save_path}")
        
        return fig