# API文档

## 核心模块API

### 数据模块 (core.data)

#### DataFetcher

数据获取类，用于从交易所获取历史和实时数据。

```python
from core.data.data_fetcher import DataFetcher

# 初始化
fetcher = DataFetcher()

# 获取OHLCV数据
data = fetcher.fetch_ohlcv(exchange, symbol, timeframe, limit, since)
```

**方法**

- `fetch_ohlcv(exchange, symbol, timeframe, limit=100, since=None)`: 获取OHLCV数据
  - `exchange`: 交易所名称，如 'binance', 'okx'
  - `symbol`: 交易对，如 'BTC/USDT'
  - `timeframe`: 时间框架，如 '1m', '5m', '1h', '1d'
  - `limit`: 数据条数，默认100
  - `since`: 起始时间戳，可选

#### DataLoader

数据加载类，用于从本地文件加载数据。

```python
from core.data.data_loader import DataLoader

# 初始化
loader = DataLoader()

# 加载CSV数据
data = loader.load_csv(file_path)

# 加载JSON数据
data = loader.load_json(file_path)
```

**方法**

- `load_csv(file_path)`: 加载CSV格式数据
- `load_json(file_path)`: 加载JSON格式数据
- `load_parquet(file_path)`: 加载Parquet格式数据

#### DataManager

数据管理类，用于数据的存储和管理。

```python
from core.data.data_manager import DataManager

# 初始化
manager = DataManager(data_dir="data")

# 保存数据
manager.save_data(data, symbol, timeframe)

# 加载数据
data = manager.load_data(symbol, timeframe)

# 列出可用的交易对
symbols = manager.list_symbols(timeframe)
```

**方法**

- `save_data(data, symbol, timeframe)`: 保存数据
- `load_data(symbol, timeframe)`: 加载数据
- `list_symbols(timeframe)`: 列出指定时间框架的可用交易对
- `delete_data(symbol, timeframe)`: 删除数据

### 交易所接口模块 (core.exchange)

#### BaseExchange

交易所基类，定义了交易所接口的标准方法。

```python
from core.exchange.base_exchange import BaseExchange

# 初始化
exchange = BaseExchange(config)

# 获取账户余额
balance = exchange.fetch_balance()

# 下限价单
order = exchange.create_limit_order(symbol, side, amount, price)

# 下市价单
order = exchange.create_market_order(symbol, side, amount)

# 取消订单
exchange.cancel_order(order_id, symbol)

# 获取订单状态
order = exchange.fetch_order(order_id, symbol)

# 获取持仓
positions = exchange.fetch_positions()
```

**方法**

- `fetch_balance()`: 获取账户余额
- `create_limit_order(symbol, side, amount, price)`: 创建限价单
- `create_market_order(symbol, side, amount)`: 创建市价单
- `cancel_order(order_id, symbol)`: 取消订单
- `fetch_order(order_id, symbol)`: 获取订单状态
- `fetch_positions()`: 获取持仓
- `fetch_ticker(symbol)`: 获取行情
- `fetch_ohlcv(symbol, timeframe, limit, since)`: 获取K线数据

#### BinanceAPI

Binance交易所API实现。

```python
from core.exchange.binance_api import BinanceAPI

# 初始化
exchange = BinanceAPI({
    "api_key": "your_api_key",
    "secret": "your_secret",
    "sandbox": True  # 测试环境
})
```

#### OKXAPI

OKX交易所API实现。

```python
from core.exchange.okx_api import OKXAPI

# 初始化
exchange = OKXAPI({
    "api_key": "your_api_key",
    "secret": "your_secret",
    "password": "your_password",
    "sandbox": True  # 测试环境
})
```

### 策略模块 (core.strategy)

#### BaseStrategy

策略基类，定义了策略接口的标准方法。

```python
from core.strategy.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
    
    def generate_signal(self, data):
        # 实现信号生成逻辑
        return {"type": "buy/sell/hold", "amount": 0.01, "price": 50000}
    
    def update(self, data):
        # 更新策略状态
        pass
```

**方法**

- `generate_signal(data)`: 生成交易信号
- `update(data)`: 更新策略状态
- `get_position(symbol)`: 获取指定交易对的持仓
- `get_all_positions()`: 获取所有持仓

#### GridStrategy

网格策略实现。

```python
from core.strategy.grid_strategy import GridStrategy

# 初始化
strategy = GridStrategy({
    "grid_size": 0.01,      # 网格大小 1%
    "grid_levels": 10,      # 网格层数
    "order_size": 0.01,     # 订单大小
    "take_profit": 0.02,    # 止盈 2%
    "stop_loss": 0.05       # 止损 5%
})
```

#### MartingaleStrategy

马丁格尔策略实现。

```python
from core.strategy.martingale_strategy import MartingaleStrategy

# 初始化
strategy = MartingaleStrategy({
    "base_order_size": 0.01,  # 基础订单大小
    "multiplier": 2.0,         # 加倍倍数
    "max_levels": 5,           # 最大层数
    "take_profit": 0.02,       # 止盈 2%
    "stop_loss": 0.1           # 止损 10%
})
```

### 回测模块 (core.backtest)

#### Backtester

回测引擎，用于策略回测。

```python
from core.backtest.backtester import Backtester

# 初始化
backtester = Backtester(
    initial_balance=10000,
    commission=0.001,
    slippage=0.0005
)

# 运行回测
results = backtester.run(strategy, data)
```

**方法**

- `run(strategy, data)`: 运行回测
- `get_results()`: 获取回测结果

#### MetricsCalculator

绩效指标计算器。

```python
from core.backtest.metrics import MetricsCalculator

# 初始化
calculator = MetricsCalculator()

# 计算所有指标
metrics = calculator.calculate_all(results)

# 计算特定指标
total_return = calculator.calculate_total_return(results)
sharpe_ratio = calculator.calculate_sharpe_ratio(results)
max_drawdown = calculator.calculate_max_drawdown(results)
```

**方法**

- `calculate_all(results)`: 计算所有指标
- `calculate_total_return(results)`: 计算总收益率
- `calculate_sharpe_ratio(results)`: 计算夏普比率
- `calculate_max_drawdown(results)`: 计算最大回撤
- `calculate_win_rate(results)`: 计算胜率
- `calculate_profit_factor(results)`: 计算盈利因子

#### ReportGenerator

报告生成器，用于生成回测报告。

```python
from core.backtest.report_generator import ReportGenerator

# 初始化
generator = ReportGenerator()

# 生成HTML报告
html_path = generator.generate_html_report(results, metrics, output_dir)

# 生成Markdown报告
md_path = generator.generate_markdown_report(results, metrics, output_dir)
```

**方法**

- `generate_html_report(results, metrics, output_dir)`: 生成HTML报告
- `generate_markdown_report(results, metrics, output_dir)`: 生成Markdown报告

### 实盘交易模块 (core.live)

#### LiveTrader

实盘交易控制器。

```python
from core.live.live_trader import LiveTrader

# 初始化
trader = LiveTrader(config)

# 运行实盘交易
trader.run()

# 停止实盘交易
trader.stop()
```

**方法**

- `run()`: 运行实盘交易
- `stop()`: 停止实盘交易
- `get_status()`: 获取运行状态

### 工具模块 (core.utils)

#### Logger

日志记录器。

```python
from core.utils.logger import Logger

# 初始化
logger = Logger("my_logger", "log.txt")

# 记录日志
logger.info("Information message")
logger.warning("Warning message")
logger.error("Error message")
logger.debug("Debug message")
```

**方法**

- `info(message)`: 记录信息级别日志
- `warning(message)`: 记录警告级别日志
- `error(message)`: 记录错误级别日志
- `debug(message)`: 记录调试级别日志

#### ConfigParser

配置文件解析器。

```python
from core.utils.config import ConfigParser

# 初始化
parser = ConfigParser()

# 读取配置
config = parser.read_config("config.yaml")

# 保存配置
parser.save_config(config, "config.yaml")

# 合并配置
merged_config = parser.merge_configs(config1, config2)

# 验证配置
is_valid = parser.validate_config(config, schema)
```

**方法**

- `read_config(file_path)`: 读取配置文件
- `save_config(config, file_path)`: 保存配置文件
- `merge_configs(config1, config2)`: 合并配置
- `validate_config(config, schema)`: 验证配置

#### RiskManager

风险管理器。

```python
from core.utils.risk_tools import RiskManager

# 初始化
risk_manager = RiskManager()

# 设置风险管理参数
risk_manager.max_position_size = 0.1  # 最大仓位10%
risk_manager.max_drawdown = 0.1  # 最大回撤10%
risk_manager.max_loss_per_trade = 0.02  # 单笔最大亏损2%

# 检查交易是否合规
is_valid = risk_manager.check_position_size(symbol, amount, price)
is_valid = risk_manager.check_drawdown()
is_valid = risk_manager.check_loss_per_trade(symbol, amount, entry_price, current_price)
```

**方法**

- `check_position_size(symbol, amount, price)`: 检查仓位大小
- `check_drawdown()`: 检查回撤
- `check_loss_per_trade(symbol, amount, entry_price, current_price)`: 检查单笔亏损

### 分析模块 (core.analysis)

#### TradeAnalyzer

交易结果分析器。

```python
from core.analysis.trade_analyzer import TradeAnalyzer

# 初始化
analyzer = TradeAnalyzer()

# 分析交易结果
analysis = analyzer.analyze_trades(trades)

# 生成分析报告
report = analyzer.generate_report(analysis)
```

**方法**

- `analyze_trades(trades)`: 分析交易结果
- `generate_report(analysis)`: 生成分析报告

#### PerformancePlot

绩效可视化工具。

```python
from core.analysis.performance_plot import PerformancePlot

# 初始化
plotter = PerformancePlot()

# 绘制收益曲线
plotter.plot_equity_curve(portfolio_value)

# 绘制回撤曲线
plotter.plot_drawdown(drawdown)

# 绘制交易分布
plotter.plot_trade_distribution(trades)

# 保存图表
plotter.save_plot("output.png")
```

**方法**

- `plot_equity_curve(portfolio_value)`: 绘制收益曲线
- `plot_drawdown(drawdown)`: 绘制回撤曲线
- `plot_trade_distribution(trades)`: 绘制交易分布
- `save_plot(file_path)`: 保存图表

#### FactorAnalyzer

因子效果评估器。

```python
from core.analysis.factor_analysis import FactorAnalyzer

# 初始化
analyzer = FactorAnalyzer()

# 计算因子收益
factor_returns = analyzer.calculate_factor_returns(factor_data, returns)

# 计算因子IC
ic = analyzer.calculate_ic(factor_data, returns)

# 计算因子换手率
turnover = analyzer.calculate_turnover(factor_data)

# 生成因子分析报告
report = analyzer.generate_factor_report(factor_data, returns)
```

**方法**

- `calculate_factor_returns(factor_data, returns)`: 计算因子收益
- `calculate_ic(factor_data, returns)`: 计算因子IC
- `calculate_turnover(factor_data)`: 计算因子换手率
- `generate_factor_report(factor_data, returns)`: 生成因子分析报告

## 配置文件格式

### 回测配置 (backtest_config.yaml)

```yaml
# 基本设置
start_date: "2023-01-01"
end_date: "2023-12-31"
initial_balance: 10000
benchmark: "BTC/USDT"

# 数据设置
data_source: "csv"
data_path: "data/BTC_USDT_1h.csv"
symbols: ["BTC/USDT"]
timeframes: ["1h"]

# 策略设置
strategy: "GridStrategy"
strategy_params:
  grid_size: 0.01
  grid_levels: 10
  order_size: 0.01
  take_profit: 0.02
  stop_loss: 0.05

# 交易设置
commission: 0.001
slippage: 0.0005

# 风控设置
max_position_size: 0.1
max_drawdown: 0.1
```

### 实盘配置 (live_config.yaml)

```yaml
# 基本设置
mode: "paper"  # paper: 模拟交易, live: 实盘交易
update_interval: 60  # 更新间隔(秒)

# 交易所设置
exchanges:
  binance:
    api_key: "your_api_key"
    secret: "your_secret"
    sandbox: true

# 策略设置
strategies:
  - name: "GridStrategy"
    symbol: "BTC/USDT"
    timeframe: "1h"
    params:
      grid_size: 0.01
      grid_levels: 10
      order_size: 0.01
      take_profit: 0.02
      stop_loss: 0.05

# 交易设置
commission: 0.001
slippage: 0.0005

# 风控设置
max_position_size: 0.1
max_drawdown: 0.1
max_loss_per_trade: 0.02

# 通知设置
notifications:
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "your_email@gmail.com"
    password: "your_password"
    recipients: ["recipient@example.com"]
  webhook:
    enabled: false
    url: "https://your-webhook-url.com"
```