"""
回测报告生成模块

提供回测结果的可视化和报告生成功能，支持多种格式输出。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.offline as pyo

from .metrics import MetricsCalculator, PerformanceMetrics


class ReportGenerator:
    """回测报告生成器"""
    
    def __init__(self, results: Dict[str, Any], output_dir: str = "results"):
        """
        初始化报告生成器
        
        Args:
            results: 回测结果字典
            output_dir: 输出目录
        """
        self.results = results
        self.output_dir = output_dir
        self.equity_curve = results.get('equity_curve', pd.DataFrame())
        self.trade_records = results.get('trade_records', pd.DataFrame())
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置matplotlib中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 设置seaborn样式
        sns.set_style("whitegrid")
        
    def generate_html_report(self) -> str:
        """
        生成HTML格式的回测报告
        
        Returns:
            str: HTML报告文件路径
        """
        # 计算绩效指标
        metrics = MetricsCalculator.calculate_returns(self.equity_curve)
        trade_metrics = MetricsCalculator.calculate_trade_metrics(self.trade_records)
        
        # 更新交易指标
        metrics.total_trades = trade_metrics['total_trades']
        metrics.win_rate = trade_metrics['win_rate']
        metrics.profit_loss_ratio = trade_metrics['profit_loss_ratio']
        metrics.avg_trade_return = trade_metrics['avg_trade_return']
        metrics.avg_win_return = trade_metrics['avg_win_return']
        metrics.avg_loss_return = trade_metrics['avg_loss_return']
        
        # 生成图表
        equity_plot = self._plot_equity_curve(plotly=True)
        drawdown_plot = self._plot_drawdown(plotly=True)
        monthly_returns_plot = self._plot_monthly_returns(plotly=True)
        trade_distribution_plot = self._plot_trade_distribution(plotly=True)
        
        # 生成HTML内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>量化交易回测报告</title>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1, h2, h3 {{
                    color: #333;
                }}
                .metrics-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .metric-card {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 6px;
                    border-left: 4px solid #007bff;
                }}
                .metric-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #007bff;
                }}
                .metric-label {{
                    font-size: 14px;
                    color: #666;
                }}
                .plot-container {{
                    margin-bottom: 30px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                th, td {{
                    padding: 10px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                .positive {{
                    color: green;
                }}
                .negative {{
                    color: red;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>量化交易回测报告</h1>
                <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                
                <h2>绩效指标</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">{metrics.total_return:.2f}%</div>
                        <div class="metric-label">总收益率</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.annual_return:.2f}%</div>
                        <div class="metric-label">年化收益率</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.max_drawdown:.2f}%</div>
                        <div class="metric-label">最大回撤</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.sharpe_ratio:.2f}</div>
                        <div class="metric-label">夏普比率</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.win_rate:.2f}%</div>
                        <div class="metric-label">胜率</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.profit_loss_ratio:.2f}</div>
                        <div class="metric-label">盈亏比</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.volatility:.2f}%</div>
                        <div class="metric-label">年化波动率</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{metrics.total_trades}</div>
                        <div class="metric-label">总交易次数</div>
                    </div>
                </div>
                
                <h2>权益曲线</h2>
                <div class="plot-container">
                    {equity_plot}
                </div>
                
                <h2>回撤分析</h2>
                <div class="plot-container">
                    {drawdown_plot}
                </div>
                
                <h2>月度收益</h2>
                <div class="plot-container">
                    {monthly_returns_plot}
                </div>
                
                <h2>交易分布</h2>
                <div class="plot-container">
                    {trade_distribution_plot}
                </div>
                
                <h2>交易记录</h2>
                {self._generate_trade_table()}
                
                <h2>风险指标</h2>
                <table>
                    <tr>
                        <th>指标</th>
                        <th>值</th>
                    </tr>
                    <tr>
                        <td>索提诺比率</td>
                        <td>{metrics.sortino_ratio:.2f}</td>
                    </tr>
                    <tr>
                        <td>卡玛比率</td>
                        <td>{metrics.calmar_ratio:.2f}</td>
                    </tr>
                    <tr>
                        <td>信息比率</td>
                        <td>{metrics.information_ratio:.2f}</td>
                    </tr>
                    <tr>
                        <td>偏度</td>
                        <td>{metrics.skewness:.2f}</td>
                    </tr>
                    <tr>
                        <td>峰度</td>
                        <td>{metrics.kurtosis:.2f}</td>
                    </tr>
                    <tr>
                        <td>VaR (95%)</td>
                        <td>{metrics.var_95:.2f}%</td>
                    </tr>
                    <tr>
                        <td>CVaR (95%)</td>
                        <td>{metrics.cvar_95:.2f}%</td>
                    </tr>
                </table>
                
                <h2>回测配置</h2>
                <table>
                    <tr>
                        <th>参数</th>
                        <th>值</th>
                    </tr>
                    <tr>
                        <td>开始日期</td>
                        <td>{metrics.start_date}</td>
                    </tr>
                    <tr>
                        <td>结束日期</td>
                        <td>{metrics.end_date}</td>
                    </tr>
                    <tr>
                        <td>初始资金</td>
                        <td>{self.results.get('initial_balance', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td>最终资金</td>
                        <td>{self.results.get('final_balance', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td>手续费率</td>
                        <td>{self.results.get('config', {}).get('fee_rate', 0):.4f}</td>
                    </tr>
                    <tr>
                        <td>滑点</td>
                        <td>{self.results.get('config', {}).get('slippage', 0):.4f}</td>
                    </tr>
                </table>
            </div>
        </body>
        </html>
        """
        
        # 保存HTML文件
        html_file = os.path.join(self.output_dir, "backtest_report.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return html_file
    
    def _plot_equity_curve(self, plotly: bool = False) -> str:
        """
        绘制权益曲线
        
        Args:
            plotly: 是否使用plotly
            
        Returns:
            str: 图表HTML或图片路径
        """
        if self.equity_curve.empty:
            return "<p>无权益曲线数据</p>"
            
        if plotly:
            # 使用plotly绘制交互式图表
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=self.equity_curve.index,
                y=self.equity_curve['equity'],
                mode='lines',
                name='权益曲线',
                line=dict(color='blue', width=2)
            ))
            
            fig.update_layout(
                title='权益曲线',
                xaxis_title='日期',
                yaxis_title='权益',
                hovermode='x unified',
                template='plotly_white'
            )
            
            # 转换为HTML
            return pyo.plot(fig, output_type='div', include_plotlyjs=False)
        else:
            # 使用matplotlib绘制静态图表
            plt.figure(figsize=(12, 6))
            plt.plot(self.equity_curve.index, self.equity_curve['equity'], label='权益曲线', color='blue')
            plt.title('权益曲线')
            plt.xlabel('日期')
            plt.ylabel('权益')
            plt.legend()
            plt.grid(True)
            
            # 保存图片
            img_file = os.path.join(self.output_dir, "equity_curve.png")
            plt.savefig(img_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            return f'<img src="{img_file}" alt="权益曲线">'
    
    def _plot_drawdown(self, plotly: bool = False) -> str:
        """
        绘制回撤曲线
        
        Args:
            plotly: 是否使用plotly
            
        Returns:
            str: 图表HTML或图片路径
        """
        if self.equity_curve.empty:
            return "<p>无权益曲线数据</p>"
            
        # 计算回撤
        rolling_max = self.equity_curve['equity'].expanding().max()
        drawdown = (self.equity_curve['equity'] - rolling_max) / rolling_max * 100
        
        if plotly:
            # 使用plotly绘制交互式图表
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=self.equity_curve.index,
                y=drawdown,
                mode='lines',
                name='回撤',
                line=dict(color='red', width=2),
                fill='tonexty'
            ))
            
            fig.update_layout(
                title='回撤曲线',
                xaxis_title='日期',
                yaxis_title='回撤 (%)',
                hovermode='x unified',
                template='plotly_white'
            )
            
            # 转换为HTML
            return pyo.plot(fig, output_type='div', include_plotlyjs=False)
        else:
            # 使用matplotlib绘制静态图表
            plt.figure(figsize=(12, 6))
            plt.fill_between(self.equity_curve.index, drawdown, 0, color='red', alpha=0.3)
            plt.plot(self.equity_curve.index, drawdown, color='red', label='回撤')
            plt.title('回撤曲线')
            plt.xlabel('日期')
            plt.ylabel('回撤 (%)')
            plt.legend()
            plt.grid(True)
            
            # 保存图片
            img_file = os.path.join(self.output_dir, "drawdown.png")
            plt.savefig(img_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            return f'<img src="{img_file}" alt="回撤曲线">'
    
    def _plot_monthly_returns(self, plotly: bool = False) -> str:
        """
        绘制月度收益热力图
        
        Args:
            plotly: 是否使用plotly
            
        Returns:
            str: 图表HTML或图片路径
        """
        if self.equity_curve.empty:
            return "<p>无权益曲线数据</p>"
            
        # 计算月度收益率
        monthly_returns = self.equity_curve['equity'].resample('M').last().pct_change().dropna() * 100
        
        # 创建年-月矩阵
        monthly_returns.index = pd.to_datetime(monthly_returns.index)
        monthly_returns_df = monthly_returns.to_frame('returns')
        monthly_returns_df['year'] = monthly_returns_df.index.year
        monthly_returns_df['month'] = monthly_returns_df.index.month
        
        # 透视表
        heatmap_data = monthly_returns_df.pivot(index='year', columns='month', values='returns')
        
        # 设置月份名称
        month_names = ['1月', '2月', '3月', '4月', '5月', '6月', 
                      '7月', '8月', '9月', '10月', '11月', '12月']
        heatmap_data.columns = [month_names[i-1] for i in heatmap_data.columns]
        
        if plotly:
            # 使用plotly绘制交互式热力图
            fig = go.Figure(data=go.Heatmap(
                z=heatmap_data.values,
                x=heatmap_data.columns,
                y=heatmap_data.index,
                colorscale='RdYlGn',
                zmid=0,
                text=heatmap_data.round(2).values,
                texttemplate="%{text}%",
                textfont={"size": 10},
                hoverongaps=False
            ))
            
            fig.update_layout(
                title='月度收益率热力图 (%)',
                xaxis_title='月份',
                yaxis_title='年份'
            )
            
            # 转换为HTML
            return pyo.plot(fig, output_type='div', include_plotlyjs=False)
        else:
            # 使用matplotlib绘制静态热力图
            plt.figure(figsize=(12, 8))
            sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="RdYlGn", center=0)
            plt.title('月度收益率热力图 (%)')
            plt.xlabel('月份')
            plt.ylabel('年份')
            
            # 保存图片
            img_file = os.path.join(self.output_dir, "monthly_returns.png")
            plt.savefig(img_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            return f'<img src="{img_file}" alt="月度收益率热力图">'
    
    def _plot_trade_distribution(self, plotly: bool = False) -> str:
        """
        绘制交易分布图
        
        Args:
            plotly: 是否使用plotly
            
        Returns:
            str: 图表HTML或图片路径
        """
        if self.trade_records.empty:
            return "<p>无交易记录数据</p>"
            
        # 计算每笔交易的盈亏
        if 'pnl' not in self.trade_records.columns:
            self.trade_records = MetricsCalculator._calculate_pnl_from_trades(self.trade_records)
            
        # 分离盈利和亏损交易
        winning_trades = self.trade_records[self.trade_records['pnl'] > 0]['pnl']
        losing_trades = self.trade_records[self.trade_records['pnl'] < 0]['pnl']
        
        if plotly:
            # 使用plotly绘制交互式直方图
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('盈利交易分布', '亏损交易分布'),
                vertical_spacing=0.1
            )
            
            if not winning_trades.empty:
                fig.add_trace(
                    go.Histogram(x=winning_trades, nbinsx=20, name='盈利交易', marker_color='green'),
                    row=1, col=1
                )
                
            if not losing_trades.empty:
                fig.add_trace(
                    go.Histogram(x=losing_trades, nbinsx=20, name='亏损交易', marker_color='red'),
                    row=2, col=1
                )
                
            fig.update_layout(
                title='交易分布',
                height=600,
                showlegend=False
            )
            
            fig.update_xaxes(title_text="盈利", row=1, col=1)
            fig.update_xaxes(title_text="亏损", row=2, col=1)
            fig.update_yaxes(title_text="交易次数", row=1, col=1)
            fig.update_yaxes(title_text="交易次数", row=2, col=1)
            
            # 转换为HTML
            return pyo.plot(fig, output_type='div', include_plotlyjs=False)
        else:
            # 使用matplotlib绘制静态直方图
            fig, axes = plt.subplots(2, 1, figsize=(12, 10))
            
            if not winning_trades.empty:
                axes[0].hist(winning_trades, bins=20, color='green', alpha=0.7)
                axes[0].set_title('盈利交易分布')
                axes[0].set_xlabel('盈利')
                axes[0].set_ylabel('交易次数')
                axes[0].grid(True)
                
            if not losing_trades.empty:
                axes[1].hist(losing_trades, bins=20, color='red', alpha=0.7)
                axes[1].set_title('亏损交易分布')
                axes[1].set_xlabel('亏损')
                axes[1].set_ylabel('交易次数')
                axes[1].grid(True)
                
            plt.tight_layout()
            
            # 保存图片
            img_file = os.path.join(self.output_dir, "trade_distribution.png")
            plt.savefig(img_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            return f'<img src="{img_file}" alt="交易分布">'
    
    def _generate_trade_table(self) -> str:
        """
        生成交易记录表格
        
        Returns:
            str: HTML表格
        """
        if self.trade_records.empty:
            return "<p>无交易记录数据</p>"
            
        # 计算每笔交易的盈亏
        if 'pnl' not in self.trade_records.columns:
            self.trade_records = MetricsCalculator._calculate_pnl_from_trades(self.trade_records)
            
        # 只显示最近50笔交易
        recent_trades = self.trade_records.tail(50).copy()
        
        # 格式化日期
        recent_trades['timestamp'] = pd.to_datetime(recent_trades['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # 格式化数值
        for col in ['price', 'quantity', 'value', 'fee', 'pnl', 'balance']:
            if col in recent_trades.columns:
                recent_trades[col] = recent_trades[col].round(4)
                
        # 生成HTML表格
        table_html = "<table>"
        table_html += "<tr><th>时间</th><th>交易对</th><th>方向</th><th>价格</th><th>数量</th><th>价值</th><th>手续费</th><th>盈亏</th><th>余额</th></tr>"
        
        for _, trade in recent_trades.iterrows():
            pnl_class = "positive" if trade['pnl'] > 0 else "negative" if trade['pnl'] < 0 else ""
            
            table_html += f"""
            <tr>
                <td>{trade['timestamp']}</td>
                <td>{trade['symbol']}</td>
                <td>{trade['side']}</td>
                <td>{trade['price']}</td>
                <td>{trade['quantity']}</td>
                <td>{trade['value']}</td>
                <td>{trade['fee']}</td>
                <td class="{pnl_class}">{trade['pnl']}</td>
                <td>{trade['balance']}</td>
            </tr>
            """
            
        table_html += "</table>"
        
        return table_html
    
    def generate_markdown_report(self) -> str:
        """
        生成Markdown格式的回测报告
        
        Returns:
            str: Markdown报告文件路径
        """
        # 计算绩效指标
        metrics = MetricsCalculator.calculate_returns(self.equity_curve)
        trade_metrics = MetricsCalculator.calculate_trade_metrics(self.trade_records)
        
        # 更新交易指标
        metrics.total_trades = trade_metrics['total_trades']
        metrics.win_rate = trade_metrics['win_rate']
        metrics.profit_loss_ratio = trade_metrics['profit_loss_ratio']
        metrics.avg_trade_return = trade_metrics['avg_trade_return']
        metrics.avg_win_return = trade_metrics['avg_win_return']
        metrics.avg_loss_return = trade_metrics['avg_loss_return']
        
        # 生成图表
        equity_plot = self._plot_equity_curve()
        drawdown_plot = self._plot_drawdown()
        monthly_returns_plot = self._plot_monthly_returns()
        trade_distribution_plot = self._plot_trade_distribution()
        
        # 生成Markdown内容
        markdown_content = f"""
# 量化交易回测报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 绩效指标

| 指标 | 值 |
|------|-----|
| 总收益率 | {metrics.total_return:.2f}% |
| 年化收益率 | {metrics.annual_return:.2f}% |
| 最大回撤 | {metrics.max_drawdown:.2f}% |
| 夏普比率 | {metrics.sharpe_ratio:.2f} |
| 胜率 | {metrics.win_rate:.2f}% |
| 盈亏比 | {metrics.profit_loss_ratio:.2f} |
| 年化波动率 | {metrics.volatility:.2f}% |
| 总交易次数 | {metrics.total_trades} |

## 权益曲线

{equity_plot}

## 回撤分析

{drawdown_plot}

## 月度收益

{monthly_returns_plot}

## 交易分布

{trade_distribution_plot}

## 风险指标

| 指标 | 值 |
|------|-----|
| 索提诺比率 | {metrics.sortino_ratio:.2f} |
| 卡玛比率 | {metrics.calmar_ratio:.2f} |
| 信息比率 | {metrics.information_ratio:.2f} |
| 偏度 | {metrics.skewness:.2f} |
| 峰度 | {metrics.kurtosis:.2f} |
| VaR (95%) | {metrics.var_95:.2f}% |
| CVaR (95%) | {metrics.cvar_95:.2f}% |

## 回测配置

| 参数 | 值 |
|------|-----|
| 开始日期 | {metrics.start_date} |
| 结束日期 | {metrics.end_date} |
| 初始资金 | {self.results.get('initial_balance', 0):.2f} |
| 最终资金 | {self.results.get('final_balance', 0):.2f} |
| 手续费率 | {self.results.get('config', {}).get('fee_rate', 0):.4f} |
| 滑点 | {self.results.get('config', {}).get('slippage', 0):.4f} |
        """
        
        # 保存Markdown文件
        md_file = os.path.join(self.output_dir, "backtest_report.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        return md_file
    
    def generate_all_reports(self) -> Dict[str, str]:
        """
        生成所有格式的报告
        
        Returns:
            Dict[str, str]: 报告文件路径字典
        """
        reports = {}
        
        try:
            reports['html'] = self.generate_html_report()
        except Exception as e:
            print(f"生成HTML报告失败: {e}")
            
        try:
            reports['markdown'] = self.generate_markdown_report()
        except Exception as e:
            print(f"生成Markdown报告失败: {e}")
            
        return reports