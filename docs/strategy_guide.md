# 策略开发指南

本指南将帮助您了解如何开发自定义交易策略，并在ProCryptoTrader系统中使用。

## 策略基础

### 策略基类

所有策略都必须继承自 `BaseStrategy` 基类，并实现必要的方法：

```python
from core.strategy.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        # 初始化策略参数
        self.parameter1 = config.get("parameter1", 0.01)
        self.parameter2 = config.get("parameter2", 10)
        
        # 初始化策略状态
        self.indicator1 = None
        self.indicator2 = None
        
    def generate_signal(self, data):
        """
        生成交易信号
        
        参数:
            data: DataFrame, 包含OHLCV数据
            
        返回:
            dict: 交易信号，包含以下字段:
                - type: str, 信号类型 ("buy", "sell", "hold")
                - amount: float, 交易数量
                - price: float, 交易价格 (可选，默认为市价)
        """
        # 实现信号生成逻辑
        if self.buy_condition(data):
            return {"type": "buy", "amount": 0.01}
        elif self.sell_condition(data):
            return {"type": "sell", "amount": 0.01}
        else:
            return {"type": "hold", "amount": 0}
    
    def update(self, data):
        """
        更新策略状态
        
        参数:
            data: DataFrame, 包含OHLCV数据
        """
        # 更新指标
        self.indicator1 = self.calculate_indicator1(data)
        self.indicator2 = self.calculate_indicator2(data)
        
        # 更新其他状态
        pass
    
    def buy_condition(self, data):
        """买入条件判断"""
        # 实现买入条件
        return self.indicator1 > self.parameter1 and self.indicator2 < self.parameter2
    
    def sell_condition(self, data):
        """卖出条件判断"""
        # 实现卖出条件
        return self.indicator1 < -self.parameter1 and self.indicator2 > self.parameter2
    
    def calculate_indicator1(self, data):
        """计算指标1"""
        # 实现指标计算
        return data["close"].pct_change().rolling(window=10).mean().iloc[-1]
    
    def calculate_indicator2(self, data):
        """计算指标2"""
        # 实现指标计算
        return data["close"].rolling(window=20).std().iloc[-1]
```

### 必需方法

- `__init__(self, config)`: 初始化策略，设置参数和状态
- `generate_signal(self, data)`: 生成交易信号，返回信号字典
- `update(self, data)`: 更新策略状态，计算指标等

### 可选方法

- `on_order_filled(self, order)`: 订单成交时的回调
- `on_position_opened(self, position)`: 持仓开启时的回调
- `on_position_closed(self, position)`: 持仓关闭时的回调

## 技术指标

### 常用技术指标

系统提供了多种常用技术指标的计算方法：

```python
import pandas as pd
import numpy as np

# 简单移动平均线 (SMA)
def calculate_sma(data, period):
    return data["close"].rolling(window=period).mean()

# 指数移动平均线 (EMA)
def calculate_ema(data, period):
    return data["close"].ewm(span=period).mean()

# 相对强弱指数 (RSI)
def calculate_rsi(data, period=14):
    delta = data["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 布林带 (Bollinger Bands)
def calculate_bollinger_bands(data, period=20, std_dev=2):
    sma = calculate_sma(data, period)
    std = data["close"].rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, sma, lower_band

# MACD
def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9):
    ema_fast = calculate_ema(data, fast_period)
    ema_slow = calculate_ema(data, slow_period)
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period).mean()
    histogram = macd - signal
    return macd, signal, histogram

# 随机指标 (Stochastic Oscillator)
def calculate_stochastic(data, k_period=14, d_period=3):
    low_min = data["low"].rolling(window=k_period).min()
    high_max = data["high"].rolling(window=k_period).max()
    k_percent = 100 * ((data["close"] - low_min) / (high_max - low_min))
    d_percent = k_percent.rolling(window=d_period).mean()
    return k_percent, d_percent
```

### 自定义指标

您可以创建自定义技术指标：

```python
def calculate_custom_indicator(data, param1, param2):
    """
    计算自定义指标
    
    参数:
        data: DataFrame, 包含OHLCV数据
        param1: float, 参数1
        param2: int, 参数2
        
    返回:
        Series: 指标值
    """
    # 实现自定义指标计算
    return data["close"].rolling(window=param2).apply(
        lambda x: np.mean(x) * param1, raw=True
    )
```

## 策略示例

### 双均线交叉策略

```python
from core.strategy.base_strategy import BaseStrategy
import pandas as pd

class DualMovingAverageStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.fast_period = config.get("fast_period", 10)
        self.slow_period = config.get("slow_period", 30)
        self.fast_ma = None
        self.slow_ma = None
        
    def generate_signal(self, data):
        # 生成交易信号
        if self.fast_ma is None or self.slow_ma is None:
            return {"type": "hold", "amount": 0}
            
        # 获取最新的均线值
        current_fast = self.fast_ma.iloc[-1]
        current_slow = self.slow_ma.iloc[-1]
        prev_fast = self.fast_ma.iloc[-2] if len(self.fast_ma) > 1 else current_fast
        prev_slow = self.slow_ma.iloc[-2] if len(self.slow_ma) > 1 else current_slow
        
        # 金叉买入
        if prev_fast <= prev_slow and current_fast > current_slow:
            return {"type": "buy", "amount": 0.01}
        # 死叉卖出
        elif prev_fast >= prev_slow and current_fast < current_slow:
            return {"type": "sell", "amount": 0.01}
        else:
            return {"type": "hold", "amount": 0}
    
    def update(self, data):
        # 更新均线
        self.fast_ma = data["close"].rolling(window=self.fast_period).mean()
        self.slow_ma = data["close"].rolling(window=self.slow_period).mean()
```

### RSI均值回归策略

```python
from core.strategy.base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class RSIMeanReversionStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.rsi_period = config.get("rsi_period", 14)
        self.overbought = config.get("overbought", 70)
        self.oversold = config.get("oversold", 30)
        self.rsi = None
        
    def generate_signal(self, data):
        # 生成交易信号
        if self.rsi is None or len(self.rsi) < 2:
            return {"type": "hold", "amount": 0}
            
        # 获取最新的RSI值
        current_rsi = self.rsi.iloc[-1]
        prev_rsi = self.rsi.iloc[-2]
        
        # 超卖区域买入
        if prev_rsi >= self.oversold and current_rsi < self.oversold:
            return {"type": "buy", "amount": 0.01}
        # 超买区域卖出
        elif prev_rsi <= self.overbought and current_rsi > self.overbought:
            return {"type": "sell", "amount": 0.01}
        else:
            return {"type": "hold", "amount": 0}
    
    def update(self, data):
        # 更新RSI
        delta = data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        self.rsi = 100 - (100 / (1 + rs))
```

### 布林带突破策略

```python
from core.strategy.base_strategy import BaseStrategy
import pandas as pd

class BollingerBandsStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.period = config.get("period", 20)
        self.std_dev = config.get("std_dev", 2)
        self.upper_band = None
        self.middle_band = None
        self.lower_band = None
        
    def generate_signal(self, data):
        # 生成交易信号
        if self.upper_band is None or self.lower_band is None:
            return {"type": "hold", "amount": 0}
            
        # 获取最新的价格和布林带
        current_price = data["close"].iloc[-1]
        current_upper = self.upper_band.iloc[-1]
        current_lower = self.lower_band.iloc[-1]
        
        # 价格突破上轨，卖出
        if current_price > current_upper:
            return {"type": "sell", "amount": 0.01}
        # 价格跌破下轨，买入
        elif current_price < current_lower:
            return {"type": "buy", "amount": 0.01}
        else:
            return {"type": "hold", "amount": 0}
    
    def update(self, data):
        # 更新布林带
        self.middle_band = data["close"].rolling(window=self.period).mean()
        std = data["close"].rolling(window=self.period).std()
        self.upper_band = self.middle_band + (std * self.std_dev)
        self.lower_band = self.middle_band - (std * self.std_dev)
```

## 策略配置

### 配置文件

策略配置通常存储在YAML文件中：

```yaml
# 策略配置
strategy: "DualMovingAverageStrategy"
strategy_params:
  fast_period: 10
  slow_period: 30
  order_size: 0.01
```

### 参数优化

策略参数可以通过回测进行优化：

```python
from core.backtest.backtester import Backtester
from core.data.data_loader import DataLoader
import itertools

# 加载数据
loader = DataLoader()
data = loader.load_csv("BTC_USDT_1h.csv")

# 定义参数范围
fast_periods = [5, 10, 15]
slow_periods = [20, 30, 40]

# 参数优化
best_sharpe = -float('inf')
best_params = None

for fast_period, slow_period in itertools.product(fast_periods, slow_periods):
    # 创建策略
    strategy = DualMovingAverageStrategy({
        "fast_period": fast_period,
        "slow_period": slow_period
    })
    
    # 运行回测
    backtester = Backtester(initial_balance=10000)
    results = backtester.run(strategy, data)
    
    # 计算夏普比率
    sharpe_ratio = results["metrics"]["sharpe_ratio"]
    
    # 更新最佳参数
    if sharpe_ratio > best_sharpe:
        best_sharpe = sharpe_ratio
        best_params = {
            "fast_period": fast_period,
            "slow_period": slow_period
        }

print(f"最佳参数: {best_params}")
print(f"最佳夏普比率: {best_sharpe:.2f}")
```

## 策略测试

### 回测

使用回测系统测试策略：

```python
from core.backtest.backtester import Backtester
from core.data.data_loader import DataLoader

# 加载数据
loader = DataLoader()
data = loader.load_csv("BTC_USDT_1h.csv")

# 创建策略
strategy = MyStrategy({
    "parameter1": 0.01,
    "parameter2": 10
})

# 创建回测引擎
backtester = Backtester(
    initial_balance=10000,
    commission=0.001,
    slippage=0.0005
)

# 运行回测
results = backtester.run(strategy, data)

# 查看结果
print(f"总收益率: {results['metrics']['total_return']:.2%}")
print(f"夏普比率: {results['metrics']['sharpe_ratio']:.2f}")
print(f"最大回撤: {results['metrics']['max_drawdown']:.2%}")
print(f"胜率: {results['metrics']['win_rate']:.2%}")
```

### 前向测试

使用前向测试验证策略：

```python
from core.live.live_trader import LiveTrader

# 创建实盘交易控制器
trader = LiveTrader({
    "mode": "paper",  # 模拟交易
    "update_interval": 60,
    "exchanges": {
        "binance": {
            "api_key": "your_api_key",
            "secret": "your_secret",
            "sandbox": True
        }
    },
    "strategies": [{
        "name": "MyStrategy",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {
            "parameter1": 0.01,
            "parameter2": 10
        }
    }]
})

# 运行前向测试
trader.run()
```

## 策略部署

### 实盘交易

将策略部署到实盘交易：

```python
from core.live.live_trader import LiveTrader

# 创建实盘交易控制器
trader = LiveTrader({
    "mode": "live",  # 实盘交易
    "update_interval": 60,
    "exchanges": {
        "binance": {
            "api_key": "your_api_key",
            "secret": "your_secret",
            "sandbox": False  # 实盘环境
        }
    },
    "strategies": [{
        "name": "MyStrategy",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {
            "parameter1": 0.01,
            "parameter2": 10
        }
    }],
    "risk_management": {
        "max_position_size": 0.1,
        "max_drawdown": 0.1
    }
})

# 运行实盘交易
trader.run()
```

## 最佳实践

### 1. 策略设计

- 保持策略简单，避免过度优化
- 使用多种技术指标确认信号
- 考虑市场环境，适应不同行情
- 设置合理的止损止盈

### 2. 风险管理

- 控制单笔交易风险
- 设置最大回撤限制
- 分散投资，不要把所有资金投入单一策略
- 定期评估策略表现

### 3. 参数优化

- 使用样本外数据验证策略
- 避免过度拟合历史数据
- 考虑参数稳定性，不要频繁调整
- 使用稳健的优化方法

### 4. 实盘部署

- 先进行模拟交易验证
- 从小资金开始，逐步增加
- 监控策略表现，及时调整
- 做好交易记录和分析

## 常见问题

### 1. 策略回测表现好，实盘表现差

- 可能原因：过度拟合、滑点、手续费、市场变化等
- 解决方法：增加样本外测试、考虑滑点和手续费、定期调整策略

### 2. 策略信号过于频繁

- 可能原因：参数设置过于敏感、指标选择不当
- 解决方法：调整参数、增加信号确认条件、使用更长期指标

### 3. 策略信号过于稀少

- 可能原因：参数设置过于保守、指标选择不当
- 解决方法：调整参数、降低信号确认条件、使用更短期指标

### 4. 策略无法处理极端行情

- 可能原因：策略设计未考虑极端情况、风险管理不足
- 解决方法：增加极端行情处理逻辑、加强风险管理、设置紧急止损

## 总结

策略开发是一个持续迭代的过程，需要不断学习、测试和优化。通过遵循本指南的建议，您可以开发出更加稳健和有效的交易策略。记住，没有完美的策略，关键是找到适合自己的策略，并严格执行风险管理规则。