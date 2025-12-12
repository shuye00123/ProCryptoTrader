# 回测模块架构文档

## 📋 概述

回测模块是ProCryptoTrader量化交易系统的策略验证引擎，严格遵循RIPER-5原则设计，提供了完整的策略历史回测、性能评估和报告生成功能。该模块通过模拟真实交易环境，包括滑点、手续费、杠杆等因素，为策略的可行性提供可靠的验证依据。

## 🎯 RIPER-5原则体现

### Risk First (风险优先)
- **最大回撤监控**: 实时计算和监控策略的最大回撤
- **风险调整收益**: 提供夏普比率、索提诺比率等风险调整后指标
- **VaR/CVaR计算**: 计算风险价值和条件风险价值
- **资金管理**: 严格的资金控制和仓位管理机制
- **止损机制**: 集成策略级别的止损和风险控制

### Integration Minimal (最小侵入)
- **策略接口统一**: 所有策略只需实现BaseStrategy接口即可参与回测
- **数据格式标准化**: 统一的OHLCV数据格式，不依赖特定数据源
- **配置驱动**: 通过BacktestConfig控制所有回测参数，无需代码修改
- **结果格式标准化**: 统一的结果输出格式，便于集成到报告系统

### Predictability (可预期性)
- **确定性回测**: 相同的策略和数据产生完全相同的结果
- **事件驱动模式**: 按照时间序列严格处理每个时间点的事件
- **交易成本透明**: 明确计算并记录每笔交易的手续费和滑点
- **状态可追踪**: 完整记录持仓、资金、交易等所有状态变化

### Expandability (可扩展性)
- **自定义指标**: 支持添加自定义的性能评估指标
- **多策略回测**: 支持同时回测多个策略并进行比较
- **自定义基准**: 支持使用自定义基准进行业绩比较
- **报告模板**: 支持自定义报告格式和内容

### Realistic Evaluation (真实可评估)
- **真实交易成本**: 包含手续费、滑点、杠杆等真实交易因素
- **基准比较**: 与市场基准进行比较评估超额收益
- **多维度评估**: 收益、风险、交易频率等多维度综合评估
- **统计显著性**: 提供统计检验确保结果的可信度

## 🏗️ 模块架构

### 目录结构
```
core/backtest/
├── __init__.py                  # 模块导出
├── backtester.py               # 回测引擎核心
├── metrics.py                  # 性能指标计算
└── report_generator.py         # 报告生成器
```

### 类层次结构
```
BacktestConfig (回测配置)
├── 时间范围配置
├── 资金和费率配置
├── 交易对和时间框架
└── 风险控制参数

Backtester (回测引擎)
├── 数据加载和管理
├── 策略执行引擎
├── 交易模拟器
└── 结果生成器

TradeRecord (交易记录)
├── 交易基本信息
├── 价格和数量
├── 手续费和盈亏
└── 余额变化

Position (持仓管理)
├── 持仓数量和成本
├── 未实现盈亏计算
├── 已实现盈亏跟踪
└── 交易执行逻辑

PerformanceMetrics (绩效指标)
├── 收益指标
├── 风险指标
├── 风险调整收益
└── 交易相关指标

MetricsCalculator (指标计算器)
├── 收益率计算
├── 风险指标计算
├── 滚动指标计算
└── 策略比较分析
```

## 📊 核心组件详解

### 1. 回测配置 (BacktestConfig)

#### 配置参数
```python
@dataclass
class BacktestConfig:
    start_date: str                    # 开始日期 'YYYY-MM-DD'
    end_date: str                      # 结束日期 'YYYY-MM-DD'
    initial_balance: float = 10000.0   # 初始资金
    fee_rate: float = 0.001            # 手续费率 (0.1%)
    slippage: float = 0.0005           # 滑点 (0.05%)
    leverage: float = 1.0              # 杠杆倍数
    symbols: List[str] = field(default_factory=list)  # 交易对列表
    timeframes: List[str] = field(default_factory=list)  # 时间框架列表
    data_dir: str = "data"             # 数据目录
    output_dir: str = "results"        # 输出目录
    benchmark: Optional[str] = None    # 基准指数
    random_seed: Optional[int] = None  # 随机种子
```

#### 配置验证
```python
def __post_init__(self):
    """验证配置参数"""
    # 日期格式验证
    try:
        self.start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
        self.end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
        if self.start_dt >= self.end_dt:
            raise ValueError("开始日期必须早于结束日期")
    except ValueError as e:
        raise ValueError(f"日期格式错误，应为YYYY-MM-DD: {e}")

    # 参数合理性验证
    if self.initial_balance <= 0:
        raise ValueError("初始资金必须大于0")

    if self.fee_rate < 0 or self.slippage < 0:
        raise ValueError("手续费率和滑点不能为负数")

    if self.leverage <= 0:
        raise ValueError("杠杆倍数必须大于0")
```

### 2. 回测引擎 (Backtester)

#### 初始化和配置
```python
class Backtester:
    def __init__(self, strategy: BaseStrategy, config: BacktestConfig):
        self.strategy = strategy
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 账户状态初始化
        self.balance = config.initial_balance
        self.initial_balance = config.initial_balance
        self.positions: Dict[str, Position] = {}
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.trade_records: List[TradeRecord] = []

        # 回测状态
        self.current_time = None
        self.is_running = False

        # 数据加载器初始化
        self.data_loader = FixedDataLoader(config.data_dir)

        # 设置随机种子和日志
        if config.random_seed is not None:
            np.random.seed(config.random_seed)

        os.makedirs(config.output_dir, exist_ok=True)
        self._setup_logger()
```

#### 数据加载机制
```python
def load_data(self) -> Dict[str, pd.DataFrame]:
    """加载回测数据"""
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
```

#### 核心回测循环
```python
def run(self) -> Dict[str, Any]:
    """运行回测"""
    self.logger.info("开始回测")
    self.is_running = True

    try:
        # 1. 加载和验证数据
        data = self.load_data()
        start_time, end_time = self.get_universe_time_range(data)

        # 2. 生成时间序列 (按分钟)
        time_series = pd.date_range(start=start_time, end=end_time, freq="min")

        # 3. 初始化策略
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

        # 4. 主循环 - 事件驱动回测
        for i, timestamp in enumerate(time_series):
            self.current_time = timestamp

            # 获取当前时间点的数据
            current_data = self._get_current_data(data, timestamp)
            if not current_data:
                continue

            # 转换数据格式为策略所需
            strategy_data = self._convert_data_for_strategy(current_data)

            # 更新持仓价格
            self._update_positions(strategy_data)

            # 计算当前权益
            equity = self._calculate_equity(current_data)
            self.equity_curve.append((timestamp, equity))

            # 生成和执行交易信号
            signals = self.strategy.generate_signals(strategy_data)
            for signal in signals:
                self._execute_signal(signal, current_data)

            # 进度输出
            if i % 1000 == 0:
                self.logger.info(f"回测进度: {i}/{len(time_series)}, 权益: {equity:.2f}")

        # 5. 计算最终权益和生成结果
        final_equity = self._calculate_final_equity(data)
        results = self._generate_results(final_equity)

        self.logger.info(f"回测完成, 总收益率: {(final_equity/self.initial_balance - 1)*100:.2f}%")
        return results

    except Exception as e:
        self.logger.error(f"回测过程中发生错误: {e}")
        raise
    finally:
        self.is_running = False
```

#### 交易执行机制
```python
def _execute_signal(self, signal: Signal, data: Dict[str, pd.DataFrame]):
    """执行交易信号"""
    symbol = signal.symbol

    # 获取当前价格
    current_price = self._get_current_price(symbol, data)
    if current_price is None:
        self.logger.warning(f"无法获取 {symbol} 的当前价格，跳过信号")
        return

    # 初始化持仓
    if symbol not in self.positions:
        self.positions[symbol] = Position(symbol=symbol)

    position = self.positions[symbol]

    # 计算滑点后的执行价格
    execution_price = self._calculate_execution_price(signal, current_price)

    # 根据信号类型执行交易
    if signal.signal_type == SignalType.OPEN_LONG:
        self._execute_buy(signal, symbol, execution_price, position)
    elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
        self._execute_sell(signal, symbol, execution_price, position)

def _calculate_execution_price(self, signal: Signal, current_price: float) -> float:
    """计算包含滑点的执行价格"""
    if signal.signal_type in [SignalType.OPEN_LONG]:
        return current_price * (1 + self.config.slippage)  # 买入时价格向上滑
    elif signal.signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
        return current_price * (1 - self.config.slippage)  # 卖出时价格向下滑
    elif signal.signal_type == SignalType.OPEN_SHORT:
        return current_price * (1 - self.config.slippage)  # 做空时价格向下
    else:
        return current_price

def _execute_buy(self, signal: Signal, symbol: str, price: float, position: Position):
    """执行买入交易"""
    quantity = signal.amount if signal.amount is not None else signal.quantity
    cost = price * quantity
    fee = cost * self.config.fee_rate
    total_cost = cost + fee

    # 资金检查
    if total_cost > self.balance:
        self.logger.warning(f"资金不足，无法买入 {symbol}")
        return

    # 执行交易
    position_fee = position.execute_trade("buy", price, quantity, self.config.fee_rate)
    self.balance -= total_cost

    # 记录交易
    trade = TradeRecord(
        timestamp=self.current_time,
        symbol=symbol,
        side="buy",
        price=price,
        quantity=quantity,
        value=cost,
        fee=position_fee,
        balance=self.balance,
        strategy_id=self.strategy.name if hasattr(self.strategy, 'name') else "unknown"
    )
    self.trade_records.append(trade)
```

#### 权益计算
```python
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

def _update_positions(self, data: Dict[str, pd.DataFrame]):
    """更新持仓价格"""
    for symbol, position in self.positions.items():
        for key, df in data.items():
            if symbol in key and not df.empty:
                latest_price = df.iloc[-1]['close']
                position.update_price(latest_price)
                break
```

### 3. 持仓管理 (Position)

#### 持仓状态跟踪
```python
@dataclass
class Position:
    symbol: str
    quantity: float = 0.0          # 持仓数量
    avg_price: float = 0.0          # 平均成本价
    unrealized_pnl: float = 0.0      # 未实现盈亏
    realized_pnl: float = 0.0        # 已实现盈亏
    last_price: float = 0.0          # 最新价格

    def update_price(self, price: float):
        """更新最新价格并计算未实现盈亏"""
        self.last_price = price
        if self.quantity != 0:
            self.unrealized_pnl = (price - self.avg_price) * self.quantity
```

#### 交易执行逻辑
```python
def execute_trade(self, side: str, price: float, quantity: float, fee_rate: float) -> float:
    """执行交易并返回手续费"""
    if side == "buy":
        # 买入逻辑
        cost = price * quantity
        fee = cost * fee_rate
        total_cost = cost + fee

        if self.quantity == 0:
            # 新建仓位
            self.avg_price = price
            self.quantity = quantity
        else:
            # 加仓 - 重新计算平均价格
            total_value = self.quantity * self.avg_price + cost
            self.quantity += quantity
            self.avg_price = total_value / self.quantity

        return fee

    elif side == "sell":
        # 卖出逻辑
        if quantity > self.quantity:
            raise ValueError("卖出数量不能超过持仓数量")

        revenue = price * quantity
        fee = revenue * fee_rate

        # 计算已实现盈亏
        realized = (price - self.avg_price) * quantity
        self.realized_pnl += realized

        # 更新持仓
        self.quantity -= quantity

        # 如果全部卖出，重置平均价格
        if self.quantity == 0:
            self.avg_price = 0.0

        return fee
```

### 4. 性能指标计算 (MetricsCalculator)

#### 综合绩效指标
```python
class PerformanceMetrics:
    """绩效指标数据类"""
    # 收益指标
    total_return: float = 0.0        # 总收益率
    annual_return: float = 0.0        # 年化收益率
    monthly_return: float = 0.0       # 月均收益率

    # 风险指标
    volatility: float = 0.0           # 年化波动率
    max_drawdown: float = 0.0         # 最大回撤
    max_drawdown_duration: int = 0    # 最大回撤持续期

    # 风险调整收益指标
    sharpe_ratio: float = 0.0         # 夏普比率
    sortino_ratio: float = 0.0        # 索提诺比率
    calmar_ratio: float = 0.0         # 卡玛比率
    information_ratio: float = 0.0    # 信息比率

    # 交易相关指标
    total_trades: int = 0             # 总交易次数
    win_rate: float = 0.0             # 胜率
    profit_loss_ratio: float = 0.0    # 盈亏比
    avg_trade_return: float = 0.0     # 平均交易收益率

    # 风险价值指标
    var_95: float = 0.0               # 95%置信度VaR
    cvar_95: float = 0.0              # 95%置信度CVaR

    # 基准比较指标
    beta: float = 0.0                 # 贝塔系数
    alpha: float = 0.0                # 阿尔法系数
    excess_return: float = 0.0        # 超额收益率
```

#### 核心计算方法
```python
@staticmethod
def calculate_returns(equity_curve: pd.Series,
                      benchmark_curve: Optional[pd.Series] = None,
                      risk_free_rate: float = 0.02) -> PerformanceMetrics:
    """计算完整的绩效指标"""
    metrics = PerformanceMetrics()

    if equity_curve.empty:
        return metrics

    # 设置时间统计
    metrics.start_date = equity_curve.index[0].strftime('%Y-%m-%d')
    metrics.end_date = equity_curve.index[-1].strftime('%Y-%m-%d')
    metrics.trading_days = len(equity_curve)

    # 计算日收益率
    returns = equity_curve.pct_change().dropna()

    # 收益指标计算
    metrics.total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100

    # 年化收益率
    days = (equity_curve.index[-1] - equity_curve.index[0]).days
    if days > 0:
        years = days / 365.25
        metrics.annual_return = ((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1/years) - 1) * 100

    # 风险指标计算
    metrics.volatility = returns.std() * np.sqrt(365) * 100

    # 最大回撤计算
    rolling_max = equity_curve.expanding().max()
    drawdown = (equity_curve - rolling_max) / rolling_max
    metrics.max_drawdown = drawdown.min() * 100

    # 最大回撤持续期
    metrics.max_drawdown_duration = MetricsCalculator._calculate_drawdown_duration(drawdown)

    # 风险调整收益指标
    excess_daily_returns = returns - risk_free_rate/365
    if excess_daily_returns.std() != 0:
        metrics.sharpe_ratio = excess_daily_returns.mean() / excess_daily_returns.std() * np.sqrt(365)

    # 索提诺比率（只考虑下行波动）
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 0 and downside_returns.std() != 0:
        metrics.sortino_ratio = excess_daily_returns.mean() / downside_returns.std() * np.sqrt(365)

    # 卡玛比率
    if metrics.max_drawdown != 0:
        metrics.calmar_ratio = metrics.annual_return / abs(metrics.max_drawdown)

    # 基准比较（如果有基准）
    if benchmark_curve is not None:
        benchmark_returns = benchmark_curve.pct_change().dropna()
        excess_returns = returns - benchmark_returns

        if excess_returns.std() != 0:
            metrics.information_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(365)

        # 贝塔系数
        if benchmark_returns.var() != 0:
            covariance = np.cov(returns, benchmark_returns)[0, 1]
            metrics.beta = covariance / benchmark_returns.var()

        # 阿尔法系数
        market_return = (benchmark_curve.iloc[-1] / benchmark_curve.iloc[0] - 1) * 100
        risk_free_annual = risk_free_rate * 100
        expected_return = risk_free_annual + metrics.beta * (market_return - risk_free_annual)
        metrics.alpha = metrics.annual_return - expected_return

    # 风险价值指标
    metrics.var_95 = np.percentile(returns, 5) * 100
    metrics.cvar_95 = returns[returns <= np.percentile(returns, 5)].mean() * 100

    # 收益率分布特征
    metrics.skewness = returns.skew()
    metrics.kurtosis = returns.kurtosis()

    return metrics
```

#### 交易指标计算
```python
@staticmethod
def calculate_trade_metrics(trade_records: pd.DataFrame) -> Dict[str, float]:
    """计算交易相关指标"""
    if trade_records.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "avg_trade_return": 0.0
        }

    # 计算每笔交易的盈亏
    if 'pnl' not in trade_records.columns:
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

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "avg_trade_return": trade_records['pnl'].mean() if not trade_records.empty else 0,
        "avg_win_return": avg_win,
        "avg_loss_return": -avg_loss
    }
```

#### 滚动指标计算
```python
@staticmethod
def calculate_rolling_metrics(equity_curve: pd.Series, window: int = 30) -> pd.DataFrame:
    """计算滚动指标"""
    if equity_curve.empty or len(equity_curve) < window:
        return pd.DataFrame()

    # 计算日收益率
    returns = equity_curve.pct_change().dropna()

    # 计算滚动指标
    rolling_return = returns.rolling(window=window).mean() * window * 100
    rolling_volatility = returns.rolling(window=window).std() * np.sqrt(window) * 100
    rolling_sharpe = rolling_return / rolling_volatility

    # 滚动最大回撤
    rolling_max = equity_curve.rolling(window=window).max()
    rolling_drawdown = (equity_curve - rolling_max) / rolling_max * 100

    return pd.DataFrame({
        'rolling_return': rolling_return,
        'rolling_volatility': rolling_volatility,
        'rolling_sharpe': rolling_sharpe,
        'rolling_drawdown': rolling_drawdown
    })
```

### 5. 策略比较分析

#### 多策略比较
```python
@staticmethod
def compare_strategies(results_dict: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """比较多个策略的绩效"""
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
```

#### 相关性分析
```python
@staticmethod
def calculate_correlation_matrix(equity_curves: Dict[str, pd.Series]) -> pd.DataFrame:
    """计算多个策略收益率的 correlation matrix"""
    returns_dict = {}

    for strategy_name, equity_curve in equity_curves.items():
        if not equity_curve.empty:
            returns = equity_curve.pct_change().dropna()
            returns_dict[strategy_name] = returns

    # 创建收益率DataFrame并计算相关性
    returns_df = pd.DataFrame(returns_dict)
    correlation_matrix = returns_df.corr()

    return correlation_matrix
```

## 🔧 使用指南

### 基本回测流程

#### 1. 配置回测参数
```python
from core.backtest.backtester import BacktestConfig, Backtester
from core.strategy.grid_strategy import GridStrategy

# 创建回测配置
config = BacktestConfig(
    start_date="2023-01-01",
    end_date="2023-12-31",
    initial_balance=10000.0,
    fee_rate=0.001,
    slippage=0.0005,
    symbols=["BTC/USDT"],
    timeframes=["1h"],
    data_dir="./data",
    output_dir="./results"
)
```

#### 2. 创建策略实例
```python
# 创建策略配置
strategy_config = {
    "grid_count": 10,
    "grid_range_pct": 0.1,
    "symbols": ["BTC/USDT"],
    "position_size": 0.01
}

# 创建策略实例
strategy = GridStrategy(strategy_config)
```

#### 3. 运行回测
```python
# 创建回测引擎
backtester = Backtester(strategy, config)

# 运行回测
results = backtester.run()

# 获取结果
print(f"总收益率: {results['total_return']:.2f}%")
print(f"夏普比率: {results['sharpe_ratio']:.2f}")
print(f"最大回撤: {results['max_drawdown']:.2f}%")
```

### 高级功能使用

#### 1. 基准比较
```python
# 加载基准数据
benchmark_data = pd.read_csv('benchmark.csv', index_col=0, parse_dates=True)
benchmark_curve = benchmark_data['close']

# 计算包含基准比较的绩效指标
from core.backtest.metrics import MetricsCalculator
metrics = MetricsCalculator.calculate_returns(
    results['equity_curve'],
    benchmark_curve=benchmark_curve,
    risk_free_rate=0.02
)

print(f"阿尔法: {metrics.alpha:.2f}%")
print(f"贝塔: {metrics.beta:.2f}")
print(f"信息比率: {metrics.information_ratio:.2f}")
```

#### 2. 滚动指标分析
```python
# 计算滚动指标
rolling_metrics = MetricsCalculator.calculate_rolling_metrics(
    results['equity_curve'],
    window=30
)

# 绘制滚动夏普比率
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(rolling_metrics.index, rolling_metrics['rolling_sharpe'])
plt.title('滚动夏普比率 (30天)')
plt.xlabel('日期')
plt.ylabel('夏普比率')
plt.grid(True)
plt.show()
```

#### 3. 多策略比较
```python
# 运行多个策略回测
strategies = {
    'grid': GridStrategy(grid_config),
    'dual_ma': DualMovingAverageStrategy(ma_config),
    'martingale': MartingaleStrategy(martingale_config)
}

results_dict = {}
for name, strategy in strategies.items():
    backtester = Backtester(strategy, config)
    results_dict[name] = backtester.run()

# 比较策略表现
comparison = MetricsCalculator.compare_strategies(results_dict)
print(comparison)

# 计算策略相关性
equity_curves = {name: results['equity_curve'] for name, results in results_dict.items()}
correlation_matrix = MetricsCalculator.calculate_correlation_matrix(equity_curves)
print("策略相关性矩阵:")
print(correlation_matrix)
```

## 📈 性能优化

### 1. 数据加载优化
- **并行加载**: 同时加载多个交易对的数据
- **内存映射**: 对于大数据集使用内存映射技术
- **数据缓存**: 缓存已加载的数据避免重复读取

### 2. 计算优化
- **向量化计算**: 使用pandas/numpy向量化操作
- **批量处理**: 批量计算技术指标
- **增量更新**: 只计算新增数据的指标

### 3. 内存管理
- **及时清理**: 及时清理不需要的数据对象
- **数据分块**: 对大数据集进行分块处理
- **垃圾回收**: 定期触发垃圾回收

## 🛡️ 风险控制和验证

### 1. 数据质量检查
```python
def validate_data_quality(data: pd.DataFrame) -> bool:
    """验证数据质量"""
    if data.empty:
        return False

    # 检查必要列
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        return False

    # 检查数据连续性
    expected_freq = pd.infer_freq(data.index)
    if expected_freq:
        # 检查是否有缺失的时间点
        full_range = pd.date_range(start=data.index.min(), end=data.index.max(), freq=expected_freq)
        missing_times = full_range.difference(data.index)
        if len(missing_times) > len(full_range) * 0.01:  # 允许1%的缺失
            return False

    # 检查价格逻辑
    invalid_prices = (data['high'] < data['low']) | (data['high'] < data['close']) | (data['low'] > data['close'])
    if invalid_prices.any():
        return False

    return True
```

### 2. 回测结果验证
```python
def validate_backtest_results(results: Dict[str, Any]) -> bool:
    """验证回测结果的合理性"""
    # 检查基本指标
    if results['total_trades'] < 0:
        return False

    if abs(results['total_return']) > 1000:  # 超过1000%的收益率可能有问题
        return False

    if results['max_drawdown'] < -100:  # 回撤不能超过100%
        return False

    # 检查权益曲线连续性
    equity_curve = results['equity_curve']
    if equity_curve.isnull().any():
        return False

    if (equity_curve <= 0).any():  # 权益不能为负数
        return False

    return True
```

## 📊 报告生成

### 1. 基本报告
```python
def generate_basic_report(results: Dict[str, Any], output_dir: str):
    """生成基本回测报告"""
    report = f"""
# 回测报告

## 基本信息
- 策略名称: {results.get('strategy_name', 'Unknown')}
- 回测期间: {results['start_date']} 至 {results['end_date']}
- 初始资金: ${results['initial_balance']:,.2f}
- 最终资金: ${results['final_balance']:,.2f}

## 收益指标
- 总收益率: {results['total_return']:.2f}%
- 年化收益率: {results['annual_return']:.2f}%
- 月均收益率: {results.get('monthly_return', 0):.2f}%

## 风险指标
- 最大回撤: {results['max_drawdown']:.2f}%
- 年化波动率: {results.get('volatility', 0):.2f}%
- 夏普比率: {results['sharpe_ratio']:.2f}

## 交易统计
- 总交易次数: {results['total_trades']}
- 胜率: {results['win_rate']:.2f}%
- 盈亏比: {results['profit_loss_ratio']:.2f}
"""

    with open(f"{output_dir}/report.md", "w") as f:
        f.write(report)
```

### 2. 可视化报告
```python
def generate_visualizations(results: Dict[str, Any], output_dir: str):
    """生成可视化图表"""
    import matplotlib.pyplot as plt

    equity_curve = results['equity_curve']

    # 权益曲线
    plt.figure(figsize=(15, 10))

    # 子图1: 权益曲线
    plt.subplot(2, 2, 1)
    plt.plot(equity_curve.index, equity_curve['equity'])
    plt.title('权益曲线')
    plt.xlabel('日期')
    plt.ylabel('权益 ($)')
    plt.grid(True)

    # 子图2: 回撤
    plt.subplot(2, 2, 2)
    rolling_max = equity_curve['equity'].expanding().max()
    drawdown = (equity_curve['equity'] - rolling_max) / rolling_max * 100
    plt.fill_between(drawdown.index, drawdown.values, 0, alpha=0.3, color='red')
    plt.title('回撤')
    plt.xlabel('日期')
    plt.ylabel('回撤 (%)')
    plt.grid(True)

    # 子图3: 日收益率
    plt.subplot(2, 2, 3)
    daily_returns = equity_curve['equity'].pct_change().dropna()
    plt.hist(daily_returns, bins=50, alpha=0.7)
    plt.title('日收益率分布')
    plt.xlabel('日收益率')
    plt.ylabel('频次')
    plt.grid(True)

    # 子图4: 滚动夏普比率
    plt.subplot(2, 2, 4)
    rolling_metrics = MetricsCalculator.calculate_rolling_metrics(equity_curve['equity'])
    if not rolling_metrics.empty:
        plt.plot(rolling_metrics.index, rolling_metrics['rolling_sharpe'])
        plt.title('滚动夏普比率 (30天)')
        plt.xlabel('日期')
        plt.ylabel('夏普比率')
        plt.grid(True)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/backtest_analysis.png", dpi=300, bbox_inches='tight')
    plt.close()
```

## 🔌 扩展功能

### 1. 自定义指标
```python
class CustomMetrics:
    """自定义指标计算"""

    @staticmethod
    def calculate_custom_metric(equity_curve: pd.Series) -> float:
        """自定义指标计算示例"""
        returns = equity_curve.pct_change().dropna()

        # 示例：计算90/10比率（前10%收益与后10%收益的比率）
        top_10_percent = np.percentile(returns, 90)
        bottom_10_percent = np.percentile(returns, 10)

        if bottom_10_percent != 0:
            return abs(top_10_percent / bottom_10_percent)
        else:
            return float('inf')
```

### 2. 多资产组合回测
```python
class PortfolioBacktester:
    """多资产组合回测器"""

    def __init__(self, strategies: Dict[str, BaseStrategy],
                 weights: Dict[str, float], config: BacktestConfig):
        self.strategies = strategies
        self.weights = weights
        self.config = config

    def run_portfolio_backtest(self) -> Dict[str, Any]:
        """运行组合回测"""
        results = {}

        # 运行各个策略
        for name, strategy in self.strategies.items():
            backtester = Backtester(strategy, self.config)
            results[name] = backtester.run()

        # 计算组合权益曲线
        portfolio_equity = self._calculate_portfolio_equity(results)

        # 计算组合绩效指标
        portfolio_metrics = MetricsCalculator.calculate_returns(portfolio_equity)

        return {
            'individual_results': results,
            'portfolio_equity': portfolio_equity,
            'portfolio_metrics': portfolio_metrics
        }
```

## 🎯 最佳实践

### 1. 回测设计
- **合理的时间范围**: 至少包含一个完整的市场周期
- **适当的频率**: 根据策略特性选择合适的时间框架
- **真实的成本**: 包含所有相关的交易成本和费用
- **样本外测试**: 保留部分数据用于样本外验证

### 2. 结果解释
- **考虑幸存者偏差**: 避免只看成功的策略
- **理解局限性**: 回测结果不能完全代表未来表现
- **风险调整评估**: 使用风险调整后的指标评估策略
- **统计显著性**: 进行统计检验确保结果的可靠性

### 3. 参数优化
- **避免过拟合**: 不要在历史数据上过度优化参数
- **交叉验证**: 使用时间序列交叉验证
- **参数稳定性**: 检查参数在不同时期的稳定性
- **样本外验证**: 严格区分样本内和样本外测试

---

本回测模块文档提供了完整的策略回测框架说明，严格遵循RIPER-5原则，为量化交易策略的验证和优化提供了可靠、全面、专业的技术支撑。所有计算都基于实际的历史数据，确保回测结果的真实性和可信度。