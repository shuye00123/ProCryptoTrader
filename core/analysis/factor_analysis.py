"""
因子效果评估模块

提供因子效果评估功能，包括因子收益分析、因子IC分析、因子换手率分析等。
遵循RIPER-5原则：风险优先、最小侵入、可预期性、可扩展性、真实可评估。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from scipy import stats

logger = logging.getLogger(__name__)


class FactorType(Enum):
    """因子类型枚举"""
    VALUE = "value"  # 价值因子
    QUALITY = "quality"  # 质量因子
    MOMENTUM = "momentum"  # 动量因子
    SIZE = "size"  # 规模因子
    VOLATILITY = "volatility"  # 波动率因子
    LIQUIDITY = "liquidity"  # 流动性因子
    GROWTH = "growth"  # 成长因子
    CUSTOM = "custom"  # 自定义因子


@dataclass
class FactorData:
    """因子数据"""
    name: str
    factor_type: FactorType
    data: pd.DataFrame  # 包含日期、标的、因子值等列
    description: str = ""
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保数据框包含必要的列
        required_columns = ['date', 'symbol', 'factor_value']
        for col in required_columns:
            if col not in self.data.columns:
                raise ValueError(f"Factor data must contain column: {col}")
        
        # 确保日期列为datetime类型
        if not pd.api.types.is_datetime64_any_dtype(self.data['date']):
            self.data['date'] = pd.to_datetime(self.data['date'])
        
        # 按日期和标的排序
        self.data = self.data.sort_values(['date', 'symbol'])


@dataclass
class FactorPerformance:
    """因子表现"""
    name: str
    factor_type: FactorType
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_ir: float = 0.0  # IC信息比率
    ic_win_rate: float = 0.0  # IC胜率
    annualized_return: float = 0.0  # 年化收益
    annualized_volatility: float = 0.0  # 年化波动率
    sharpe_ratio: float = 0.0  # 夏普比率
    max_drawdown: float = 0.0  # 最大回撤
    turnover: float = 0.0  # 换手率
    group_ic_mean: Dict[str, float] = field(default_factory=dict)  # 分组IC均值
    group_ic_std: Dict[str, float] = field(default_factory=dict)  # 分组IC标准差
    group_return: Dict[str, float] = field(default_factory=dict)  # 分组收益
    long_short_return: float = 0.0  # 多空收益
    long_short_sharpe: float = 0.0  # 多空夏普比率


class FactorAnalyzer:
    """因子分析器"""
    
    def __init__(self):
        """初始化因子分析器"""
        self.factor_data: Dict[str, FactorData] = {}
        self.factor_performance: Dict[str, FactorPerformance] = {}
    
    def add_factor(self, factor_data: FactorData):
        """
        添加因子数据
        
        Args:
            factor_data: 因子数据
        """
        self.factor_data[factor_data.name] = factor_data
        # 如果已有该因子的表现数据，则清除
        if factor_data.name in self.factor_performance:
            del self.factor_performance[factor_data.name]
    
    def remove_factor(self, factor_name: str):
        """
        移除因子数据
        
        Args:
            factor_name: 因子名称
        """
        if factor_name in self.factor_data:
            del self.factor_data[factor_name]
        if factor_name in self.factor_performance:
            del self.factor_performance[factor_name]
    
    def calculate_ic(self, factor_name: str, price_data: pd.DataFrame, 
                    forward_period: int = 1) -> pd.DataFrame:
        """
        计算因子IC值
        
        Args:
            factor_name: 因子名称
            price_data: 价格数据，包含日期、标的、收益率等列
            forward_period: 前向周期（天）
            
        Returns:
            pd.DataFrame: IC值数据框，包含日期、IC值等列
        """
        if factor_name not in self.factor_data:
            raise ValueError(f"Factor not found: {factor_name}")
        
        factor_df = self.factor_data[factor_name].data.copy()
        
        # 确保价格数据包含必要的列
        required_columns = ['date', 'symbol', 'return']
        for col in required_columns:
            if col not in price_data.columns:
                raise ValueError(f"Price data must contain column: {col}")
        
        # 确保日期列为datetime类型
        if not pd.api.types.is_datetime64_any_dtype(price_data['date']):
            price_data['date'] = pd.to_datetime(price_data['date'])
        
        # 按日期和标的排序
        price_data = price_data.sort_values(['date', 'symbol'])
        
        # 计算前向收益率
        price_data['forward_return'] = price_data.groupby('symbol')['return'].shift(-forward_period)
        
        # 合并因子数据和价格数据
        merged_df = pd.merge(factor_df, price_data[['date', 'symbol', 'forward_return']], 
                           on=['date', 'symbol'], how='inner')
        
        # 去除缺失值
        merged_df = merged_df.dropna(subset=['factor_value', 'forward_return'])
        
        # 计算IC值
        ic_df = merged_df.groupby('date').apply(
            lambda x: pd.Series({
                'ic': x['factor_value'].corr(x['forward_return']),
                'rank_ic': x['factor_value'].rank().corr(x['forward_return'].rank())
            })
        ).reset_index()
        
        return ic_df
    
    def calculate_ic_statistics(self, factor_name: str, price_data: pd.DataFrame, 
                              forward_period: int = 1) -> Dict[str, float]:
        """
        计算因子IC统计指标
        
        Args:
            factor_name: 因子名称
            price_data: 价格数据
            forward_period: 前向周期（天）
            
        Returns:
            Dict[str, float]: IC统计指标
        """
        ic_df = self.calculate_ic(factor_name, price_data, forward_period)
        
        if ic_df.empty:
            return {
                'ic_mean': 0.0,
                'ic_std': 0.0,
                'ic_ir': 0.0,
                'ic_win_rate': 0.0,
                'rank_ic_mean': 0.0,
                'rank_ic_std': 0.0,
                'rank_ic_ir': 0.0,
                'rank_ic_win_rate': 0.0
            }
        
        # 计算IC统计指标
        ic_mean = ic_df['ic'].mean()
        ic_std = ic_df['ic'].std()
        ic_ir = ic_mean / ic_std if ic_std != 0 else 0
        ic_win_rate = (ic_df['ic'] > 0).mean()
        
        rank_ic_mean = ic_df['rank_ic'].mean()
        rank_ic_std = ic_df['rank_ic'].std()
        rank_ic_ir = rank_ic_mean / rank_ic_std if rank_ic_std != 0 else 0
        rank_ic_win_rate = (ic_df['rank_ic'] > 0).mean()
        
        return {
            'ic_mean': ic_mean,
            'ic_std': ic_std,
            'ic_ir': ic_ir,
            'ic_win_rate': ic_win_rate,
            'rank_ic_mean': rank_ic_mean,
            'rank_ic_std': rank_ic_std,
            'rank_ic_ir': rank_ic_ir,
            'rank_ic_win_rate': rank_ic_win_rate
        }
    
    def calculate_factor_returns(self, factor_name: str, price_data: pd.DataFrame, 
                               n_groups: int = 5, forward_period: int = 1) -> pd.DataFrame:
        """
        计算因子分组收益
        
        Args:
            factor_name: 因子名称
            price_data: 价格数据
            n_groups: 分组数
            forward_period: 前向周期（天）
            
        Returns:
            pd.DataFrame: 因子分组收益数据框
        """
        if factor_name not in self.factor_data:
            raise ValueError(f"Factor not found: {factor_name}")
        
        factor_df = self.factor_data[factor_name].data.copy()
        
        # 确保价格数据包含必要的列
        required_columns = ['date', 'symbol', 'return']
        for col in required_columns:
            if col not in price_data.columns:
                raise ValueError(f"Price data must contain column: {col}")
        
        # 确保日期列为datetime类型
        if not pd.api.types.is_datetime64_any_dtype(price_data['date']):
            price_data['date'] = pd.to_datetime(price_data['date'])
        
        # 按日期和标的排序
        price_data = price_data.sort_values(['date', 'symbol'])
        
        # 计算前向收益率
        price_data['forward_return'] = price_data.groupby('symbol')['return'].shift(-forward_period)
        
        # 合并因子数据和价格数据
        merged_df = pd.merge(factor_df, price_data[['date', 'symbol', 'forward_return']], 
                           on=['date', 'symbol'], how='inner')
        
        # 去除缺失值
        merged_df = merged_df.dropna(subset=['factor_value', 'forward_return'])
        
        # 按日期分组并计算因子分位数
        def assign_groups(df):
            """分配因子值到分组"""
            df = df.copy()
            # 计算分位数
            df['group'] = pd.qcut(df['factor_value'], n_groups, labels=False, duplicates='drop') + 1
            return df
        
        grouped_df = merged_df.groupby('date').apply(assign_groups).reset_index(drop=True)
        
        # 计算各分组平均收益
        group_returns = grouped_df.groupby(['date', 'group'])['forward_return'].mean().unstack()
        
        # 计算多空收益（最高组 - 最低组）
        if n_groups in group_returns.columns and 1 in group_returns.columns:
            group_returns['long_short'] = group_returns[n_groups] - group_returns[1]
        
        return group_returns
    
    def calculate_turnover(self, factor_name: str, n_groups: int = 5) -> pd.DataFrame:
        """
        计算因子换手率
        
        Args:
            factor_name: 因子名称
            n_groups: 分组数
            
        Returns:
            pd.DataFrame: 换手率数据框
        """
        if factor_name not in self.factor_data:
            raise ValueError(f"Factor not found: {factor_name}")
        
        factor_df = self.factor_data[factor_name].data.copy()
        
        # 按日期分组并计算因子分位数
        def assign_groups(df):
            """分配因子值到分组"""
            df = df.copy()
            # 计算分位数
            df['group'] = pd.qcut(df['factor_value'], n_groups, labels=False, duplicates='drop') + 1
            return df
        
        grouped_df = factor_df.groupby('date').apply(assign_groups).reset_index(drop=True)
        
        # 计算换手率
        turnover_df = pd.DataFrame()
        
        for group in range(1, n_groups + 1):
            group_data = grouped_df[grouped_df['group'] == group][['date', 'symbol']]
            
            # 创建透视表
            pivot_df = group_data.pivot_table(index='symbol', columns='date', values='symbol', aggfunc='count')
            pivot_df = pivot_df.notna().astype(int)
            
            # 计算换手率
            if pivot_df.shape[1] > 1:
                # 计算相邻两期的换手率
                turnover = []
                dates = pivot_df.columns.tolist()
                
                for i in range(1, len(dates)):
                    prev_date = dates[i-1]
                    curr_date = dates[i]
                    
                    # 计算新增和减少的标的数量
                    prev_symbols = set(pivot_df[pivot_df[prev_date] == 1].index)
                    curr_symbols = set(pivot_df[pivot_df[curr_date] == 1].index)
                    
                    # 计算换手率
                    new_symbols = curr_symbols - prev_symbols
                    removed_symbols = prev_symbols - curr_symbols
                    
                    if len(prev_symbols) > 0:
                        turnover_rate = (len(new_symbols) + len(removed_symbols)) / (2 * len(prev_symbols))
                    else:
                        turnover_rate = 0
                    
                    turnover.append({
                        'date': curr_date,
                        'group': group,
                        'turnover': turnover_rate
                    })
                
                group_turnover = pd.DataFrame(turnover)
                turnover_df = pd.concat([turnover_df, group_turnover], ignore_index=True)
        
        # 计算平均换手率
        avg_turnover = turnover_df.groupby('group')['turnover'].mean().reset_index()
        avg_turnover['date'] = 'Average'
        turnover_df = pd.concat([turnover_df, avg_turnover], ignore_index=True)
        
        return turnover_df
    
    def analyze_factor(self, factor_name: str, price_data: pd.DataFrame, 
                      n_groups: int = 5, forward_period: int = 1) -> FactorPerformance:
        """
        分析因子表现
        
        Args:
            factor_name: 因子名称
            price_data: 价格数据
            n_groups: 分组数
            forward_period: 前向周期（天）
            
        Returns:
            FactorPerformance: 因子表现
        """
        if factor_name not in self.factor_data:
            raise ValueError(f"Factor not found: {factor_name}")
        
        factor_data = self.factor_data[factor_name]
        
        # 计算IC统计
        ic_stats = self.calculate_ic_statistics(factor_name, price_data, forward_period)
        
        # 计算因子分组收益
        group_returns = self.calculate_factor_returns(factor_name, price_data, n_groups, forward_period)
        
        # 计算换手率
        turnover_df = self.calculate_turnover(factor_name, n_groups)
        
        # 计算分组IC
        ic_df = self.calculate_ic(factor_name, price_data, forward_period)
        
        # 计算分组IC统计
        group_ic_stats = {}
        factor_df = factor_data.data.copy()
        
        # 确保价格数据包含必要的列
        required_columns = ['date', 'symbol', 'return']
        for col in required_columns:
            if col not in price_data.columns:
                raise ValueError(f"Price data must contain column: {col}")
        
        # 确保日期列为datetime类型
        if not pd.api.types.is_datetime64_any_dtype(price_data['date']):
            price_data['date'] = pd.to_datetime(price_data['date'])
        
        # 按日期和标的排序
        price_data = price_data.sort_values(['date', 'symbol'])
        
        # 计算前向收益率
        price_data['forward_return'] = price_data.groupby('symbol')['return'].shift(-forward_period)
        
        # 合并因子数据和价格数据
        merged_df = pd.merge(factor_df, price_data[['date', 'symbol', 'forward_return']], 
                           on=['date', 'symbol'], how='inner')
        
        # 去除缺失值
        merged_df = merged_df.dropna(subset=['factor_value', 'forward_return'])
        
        # 按日期分组并计算因子分位数
        def assign_groups(df):
            """分配因子值到分组"""
            df = df.copy()
            # 计算分位数
            df['group'] = pd.qcut(df['factor_value'], n_groups, labels=False, duplicates='drop') + 1
            return df
        
        grouped_df = merged_df.groupby('date').apply(assign_groups).reset_index(drop=True)
        
        # 计算各分组IC
        for group in range(1, n_groups + 1):
            group_data = grouped_df[grouped_df['group'] == group]
            
            if not group_data.empty:
                group_ic = group_data.groupby('date').apply(
                    lambda x: x['factor_value'].corr(x['forward_return'])
                ).mean()
                
                group_ic_std = group_data.groupby('date').apply(
                    lambda x: x['factor_value'].corr(x['forward_return'])
                ).std()
                
                group_ic_stats[str(group)] = {
                    'mean': group_ic,
                    'std': group_ic_std
                }
        
        # 计算分组收益
        group_return_stats = {}
        if not group_returns.empty:
            for group in range(1, n_groups + 1):
                if group in group_returns.columns:
                    group_return = group_returns[group].mean() * 252  # 年化收益
                    group_return_stats[str(group)] = group_return
        
        # 计算多空收益
        long_short_return = 0.0
        long_short_sharpe = 0.0
        
        if not group_returns.empty and 'long_short' in group_returns.columns:
            long_short_daily = group_returns['long_short'].dropna()
            if not long_short_daily.empty:
                long_short_return = long_short_daily.mean() * 252  # 年化收益
                long_short_vol = long_short_daily.std() * np.sqrt(252)  # 年化波动率
                long_short_sharpe = long_short_return / long_short_vol if long_short_vol != 0 else 0
        
        # 计算换手率
        avg_turnover = 0.0
        if not turnover_df.empty:
            avg_turnover = turnover_df[turnover_df['date'] == 'Average']['turnover'].mean()
        
        # 创建因子表现对象
        performance = FactorPerformance(
            name=factor_name,
            factor_type=factor_data.factor_type,
            ic_mean=ic_stats['ic_mean'],
            ic_std=ic_stats['ic_std'],
            ic_ir=ic_stats['ic_ir'],
            ic_win_rate=ic_stats['ic_win_rate'],
            annualized_return=long_short_return,  # 使用多空收益作为因子收益
            annualized_volatility=0.0,  # 需要额外计算
            sharpe_ratio=long_short_sharpe,  # 使用多空夏普比率作为因子夏普比率
            max_drawdown=0.0,  # 需要额外计算
            turnover=avg_turnover,
            group_ic_mean={group: stats['mean'] for group, stats in group_ic_stats.items()},
            group_ic_std={group: stats['std'] for group, stats in group_ic_stats.items()},
            group_return=group_return_stats,
            long_short_return=long_short_return,
            long_short_sharpe=long_short_sharpe
        )
        
        # 保存因子表现
        self.factor_performance[factor_name] = performance
        
        return performance
    
    def compare_factors(self, factor_names: List[str], price_data: pd.DataFrame, 
                       n_groups: int = 5, forward_period: int = 1) -> pd.DataFrame:
        """
        比较多个因子的表现
        
        Args:
            factor_names: 因子名称列表
            price_data: 价格数据
            n_groups: 分组数
            forward_period: 前向周期（天）
            
        Returns:
            pd.DataFrame: 因子比较结果
        """
        # 分析每个因子
        performances = []
        for factor_name in factor_names:
            if factor_name in self.factor_data:
                performance = self.analyze_factor(factor_name, price_data, n_groups, forward_period)
                performances.append(performance)
        
        # 创建比较结果数据框
        comparison_data = []
        for performance in performances:
            comparison_data.append({
                'Factor Name': performance.name,
                'Factor Type': performance.factor_type.value,
                'IC Mean': performance.ic_mean,
                'IC IR': performance.ic_ir,
                'IC Win Rate': performance.ic_win_rate,
                'Annualized Return': performance.annualized_return,
                'Sharpe Ratio': performance.sharpe_ratio,
                'Max Drawdown': performance.max_drawdown,
                'Turnover': performance.turnover,
                'Long-Short Return': performance.long_short_return,
                'Long-Short Sharpe': performance.long_short_sharpe
            })
        
        comparison_df = pd.DataFrame(comparison_data)
        
        return comparison_df
    
    def calculate_factor_correlation(self, factor_names: List[str]) -> pd.DataFrame:
        """
        计算因子相关性
        
        Args:
            factor_names: 因子名称列表
            
        Returns:
            pd.DataFrame: 因子相关性矩阵
        """
        # 收集因子数据
        factor_dfs = []
        for factor_name in factor_names:
            if factor_name in self.factor_data:
                factor_df = self.factor_data[factor_name].data.copy()
                factor_df = factor_df.rename(columns={'factor_value': factor_name})
                factor_dfs.append(factor_df[['date', 'symbol', factor_name]])
        
        if not factor_dfs:
            return pd.DataFrame()
        
        # 合并因子数据
        merged_df = factor_dfs[0]
        for factor_df in factor_dfs[1:]:
            merged_df = pd.merge(merged_df, factor_df, on=['date', 'symbol'], how='inner')
        
        # 计算因子相关性
        factor_columns = factor_names
        correlation_matrix = merged_df[factor_columns].corr()
        
        return correlation_matrix
    
    def generate_factor_report(self, factor_name: str, price_data: pd.DataFrame, 
                             n_groups: int = 5, forward_period: int = 1) -> Dict[str, Any]:
        """
        生成因子分析报告
        
        Args:
            factor_name: 因子名称
            price_data: 价格数据
            n_groups: 分组数
            forward_period: 前向周期（天）
            
        Returns:
            Dict[str, Any]: 因子分析报告
        """
        if factor_name not in self.factor_data:
            raise ValueError(f"Factor not found: {factor_name}")
        
        # 分析因子表现
        performance = self.analyze_factor(factor_name, price_data, n_groups, forward_period)
        
        # 计算IC值
        ic_df = self.calculate_ic(factor_name, price_data, forward_period)
        
        # 计算因子分组收益
        group_returns = self.calculate_factor_returns(factor_name, price_data, n_groups, forward_period)
        
        # 计算换手率
        turnover_df = self.calculate_turnover(factor_name, n_groups)
        
        # 构建报告
        report = {
            'factor_info': {
                'name': performance.name,
                'type': performance.factor_type.value,
                'description': self.factor_data[factor_name].description
            },
            'ic_analysis': {
                'ic_mean': performance.ic_mean,
                'ic_std': performance.ic_std,
                'ic_ir': performance.ic_ir,
                'ic_win_rate': performance.ic_win_rate,
                'ic_series': ic_df.to_dict('records') if not ic_df.empty else []
            },
            'group_analysis': {
                'n_groups': n_groups,
                'group_ic_mean': performance.group_ic_mean,
                'group_ic_std': performance.group_ic_std,
                'group_return': performance.group_return,
                'group_returns': group_returns.to_dict() if not group_returns.empty else {}
            },
            'turnover_analysis': {
                'avg_turnover': performance.turnover,
                'turnover_series': turnover_df.to_dict('records') if not turnover_df.empty else []
            },
            'performance_summary': {
                'annualized_return': performance.annualized_return,
                'sharpe_ratio': performance.sharpe_ratio,
                'max_drawdown': performance.max_drawdown,
                'long_short_return': performance.long_short_return,
                'long_short_sharpe': performance.long_short_sharpe
            }
        }
        
        return report