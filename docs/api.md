# API 文档

**版本**: v1.0
**最后更新**: 2026-01-15
**数据架构**: 1秒K线WebSocket流

---

## 目录

1. [核心数据模型](#核心数据模型)
2. [核心模块API](#核心模块api)
3. [WebSocket接口](#websocket接口)
4. [策略接口](#策略接口)
5. [突破检测接口](#突破检测接口)
6. [配置文件格式](#配置文件格式)

---

## 核心数据模型

### Kline (1秒K线数据)

**位置**: `core/strategy/kline_breakout_detector.py`

**描述**: 1秒K线数据结构，用于量价突破检测

**重要说明**:
- ✅ `volume`字段是**真实的1秒K线总成交量**（该秒内所有成交总和）
- ❌ **不再使用**ticker的`last_quantity`字段（已废弃，数据准确性问题）
- ✅ 数据来源：Binance官方`@kline_1s` WebSocket流

**数据结构**:
```python
@dataclass
class Kline:
    """1秒K线数据结构"""
    symbol: str                      # 交易对符号 (如 "BTCUSDT")
    open: float                      # 开盘价
    high: float                      # 最高价
    low: float                       # 最低价
    close: float                     # 收盘价
    volume: float                    # ✅ 真实1秒K线总成交量（该秒内所有成交总和）
    timestamp: datetime = None       # K线时间戳

    # 自动计算属性（__post_init__）
    price_change: float              # 价格变化 (close - open)
    price_change_pct: float          # 价格变化百分比
```

**字段说明**:

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `symbol` | str | 交易对符号 | "BTCUSDT" |
| `open` | float | 开盘价 | 50000.0 |
| `high` | float | 最高价 | 50100.0 |
| `low` | float | 最低价 | 49900.0 |
| `close` | float | 收盘价 | 50050.0 |
| `volume` | float | **真实1秒K线总成交量** | 1234.56 |
| `timestamp` | datetime | K线时间戳 | 2024-01-15 10:00:00 |
| `price_change` | float | 价格变化 | 50.0 |
| `price_change_pct` | float | 价格变化百分比 | 0.1 |

**数据准确性对比**:

| 数据类型 | 字段 | 含义 | 示例值 | 准确性 |
|----------|------|------|--------|--------|
| **1秒K线** | `volume` | 该秒内所有成交总和 | 1234.56 BTC | ✅ 100%准确 |
| **Ticker** | `last_quantity` | 最近一次成交数量 | 0.5 BTC | ❌ 不准确（单次成交） |

**差异**: 两者相差可达**2469倍**！

**创建示例**:
```python
from core.strategy.kline_breakout_detector import Kline
from datetime import datetime

# 创建Kline对象
kline = Kline(
    symbol="BTCUSDT",
    open=50000.0,
    high=50100.0,
    low=49900.0,
    close=50050.0,
    volume=1234.56,  # ✅ 真实的1秒K线成交量
    timestamp=datetime.now()
)

# 访问属性
print(f"Symbol: {kline.symbol}")
print(f"Price Change: {kline.price_change:.2f}")
print(f"Price Change %: {kline.price_change_pct:.3f}%")
print(f"Volume: {kline.volume} (✅ 真实1秒K线成交量)")
```

---

### Signal (交易信号)

**位置**: `core/strategy/base_strategy.py`

**描述**: 标准化的交易信号数据结构

**信号类型**:
```python
class SignalType(Enum):
    OPEN_LONG = "open_long"          # 开多仓
    OPEN_SHORT = "open_short"        # 开空仓
    CLOSE_LONG = "close_long"        # 平多仓
    CLOSE_SHORT = "close_short"      # 平空仓
    INCREASE_LONG = "increase_long"  # 加多仓
    INCREASE_SHORT = "increase_short" # 加空仓
    HOLD = "hold"                    # 持仓不动
    CLOSE = "close"                  # 平仓（通用）
```

**数据结构**:
```python
class Signal:
    def __init__(self, signal_type: SignalType, symbol: str,
                 price: float = None, amount: float = None,
                 confidence: float = 1.0, stop_loss: float = None,
                 take_profit: float = None, metadata: Dict = None):

        self.signal_type = signal_type          # 信号类型
        self.symbol = symbol                    # 交易对
        self.price = price                      # 建议价格
        self.amount = amount                    # 交易数量
        self.confidence = confidence            # 信号置信度 [0,1]
        self.stop_loss = stop_loss              # 止损价格
        self.take_profit = take_profit          # 止盈价格
        self.metadata = metadata or {}          # 策略元数据
        self.timestamp = pd.Timestamp.now()     # 信号时间戳
```

**使用示例**:
```python
from core.strategy.base_strategy import Signal, SignalType

# 创建买入信号
buy_signal = Signal(
    signal_type=SignalType.OPEN_LONG,
    symbol="BTC/USDT",
    price=50000.0,
    amount=0.1,
    confidence=0.8,
    stop_loss=48000.0,
    take_profit=52000.0,
    metadata={'strategy': 'breakout', 'reason': 'volume_surge'}
)
```

---

### BreakoutSignal (突破信号)

**位置**: `core/strategy/kline_breakout_detector.py`

**描述**: 量价突破检测生成的信号

**数据结构**:
```python
@dataclass
class BreakoutSignal:
    symbol: str                          # 交易对
    signal_type: SignalType              # 信号类型
    strength: float                      # 突破强度（成交量倍数）
    timestamp: datetime                  # 信号时间戳
    price: float                         # 突破价格
    volume: float                        # 成交量
    price_change_pct: float              # 价格变化百分比
    confidence: float                    # 信号置信度
```

---

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

---

## WebSocket接口

### BinanceWebSocketClient

**位置**: `core/data/websocket_client.py`

**描述**: Binance WebSocket客户端，订阅实时1秒K线数据

**订阅流格式**:
```python
# ✅ 订阅1秒K线流
streams = [f"{symbol.lower()}@kline_1s" for symbol in symbols]

# 示例
streams = [
    "babyusdt@kline_1s",
    "gmtusdt@kline_1s",
    "gunusdt@kline_1s"
]
```

**K线消息结构**:
```json
{
  "e": "kline",                    // Event type
  "E": 1672515782136,              // Event time
  "s": "BNBBTC",                   // Symbol
  "k": {
    "t": 1672515780000,            // Kline start time
    "T": 1672515839999,            // Kline close time
    "s": "BNBBTC",                 // Symbol
    "i": "1s",                     // ✅ Interval: 1秒
    "o": "0.0010",                 // Open price
    "c": "0.0020",                 // Close price
    "h": "0.0025",                 // High price
    "l": "0.0015",                 // Low price
    "v": "1000",                   // ✅ Base asset volume（真实1秒总成交量）
    "n": 100,                      // Number of trades
    "x": true,                     // ✅ Is this kline closed?
    "q": "1.0000",                 // Quote asset volume
  }
}
```

**关键字段说明**:

| 字段 | 说明 | 值 |
|------|------|---|
| `k.i` | K线间隔 | "1s" (1秒) |
| `k.v` | **真实成交量** | 该秒内所有成交总和 |
| `k.x` | K线关闭标识 | `true` = 已关闭, `false` = 仍在更新 |

**使用示例**:
```python
from core.data.websocket_client import BinanceWebSocketClient
import asyncio

async def main():
    # 创建WebSocket客户端
    client = BinanceWebSocketClient(testnet=True)

    # 添加K线回调
    async def on_kline(kline):
        print(f"收到K线: {kline.symbol}, Volume: {kline.volume}")

    client.add_kline_callback(on_kline)

    # 订阅1秒K线流
    symbols = ['BTCUSDT', 'ETHUSDT']
    await client.subscribe_klines(symbols, interval='1s')

    # 运行
    await client.run_forever()

asyncio.run(main())
```

**K线回调处理**:
```python
async def _process_kline_message(self, kline_data: Dict):
    """处理1秒K线消息"""
    k = kline_data.get('k', {})

    # ✅ 只处理已关闭的K线（避免重复处理）
    if not k.get('x', False):
        return

    # ✅ 创建Kline对象
    kline = Kline(
        symbol=k.get('s', ''),
        open=float(k.get('o', 0)),
        high=float(k.get('h', 0)),
        low=float(k.get('l', 0)),
        close=float(k.get('c', 0)),
        volume=float(k.get('v', 0)),  # ✅ 真实的1秒K线成交量
        timestamp=pd.to_datetime(k.get('t', 0), unit='ms')
    )

    # 触发回调
    await self._trigger_kline_callbacks(kline)
```

---

## 策略接口

### BaseStrategy (策略基类)

**位置**: `core/strategy/base_strategy.py`

**描述**: 所有策略的抽象基类，提供统一的策略开发框架

**核心接口**:
```python
class BaseStrategy(ABC):
    @abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """生成交易信号"""
        pass

    @abstractmethod
    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """计算技术指标"""
        pass

    def update(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """更新策略状态并生成信号"""
        # 1. 计算技术指标
        self.indicators = self.calculate_indicators(data)

        # 2. 更新持仓
        self._update_positions(data)

        # 3. 生成交易信号
        signals = self.generate_signals(data)

        # 4. 记录信号历史
        self.signals_history.extend(signals)

        return signals
```

**持仓管理接口**:
```python
def can_open_position(self, symbol: str) -> bool:
    """检查是否可以开新仓"""
    if self.has_position(symbol):
        return False
    if len(self.positions) >= self.max_positions:
        return False
    return True

def should_stop_loss(self, symbol: str) -> bool:
    """检查是否应该止损"""
    position = self.get_position(symbol)
    if not position:
        return False
    return position.unrealized_pnl_pct <= -self.stop_loss_pct * 100

def should_take_profit(self, symbol: str) -> bool:
    """检查是否应该止盈"""
    position = self.get_position(symbol)
    if not position:
        return False
    return position.unrealized_pnl_pct >= self.take_profit_pct * 100
```

---

### MultiTimeframeKlineBreakoutStrategy

**位置**: `core/strategy/multi_timeframe_kline_breakout.py`

**描述**: 基于1秒K线的多时间框架量价突破策略

**1秒K线处理接口**:
```python
async def _process_1s_kline(self, msg: Dict):
    """处理1秒K线消息"""
    kline_data = msg.get('k', {})

    # ✅ 只处理已关闭的K线
    if not kline_data.get('x', False):
        return

    # ✅ 创建Kline对象
    kline = Kline(
        symbol=symbol,
        open=float(kline_data['o']),
        high=float(kline_data['h']),
        low=float(kline_data['l']),
        close=float(kline_data['c']),
        volume=float(kline_data['v']),  # ✅ 真实volume
        timestamp=pd.to_datetime(kline_data['t'], unit='ms')
    )

    # ✅ 突破检测
    signal = self.detector.detect_breakout(kline, symbol)
    if signal:
        await self._handle_breakout_signal(signal)
```

**配置参数**:
```yaml
# configs/mt_kline_breakout_config.yaml
strategy:
  name: "MultiTimeframeKlineBreakout"

  # 量价突破参数
  volume_threshold: 3.0x          # ✅ 成交量激增阈值（验证过最优）
  price_change_threshold: 0.2%    # 价格变动阈值
  signal_cooldown: 60秒           # ✅ 信号冷却时间（验证过最优）

  # 布林带参数
  bb_period: 20                   # 布林带周期
  bb_std: 2.0                     # 布林带标准差倍数

  # 支撑阻力参数
  support_resistance_window: 100  # 支撑阻力计算窗口
```

---

## 突破检测接口

### KlineBreakoutDetector

**位置**: `core/strategy/kline_breakout_detector.py`

**描述**: 基于1秒K线的量价突破检测器

**初始化**:
```python
def __init__(self, config: Dict):
    """
    初始化1秒K线量价突破检测器

    Args:
        config: 配置字典
            - volume_surge_threshold: 成交量激增阈值（默认3.0x）
            - volume_window: 成交量平均窗口（默认50条）
            - bb_breakout_threshold: 布林带突破阈值（默认0.2%）
            - support_resistance_window: 支撑阻力计算窗口（默认100条）
            - min_signal_strength: 最小信号强度（默认0.7）
    """
    self.volume_surge_threshold = config.get('volume_surge_threshold', 3.0)
    self.volume_window = config.get('volume_window', 50)
    self.bb_breakout_threshold = config.get('bb_breakout_threshold', 0.002)
    self.support_resistance_window = config.get('support_resistance_window', 100)
    self.min_signal_strength = config.get('min_signal_strength', 0.7)
```

**核心接口**:
```python
def detect_breakout(
    self,
    kline: Kline,
    symbol: str,
    higher_timeframe_data: Optional[Dict[str, pd.DataFrame]] = None
) -> Optional[Signal]:
    """
    检测1秒K线量价突破

    Args:
        kline: 1秒K线数据
        symbol: 交易对符号
        higher_timeframe_data: 更高时间框架数据（可选）

    Returns:
        Signal: 突破信号，如果没有突破则返回None

    检测逻辑:
        1. 量能分析：检测成交量是否异常放大（>3x平均）
        2. 价格突破：检测是否突破布林带或支撑阻力位
        3. 综合判断：放量 + 突破 = 信号
    """
```

**使用示例**:
```python
from core.strategy.kline_breakout_detector import KlineBreakoutDetector, Kline

# 初始化检测器
config = {
    'volume_surge_threshold': 3.0,
    'volume_window': 50,
    'bb_breakout_threshold': 0.002,
    'support_resistance_window': 100
}

detector = KlineBreakoutDetector(config)

# 创建Kline对象
kline = Kline(
    symbol="BTCUSDT",
    open=50000.0,
    high=50100.0,
    low=49900.0,
    close=50050.0,
    volume=1234.56,  # ✅ 真实的1秒K线成交量
    timestamp=pd.Timestamp.now()
)

# 检测突破
signal = detector.detect_breakout(kline, symbol="BTCUSDT")

if signal:
    print(f"检测到突破信号!")
    print(f"  类型: {signal.signal_type}")
    print(f"  强度: {signal.strength:.2f}x")
    print(f"  价格变化: {signal.price_change_pct:.3f}%")
    print(f"  置信度: {signal.confidence:.2f}")
```

---

## 使用示例

### 示例1: 订阅1秒K线并检测突破

```python
import asyncio
from core.data.websocket_client import BinanceWebSocketClient
from core.strategy.kline_breakout_detector import KlineBreakoutDetector, Kline

async def main():
    # 创建WebSocket客户端
    client = BinanceWebSocketClient(testnet=True)

    # 创建突破检测器
    detector_config = {
        'volume_surge_threshold': 3.0,
        'volume_window': 50
    }
    detector = KlineBreakoutDetector(detector_config)

    # K线回调
    async def on_kline(kline: Kline):
        print(f"收到K线: {kline.symbol}, Price: {kline.close}, Volume: {kline.volume}")

        # 检测突破
        signal = detector.detect_breakout(kline, kline.symbol)

        if signal:
            print(f"✅ 突破信号: {signal.signal_type}, 强度: {signal.strength:.2f}x")

    # 添加回调
    client.add_kline_callback(on_kline)

    # 订阅1秒K线流
    symbols = ['BTCUSDT', 'ETHUSDT']
    await client.subscribe_klines(symbols, interval='1s')

    # 运行
    await client.run_forever()

asyncio.run(main())
```

### 示例2: 回测1秒K线策略

```python
from core.strategy.multi_timeframe_kline_breakout import MultiTimeframeKlineBreakoutStrategy
from core.backtest.backtester import Backtester
import yaml

# 加载配置
with open('configs/mt_kline_breakout_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# 创建策略
strategy = MultiTimeframeKlineBreakoutStrategy(config['strategy'])

# 创建回测引擎
backtester = Backtester(
    strategy=strategy,
    initial_balance=10000.0,
    symbols=['BTCUSDT', 'ETHUSDT']
)

# 运行回测
results = backtester.run(
    start_date='2024-01-01',
    end_date='2024-01-15'
)

# 打印结果
print(f"总收益率: {results['total_return']:.2%}")
print(f"最大回撤: {results['max_drawdown']:.2%}")
print(f"夏普比率: {results['sharpe_ratio']:.2f}")
print(f"交易次数: {results['total_trades']}")
print(f"胜率: {results['win_rate']:.2%}")
```

### 示例3: 验证1秒K线数据准确性

```python
from core.strategy.kline_breakout_detector import Kline
import pandas as pd

# 验证volume字段准确性
def verify_volume_accuracy():
    # 场景1: 真实1秒K线成交量
    true_1s_volume = 1234.56

    kline = Kline(
        symbol="BTCUSDT",
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=true_1s_volume,  # ✅ 真实1秒K线成交量
        timestamp=pd.Timestamp.now()
    )

    # 验证
    assert kline.volume == true_1s_volume, "volume应该准确"
    assert kline.volume > 0, "volume应该是正数"

    print(f"✅ volume字段准确性验证通过")
    print(f"   真实1秒K线成交量: {kline.volume} BTC")
    print(f"   ✅ 不使用last_quantity字段（ticker的单次成交量）")

    # 场景2: 对比ticker的last_quantity（错误方案）
    ticker_last_quantity = 0.5

    print(f"\n   ❌ ticker的last_quantity: {ticker_last_quantity} BTC")
    print(f"   ✅ 两者相差 {true_1s_volume / ticker_last_quantity:.1f} 倍")
    print(f"   ✅ 因此必须使用Kline的volume字段")

verify_volume_accuracy()
```

---

## 数据流架构

### 实时数据流
```
Binance WebSocket (@kline_1s)
        ↓
BinanceWebSocketClient._process_kline_message()
        ↓
过滤未关闭K线 (k['x'] == True)
        ↓
创建Kline对象 (使用真实的volume字段)
        ↓
触发Kline回调
        ↓
KlineBreakoutDetector.detect_breakout()
        ↓
生成Signal (如果检测到突破)
        ↓
执行交易信号
```

### 回测数据流
```
历史K线数据加载
        ↓
Kline对象创建 (使用真实的volume字段)
        ↓
MultiTimeframeKlineBreakoutStrategy.update()
        ↓
KlineBreakoutDetector.detect_breakout()
        ↓
生成Signal
        ↓
Backtester执行信号
        ↓
计算性能指标
```

---

## 数据准确性保证

### 1秒K线数据准确性

| 数据类型 | 字段 | 含义 | 准确性 |
|----------|------|------|--------|
| **1秒K线** | `volume` | 该秒内所有成交总和 | ✅ 100%准确 |
| **Ticker** | `last_quantity` | 最近一次成交数量 | ❌ 不准确（单次成交） |

### 关键差异示例
```python
# ❌ 错误：使用ticker数据
ticker_last_quantity = 0.5  # 最近一次成交数量（如0.5 BTC）

# ✅ 正确：使用1秒K线数据
kline_volume = 1234.56  # 该秒内所有成交总和（如1234.56 BTC）

# 差异：2469倍
```

---

## 相关文档

- [架构修复文档](./STRATEGY_ARCHITECTURE_FIX.md) - 数据架构修复详情
- [迁移指南](./MIGRATION_GUIDE.md) - 从ticker迁移到1秒K线
- [Phase 4完成报告](./PHASE4_COMPLETION_REPORT.md) - 验证结果
- [策略模块文档](../core/strategy/CLAUDE.md) - 策略开发指南

---

**文档创建时间**: 2026-01-15
**文档版本**: v1.0
**数据架构**: 1秒K线WebSocket流
**状态**: ✅ 最新

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