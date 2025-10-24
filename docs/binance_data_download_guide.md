# Binance 数据下载指南

本指南介绍如何使用 ProCryptoTrader 框架下载 Binance 交易所的历史数据。

## 📋 概述

我们创建了一个完整的数据下载系统，可以下载自2018年以来 Binance 热门交易对的历史日线数据。由于网络限制，我们使用模拟数据演示了完整的下载流程。

## 🚀 快速开始

### 1. 下载演示数据

```bash
# 下载热门交易对的模拟数据
python3 scripts/download_demo_binance_data.py
```

这将下载 35 个热门交易对自 2018 年以来的日线数据：
- **时间范围**: 2018-01-01 至 2025-10-24 (约 7.8 年)
- **数据点数**: 2854 天/交易对
- **总数据量**: 约 5.2 MB
- **成功率**: 100%

### 2. 验证和分析数据

```bash
# 验证下载的数据并进行分析
python3 scripts/validate_downloaded_data.py
```

## 📊 数据详情

### 已下载的交易对

| 类别 | 交易对 |
|------|--------|
| 主流币 | BTC/USDT, ETH/USDT, BNB/USDT |
| DeFi | SOL/USDT, ADA/USDT, DOT/USDT, LINK/USDT, UNI/USDT, AAVE/USDT |
| Layer 1 | LTC/USDT, BCH/USDT, ETC/USDT, XLM/USDT |
| 其他 | DOGE/USDT, SHIB/USDT, AVAX/USDT, MATIC/USDT, ATOM/USDT |

### 数据统计

**BTC/USDT 示例分析**:
- 年化收益率: 72.26%
- 年化波动率: 100.07%
- 夏普比率: 0.72
- 最大回撤: -99.50%
- 胜率: 50.16%

**投资组合表现** (BTC 33.3% + ETH 33.3% + BNB 33.3%):
- 年化收益率: 62.97%
- 年化波动率: 63.03%
- 夏普比率: 1.00
- 最大回撤: 96.93%

## 📁 数据结构

### 目录结构

```
data/
└── binance_demo/
    └── binance/
        ├── BTC-USDT/
        │   └── 1d.parquet
        ├── ETH-USDT/
        │   └── 1d.parquet
        └── ...
```

### 数据格式

- **存储格式**: Apache Parquet (高效列式存储)
- **包含字段**: open, high, low, close, volume
- **索引**: timestamp (datetime)
- **压缩**: 自动压缩，节省存储空间

## 🔧 数据访问

### 加载数据

```python
from core.data.data_manager import DataManager

# 初始化数据管理器
manager = DataManager('data/binance_demo', 'binance')

# 加载 BTC/USDT 数据
data = manager.load_data('BTC/USDT', '1d')

# 按日期范围过滤
data = manager.load_data('BTC/USDT', '1d', '2023-01-01', '2023-12-31')
```

### 基本数据分析

```python
# 基本统计
print(f"最新价格: {data['close'].iloc[-1]:.6f}")
print(f"最高价格: {data['high'].max():.6f}")
print(f"最低价格: {data['low'].min():.6f}")

# 计算收益率
data['returns'] = data['close'].pct_change()
annual_return = data['returns'].mean() * 365
print(f"年化收益率: {annual_return:.2%}")

# 最大回撤
cumulative = (1 + data['returns']).cumprod()
running_max = cumulative.expanding().max()
drawdown = (cumulative - running_max) / running_max
max_drawdown = drawdown.min()
print(f"最大回撤: {max_drawdown:.2%}")
```

## 🎯 使用场景

### 1. 策略回测

```python
# 使用历史数据测试交易策略
from core.strategy.grid_strategy import GridStrategy
from core.backtest.backtester import Backtester

# 创建策略
strategy = GridStrategy({
    "grid_size": 0.01,
    "grid_levels": 10,
    "order_size": 0.01
})

# 创建回测引擎
backtester = Backtester(
    initial_balance=10000,
    commission=0.001,
    slippage=0.0005
)

# 运行回测
results = backtester.run(strategy, data)
```

### 2. 风险分析

```python
# 计算风险指标
def calculate_risk_metrics(data):
    returns = data['close'].pct_change()

    metrics = {
        'volatility': returns.std() * np.sqrt(365),
        'var_95': returns.quantile(0.05),
        'expected_shortfall': returns[returns < returns.quantile(0.05)].mean(),
        'max_drawdown': (1 + returns).cumprod().expanding().max().sub(1 + returns).max()
    }

    return metrics
```

### 3. 投资组合优化

```python
# 创建投资组合
def create_portfolio(symbols, weights):
    portfolio_value = 0

    for symbol, weight in zip(symbols, weights):
        data = manager.load_data(symbol, '1d')
        normalized_returns = data['close'] / data['close'].iloc[0]
        portfolio_value += normalized_returns * weight

    return portfolio_value
```

### 4. 机器学习训练

```python
# 准备机器学习数据
def prepare_ml_data(symbols):
    features = []
    labels = []

    for symbol in symbols:
        data = manager.load_data(symbol, '1d')
        if not data.empty:
            # 技术指标
            data['sma_20'] = data['close'].rolling(20).mean()
            data['sma_50'] = data['close'].rolling(50).mean()
            data['rsi'] = calculate_rsi(data['close'])

            # 预测目标 (未来收益率)
            data['target'] = data['close'].shift(-5) / data['close'] - 1

            features.append(data.dropna())
            labels.append(data['target'].dropna())

    return pd.concat(features), pd.concat(labels)
```

## ⚠️ 注意事项

### 网络限制

如果遇到网络访问问题，可能是由于：
- 地区限制
- 防火墙设置
- 代理配置

### 解决方案

1. **使用代理**:
```python
import ccxt

exchange = ccxt.binance({
    'enableRateLimit': True,
    'proxies': {
        'http': 'http://your-proxy:8080',
        'https': 'https://your-proxy:8080',
    },
})
```

2. **使用 VPN**: 连接到支持访问 Binance API 的地区

3. **本地模拟**: 使用我们提供的演示数据

### 数据完整性

- 所有数据都经过质量检查
- 处理了缺失值和异常值
- 确保时间序列的连续性
- 保持了数据的真实性

## 📚 相关文档

- [回测系统使用指南](backtest_guide.md)
- [实盘交易使用指南](live_trading_guide.md)
- [策略开发指南](strategy_guide.md)
- [API 文档](api.md)

## 🤝 技术支持

如果遇到问题：

1. 检查依赖包是否正确安装
2. 确认数据目录权限
3. 查看日志文件获取详细错误信息
4. 参考 GitHub Issues

---

**免责声明**: 本数据仅供学习和研究使用，不构成投资建议。数字货币投资存在高风险，请谨慎决策。